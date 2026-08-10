# Training Pipeline

## Overview

va-sdk generates fine-tuning data but doesn't handle training itself.
The output is standard OpenAI fine-tuning JSONL format.

## Generation Tiers

| Tier | Method | Coverage | API Calls | Description |
|------|--------|----------|-----------|-------------|
| 1 | Enumerate param enums → teacher generates prompts | ~70% | ~N * 3 calls | Single-turn conversations. Zero developer effort. |
| 2 | Same + systematically remove required params → teacher generates slot-elicitation turns | ~90% | Additional calls | Multi-turn conversations with natural slot filling. |

## Output Format

```jsonl
{"messages": [
  {"role": "system", "content": "You are a tool-calling voice assistant..."},
  {"role": "user", "content": "what's my checking balance?"},
  {"role": "assistant", "tool_calls": [{
    "id": "call_1", "type": "function",
    "function": {"name": "check_balance", "arguments": "{\"account_type\": \"checking\"}"}
  }]}
], "tools": [
  {"type": "function", "function": {"name": "check_balance", ...}}
]}
```

## Training Options

### Option A — Modal (cloud GPU)

Use the Modal training script. Takes train.jsonl + test.jsonl, fine-tunes,
and outputs LoRA adapters or merged weights.

### Option B — Distil CLI

Upload to Distil platform for knowledge-distillation training with auto-evaluation.

### Option C — Unsloth (local GPU)

Fine-tune locally with Unsloth LoRA. Works with any HuggingFace model.

## Post-Training

After fine-tuning:
1. **Strip descriptions** from tool schemas — the fine-tuned model doesn't need
   them and this saves ~40-50% input tokens per call.
2. **Serve with llama.cpp / MLX / Ollama** — the model exposes an
   OpenAI-compatible `/v1/chat/completions` endpoint.
3. **Point va-sdk at the served model** via `--slm-port`.

## Key Training Data Properties

- **~30% of turns** should include ASR transcription artifacts (filler words,
  homophones, word splits, mis-transcriptions).
- **Multi-turn slot filling** across 2-5 turns per conversation.
- **Intent changes** mid-conversation (user starts asking about balance,
  switches to transfer).
- **Error recovery** — `intent_unclear` followed by clarification.
- **ASR robustness** — training data uses casual language ("checkin" instead of
  "checking", "save ins" instead of "savings").
- All conversations end with `goodbye`.

## Evaluation

Dict equality of predicted JSON vs reference JSON (exact match on tool name +
arguments). Run on held-out test set after training.
