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


def _load_toolkit():
    tool_path = os.environ.get("VA_SDK_TOOL_PATH")
    if not tool_path:
        raise RuntimeError("VA_SDK_TOOL_PATH not set")

    import importlib.util

    spec = importlib.util.spec_from_file_location("voice_tools", tool_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    toolkit = getattr(mod, "toolkit", None)
    if toolkit is None:
        raise RuntimeError(f"No 'toolkit' variable found in {tool_path}")
    return toolkit


def _build_pipeline():
    from va_sdk.asr import WhisperASR
    from va_sdk.orchestrator import VoiceOrchestrator
    from va_sdk.pipeline import VoicePipeline
    from va_sdk.telemetry import ConsoleTelemetry, InMemoryCollector
    from va_sdk.tts import KokoroTTS

    global _collector
    _collector = InMemoryCollector(delegate=ConsoleTelemetry())

    toolkit = _load_toolkit()

    backend = os.environ.get("VA_SDK_MODEL_BACKEND", "mlx")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model_name = os.environ.get("VA_SDK_MODEL_NAME", "")

    if backend == "openai":
        from va_sdk.models.openai_backend import OpenAIBackend
        model = OpenAIBackend(
            api_key=api_key,
            model=model_name or "gpt-4o",
        )
    else:
        from va_sdk.models.mlx_backend import MLXBackend
        slm_port = int(os.environ.get("VA_SDK_SLM_PORT", "8002"))
        model = MLXBackend(base_url=f"http://localhost:{slm_port}/v1")

    orchestrator = VoiceOrchestrator(toolkit, model, telemetry=_collector)

    asr_backend = os.environ.get("VA_SDK_ASR_BACKEND", "whisper")
    tts_backend = os.environ.get("VA_SDK_TTS_BACKEND", "kokoro")

    asr = None
    tts = None

    if asr_backend == "whisper":
        asr = WhisperASR()

    if tts_backend == "kokoro":
        tts = KokoroTTS()
    elif tts_backend == "mac-say":
        from va_sdk.tts import MacSayTTS
        tts = MacSayTTS()

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


@app.on_event("startup")
def startup():
    pipeline = _get_pipeline()

    import numpy as np

    if pipeline.asr is not None:
        pipeline.asr.transcribe(np.zeros(1600, dtype=np.float32), 16000)
    if pipeline.tts is not None:
        pipeline.tts.synthesize("Ready.")

    print("✓ Voice pipeline ready")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/dashboard")
async def dashboard_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard/")


@app.get("/dashboard/")
async def dashboard_index():
    from fastapi.responses import HTMLResponse
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard", "index.html")
    if os.path.exists(dashboard_path):
        return HTMLResponse(open(dashboard_path).read())
    return HTMLResponse("<h1>Dashboard not bundled. Run from source: cd packages/frontend && npm run dev</h1>", status_code=404)


@app.get("/dashboard/{path:path}")
async def dashboard_static(path: str):
    from fastapi.responses import FileResponse

    file_path = os.path.join(os.path.dirname(__file__), "dashboard", path)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return JSONResponse({"error": "not found"}, status_code=404)


@app.get("/events")
async def get_events(limit: int = 50, type: str | None = None):
    if _collector is None:
        return {"events": []}

    event_types = type.split(",") if type else None
    events = _collector.recent(limit=limit, event_types=event_types)
    return {"events": events}


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
    pipeline = _get_pipeline()
    response = pipeline.orchestrator.process_utterance(text, auth_context)

    return {
        "response": response,
        "timings": pipeline.orchestrator.last_timings,
    }


@app.post("/voice")
async def voice(
    audio: UploadFile,
    authorization: str | None = Header(default=None),
):
    try:
        audio_data = await audio.read()

        if len(audio_data) < 1000:
            return JSONResponse({"error": "Audio upload was empty or too short."}, status_code=400)

        suffix = _audio_suffix(audio.filename, audio.content_type)

        auth_context = {}
        if authorization:
            auth_context["token"] = authorization.replace("Bearer ", "")

        pipeline = _get_pipeline()
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: pipeline.process(
                    audio_data,
                    auth_context=auth_context,
                    audio_suffix=suffix,
                ),
            ),
            timeout=90,
        )

        resp = {
            "transcript": result.transcript,
            "response": result.response,
            "timings": result.timings,
        }
        if result.audio_base64:
            resp["audio_base64"] = result.audio_base64

        return JSONResponse(resp)
    except asyncio.TimeoutError:
        return JSONResponse({"error": "Voice processing timed out."}, status_code=504)
    except ValueError as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=400)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.post("/stream")
async def voice_stream(
    audio: UploadFile,
    authorization: str | None = Header(default=None),
):
    async def event_stream():
        try:
            audio_data = await audio.read()
            if len(audio_data) < 1000:
                yield _stream_event({"type": "error", "error": "Audio upload was empty or too short."})
                return

            suffix = _audio_suffix(audio.filename, audio.content_type)

            auth_context = {}
            if authorization:
                auth_context["token"] = authorization.replace("Bearer ", "")

            pipeline = _get_pipeline()
            loop = asyncio.get_running_loop()

            yield _stream_event({"type": "stage", "stage": "transcribing"})

            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: pipeline.process(
                        audio_data,
                        auth_context=auth_context,
                        audio_suffix=suffix,
                    ),
                ),
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
            yield _stream_event({"type": "error", "error": "Voice processing timed out."})
        except Exception as exc:
            yield _stream_event({"type": "error", "error": str(exc)[:200]})

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
