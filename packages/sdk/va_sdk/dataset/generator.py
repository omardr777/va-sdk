"""Dataset generation pipeline — auto-synthesizes fine-tuning data from a Tool registry.

Tiers:
  1. Single-turn (enumerate enums → teacher generates user prompts)
  2. Multi-turn slot-filling (remove required params → teacher generates elicitation)
  3. Seed-based (developer provides seeds → format + optional expansion)
"""

from __future__ import annotations

import itertools
import json
import os
import random
from dataclasses import dataclass, field
from typing import Any

from va_sdk.tool import Param, Tool, Toolkit


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

META_TOOLS = {"greeting", "goodbye", "thank_you"}


@dataclass
class Turn:
    user: str
    function_name: str
    arguments: dict[str, Any]


@dataclass
class Conversation:
    turns: list[Turn]
    source: str = ""


# ---------------------------------------------------------------------------
# Invocation enumerator
# ---------------------------------------------------------------------------

def enumerate_invocations(tool: Tool) -> list[dict[str, Any]]:
    if not tool.params:
        return [{}]

    values_by_param: dict[str, list[Any]] = {}
    for p in tool.params:
        if p.enum:
            values_by_param[p.name] = p.enum
        elif p.type == "number":
            values_by_param[p.name] = ["FILL_INT"]
        elif p.type == "boolean":
            values_by_param[p.name] = [True, False]
        else:
            values_by_param[p.name] = ["FILL_STR"]

    keys = list(values_by_param.keys())
    value_lists = [values_by_param[k] for k in keys]

    results: list[dict[str, Any]] = []
    for combo in itertools.product(*value_lists):
        invocation = {}
        for i, key in enumerate(keys):
            val = combo[i]
            if val == "FILL_INT":
                invocation[key] = -1
            elif val == "FILL_STR":
                invocation[key] = "PLACEHOLDER"
            else:
                invocation[key] = val
        results.append(invocation)

    return results


def enumerate_all_invocations(tools: list[Tool]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for tool in tools:
        if tool.name in META_TOOLS or tool.name == "intent_unclear":
            result[tool.name] = [{}]
        else:
            result[tool.name] = enumerate_invocations(tool)
    return result


# ---------------------------------------------------------------------------
# Teacher client
# ---------------------------------------------------------------------------

class TeacherClient:
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self.model = model
        self.last_latency_ms: float = 0.0

    def generate(self, prompt: str, temperature: float = 0.8) -> str:
        import time

        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=4096,
            )
            content = response.choices[0].message.content or ""
        finally:
            self.last_latency_ms = (time.perf_counter() - started) * 1000

        return content


# ---------------------------------------------------------------------------
# Tier 1 — Single-turn generation from enumerated invocations
# ---------------------------------------------------------------------------

SINGLE_TURN_PROMPT = """You are generating training data for a voice assistant. Given a tool
call with specific argument values, write {n} natural-sounding user prompts
that a real person might say to trigger this exact call. Vary the wording.

Tool: {tool_name}
Description: {tool_description}
Arguments: {arguments}

Return ONLY a JSON array of strings, like: ["prompt 1", "prompt 2"]

Prompts:"""


def generate_single_turn_prompts(
    tool: Tool,
    invocation: dict[str, Any],
    teacher: TeacherClient,
    n_prompts: int = 3,
) -> list[str]:
    prompt = SINGLE_TURN_PROMPT.format(
        n=n_prompts,
        tool_name=tool.name,
        tool_description=tool.description,
        arguments=json.dumps(invocation, indent=2),
    )

    raw = teacher.generate(prompt)
    try:
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            return [str(p) for p in parsed]
        return [raw.strip().strip('"')]
    except json.JSONDecodeError:
        cleaned = raw.strip().strip("```json").strip("```").strip()
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return [str(p) for p in parsed]
        except json.JSONDecodeError:
            pass
        return [raw.strip().strip('"')]


# ---------------------------------------------------------------------------
# Tier 2 — Multi-turn slot-filling generation
# ---------------------------------------------------------------------------

SLOT_FILLING_PROMPT = """Generate a multi-turn conversation for a voice assistant.
The user wants to call {tool_name} but doesn't provide all required info at once.
The required arguments are: {required_args}

First the user makes a partial request missing some info.
Then the assistant would ask for the missing info, but you only write what
the USER would say in response — the assistant's turns are handled by the system.

Write a short dialogue with {num_turns} user turns, each progressively adding
more of the required info. The final turn should provide ALL missing info.

Arguments to convey: {arguments}

Return ONLY a JSON array of strings — one string per user turn.

User turns:"""


def generate_slot_filling_turns(
    tool: Tool,
    invocation: dict[str, Any],
    teacher: TeacherClient,
) -> list[str] | None:
    required = tool.required_args
    if len(required) < 2:
        return None

    present = [k for k in required if invocation.get(k) is not None]
    if len(present) == len(required):
        return None

    prompt = SLOT_FILLING_PROMPT.format(
        tool_name=tool.name,
        required_args=", ".join(required),
        num_turns=min(len(required) - len(present) + 1, 4),
        arguments=json.dumps(invocation, indent=2),
    )
    raw = teacher.generate(prompt)
    try:
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            return [str(p) for p in parsed]
    except json.JSONDecodeError:
        cleaned = raw.strip().strip("```json").strip("```").strip()
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return [str(p) for p in parsed]
        except json.JSONDecodeError:
            pass
    return None


# ---------------------------------------------------------------------------
# Tier 3/4 — Seed-based conversation formatting
# ---------------------------------------------------------------------------

def format_seed_conversation(
    turns: list[Turn],
    tools: list[Tool],
    system_prompt: str,
) -> dict[str, Any]:
    tool_schemas = [t.to_openai_tool() for t in tools]

    messages = [{"role": "system", "content": system_prompt}]
    for turn in turns:
        messages.append({"role": "user", "content": turn.user})
        messages.append({
            "role": "assistant",
            "tool_calls": [{
                "id": f"call_{len(messages)}",
                "type": "function",
                "function": {
                    "name": turn.function_name,
                    "arguments": json.dumps(turn.arguments),
                },
            }],
        })

    return {"messages": messages, "tools": tool_schemas}


def generate_seed_from_banking_template(
    seed_scenarios: list[list[tuple[str, str, dict]]],
    tools: list[Tool],
    system_prompt: str,
) -> list[dict[str, Any]]:
    results = []
    for scenario in seed_scenarios:
        turns = [Turn(user=u, function_name=fn, arguments=args) for u, fn, args in scenario]
        results.append(format_seed_conversation(turns, tools, system_prompt))
    return results


# ---------------------------------------------------------------------------
# Full pipeline runner
# ---------------------------------------------------------------------------

@dataclass
class GenerationResult:
    conversations: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def generate_dataset(
    toolkit: Toolkit,
    teacher: TeacherClient,
    *,
    tiers: list[int] | None = None,
    n_prompts_per_invocation: int = 3,
    system_prompt: str = "",
    seed_scenarios: list[list[tuple[str, str, dict]]] | None = None,
) -> GenerationResult:
    tiers = tiers or [1]
    result = GenerationResult()
    tool_schemas = [t.to_openai_tool() for t in toolkit.tools]
    openai_tools = toolkit.to_openai_tools()

    stats: dict[str, int] = {
        "single_turn_prompts": 0,
        "multi_turn_conversations": 0,
        "seed_conversations": 0,
    }

    if not system_prompt:
        system_prompt = (
            "You are a tool-calling voice assistant. Always respond with a tool call."
        )

    if 1 in tiers:
        tools = [t for t in toolkit.tools if t.name not in META_TOOLS and t.name != "intent_unclear" and t.params]
        for tool in tools:
            invocations = enumerate_invocations(tool)
            for inv in invocations:
                prompts = generate_single_turn_prompts(tool, inv, teacher, n_prompts_per_invocation)
                for prompt_text in prompts:
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt_text},
                        {"role": "assistant", "tool_calls": [{
                            "id": f"call_{hash(prompt_text) % 100000}",
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "arguments": json.dumps(inv),
                            },
                        }]},
                    ]
                    result.conversations.append({"messages": messages, "tools": openai_tools})
                    stats["single_turn_prompts"] += 1

    if 2 in tiers:
        tools = [t for t in toolkit.tools if t.name not in META_TOOLS and t.name != "intent_unclear" and len(t.required_args) >= 2]
        for tool in tools:
            invocations = enumerate_invocations(tool)
            for inv in invocations:
                user_turns = generate_slot_filling_turns(tool, inv, teacher)
                if not user_turns:
                    continue

                messages = [{"role": "system", "content": system_prompt}]
                for i, user_text in enumerate(user_turns):
                    partial_args = {}
                    for req in tool.required_args:
                        if i == len(user_turns) - 1:
                            partial_args[req] = inv.get(req)
                        elif random.random() < 0.5:
                            partial_args[req] = inv.get(req)

                    messages.append({"role": "user", "content": user_text})
                    if i == len(user_turns) - 1:
                        messages.append({"role": "assistant", "tool_calls": [{
                            "id": f"call_{hash(user_text) % 100000}",
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "arguments": json.dumps(inv),
                            },
                        }]})

                result.conversations.append({"messages": messages, "tools": openai_tools})
                stats["multi_turn_conversations"] += 1

    if 3 in tiers and seed_scenarios is not None:
        formatted = generate_seed_from_banking_template(
            seed_scenarios, list(toolkit.tools), system_prompt,
        )
        result.conversations.extend(formatted)
        stats["seed_conversations"] = len(formatted)

    result.stats = stats
    return result
