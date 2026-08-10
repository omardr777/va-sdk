# ADR-004: ToolError Hierarchy for Backend Failures

**Status:** Accepted  
**Date:** 2026-08-10

## Context

Backend API calls can fail in different ways: auth expiry, resource not
found, input validation, generic errors. The user's experience should
differ based on the error type.

## Decision

**`ToolError` class hierarchy raised from the `call` lambda.** The
orchestrator catches specific error types and formats
contextually-appropriate messages.

```python
class ToolError(Exception):
    @staticmethod auth_expired(msg) → ToolError
    @staticmethod not_found(msg) → ToolError
    @staticmethod validation(msg) → ToolError
    @staticmethod generic(msg) → ToolError
```

The orchestrator handles each:
- `auth_expired` — signals frontend to re-authenticate
- `not_found` — "I couldn't find a {thing}. Do you have one?"
- `validation` — "That value doesn't seem right. Try {constraint}."
- `generic` — "Something went wrong. Could you try again?"

Each tool also has an `error_template` for the generic fallback.

## Rationale

1. **Developer control.** The lambda author knows the backend's failure modes
   and raises the right error with a user-friendly message.
2. **Consistent UX.** The orchestrator formats errors uniformly regardless of
   which tool failed.
3. **Simple protocol.** Raise from Python code, catch in orchestrator. No
   complex error mapping config.

## Consequences

- Tool lambdas must import and use `ToolError`.
- The orchestrator must handle all four error types.
- Custom error types can be added later via subclassing.
