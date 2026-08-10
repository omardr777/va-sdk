# va-sdk — Voice Assistant SDK

Toolkit for SaaS developers to voice-enable their APIs using Small Language
Models (SLMs).

> **Status:** Alpha. Phase 1 implementation in progress.

## Quickstart (Phase 1 — coming soon)

```bash
pip install va-sdk

# Write your tools
cat > voice_tools.py <<'EOF'
from va_sdk import Tool, Param, Toolkit, ToolError

tools = [
    Tool(
        name="check_balance",
        description="Check the balance of a bank account.",
        params=[
            Param("account_type", type="string",
                  enum=["checking", "savings", "credit"],
                  description="Type of account", prompt="which account"),
        ],
        call=lambda api, account_type: api.get(f"/accounts?type={account_type}"),
        map_result=lambda data, args: {"balance": data[0]["balance"]},
        success_template="Your {account_type} balance is ${balance:.2f}.",
        error_template="Couldn't check {account_type}: {error_message}.",
    ),
]

toolkit = Toolkit(
    tools=tools,
    api_factory=lambda auth: BankAPI(auth["token"]),
)
EOF

# Start the voice server
va-sdk serve --tools voice_tools.py
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture
overview and [docs/ADR/](docs/adr/) for architected decisions.

## Project Structure

```
va-sdk/
├── packages/
│   ├── sdk/          # Python SDK (pip install va-sdk)
│   ├── frontend/     # React dashboard (Dataset Studio + Voice Playground)
│   └── react-widget/ # @va-sdk/react VoiceAssistant FAB component
├── templates/        # Shipped domain starter packs
│   └── banking/      # Banking seed conversations + tool definitions
└── docs/
    ├── CONTEXT.md
    ├── ARCHITECTURE.md
    └── adr/
```
