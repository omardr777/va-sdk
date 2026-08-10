# va-sdk — Domain Context

## What is va-sdk?

**va-sdk** is a toolkit for SaaS developers to voice-enable their APIs using
Small Language Models (SLMs). It provides three tools:

1. **SDK** — Register backend tools, run a deterministic orchestrator, serve a
   voice pipeline (ASR → SLM → Tool Execution → TTS).
2. **Dataset Generator** — Auto-synthesize fine-tuning data from tool
   registries. Expand seed conversations. Validate and export.
3. **Frontend Dashboard** — Test tools in a voice playground. Manage datasets
   visually. Embed a voice widget into any web app.

## Core Principles

### 1. SLM as classifier, not generator

The SLM outputs only structured JSON tool-calls. It never generates
user-facing text. All customer responses come from deterministic templates in
the orchestrator. This is what makes a 0.6B model viable — the SLM is a
router, not a conversationalist.

### 2. Tool Registration, not decorator coupling

Voice tools are declared as first-class entities in a registry. They are
separate from backend API implementations. One voice intent can call multiple
REST endpoints. Meta tools (greeting, goodbye) have no backend at all. The
registry is the single source of truth for the voice layer.

### 3. Deterministic orchestration

Slot filling, alias handling, error recovery, and response generation are
all deterministic. The orchestrator never delegates these to the SLM. This
gives predictable latency, brand-consistent responses, and no hallucination
in customer-facing text.

### 4. Gradient of investment

Developers can run one command and get a trainable dataset from their tool
registry alone. Want better quality? Run slot-filling auto-synthesis. Want
production quality? Start from a shipped domain template and customize. Need
exact domain coverage? Write custom seeds. One pipeline, escalating
investment.

## Use Cases

| Use Case | Example |
|----------|---------|
| Banking | "Transfer $50 from checking to savings" |
| E-commerce | "Track my order #1234" |
| Healthcare | "Book an appointment with Dr. Smith" |
| SaaS general | "Change my plan to pro" |

## Target Audience

SaaS developers who want to add voice capabilities to their product without:
- Sending customer data to cloud LLMs
- Paying per-token costs at scale
- Latency that breaks natural conversation flow (<500ms round-trip)

## Inspirations

This project generalizes the architecture and lessons from **VoiceTeller**,
a low-latency banking voice assistant built by Distil Labs. VoiceTeller
demonstrated that a 0.6B fine-tuned SLM with deterministic orchestration can
achieve 90.9% tool-call accuracy, exceeding a 120B teacher model (87.5%),
with ~40ms inference latency.

### Key references

- OpenAI Function Calling Guide & Fine-Tuning Cookbook
- Anthropic Tool Use Guide and "Writing Effective Tools for Agents"
- MCP (Model Context Protocol) Tools specification
- Vapi and LiveKit Agents (voice agent platforms)

## Glossary

| Term | Definition |
|------|------------|
| SLM | Small Language Model (0.6B–1.5B parameters). Runs locally. |
| Tool | A declared capability: name, description, params, execution callback. |
| Orchestrator | Deterministic runtime: slot filling, tool dispatch, template rendering. |
| Voice Pipeline | Full audio-in → audio-out: ASR → Orchestrator → TTS. |
| Teacher Model | Large model (GPT-4o / Claude) used to generate synthetic training data. |
| Seed | A hand-written example conversation used to bootstrap dataset generation. |
| Slot Filling | The orchestrator asks follow-up questions when required params are missing. |
| Template | Deterministic format string for success/error responses. |
