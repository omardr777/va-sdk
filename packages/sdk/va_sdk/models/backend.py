from __future__ import annotations

from typing import Protocol

from va_sdk.tool import Tool


class ToolCall:
    """Normalized tool call returned by any model backend."""

    def __init__(self, name: str, arguments: dict):
        self.name = name
        self.arguments = arguments


class ModelBackend(Protocol):
    """Protocol for LLM backends that accept tools and return tool calls.

    All backends receive the same inputs and return the same output shape.
    The orchestrator never knows which backend is in use.
    """

    def invoke(self, tools: list[dict], messages: list[dict]) -> ToolCall | str:
        """Send conversation history + tools to the model.

        Returns a ``ToolCall`` on success, or an error string on failure.
        """
        ...
