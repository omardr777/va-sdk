# BankCo Voice Assistant — Example

Full working example of voice-enabling a banking backend with va-sdk.

## Architecture

```
banking/
├── backend/          # FastAPI + SQLite banking backend (port 8001)
├── tools.py          # Tool registry (symlinked from templates/banking/)
├── default_voice.wav # TTS reference voice for cloning
└── README.md
```

## Quickstart

```bash
# 1. Install dependencies
pip install va-sdk
pip install -r backend/requirements.txt

# 2. Start the full stack
va-sdk demo banking

# 3. Open dashboard
cd packages/frontend && npm run dev
```

## What it does

Start the banking backend on port 8001 and the voice pipeline on port 8766.
The banking backend auto-provisions 3 accounts (checking: $2,500, savings:
$8,000, credit: $0) and a demo user (`demo@bankco.io` / `demo1234`).

## Voice Operations

| Task | Example |
|------|---------|
| Check balance | "What's my checking balance?" |
| Transfer money | "Transfer $50 from checking to savings" |
| Cancel card | "Cancel my debit card ending in 8192" |
| Pay bill | "Pay $100 to Electric Company" |
| Report fraud | "I want to report fraud on my credit card" |
| List beneficiaries | "Who are my beneficiaries?" |
| Get statement | "Send me my savings statement" |
| Activate card | "Activate my card ending in 1234" |
| Replace card | "Replace my debit card 8192" |
| Reset PIN | "Reset my PIN for debit card 8192" |
