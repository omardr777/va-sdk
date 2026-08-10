---
name: voice-enable
description: Voice-enable a SaaS API using va-sdk. Generates tool registries, fine-tuning datasets, trains SLMs, and runs the voice pipeline. Use when the user wants to add voice capabilities to their API, build a voice assistant, voice-enable their backend, or mentions "voice", "SLM", "voice assistant", "va-sdk".
---

# Voice-Enable Your API

## Quick start

The agent's job: read the developer's backend, generate a tool registry, produce
training data, and optionally train and serve the voice pipeline. The developer
just says "voice-enable my API" and the agent handles everything.

## Phase 0 — Install va-sdk (do this first)

Before anything else, install the package:

```bash
# If va-sdk is a sibling directory (common during development):
pip install "$(cd .. && pwd)/va-sdk/packages/sdk"

# Or from git:
pip install "va-sdk @ git+file://$HOME/...va-sdk/packages/sdk"

# Or if published to PyPI:
pip install va-sdk
```

Verify with: `python -c "from va_sdk import Tool; print('ok')"`

Also install backend dependencies needed for the generated `voice_tools.py`:
`httpx` (used by the `BankAPI` client in the tool registry).

## Phase 1 — Discover the Backend

First, understand what the backend can do:

1. **Find the OpenAPI spec** — Look for `openapi.json`, `openapi.yaml`,
   FastAPI `/docs` endpoints, `swagger.json`, or `schema.graphql`.
   Try `GET /openapi.json` and `GET /docs` on the backend URL.

2. **If no spec exists**, read the source code directly. Look for:
   - Route definitions (`@app.get`, `@router.post`, Express routes, etc.)
   - Request/response schemas (Pydantic models, Zod types, etc.)
   - Auth mechanism (JWT, API key, session cookie, etc.)

3. **Document what you found**:
   - Base URL
   - Auth method (and how to get a token)
   - List of endpoints with HTTP method, path, parameters, and response shape

## Phase 2 — Generate the Tool Registry

Create `voice_tools.py` using the va-sdk `Tool` class. See
[references/TOOL_REGISTRY_SPEC.md](references/TOOL_REGISTRY_SPEC.md) for the full
API reference.

**Rules for good tool design:**

1. **Consolidate**: One voice intent may call multiple endpoints.
   E.g. "cancel card" → GET /cards to find → POST /cards/{id}/cancel.
   Write a single `call` lambda that chains them.

2. **Descriptions matter**: Write 2-4 sentence descriptions covering what the
   tool does, when to use it, and when NOT to use it.

3. **Every param needs `prompt`**: This is what the assistant says when
   eliciting a missing slot. Use natural language.

4. **Auth flows through `api_factory`**: The lambda receives an `api` object
   as its first argument. The `api_factory` creates it from `auth_context`.

5. **Raise `ToolError` on failures**: Use `.not_found()`, `.validation()`,
   `.auth_expired()`, `.generic()`.

6. **Meta tools are built-in**: `greeting`, `goodbye`, `thank_you`,
   `intent_unclear`, `speak_to_human` are handled by the orchestrator
   automatically. Don't register them as Tools.

**Minimal example:**

```python
import httpx
from va_sdk import Tool, Param, Toolkit, ToolError

class MyAPI:
    def __init__(self, token: str):
        self.http = httpx.Client(
            base_url="http://localhost:8001",
            headers={"Authorization": f"Bearer {token}"},
        )
    def get(self, path, **kw):
        resp = self.http.get(path, **kw)
        if resp.status_code >= 400:
            detail = resp.json().get("detail", "Backend error")
            if resp.status_code == 401:
                raise ToolError.auth_expired("Session expired.")
            if "not found" in str(detail).lower():
                raise ToolError.not_found(str(detail))
            raise ToolError.generic(str(detail))
        return resp.json()

tools = [
    Tool(
        name="check_balance",
        description="Check an account balance. Use when the user asks about "
                    "their balance. Do not use for transfers or statements.",
        params=[
            Param("account_type", type="string",
                  enum=["checking", "savings", "credit"],
                  description="Type of account",
                  prompt="which account"),
        ],
        call=lambda api, account_type: api.get(
            "/accounts", params={"type": account_type}
        ),
        map_result=lambda data, args: {"balance": data[0]["balance"]},
        success_template="Your {account_type} balance is ${balance:.2f}.",
        error_template="Couldn't check balance: {error_message}.",
        category="banking",
    ),
]

toolkit = Toolkit(
    tools=tools,
    api_factory=lambda auth_ctx: MyAPI(auth_ctx["token"]),
)
```

## Phase 3 — Validate

```bash
va-sdk validate --tools voice_tools.py
```

Fix any issues reported before continuing.

## Phase 4 — Generate Training Data

```bash
va-sdk generate \
  --tools voice_tools.py \
  --output ./data \
  --tiers 1,2 \
  --model gpt-4o \
  --n-prompts 3
```

This will:
- Enumerate every valid argument combination from your tool params
- Use the teacher model to generate natural-sounding user prompts
- Generate multi-turn slot-filling conversations
- Validate all output against the tool schemas
- Export `data/train.jsonl` and `data/test.jsonl`

Requires `OPENAI_API_KEY` in the environment.

## Phase 5 — Train (Optional)

Send the generated dataset to Modal or your fine-tuning platform. The data is in
OpenAI fine-tuning JSONL format.

## Phase 6 — Serve

```bash
va-sdk serve \
  --tools voice_tools.py \
  --port 8766 \
  --slm-port 8002 \
  --asr-backend whisper \
  --tts-backend kokoro
```

Then open the dashboard (`cd packages/frontend && npm run dev`) to test.

## Phase 7 — Embed in Your App

```tsx
import { VoiceAssistant } from "@va-sdk/react";

<VoiceAssistant
  voiceEndpoint="http://localhost:8766"
  authToken={userJwt}
  position="bottom-right"
/>
```

See [references/EXAMPLES.md](references/EXAMPLES.md) for complete examples and
[references/TRAINING.md](references/TRAINING.md) for the full training pipeline.
