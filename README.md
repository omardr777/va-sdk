# va-sdk — Voice Assistant SDK

**Agentic-first.** Tell an AI agent to voice-enable your API and it handles
everything — tool registration, dataset generation, training, and serving.

## Agentic Quickstart

```
User: "Voice-enable my banking API at http://localhost:8001"

Agent:
  1. Reads your OpenAPI spec (or source code)
  2. Generates voice_tools.py with proper Tool definitions
  3. Validates: va-sdk validate --tools voice_tools.py
  4. Generates training data: va-sdk generate --tools voice_tools.py
  5. Serves: va-sdk serve --tools voice_tools.py
  6. Opens the dashboard to test live
```

The agent uses the [voice-enable skill](.opencode/skills/voice-enable/SKILL.md).

## Manual Quickstart

```bash
pip install va-sdk

# Start the voice server with banking template
va-sdk serve --tools templates/banking/tools.py

# Test via text
curl -X POST http://localhost:8766/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"text": "check my checking balance", "auth_context": {"token": "demo"}}'
```

## CLI Commands

```bash
va-sdk serve --tools voice_tools.py    # Start voice pipeline server
va-sdk generate --tools voice_tools.py # Generate fine-tuning dataset
va-sdk validate --tools voice_tools.py # Validate tool registry
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture
overview and [docs/adr/](docs/adr/) for architecture decisions.

## Project Structure

```
va-sdk/
├── .opencode/skills/      # Agent skill — tells AI how to voice-enable APIs
├── packages/
│   ├── sdk/               # pip install va-sdk
│   ├── frontend/          # React dashboard
│   └── react-widget/      # @va-sdk/react FAB component
├── templates/banking/     # Shipped banking seed templates
└── docs/
    ├── CONTEXT.md
    ├── ARCHITECTURE.md
    └── adr/
```
