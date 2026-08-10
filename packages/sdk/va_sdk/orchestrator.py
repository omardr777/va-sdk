from __future__ import annotations

import json
import time

from va_sdk.models.backend import ModelBackend, ToolCall
from va_sdk.tool import Toolkit, ToolError


SYSTEM_PROMPT_TEMPLATE = """\
You are a tool-calling model working on:
<task_description>You are a voice assistant. The user input is automatically
transcribed speech from an ASR system, so it may contain transcription errors,
homophones, filler words, or unusual phrasings. Parse the user's request and
return the appropriate function call despite any transcription artifacts. If
you can identify the intent, call the matching function. Extract any mentioned
argument values; omit arguments not mentioned. If you cannot understand what
the user wants, call intent_unclear(). Use conversation history to understand
context from previous turns.</task_description>

Respond to the conversation history by generating an appropriate tool call
that satisfies the user request. Generate only the tool call according to the
provided tool schema, do not generate anything else. Always respond with a
tool call.
"""

MAX_CONTEXT_MESSAGES = 8

META_RESPONSES = {
    "greeting": "Hello! How can I help you today?",
    "goodbye": "Goodbye! Thanks for calling.",
    "thank_you": "You're welcome! Is there anything else I can help with?",
    "intent_unclear": "I didn't quite understand that. Could you rephrase?",
    "speak_to_human": "Connecting you to an agent now. Please hold.",
}


class VoiceOrchestrator:
    """Deterministic dialogue manager.

    Takes text transcriptions, routes them through an LLM, fills missing
    slots, executes backend tools, and renders template responses.

    Usage::

        orchestrator = VoiceOrchestrator(toolkit, model_backend)
        response = orchestrator.process_utterance("check my savings balance")
    """

    def __init__(
        self,
        toolkit: Toolkit,
        model: ModelBackend,
        *,
        system_prompt: str | None = None,
        debug: bool = False,
    ):
        self.toolkit = toolkit
        self.model = model
        self.system_prompt = system_prompt or SYSTEM_PROMPT_TEMPLATE
        self.debug = debug
        self.conversation_history: list[dict] = []
        self.last_timings: dict[str, float] = {}

    def process_utterance(
        self, transcript: str, auth_context: dict | None = None
    ) -> str | None:
        """Full turn: user text in → bot response out.

        Returns ``None`` when the conversation ends (``goodbye``).
        """
        transcript = transcript.strip()
        if transcript.lower() in ("quit", "exit"):
            return None

        self._log(f"[user] {transcript}")

        self.conversation_history.append({"role": "user", "content": transcript})

        turn_start = time.perf_counter()
        function_call = self._invoke_model()
        self.last_timings["model_ms"] = getattr(self.model, "last_latency_ms", 0)

        if isinstance(function_call, str):
            self._log(f"[model error] {function_call}")
            return META_RESPONSES["intent_unclear"]

        self._log(f"[tool_call] {function_call.name} {function_call.arguments}")

        tool_call_msg = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": str(len(self.conversation_history)),
                    "type": "function",
                    "function": {
                        "name": function_call.name,
                        "arguments": json.dumps(function_call.arguments),
                    },
                }
            ],
        }
        self.conversation_history.append(tool_call_msg)

        response = self._handle_function_call(function_call, auth_context or {})
        self.last_timings["turn_total_ms"] = (time.perf_counter() - turn_start) * 1000
        return response

    def reset(self) -> None:
        self.conversation_history = []

    def _invoke_model(self) -> ToolCall | str:
        tools = self.toolkit.to_openai_tools()
        messages = [{"role": "system", "content": self.system_prompt}] + \
                   self.conversation_history[-MAX_CONTEXT_MESSAGES:]
        return self.model.invoke(tools, messages)

    def _handle_function_call(
        self, fn: ToolCall, auth_context: dict
    ) -> str | None:
        name = fn.name
        arguments = fn.arguments

        if name in META_RESPONSES:
            if name == "goodbye":
                self.reset()
                return None
            self.reset()
            return META_RESPONSES[name]

        tool = self.toolkit.get(name)
        if tool is None:
            self.reset()
            return META_RESPONSES["intent_unclear"]

        missing = [arg for arg in tool.required_args if arguments.get(arg) is None]
        if missing:
            return self._build_slot_elicitation(tool, missing)

        return self._execute_and_respond(tool, arguments, auth_context)

    def _build_slot_elicitation(self, tool: Tool, missing: list[str]) -> str:
        prompts = tool.slot_prompts
        questions = [prompts.get(arg, f"the {arg.replace('_', ' ')}") for arg in missing]
        if len(questions) == 1:
            return f"Could you provide {questions[0]}?"
        return f"Could you provide {', '.join(questions[:-1])}, and {questions[-1]}?"

    def _execute_and_respond(
        self, tool: Tool, arguments: dict, auth_context: dict
    ) -> str:
        import asyncio

        api = self.toolkit.api_factory(auth_context)
        started = time.perf_counter()

        try:
            if asyncio.iscoroutinefunction(tool._call):
                raise RuntimeError(
                    "Async tool calls are not supported in synchronous orchestrator. "
                    "Use VoiceOrchestratorAsync for async tools."
                )
            api_result = tool._call(api, **arguments)
        except ToolError as exc:
            self.last_timings["backend_ms"] = (time.perf_counter() - started) * 1000
            return self._format_error(tool, exc)
        except Exception as exc:
            self.last_timings["backend_ms"] = (time.perf_counter() - started) * 1000
            return self._format_error(tool, ToolError.generic(str(exc)))

        self.last_timings["backend_ms"] = (time.perf_counter() - started) * 1000

        if tool.map_result:
            api_result = tool.map_result(api_result, arguments)

        try:
            merged = {**api_result, **arguments}
            response = tool.success_template.format(**merged)
        except (KeyError, ValueError) as exc:
            self._log(f"[template error] {exc}")
            response = tool.success_template

        self.reset()
        return response

    def _format_error(self, tool: Tool, exc: ToolError) -> str:
        msg = exc.message

        if exc.kind == "auth_expired":
            self.reset()
            return msg

        try:
            response = tool.error_template.format(error_message=msg)
        except (KeyError, ValueError):
            response = f"I couldn't complete that: {msg}."

        self.reset()
        return response

    def _log(self, message: str) -> None:
        if self.debug:
            print(f"  [DEBUG orc] {message}")
