# va-sdk — Architecture

## High-Level Overview

```
┌──────────────────────────────────────────────────────┐
│  Developer's Backend                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ Accounts │  │  Cards   │  │   Auth   │  ...       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘            │
│       │              │              │                  │
│       └──────┬───────┴──────┬───────┘                  │
│              │              │                          │
│         voice_tools.py      │                          │
│         (Tool registry)     │                          │
└──────────────┬──────────────┼──────────────────────────┘
               │              │
               ▼              ▼
┌───────────────────────────────────────────────────────┐
│  va-sdk                                                │
│                                                        │
│  ┌─────────────┐  ┌────────────┐  ┌───────────────┐   │
│  │ Orchestrator │  │  Dataset   │  │ CLI / Server  │   │
│  │              │  │  Generator │  │               │   │
│  │ slot filling │  │ schema enum│  │ va-sdk serve  │   │
│  │ tool dispatch│  │ seed expand│  │ va-sdk gen    │   │
│  │ templates    │  │ validate   │  │ va-sdk val    │   │
│  └──────┬───────┘  └─────┬──────┘  └───────────────┘   │
│         │                │                              │
│    ┌────▼────┐      ┌────▼─────┐                        │
│    │   SLM   │      │  Teacher │                        │
│    │  (MLX)  │      │  (Cloud) │                        │
│    └─────────┘      └──────────┘                        │
│                                                        │
└────────────────────────────────────────────────────────┘
               │
               ▼
┌───────────────────────────────────────────────────────┐
│  Frontend                                              │
│  ┌─────────────────┐  ┌──────────────────┐            │
│  │ Dataset Studio  │  │ Voice Playground │            │
│  │ browse/filter/  │  │ tool catalog/    │            │
│  │ generate/expand │  │ auth/convo log   │            │
│  └─────────────────┘  └──────────────────┘            │
│  ┌──────────────────────────────────────┐             │
│  │  @va-sdk/react VoiceAssistant FAB    │             │
│  └──────────────────────────────────────┘             │
└───────────────────────────────────────────────────────┘
```

## Monorepo Structure

```
va-sdk/
├── packages/
│   ├── sdk/                         # pip install va-sdk
│   │   ├── va_sdk/
│   │   │   ├── __init__.py
│   │   │   ├── tool.py              # Tool, Param, ToolError, Toolkit
│   │   │   ├── orchestrator.py      # VoiceOrchestrator (text → text)
│   │   │   ├── pipeline.py          # VoicePipeline (audio → audio)
│   │   │   ├── server.py            # Reference FastAPI voice server
│   │   │   ├── dataset/
│   │   │   │   ├── generator.py     # Schema enumerator + seed auto-synthesis
│   │   │   │   ├── expander.py      # Paraphraser + ASR artifacts + dedupe
│   │   │   │   ├── validator.py     # Schema check + semantic judge
│   │   │   │   └── exporter.py      # → train.jsonl + test.jsonl
│   │   │   └── models/
│   │   │       ├── backend.py       # ModelBackend protocol
│   │   │       └── mlx_backend.py   # MLX backend (MVP)
│   │   ├── cli.py                   # va-sdk serve | generate | validate
│   │   └── pyproject.toml
│   │
│   ├── frontend/                    # React 19 + Vite 8 + Tailwind CSS 4
│   │   └── src/
│   │       ├── pages/
│   │       │   ├── DatasetStudio.tsx
│   │       │   └── VoicePlayground.tsx
│   │       ├── components/
│   │       │   ├── Layout.tsx
│   │       │   └── VoiceAssistant.tsx
│   │       └── api/
│   │           └── client.ts
│   │
│   └── react-widget/                # npm: @va-sdk/react
│       └── src/
│           └── VoiceAssistant.tsx
│
├── templates/                       # Shipped domain starter packs
│   └── banking/
│       ├── tools.py
│       ├── seeds.jsonl
│       └── job_description.json
│
├── docs/
│   ├── CONTEXT.md
│   ├── ARCHITECTURE.md
│   └── adr/
└── README.md
```

## Core Components

### tool.py — Tool Registry

The source of truth for voice capabilities. A `Tool` declares:
- What it does (`name`, `description`, `params`)
- How to execute it (`call` lambda with injected `api`)
- How to respond (`success_template`, `error_template`)
- How to train from it (`input_examples`, param `enum` values)

```python
Tool(
    name="check_balance",
    description="Check the balance of a bank account.",
    params=[
        Param("account_type", type="string",
              enum=["checking", "savings", "credit"],
              description="Type of account",
              prompt="which account"),
    ],
    call=lambda api, account_type: api.get(f"/accounts?type={account_type}"),
    map_result=lambda data, args: {"balance": data[0]["balance"]},
    success_template="Your {account_type} balance is ${balance:.2f}.",
    error_template="Couldn't check {account_type}: {error_message}.",
    input_examples=[{"account_type": "checking"}],
    category="banking",
)
```

### orchestrator.py — VoiceOrchestrator

Text-in, text-out. Core loop:

```
user utterance
  → append to conversation history
  → call SLM with tools + history (tool_choice="required")
  → parse tool_call (name + arguments)
  → check missing required args
  → if missing: generate slot elicitation, return question
  → if complete: execute tool.call(api, **args)
  → catch ToolError, format error_template
  → format success_template with {**api_result, **args}
  → reset conversation history
  → return response text
```

Key properties:
- All tool_call messages are recorded in conversation history
- `required` is always `[]` in the LLM schema — the model can omit any arg
- Slot filling is deterministic: orchestrator checks `FUNCTION_REQUIRED_ARGS`
- Reset after every completed turn or error
- Meta tools (greeting, goodbye, thank_you) are hardcoded constants

### pipeline.py — VoicePipeline

Wraps orchestrator with ASR and TTS:

```
audio bytes → ASR → text
text → Orchestrator → response_text
response_text → TTS → audio bytes
```

Session state managed via pluggable `SessionStore`. MVP uses `InMemoryStore`.

### models/ — Model Backends

```python
class ModelBackend(Protocol):
    def invoke(self, tools: list[dict], messages: list[dict]) -> ToolCall:
        """name: str, arguments: dict"""
```

MVP: `MLXBackend` (Apple Silicon, loads Qwen3-0.6B models).
Future: `OllamaBackend`, `OpenAIBackend`, `AnthropicBackend`.

### dataset/ — Dataset Generator

Four tiers of generation, escalating in quality and developer effort:

| Tier | Method | Coverage | Effort |
|------|--------|----------|--------|
| 1 | Auto-synthesis from registry enums | ~70% | Zero |
| 2 | Slot-filling auto-synthesis | ~90% | Zero |
| 3 | Shipped domain templates (banking) | ~95% | Customize |
| 4 | Custom seeds | ~100% | High |

Pipeline: generate → expand (paraphrase + ASR artifacts) → validate (schema +
semantic judge) → dedupe → export (train.jsonl + test.jsonl).

Teacher model: cloud API (GPT-4o / Claude) for MVP.

### server.py — Reference Server

FastAPI server wrapping the voice pipeline. Endpoints:
- `POST /voice` — audio + auth_context → transcribe → orchestrate → synthesize → audio response
- `POST /orchestrate` — text + auth_context → response text (no audio)
- `GET /health` — liveness check

### cli.py — CLI

```
va-sdk serve       Start reference FastAPI server
va-sdk generate    Run dataset generation pipeline
va-sdk validate    Validate tools.py schema and consistency
```

## Runtime Data Flow

```
Browser mic → POST /voice (audio + auth_context)
  ├─ ASR:              audio → "what's my checking balance?"
  ├─ Orchestrator:
  │   ├─ SLM.invoke()  → {"name": "check_balance", "arguments": {"account_type": "checking"}}
  │   ├─ slot check    → no missing args
  │   ├─ api_factory   → create API client from auth_context
  │   ├─ tool.call     → GET /accounts?type=checking → {"balance": 2500.0}
  │   ├─ map_result    → {"balance": 2500.0}
  │   └─ template      → "Your checking balance is $2,500.00."
  └─ TTS:              text → audio bytes → return to browser
```

## Dataset Generation Flow

```
voice_tools.py
  ├─ Tier 1: Enumerate Param.enum → all invocation combos
  │   └─ Teacher generates 2-3 natural user prompts per invocation
  │       → train.jsonl (single-turn)
  │
  ├─ Tier 2: Systematically remove required params
  │   └─ Teacher generates slot-elicitation turns
  │       → merged into train.jsonl (multi-turn)
  │
  ├─ Tier 3: Load shipped template seeds
  │   └─ expander: paraphraser + ASR artifacts + dedupe + validate
  │       → train.jsonl
  │
  └─ Tier 4: Load custom seeds
      └─ same expansion pipeline as Tier 3
```

## Training Data Format

```jsonl
{
  "messages": [
    {"role": "system", "content": "You are a banking assistant..."},
    {"role": "user", "content": "transfer $50 from checking to savings"},
    {"role": "assistant", "tool_calls": [
      {
        "id": "call_1",
        "type": "function",
        "function": {
          "name": "transfer_money",
          "arguments": "{\"amount\": 50, \"from_account\": \"checking\", \"to_account\": \"savings\"}"
        }
      }
    ]}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "transfer_money",
        "description": "Transfer money between accounts",
        "parameters": {
          "type": "object",
          "properties": {
            "amount": {"type": "number"},
            "from_account": {"type": "string"},
            "to_account": {"type": "string"}
          },
          "required": []
        }
      }
    }
  ]
}
```

Note: After fine-tuning, parameter descriptions are stripped from the tool
schemas to reduce token usage by ~40-50%. This is critical for SLMs with
limited context windows.
