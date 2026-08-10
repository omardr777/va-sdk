# ADR-001: Tool Registration Pattern (not Decorators)

**Status:** Accepted  
**Date:** 2026-08-10

## Context

We need developers to declare what their backend can do for the voice
assistant. Two approaches were considered:

1. **Decorators** on existing API functions — `@voice_tool` on FastAPI
   endpoints. Auto-extracts schemas from type hints.
2. **Tool Registry** — a standalone file where tools are declared as
   first-class entities, separate from backend implementations.

## Decision

**Tool Registry pattern.** Tools are declared explicitly in a registry, not
coupled to backend code via decorators.

## Rationale

1. **Voice intents don't map 1:1 to REST endpoints.** One voice intent
   (e.g., "cancel card") calls multiple endpoints (GET to find card, POST to
   cancel). Decorators on endpoints can't express composite operations.
2. **Meta tools have no backend.** `greeting`, `goodbye`, `thank_you` are
   pure templates. Decorators need a function to decorate.
3. **Natural language is first-class.** Tool descriptions, slot prompts, and
   response templates are the highest-leverage inputs for accuracy. They
   deserve their own file and iteration loop.
4. **Industry consensus.** OpenAI, Anthropic, MCP, Vapi, and LiveKit all use
   explicit tool declarations. The `tools` parameter in every API is a
   registry of standalone schema objects.
5. **Fine-tuning pipeline compatibility.** The dataset generator enumerates
   the registry to auto-synthesize training data. A decorator-based approach
   provides no benefit here.
6. **Anthropic explicitly warns against wrapping endpoints.** Their
   engineering blog advises consolidating related operations into fewer tools
   rather than exposing every API endpoint.

## Consequences

- Developers maintain a `voice_tools.py` file alongside their backend.
- OpenAPI → scaffolded registry is a future convenience (CLI reads spec,
  generates stub registry).
- Meta tools are hardcoded constants in the orchestrator, not part of the
  registry.
