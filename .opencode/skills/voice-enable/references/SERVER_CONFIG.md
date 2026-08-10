# Server & CLI Reference

## va-sdk serve

```bash
va-sdk serve \
  --tools voice_tools.py \
  --port 8766 \
  --slm-port 8002 \
  --asr-backend whisper \
  --tts-backend kokoro
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--tools` | *(required)* | Path to the tool registry Python file |
| `--port` | `8766` | HTTP server port |
| `--slm-port` | `8002` | Port of the MLX SLM server |
| `--asr-backend` | `whisper` | ASR backend (`whisper`) |
| `--tts-backend` | `kokoro` | TTS backend (`kokoro`, `mac-say`) |

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `GET` | `/events` | Recent telemetry events (query: `?limit=50&type=turn_complete`) |
| `POST` | `/orchestrate` | Text-in, text-out. Body: `{"text": "...", "auth_context": {...}}` |
| `POST` | `/voice` | Audio-in (multipart), JSON-out with base64 audio |
| `POST` | `/stream` | Audio-in, NDJSON streaming progress events |

## va-sdk validate

```bash
va-sdk validate --tools voice_tools.py
```

Checks:
- Every tool has a `call` lambda
- Every tool has a description ≥ 20 characters
- Every tool has a `success_template`
- Every param has a `description`
- Every required param has a `prompt`

## va-sdk generate

```bash
va-sdk generate \
  --tools voice_tools.py \
  --output ./data \
  --tiers 1,2 \
  --model gpt-4o \
  --n-prompts 3 \
  --api-key $OPENAI_API_KEY
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--tools` | *(required)* | Path to tool registry |
| `--output` | `./data` | Output directory for JSONL files |
| `--tiers` | `1` | Comma-separated tiers (1=single-turn, 2=multi-turn) |
| `--model` | `gpt-4o` | Teacher model for generation |
| `--n-prompts` | `3` | User prompts per invocation combo |
| `--api-key` | `$OPENAI_API_KEY` | OpenAI API key |

## Telemetry

The server exposes events at `GET /events`. Dashboard polls this endpoint.

For PostHog integration:

```python
from va_sdk import InMemoryCollector, PostHogTelemetry

collector = InMemoryCollector(delegate=PostHogTelemetry(api_key="phc_..."))
orchestrator = VoiceOrchestrator(toolkit, model, telemetry=collector)
```

Event types: `slm_call`, `tool_execute`, `slot_fill`, `error`, `turn_complete`,
`asr_transcribe`, `tts_synthesize`, `generate_start`, `generate_complete`.
