from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_MLX_SLM_PORT = 8002
DEFAULT_SERVER_PORT = 8766
DEFAULT_BACKEND_PORT = 8001
DEFAULT_ASR_BACKEND = "whisper"
DEFAULT_TTS_BACKEND = "kokoro"


def serve(args: list[str]) -> None:
    """Start the reference FastAPI voice pipeline server."""
    import uvicorn

    port = DEFAULT_SERVER_PORT
    tool_path = None
    asr_backend = DEFAULT_ASR_BACKEND
    tts_backend = DEFAULT_TTS_BACKEND

    i = 0
    while i < len(args):
        if args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        elif args[i] == "--tools" and i + 1 < len(args):
            tool_path = args[i + 1]
            i += 2
        elif args[i] == "--asr-backend" and i + 1 < len(args):
            asr_backend = args[i + 1]
            i += 2
        elif args[i] == "--tts-backend" and i + 1 < len(args):
            tts_backend = args[i + 1]
            i += 2
        else:
            i += 1

    if tool_path is None:
        print("Error: --tools <path> is required")
        print("Usage: va-sdk serve --tools ./voice_tools.py [--port 8766] [--slm-port 8002] "
              "[--asr-backend whisper] [--tts-backend kokoro|mac-say]")
        sys.exit(1)

    tool_path = os.path.abspath(tool_path)
    os.environ["VA_SDK_TOOL_PATH"] = tool_path
    os.environ["VA_SDK_ASR_BACKEND"] = asr_backend
    os.environ["VA_SDK_TTS_BACKEND"] = tts_backend

    slm_port = DEFAULT_MLX_SLM_PORT
    i = 0
    while i < len(args):
        if args[i] == "--slm-port" and i + 1 < len(args):
            slm_port = int(args[i + 1])
            break
        i += 1
    os.environ["VA_SDK_SLM_PORT"] = str(slm_port)

    uvicorn.run(
        "va_sdk.server:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


def generate(args: list[str]) -> None:
    """Run the dataset generation pipeline."""
    tool_path = None
    output_dir = "./data"
    tiers: list[int] = [1]
    api_key: str | None = None
    model: str = "gpt-4o"
    n_prompts: int = 3

    i = 0
    while i < len(args):
        if args[i] == "--tools" and i + 1 < len(args):
            tool_path = args[i + 1]; i += 2
        elif args[i] == "--output" and i + 1 < len(args):
            output_dir = args[i + 1]; i += 2
        elif args[i] == "--tiers" and i + 1 < len(args):
            tiers = [int(t) for t in args[i + 1].split(",")]; i += 2
        elif args[i] == "--api-key" and i + 1 < len(args):
            api_key = args[i + 1]; i += 2
        elif args[i] == "--model" and i + 1 < len(args):
            model = args[i + 1]; i += 2
        elif args[i] == "--n-prompts" and i + 1 < len(args):
            n_prompts = int(args[i + 1]); i += 2
        else:
            i += 1

    if tool_path is None:
        print("Error: --tools <path> is required")
        print("Usage: va-sdk generate --tools ./voice_tools.py "
              "[--output ./data] [--tiers 1,2] [--model gpt-4o] "
              "[--n-prompts 3] [--api-key $OPENAI_API_KEY]")
        sys.exit(1)

    tool_path = os.path.abspath(tool_path)
    api_key = api_key or os.environ.get("OPENAI_API_KEY")

    if api_key is None and any(t in tiers for t in (1, 2)):
        print("Error: OPENAI_API_KEY is required for tiers 1-3 generation.")
        print("Set it via --api-key or the OPENAI_API_KEY environment variable.")
        sys.exit(1)

    import importlib.util
    spec = importlib.util.spec_from_file_location("voice_tools", tool_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    toolkit = getattr(mod, "toolkit", None)
    if toolkit is None:
        print(f"Error: no 'toolkit' variable found in {tool_path}")
        sys.exit(1)

    from va_sdk.dataset.generator import TeacherClient, generate_dataset
    from va_sdk.dataset.validator import validate_dataset
    from va_sdk.dataset.exporter import export_jsonl

    print(f"Generating dataset from {len(toolkit.tools)} tools...")
    print(f"  Tiers: {tiers}")
    print(f"  Model: {model}")
    print()

    teacher = TeacherClient(api_key=api_key, model=model)
    result = generate_dataset(
        toolkit,
        teacher,
        tiers=tiers,
        n_prompts_per_invocation=n_prompts,
    )

    print(f"  Single-turn prompts:   {result.stats.get('single_turn_prompts', 0)}")
    print(f"  Multi-turn convos:     {result.stats.get('multi_turn_conversations', 0)}")

    valid, rejected = validate_dataset(result.conversations, list(toolkit.tools))
    print(f"  Validation: {len(valid)} valid, {rejected} rejected")

    train_path, test_path, n_train, n_test = export_jsonl(valid, output_dir)
    print(f"  Exported: {n_train} train → {train_path}")
    print(f"            {n_test} test  → {test_path}")
    print()
    print("Done.")


def validate(args: list[str]) -> None:
    """Validate a tool registry file."""
    tool_path = None

    i = 0
    while i < len(args):
        if args[i] == "--tools" and i + 1 < len(args):
            tool_path = args[i + 1]
            i += 2
        else:
            i += 1

    if tool_path is None:
        print("Error: --tools <path> is required")
        print("Usage: va-sdk validate --tools ./voice_tools.py")
        sys.exit(1)

    tool_path = os.path.abspath(tool_path)
    spec = importlib.util.spec_from_file_location("voice_tools", tool_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    toolkit = getattr(mod, "toolkit", None)
    if toolkit is None:
        print(f"Error: no 'toolkit' variable found in {tool_path}")
        sys.exit(1)

    errors: list[str] = []
    for tool in toolkit.tools:
        if not tool.description or len(tool.description) < 20:
            errors.append(f"  {tool.name}: description too short (<20 chars)")
        if not tool.success_template:
            errors.append(f"  {tool.name}: missing success_template")
        for p in tool.params:
            if not p.description:
                errors.append(f"  {tool.name}.{p.name}: missing description")
            if p.required and not p.prompt:
                errors.append(f"  {tool.name}.{p.name}: required but no prompt")

    if errors:
        print(f"Found {len(errors)} issue(s):")
        for e in errors:
            print(e)
        sys.exit(1)

    print(f"✓ Validated {len(toolkit.tools)} tool(s) — all good.")


def demo(args: list[str]) -> None:
    """Start the full example stack (backend + voice server)."""
    import threading

    example = "banking" if not args else args[0]
    repo_root = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent.parent

    backend_path = repo_root / "examples" / example / "backend"
    if not backend_path.exists():
        print(f"Error: example '{example}' not found at {backend_path}")
        sys.exit(1)

    tools_path = repo_root / "examples" / example / "tools.py"
    if not tools_path.exists():
        print(f"Error: tools.py not found at {tools_path}")
        sys.exit(1)

    backend_port = DEFAULT_BACKEND_PORT
    slm_port = DEFAULT_MLX_SLM_PORT
    voice_port = DEFAULT_SERVER_PORT

    print(f"=== va-sdk demo: {example} ===")
    print(f"  Backend:    http://localhost:{backend_port}")
    print(f"  Voice API:  http://localhost:{voice_port}")
    print(f"  Dashboard:  cd packages/frontend && npm run dev")
    print()

    os.environ["VA_SDK_TOOL_PATH"] = str(tools_path.resolve())
    os.environ["VA_SDK_SLM_PORT"] = str(slm_port)
    os.environ["VA_SDK_ASR_BACKEND"] = DEFAULT_ASR_BACKEND
    os.environ["VA_SDK_TTS_BACKEND"] = DEFAULT_TTS_BACKEND

    def _start_backend():
        import uvicorn

        sys.path.insert(0, str(backend_path.resolve()))
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=backend_port,
            reload=False,
            log_level="warning",
        )

    backend_thread = threading.Thread(target=_start_backend, daemon=True)
    backend_thread.start()

    import time

    time.sleep(2)
    print("  Backend started.")

    # Seed a demo user
    try:
        import httpx

        resp = httpx.post(
            f"http://localhost:{backend_port}/auth/register",
            json={"email": "demo@bankco.io", "password": "demo1234"},
        )
        if resp.status_code == 201 or (
            resp.status_code == 400 and "already" in resp.text.lower()
        ):
            print("  Demo user ready (demo@bankco.io / demo1234)")
    except Exception:
        print("  (demo user seed skipped — backend may not be ready)")

    print("  Starting voice server...")
    print()

    import uvicorn

    uvicorn.run(
        "va_sdk.server:app",
        host="0.0.0.0",
        port=voice_port,
        reload=False,
    )


COMMANDS = {
    "serve": serve,
    "generate": generate,
    "validate": validate,
    "demo": demo,
}


def main() -> None:
    # Ensure va_sdk is importable when running from the repo
    sdk_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    if sdk_path not in sys.path:
        sys.path.insert(0, sdk_path)

    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Usage: va-sdk <command> [options]")
        print()
        print("Commands:")
        print("  serve      Start the reference voice pipeline server")
        print("  generate   Generate fine-tuning dataset from tool registry")
        print("  validate   Validate a tool registry file")
        sys.exit(1)

    command = sys.argv[1]
    COMMANDS[command](sys.argv[2:])


if __name__ == "__main__":
    main()
