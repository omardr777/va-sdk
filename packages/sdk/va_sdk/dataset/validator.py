from __future__ import annotations

from typing import Any

from va_sdk.tool import Tool


def validate_conversation(
    conversation: dict[str, Any],
    tools: list[Tool],
    *,
    check_arguments: bool = True,
) -> list[str]:
    errors: list[str] = []

    tool_names = {t.name for t in tools}
    tool_schemas = {t.name: t for t in tools}
    tool_params = {}
    for t in tools:
        param_specs = {}
        for p in t.params:
            param_specs[p.name] = {
                "type": p.type,
                "enum": p.enum,
                "required": p.required,
            }
        tool_params[t.name] = param_specs

    messages = conversation.get("messages", [])
    if not messages:
        errors.append("conversation has no messages")
        return errors

    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        if role not in ("system", "user", "assistant"):
            errors.append(f"message[{i}]: invalid role '{role}'")
            continue

        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            continue

        for j, tc in enumerate(tool_calls):
            fn = tc.get("function", {})
            name = fn.get("name", "")
            if name not in tool_names:
                errors.append(f"message[{i}].tool_calls[{j}]: unknown function '{name}'")
                continue

            if not check_arguments:
                continue

            import json

            args_raw = fn.get("arguments", "{}")
            if isinstance(args_raw, str):
                try:
                    args = json.loads(args_raw)
                except json.JSONDecodeError:
                    errors.append(
                        f"message[{i}].tool_calls[{j}]: invalid JSON arguments"
                    )
                    continue
            else:
                args = args_raw

            specs = tool_params.get(name, {})
            for arg_name, arg_value in args.items():
                spec = specs.get(arg_name)
                if not spec:
                    if arg_name not in specs:
                        errors.append(
                            f"message[{i}].tool_calls[{j}]: unknown argument '{arg_name}' for '{name}'"
                        )
                    continue

                if spec.get("enum") and arg_value not in spec["enum"]:
                    errors.append(
                        f"message[{i}].tool_calls[{j}]: invalid enum value '{arg_value}' "
                        f"for '{arg_name}' (expected: {spec['enum']})"
                    )
                    continue

                if spec["type"] == "number":
                    if not isinstance(arg_value, (int, float)):
                        errors.append(
                            f"message[{i}].tool_calls[{j}]: '{arg_name}' should be number, got {type(arg_value).__name__}"
                        )

    return errors


def validate_dataset(
    conversations: list[dict[str, Any]],
    tools: list[Tool],
) -> tuple[list[dict[str, Any]], int]:
    valid = []
    rejected = 0
    for conv in conversations:
        errors = validate_conversation(conv, tools)
        if errors:
            rejected += 1
        else:
            valid.append(conv)
    return valid, rejected
