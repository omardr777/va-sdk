from __future__ import annotations

from va_sdk.models.backend import ToolCall


class MLXBackend:
    """OpenAI-compatible backend backed by an MLX-served model on Apple Silicon.

    MVPs targets ``smollm2-135m-bankco-mlx-fp16`` — the fine-tuned SmolLM2
    served by ``python serve_smolm2_mlx.py`` on port 8002.
    """

    def __init__(self, base_url: str = "http://localhost:8002/v1"):
        self.base_url = base_url
        self.last_latency_ms: float = 0.0

    def invoke(self, tools: list[dict], messages: list[dict]) -> ToolCall | str:
        import json
        import time

        import httpx

        body = {
            "model": "smollm2-135m-bankco-mlx-fp16",
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
                timeout=30.0,
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
                    args = parsed.get("arguments", parsed.get("parameters", {}))
                    if isinstance(args, str):
                        args = json.loads(args)
                    return ToolCall(name=parsed["name"], arguments=args)
            except (json.JSONDecodeError, KeyError):
                pass

        return f"No valid tool call in SLM response, model returned {message}"
