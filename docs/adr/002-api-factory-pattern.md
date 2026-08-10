# ADR-002: Lambda-based Tool Execution with Injected `api`

**Status:** Accepted  
**Date:** 2026-08-10

## Context

Tool execution requires calling the developer's backend API. The tool's
`call` function needs access to an authenticated client. Two options:

1. **Auth injection** (`call(auth, **params)`) — SDK injects auth provider.
   Lambda calls `auth.get("/accounts")`.
2. **Closure** (`call(**params)`) — developer captures an authenticated
   client from outer scope.

## Decision

**Injected `api` via `api_factory`.** The lambda receives `api` as its first
argument. The SDK calls a developer-provided factory to create an
authenticated API client per session.

```python
toolkit = Toolkit(
    tools=[...],
    api_factory=lambda auth_context: BankAPI(auth_context["token"]),
)

def check_balance(api: BankAPI, account_type: str) -> dict:
    resp = api.get(f"/accounts?type={account_type}")
    ...
```

## Rationale

1. **Supports any backend.** `api` is opaque — HTTP client, DB cursor, gRPC
   stub, whatever the developer's stack uses.
2. **Re-auth transparent.** The factory is called once per session. Token
   refresh is the factory's responsibility.
3. **Testable.** Inject a mock API in tests without touching the lambda.
4. **Clean lambda signature.** Only `api` + declared params. No auth noise.

## Consequences

- `Toolkit` requires an `api_factory` callable.
- Auth context flows from the voice server (extracts from request headers) →
  factory → `api` → lambda.
- `ToolError.auth_expired()` signals the frontend to re-authenticate.
