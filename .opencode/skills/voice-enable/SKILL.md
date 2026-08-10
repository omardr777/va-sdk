---
name: voice-enable
description: Voice-enable a SaaS API using va-sdk. Generates tool registries, fine-tuning datasets, trains SLMs, and runs the voice pipeline. Use when the user wants to add voice capabilities to their API, build a voice assistant, voice-enable their backend, or mentions "voice", "SLM", "voice assistant", "va-sdk".
---

# Voice-Enable Your API

The agent reads the developer's backend, generates a tool registry, then
the developer opens the dashboard to test, generate training data, train on
Modal, and serve with their fine-tuned model.

## Phase 0 — Install

```bash
pip install va-sdk httpx

# Verify
va-sdk --help
```

## Phase 1 — Discover the Backend

1. **Find the OpenAPI spec** — `GET /openapi.json`, `/docs`, or read source.
2. **If no spec exists**, read route definitions, schemas, and auth mechanism.
3. **Document**: base URL, auth method, all endpoints (method, path, params, response).

## Phase 2 — Generate voice_tools.py

Create `voice_tools.py` with `Tool` + `Toolkit`. See
[TOOL_REGISTRY_SPEC.md](references/TOOL_REGISTRY_SPEC.md).

**Rules:**
1. **Consolidate** — one voice intent can call multiple endpoints
2. **Descriptions** — 2-4 sentences: what, when, when-not
3. **Every required param needs `prompt`** — natural language slot elicitation
4. **`api_factory` receives `auth_context`** — `lambda auth_ctx: MyAPI(auth_ctx.get("token"))`
5. **Raise `ToolError`** — `.not_found()`, `.validation()`, `.auth_expired()`, `.generic()`
6. **Meta tools are built-in** — don't register `greeting`, `goodbye`, `thank_you`, `intent_unclear`, `speak_to_human`

```python
import httpx
from va_sdk import Tool, Param, Toolkit, ToolError

class MyAPI:
    def __init__(self, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.http = httpx.Client(base_url="http://localhost:8001", headers=headers)
    def get(self, path, **kw):
        r = self.http.get(path, **kw)
        if r.status_code == 401: raise ToolError.auth_expired("Session expired")
        if r.status_code >= 400:
            d = r.json().get("detail", "Backend error")
            if "not found" in str(d).lower(): raise ToolError.not_found(str(d))
            raise ToolError.generic(str(d))
        return r.json()
    def post(self, path, json=None, **kw):
        r = self.http.post(path, json=json, **kw)
        if r.status_code == 401: raise ToolError.auth_expired("Session expired")
        if r.status_code >= 400:
            raise ToolError.generic(r.json().get("detail", "Backend error"))
        return r.json()

tools = [
    Tool(
        name="check_balance",
        description="Check an account balance. Use when the user asks about "
                    "their balance. Do not use for transfers or statements.",
        params=[
            Param("account_type", type="string",
                  enum=["checking", "savings", "credit"],
                  description="Type of account", prompt="which account"),
        ],
        call=lambda api, account_type: api.get("/accounts", params={"type": account_type}),
        map_result=lambda data, args: {"balance": data[0]["balance"] if data else 0},
        success_template="Your {account_type} balance is ${balance:.2f}.",
        error_template="Couldn't check balance: {error_message}.",
        category="banking",
    ),
]

toolkit = Toolkit(
    tools=tools,
    api_factory=lambda auth_ctx: MyAPI(auth_ctx.get("token") if auth_ctx else None),
)
```

## Phase 3 — Validate

```bash
va-sdk validate --tools voice_tools.py
```

## Phase 4 — Test & Generate from the Dashboard

```bash
va-sdk serve --tools voice_tools.py
```

This starts the server on port 8766. Open `http://localhost:8766/dashboard`.

**The dashboard is bundled in the pip package — no cloning needed.**

From the dashboard, everything happens in the browser:
- **Playground tab**: enter API key → Connect → your tools auto-populate → test voice
- **Dataset tab**: enter API key → click Generate → `train.jsonl` + `test.jsonl` exported
- **Train section** (in Dataset tab): enter Modal token → click Train → job submitted

No CLI flags needed. All API keys, model selection, and config are set in the UI.

Backend options (configured in the Playground tab):
- `openai` — uses GPT-4o (or any OpenAI model). Needs API key.
- `local` — uses a local llama.cpp server pointed at your fine-tuned model.
- `mlx` — uses an MLX server on Apple Silicon (not needed for most users).

## Phase 5 — Train on Modal (Optional)

From the Dataset Studio page, after generating data:
1. Enter your Modal API token
2. Select base model (default: `Qwen/Qwen2.5-0.5B-Instruct`)
3. Click "Train on Modal"
4. Status polls automatically: submitted → running → done
5. Weights download to `./models/`

The dashboard calls `POST /api/train` with the config. The server runs
`va_sdk.dataset.modal_train.ModalTrainer` which uploads the dataset to Modal
and runs a LoRA fine-tune on a GPU.

## Phase 6 — Serve Your Fine-Tuned Model

Once trained, start your local model server:

```bash
# Start llama.cpp pointing at your fine-tuned weights
llama-server -m ./models/va-sdk-xxx.gguf --port 8080

# Serve with your model
va-sdk serve --tools voice_tools.py --backend local --model local
```

This runs the full voice pipeline (ASR → SLM → Tool Execution → TTS) using YOUR
fine-tuned model — no cloud API needed.

Endpoints for your frontend:
| Endpoint | Description |
|---|---|
| `POST /orchestrate` | Text in → text out. `{"text": "...", "auth_context": {...}}` |
| `POST /voice` | Audio in → audio out (base64 WAV) |
| `POST /stream` | Audio in → NDJSON streaming progress |
| `GET /events` | Telemetry: turn_complete, error, slm_call, tool_execute, slot_fill |

## Phase 7 — Embed in Your App

```tsx
import { VoiceAssistant } from "@va-sdk/react";

<VoiceAssistant
  voiceEndpoint="http://localhost:8766"
  authToken={userJwt}
  position="bottom-right"
/>
```

## Server API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/api/tools` | List all registered tools with params |
| `POST` | `/api/configure` | Set backend config `{backend, api_key, model}` |
| `GET` | `/events` | Recent telemetry events |
| `POST` | `/orchestrate` | Text → text. `{text, auth_context}` |
| `POST` | `/voice` | Audio → audio (multipart) |
| `POST` | `/stream` | Audio → NDJSON streaming |
| `POST` | `/api/generate` | Dataset generation `{tiers, model, api_key, n_prompts, output_dir}` |
| `POST` | `/api/train` | Modal training `{modal_token, model, train_path, test_path}` |
| `GET` | `/api/train/{id}` | Training job status |
| `GET` | `/dashboard` | Bundled React dashboard |

See [EXAMPLES.md](references/EXAMPLES.md) for complete patterns and
[TRAINING.md](references/TRAINING.md) for the training pipeline details.
