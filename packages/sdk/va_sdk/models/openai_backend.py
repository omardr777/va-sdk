from __future__ import annotations

import json
import time

from va_sdk.models.backend import ToolCall


class OpenAIBackend:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        base_url: str | None = None,
    ):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.last_latency_ms = 0.0

    def invoke(self, tools: list[dict], messages: list[dict]) -> ToolCall | str:
        started = time.perf_counter()
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="required",
                temperature=0,
            )
            self.last_latency_ms = (time.perf_counter() - started) * 1000

            choice = resp.choices[0]
            if choice.message.tool_calls:
                tc = choice.message.tool_calls[0]
                args = tc.function.arguments
                if isinstance(args, str):
                    args = json.loads(args)
                return ToolCall(name=tc.function.name, arguments=args)

            content = choice.message.content or ""
            if content:
                try:
                    parsed = json.loads(content.strip())
                    if "name" in parsed:
                        a = parsed.get("arguments", {})
                        if isinstance(a, str):
                            a = json.loads(a)
                        return ToolCall(name=parsed["name"], arguments=a)
                except (json.JSONDecodeError, KeyError):
                    pass

            return f"No valid tool call in OpenAI response: {content}"
        except Exception as exc:
            self.last_latency_ms = (time.perf_counter() - started) * 1000
            return str(exc)
