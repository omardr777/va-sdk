from __future__ import annotations

import json
import os
from typing import Any


def extract_params(
    transcript: str,
    tool_name: str,
    tool_schema: dict,
    api_key: str | None = None,
    model: str = "gpt-4o",
) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
    schema_props = tool_schema.get("function", {}).get("parameters", {}).get("properties", {})

    prompt = f"""Extract the following parameters from this user transcript.
Return ONLY a JSON object with the parameter names as keys. Omit parameters not mentioned.

Tool: {tool_name}
Parameters: {json.dumps({k: {"type": v.get("type", "string"), "enum": v.get("enum")} for k, v in schema_props.items()}, indent=2)}

Transcript: "{transcript}"

JSON:"""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content or "{}")


def generate_conversation_draft(
    tools: list[dict],
    description: str,
    turns: int = 4,
    include_asr_noise: bool = True,
    prompt_template: str | None = None,
    api_key: str | None = None,
    model: str = "gpt-4o",
) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    tool_names = [t["function"]["name"] for t in tools]

    default_prompt = f"""Generate a multi-turn voice assistant conversation based on this description.
Return a JSON object with a "steps" array. Each step has:
- "user_text": what the user says (natural, conversational)
{f'- Include ASR transcription artifacts (filler words, homophones, word splits) in ~30% of turns.' if include_asr_noise else ''}
- "function_name": one of {tool_names} or "greeting"/"goodbye"/"thank_you"/"intent_unclear"
- "arguments_json": JSON string of arguments (empty object "{{}}" if no args needed)

Description: {description}
Turns: {turns}
{f'Additional instructions:\n{prompt_template}' if prompt_template else ''}

Return ONLY valid JSON in this format:
{{"steps": [{{"user_text": "...", "function_name": "...", "arguments_json": "{{...}}"}}]}}"""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": default_prompt}],
        temperature=0.8,
        response_format={"type": "json_object"},
    )

    content = resp.choices[0].message.content or "{}"
    parsed = json.loads(content)
    steps = parsed.get("steps", [])

    messages = []
    for step in steps:
        try:
            args = json.loads(step.get("arguments_json", "{}")) if isinstance(step.get("arguments_json"), str) else step.get("arguments_json", {})
        except (json.JSONDecodeError, TypeError):
            args = {}

        messages.append({
            "role": "user",
            "content": step.get("user_text", ""),
        })
        messages.append({
            "role": "assistant",
            "tool_calls": [{
                "id": f"call_{len(messages)}",
                "type": "function",
                "function": {
                    "name": step.get("function_name", "intent_unclear"),
                    "arguments": json.dumps(args),
                },
            }],
        })

    return {
        "messages": messages,
        "tools": tools,
        "source": "ai_assist",
    }
