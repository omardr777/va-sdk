# ADR-003: Split Slot Filling — SLM Schema vs Orchestrator Logic

**Status:** Accepted  
**Date:** 2026-08-10

## Context

When the SLM returns a tool call with missing arguments, the system must
elicit them from the user. Two approaches:

1. **Let the LLM handle it** — set `required` fields in the LLM schema. The
   model either fills them or asks for them. Less control, inconsistent.
2. **Deterministic slot filling** — LLM schema has `required: []` always. The
   orchestrator checks missing args and generates elicitation prompts.

## Decision

**Deterministic slot filling.** `Param.required` controls only the
orchestrator's slot elicitation. The LLM's tool schema always has
`required: []`.

## Rationale

1. **Predictable user experience.** The orchestrator generates consistent,
   brand-appropriate slot elicitation prompts from `Param.prompt`.
2. **SLM is a classifier, not a conversationalist.** Asking a 0.6B model to
   handle dialogue flow is asking for hallucination.
3. **OpenAI best practice.** Their fine-tuning cookbook documents that
   letting the model infer missing values causes errors. Deterministic checks
   offload this from the model.
4. **Anthropic confirms it.** Their docs note that Claude Sonnet "might guess
   values you didn't supply" when parameters are missing. Not acceptable for
   banking.

## Consequences

- `Param.required` and `Param.prompt` are required for params that trigger
  elicitation.
- Multi-turn conversations are synthesized by the dataset generator by
  systematically removing required params.
- The orchestrator carries prior argument values forward from conversation
  history via the SLM's context (not explicit state).
