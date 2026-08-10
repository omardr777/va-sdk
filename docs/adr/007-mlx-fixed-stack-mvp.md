# ADR-007: MLX Backend and Fixed Model Stack (MVP)

**Status:** Accepted  
**Date:** 2026-08-10

## Context

The SDK needs an SLM inference backend for MVP. The model must be open-source
and run locally on developer hardware.

## Decision

**MLX backend on Apple Silicon with Qwen3-0.6B for MVP.** The model stack is
fixed — no pluggable model backends yet. ASR uses Whisper, TTS uses Kokoro
(as in the current VoiceTeller project).

## Rationale

1. **Proven in VoiceTeller.** The same stack achieves ~40ms SLM inference,
   ~75ms TTS synthesis, sub-400ms total latency. Within the 500-800ms
   threshold for natural conversation.
2. **No cloud dependency.** Everything runs locally. No API keys. Customer
   data stays on-device.
3. **MVP scope.** Pluggable backends (Ollama, OpenAI, Anthropic) add
   complexity without changing the core value proposition. They can be added
   later.
4. **Apple Silicon is the default for local AI development.** MLX is
   optimized for M-series chips.

## Consequences

- `MLXBackend` is the only `ModelBackend` implementation for MVP.
- `ModelBackend` protocol exists for future extension.
- The reference voice server requires an MLX-compatible Mac.
- Training uses Modal (cloud GPU), not local.
