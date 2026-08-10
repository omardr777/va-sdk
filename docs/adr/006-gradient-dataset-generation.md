# ADR-006: Gradient Dataset Generation (4 Tiers)

**Status:** Accepted  
**Date:** 2026-08-10

## Context

The SDK must generate fine-tuning data from the tool registry. The developer
may have zero, some, or extensive domain knowledge. The system must work
across this spectrum.

## Decision

**Four-tier dataset generation, escalating in quality and developer effort.**

| Tier | Method | Coverage | Developer Effort |
|------|--------|----------|-----------------|
| 1 | Single-turn auto-synthesis from registry enums | ~70% | Zero (one CLI command) |
| 2 | Multi-turn slot-filling auto-synthesis | ~90% | Zero |
| 3 | Shipped domain seed templates (banking) | ~95% | Customize template |
| 4 | Custom seed conversations | ~100% | Write seeds |

## Rationale

1. **Zero-effort tier lowers adoption friction.** One command produces a
   trainable model. Works for simple CRUD backends.
2. **Slot-filling is mechanically derivable.** The registry knows which
   params are required. The system can synthesize missing-slot scenarios
   deterministically. The teacher only writes natural language prompts.
3. **Shipped templates accelerate common domains.** Banking ships as the
   reference domain. E-commerce, healthcare, etc. can follow.
4. **Custom seeds for exact control.** Power users who need specific patterns
   (intent changes, error recovery, ASR artifacts) write their own.
5. **OpenAI cookbook validates the approach.** Their fine-tuning cookbook
   uses the same enumeration → teacher-generated prompts pipeline.

## Consequences

- `va-sdk generate` runs tiers 1+2 automatically. Tiers 3+4 are opt-in.
- Teacher model: cloud API (GPT-4o / Claude) for MVP.
- Training: Modal (cloud GPU) for MVP fine-tuning.
- Output format: JSONL matching OpenAI fine-tuning API format.
