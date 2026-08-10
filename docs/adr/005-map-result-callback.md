# ADR-005: map_result Callback for API Response Transformation

**Status:** Accepted  
**Date:** 2026-08-10

## Context

API responses rarely match the shape needed for template rendering. Example:
`GET /accounts?type=checking` returns `[{"balance": 2500.0}]` but the
template needs `{"balance": 2500.0}`.

Three options:
1. **`map_result` callback** — explicit transformation function.
2. **Dotted-path templates** — `"${response[0].balance:.2f}"`.
3. **Lambda returns template-ready dict** — simplest, but mixes concerns.

## Decision

**`map_result` callback on `Tool`.** The callback receives `(api_result,
original_args)` and returns a dict for template rendering. Optional — if not
provided, the lambda's return value is used directly.

```python
Tool(
    call=lambda api, account_type: api.get(f"/accounts?type={account_type}"),
    map_result=lambda data, args: {"balance": data[0]["balance"]},
    success_template="Your {account_type} balance is ${balance:.2f}.",
)
```

## Rationale

1. **Separation of concerns.** The `call` lambda calls the API. `map_result`
   shapes the response. The template is pure presentation.
2. **Testable.** Each function is independently testable.
3. **Optional.** Simple tools skip it. Complex responses use it.

## Consequences

- `map_result` receives `(api_result, dict_of_original_args)`.
- The merged dict `{**mapped_result, **original_args}` is passed to the
  template. Original args overwrite mapped values on collision.
