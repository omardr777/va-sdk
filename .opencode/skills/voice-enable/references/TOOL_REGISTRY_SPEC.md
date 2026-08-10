# Tool Registry Spec

## Tool class

```python
class Tool:
    name: str                   # Unique. snake_case. e.g. "check_balance"
    description: str            # 2-4 sentences. What, when, when-not.
    params: list[Param]         # Ordered. Controls slot elicitation order.
    call: Callable              # (api, **kwargs) -> dict
    success_template: str       # Format string. {api_result} + {original_args}
    error_template: str = "..." # Format string. Has {error_message}.
    map_result: Callable|None   # (api_result, args) -> dict. Optional.
    input_examples: list[dict]  # e.g. [{"account_type": "checking"}]
    category: str|None          # Optional grouping for UI
```

## Param class

```python
class Param:
    name: str                   # snake_case. e.g. "account_type"
    type: "string"|"number"|"boolean"
    required: bool = True       # Orchestrator elicits if missing
    enum: list[str]|None = None # Constrains valid values
    description: str            # For the LLM. e.g. "Type of account to check"
    prompt: str|None = None     # "which account" — natural language slot prompt
```

## Toolkit class

```python
class Toolkit:
    def __init__(self, tools: list[Tool], api_factory: Callable): ...
```

The `api_factory` receives `auth_context: dict` and returns the `api` object that
is injected as the first argument to every `call` lambda.

## ToolError

```python
ToolError.auth_expired(msg)    # Signals frontend to re-authenticate
ToolError.not_found(msg)       # Resource doesn't exist
ToolError.validation(msg)      # Input validation failed
ToolError.generic(msg)          # Catch-all
```

Raise these from inside `call` lambdas. The orchestrator formats them with the
tool's `error_template`.

## Response rendering

Templates use Python `.format()`. The merged dict passed is:
`{**mapped_api_result, **original_arguments}`

Original args overwrite api results on key collision. Numeric formatting
works: `"${amount:.2f}"`.

## Meta tools (automatic)

These are hardcoded in the orchestrator — do NOT register them:

| Tool | Response |
|------|----------|
| `greeting` | "Hello! How can I help you today?" |
| `goodbye` | "Goodbye! Thanks for calling." |
| `thank_you` | "You're welcome! Is there anything else I can help with?" |
| `intent_unclear` | "I didn't quite understand that. Could you rephrase?" |
| `speak_to_human` | "Connecting you to an agent now. Please hold." |

## LLM tool schema

The orchestrator generates OpenAI-style tool schemas from the registry.
Key decisions:
- `required: []` always — the SLM can omit any arg. Slot filling is deterministic.
- `additionalProperties: false` — strict mode compatible.
- Param descriptions are included for the LLM, may be stripped after fine-tuning.
