from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal


class ToolError(Exception):
    """Raised from tool call lambdas to signal backend failures.

    The orchestrator catches these and formats user-facing error messages.
    """

    def __init__(self, message: str, kind: str = "generic"):
        super().__init__(message)
        self.kind = kind
        self.message = message

    @classmethod
    def auth_expired(cls, message: str) -> ToolError:
        return cls(message, kind="auth_expired")

    @classmethod
    def not_found(cls, message: str) -> ToolError:
        return cls(message, kind="not_found")

    @classmethod
    def validation(cls, message: str) -> ToolError:
        return cls(message, kind="validation")

    @classmethod
    def generic(cls, message: str) -> ToolError:
        return cls(message, kind="generic")


class Param:
    """A parameter declared by a voice tool."""

    def __init__(
        self,
        name: str,
        *,
        type: Literal["string", "number", "boolean"] = "string",
        required: bool = True,
        enum: list[str] | None = None,
        description: str,
        prompt: str | None = None,
    ):
        self.name = name
        self.type = type
        self.required = required
        self.enum = enum
        self.description = description
        self.prompt = prompt

    def to_openai_schema(self) -> dict[str, Any]:
        """Generate the JSON Schema property for OpenAI tool definitions."""
        prop: dict[str, Any] = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum:
            prop["enum"] = self.enum
        return prop


class Tool:
    """A declared voice capability.

    Tools are the source of truth for what the voice assistant can do.
    """

    def __init__(
        self,
        name: str,
        *,
        description: str,
        params: list[Param],
        call: Callable[..., dict[str, Any]],
        success_template: str,
        error_template: str = "Something went wrong: {error_message}.",
        map_result: Callable[[Any, dict[str, Any]], dict[str, Any]] | None = None,
        input_examples: list[dict[str, Any]] | None = None,
        category: str | None = None,
    ):
        self.name = name
        self.description = description
        self.params = params
        self._call = call
        self.success_template = success_template
        self.error_template = error_template
        self.map_result = map_result
        self.input_examples = input_examples or []
        self.category = category

    @property
    def required_args(self) -> list[str]:
        """Args the orchestrator must elicit before calling the backend."""
        return [p.name for p in self.params if p.required]

    @property
    def slot_prompts(self) -> dict[str, str]:
        """Natural language prompts for each slot that may be elicited."""
        return {p.name: p.prompt or f"the {p.name.replace('_', ' ')}" for p in self.params}

    async def call(self, api: Any, **kwargs: Any) -> dict[str, Any]:
        """Execute the tool's backend call.

        The orchestrator injects ``api`` (from ``api_factory``) as the first
        positional argument.  Remaining kwargs match the declared params.
        """
        import inspect

        if inspect.iscoroutinefunction(self._call):
            return await self._call(api, **kwargs)
        return self._call(api, **kwargs)

    def to_openai_tool(self) -> dict[str, Any]:
        """Generate the OpenAI tool definition for function calling."""
        properties: dict[str, Any] = {}
        for p in self.params:
            properties[p.name] = p.to_openai_schema()

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }


class Toolkit:
    """Registry of voice tools and the API factory that connects them.

    Usage::

        toolkit = Toolkit(
            tools=[check_balance, transfer_money, ...],
            api_factory=lambda auth_ctx: MyAPI(auth_ctx["token"]),
        )
    """

    def __init__(
        self,
        tools: list[Tool],
        api_factory: Callable[[dict[str, Any]], Any],
    ):
        self.tools = tools
        self.api_factory = api_factory
        self._tool_by_name: dict[str, Tool] = {t.name: t for t in tools}

    def get(self, name: str) -> Tool | None:
        return self._tool_by_name.get(name)

    def to_openai_tools(self) -> list[dict[str, Any]]:
        return [t.to_openai_tool() for t in self.tools]
