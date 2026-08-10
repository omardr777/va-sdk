from __future__ import annotations

import json
import time

from va_sdk.models.backend import ToolCall


class LocalBackend:
    def __init__(self, base_url: str = "http://localhost:8080/v1", model: str = "local"):
        self.base_url = base_url
        self.model = model
        self.last_latency_ms = 0.0

    def invoke(self, tools: list[dict], messages: list[dict]) -> ToolCall | str:
        import httpx

        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "tools": tools,
            "tool_choice": "required",
        }

        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                json=body,
                timeout=60.0,
            )
            response.raise_for_status()
        finally:
            self.last_latency_ms = (time.perf_counter() - started) * 1000

        data = response.json()
        message = data["choices"][0]["message"]

        if message.get("tool_calls"):
            fn = message["tool_calls"][0]["function"]
            arguments = fn["arguments"]
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            return ToolCall(name=fn["name"], arguments=arguments)

        content = message.get("content", "")
        if content:
            try:
                parsed = json.loads(content.strip())
                if "name" in parsed:
                    args = parsed.get("arguments", {})
                    if isinstance(args, str):
                        args = json.loads(args)
                    return ToolCall(name=parsed["name"], arguments=args)
            except (json.JSONDecodeError, KeyError):
                pass

        return f"No valid tool call in response: {message}"
