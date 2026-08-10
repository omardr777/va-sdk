from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Header, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="va-sdk Voice Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_pipeline = None
_collector = None
_toolkit = None
_config: dict = {}


def _load_toolkit():
    global _toolkit
    if _toolkit is not None:
        return _toolkit
    tool_path = os.environ.get("VA_SDK_TOOL_PATH")
    if not tool_path:
        raise RuntimeError("VA_SDK_TOOL_PATH not set")
    import importlib.util
    spec = importlib.util.spec_from_file_location("voice_tools", tool_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _toolkit = getattr(mod, "toolkit", None)
    if _toolkit is None:
        raise RuntimeError(f"No 'toolkit' variable found in {tool_path}")
    return _toolkit


def _build_pipeline():
    from va_sdk.orchestrator import VoiceOrchestrator
    from va_sdk.pipeline import VoicePipeline
    from va_sdk.telemetry import ConsoleTelemetry, InMemoryCollector

    global _collector, _config
    _collector = InMemoryCollector(delegate=ConsoleTelemetry())

    toolkit = _load_toolkit()

    backend = _config.get("backend", "openai")
    api_key = _config.get("api_key", os.environ.get("OPENAI_API_KEY", ""))
    model_name = _config.get("model", "gpt-4o")

    if backend == "openai":
        from va_sdk.models.openai_backend import OpenAIBackend
        model = OpenAIBackend(api_key=api_key, model=model_name)
    else:
        from va_sdk.models.mlx_backend import MLXBackend
        slm_port = int(os.environ.get("VA_SDK_SLM_PORT", "8002"))
        model = MLXBackend(base_url=f"http://localhost:{slm_port}/v1")

    orchestrator = VoiceOrchestrator(toolkit, model, telemetry=_collector)

    asr = None
    tts = None

    asr_backend = os.environ.get("VA_SDK_ASR_BACKEND", "whisper")
    if asr_backend == "whisper":
        try:
            from va_sdk.asr import WhisperASR
            asr = WhisperASR()
        except ImportError:
            pass

    tts_backend = os.environ.get("VA_SDK_TTS_BACKEND", "kokoro")
    if tts_backend == "kokoro":
        try:
            from va_sdk.tts import KokoroTTS
            tts = KokoroTTS()
        except ImportError:
            pass
    elif tts_backend == "mac-say":
        try:
            from va_sdk.tts import MacSayTTS
            tts = MacSayTTS()
        except ImportError:
            pass

    return VoicePipeline(orchestrator, asr=asr, tts=tts, telemetry=_collector)


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = _build_pipeline()
    return _pipeline


def _audio_suffix(filename: str | None, content_type: str | None) -> str:
    if filename:
        filename = filename.lower()
        if filename.endswith((".m4a", ".mp4")):
            return ".m4a"
        if filename.endswith(".ogg"):
            return ".ogg"
        if filename.endswith(".wav"):
            return ".wav"
    if content_type:
        if content_type in ("audio/mp4", "audio/m4a"):
            return ".m4a"
        if content_type == "audio/ogg":
            return ".ogg"
        if content_type == "audio/wav":
            return ".wav"
    return ".webm"


def _stream_event(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":")) + "\n"


# ---------------------------------------------------------------------------
# Startup — just load the toolkit (no model needed yet)
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup():
    _load_toolkit()
    print(f"✓ Toolkit loaded ({len(_toolkit.tools)} tools)")
    print("  Configure a model backend from the dashboard or POST /api/configure")
    print("  Dashboard: http://localhost:8766/dashboard")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Tools API
# ---------------------------------------------------------------------------

@app.get("/api/tools")
async def get_tools():
    toolkit = _load_toolkit()
    tools = []
    for t in toolkit.tools:
        tools.append({
            "name": t.name,
            "description": t.description,
            "category": t.category or "general",
            "params": [
                {
                    "name": p.name,
                    "type": p.type,
                    "required": p.required,
                    "enum": p.enum,
                    "description": p.description,
                    "prompt": p.prompt,
                }
                for p in t.params
            ],
        })
    return {"tools": tools, "count": len(tools)}


# ---------------------------------------------------------------------------
# Configure model backend
# ---------------------------------------------------------------------------

@app.post("/api/configure")
async def configure(request: Request):
    global _pipeline, _config
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    _config = {
        "backend": body.get("backend", "openai"),
        "api_key": body.get("api_key", ""),
        "model": body.get("model", "gpt-4o"),
    }

    try:
        _pipeline = _build_pipeline()
        return {"status": "ok", "backend": _config["backend"], "model": _config["model"]}
    except Exception as e:
        _pipeline = None
        return JSONResponse({"error": str(e)}, status_code=400)


# ---------------------------------------------------------------------------
# Events / telemetry
# ---------------------------------------------------------------------------

@app.get("/events")
async def get_events(limit: int = 50, type: str | None = None):
    if _collector is None:
        return {"events": []}
    event_types = type.split(",") if type else None
    events = _collector.recent(limit=limit, event_types=event_types)
    return {"events": events}


# ---------------------------------------------------------------------------
# Orchestrate (text → text)
# ---------------------------------------------------------------------------

@app.post("/orchestrate")
async def orchestrate(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    text = body.get("text", "")
    if not text:
        return JSONResponse({"error": "Missing 'text' field"}, status_code=400)

    auth_context = body.get("auth_context", {})
    try:
        pipeline = _get_pipeline()
    except Exception as e:
        return JSONResponse({"error": f"Model not configured: {e}"}, status_code=400)

    response = pipeline.orchestrator.process_utterance(text, auth_context)
    return {
        "response": response,
        "timings": pipeline.orchestrator.last_timings,
    }


# ---------------------------------------------------------------------------
# Voice endpoints
# ---------------------------------------------------------------------------

@app.post("/voice")
async def voice(audio: UploadFile, authorization: str | None = Header(default=None)):
    try:
        audio_data = await audio.read()
        if len(audio_data) < 1000:
            return JSONResponse({"error": "Audio too short"}, status_code=400)

        suffix = _audio_suffix(audio.filename, audio.content_type)
        auth_context = {}
        if authorization:
            auth_context["token"] = authorization.replace("Bearer ", "")

        pipeline = _get_pipeline()
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: pipeline.process(
                audio_data, auth_context=auth_context, audio_suffix=suffix,
            )),
            timeout=90,
        )

        resp = {"transcript": result.transcript, "response": result.response, "timings": result.timings}
        if result.audio_base64:
            resp["audio_base64"] = result.audio_base64
        return JSONResponse(resp)
    except asyncio.TimeoutError:
        return JSONResponse({"error": "Timed out"}, status_code=504)
    except ValueError as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=400)
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.post("/stream")
async def voice_stream(audio: UploadFile, authorization: str | None = Header(default=None)):
    async def event_stream():
        try:
            audio_data = await audio.read()
            if len(audio_data) < 1000:
                yield _stream_event({"type": "error", "error": "Audio too short"})
                return

            suffix = _audio_suffix(audio.filename, audio.content_type)
            auth_context = {}
            if authorization:
                auth_context["token"] = authorization.replace("Bearer ", "")

            pipeline = _get_pipeline()
            loop = asyncio.get_running_loop()
            yield _stream_event({"type": "stage", "stage": "transcribing"})

            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: pipeline.process(
                    audio_data, auth_context=auth_context, audio_suffix=suffix,
                )),
                timeout=90,
            )

            yield _stream_event({
                "type": "complete",
                "result": {
                    "transcript": result.transcript,
                    "response": result.response,
                    "audio_base64": result.audio_base64,
                    "timings": result.timings,
                },
            })
        except asyncio.TimeoutError:
            yield _stream_event({"type": "error", "error": "Timed out"})
        except Exception as exc:
            yield _stream_event({"type": "error", "error": str(exc)[:200]})

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Dataset generation
# ---------------------------------------------------------------------------

@app.post("/api/generate")
async def generate_dataset(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    tiers = body.get("tiers", [1])
    api_key = body.get("api_key", os.environ.get("OPENAI_API_KEY", ""))
    model = body.get("model", "gpt-4o")
    n_prompts = body.get("n_prompts", 3)
    output_dir = body.get("output_dir", "./data")

    if not api_key and any(t in tiers for t in (1, 2)):
        return JSONResponse({"error": "API key required for tiers 1-2. Provide api_key in request body."}, status_code=400)

    from va_sdk.dataset.generator import TeacherClient, generate_dataset
    from va_sdk.dataset.validator import validate_dataset
    from va_sdk.dataset.exporter import export_jsonl

    toolkit = _load_toolkit()
    teacher = TeacherClient(api_key=api_key, model=model)

    if _collector:
        from va_sdk.telemetry import event_generate_start
        _collector.emit(event_generate_start({"tiers": tiers, "model": model, "n_prompts": n_prompts}))

    import threading

    result_holder: dict = {}

    def _run():
        result = generate_dataset(toolkit, teacher, tiers=tiers, n_prompts_per_invocation=n_prompts)
        valid, rejected = validate_dataset(result.conversations, list(toolkit.tools))
        train_path, test_path, n_train, n_test = export_jsonl(valid, output_dir)
        result_holder["result"] = {
            "single_turn_prompts": result.stats.get("single_turn_prompts", 0),
            "multi_turn_conversations": result.stats.get("multi_turn_conversations", 0),
            "valid": len(valid),
            "rejected": rejected,
            "train_count": n_train,
            "test_count": n_test,
            "train_path": str(train_path),
            "test_path": str(test_path),
        }

    t = threading.Thread(target=_run)
    t.start()
    t.join()

    r = result_holder.get("result", {"error": "Generation failed"})

    if _collector:
        from va_sdk.telemetry import event_generate_complete
        _collector.emit(event_generate_complete(r))

    return r


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse


@app.get("/dashboard")
async def dashboard_redirect():
    return RedirectResponse(url="/dashboard/")


@app.get("/dashboard/")
async def dashboard_index():
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard", "index.html")
    if os.path.exists(dashboard_path):
        return HTMLResponse(open(dashboard_path).read())
    return HTMLResponse("<h1>Dashboard not bundled</h1>", status_code=404)


@app.get("/dashboard/{path:path}")
async def dashboard_static(path: str):
    file_path = os.path.join(os.path.dirname(__file__), "dashboard", path)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return JSONResponse({"error": "not found"}, status_code=404)
