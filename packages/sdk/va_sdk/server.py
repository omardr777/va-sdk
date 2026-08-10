from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
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
_storage: Any = None


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
    elif backend in ("local", "mlx"):
        from va_sdk.models.local_backend import LocalBackend
        port = _config.get("port", os.environ.get("VA_SDK_MODEL_PORT", "8080"))
        model = LocalBackend(base_url=f"http://localhost:{port}/v1", model=model_name or "local")
    else:
        from va_sdk.models.mlx_backend import MLXBackend
        slm_port = int(os.environ.get("VA_SDK_SLM_PORT", "8002"))
        model = MLXBackend(base_url=f"http://localhost:{slm_port}/v1")

    orchestrator = VoiceOrchestrator(toolkit, model, telemetry=_collector)

    asr = None
    tts = None

    asr_backend = os.environ.get("VA_SDK_ASR_BACKEND", "qwen-mlx")
    if asr_backend == "whisper":
        try:
            from va_sdk.asr import WhisperASR
            asr = WhisperASR()
        except ImportError:
            pass
    elif asr_backend == "qwen":
        try:
            from va_sdk.asr import Qwen3ASR
            asr = Qwen3ASR()
        except ImportError:
            pass
    elif asr_backend == "qwen-mlx":
        try:
            from va_sdk.asr import MLXQwenASR
            asr = MLXQwenASR()
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
    global _storage
    from va_sdk.dataset.store import DatasetStore
    _load_toolkit()
    _storage = DatasetStore()
    print(f"✓ Toolkit loaded ({len(_toolkit.tools)} tools)")
    print(f"✓ Seed store ready ({_storage.count} conversations)")
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
# Training
# ---------------------------------------------------------------------------

_training_jobs: dict[str, dict] = {}


@app.post("/api/train")
async def start_training(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    modal_token = body.get("modal_token", "")
    model_name = body.get("model", "Qwen/Qwen2.5-0.5B-Instruct")
    train_path = body.get("train_path", "./data/train.jsonl")
    test_path = body.get("test_path", "./data/test.jsonl")

    if not modal_token:
        return JSONResponse({"error": "modal_token is required"}, status_code=400)

    import uuid
    job_id = str(uuid.uuid4())[:8]

    _training_jobs[job_id] = {
        "id": job_id,
        "status": "submitted",
        "model": model_name,
        "train_path": train_path,
        "test_path": test_path,
        "created_at": __import__("time").time(),
        "output_path": f"./models/va-sdk-{job_id}",
    }

    def _run():
        try:
            _training_jobs[job_id]["status"] = "running"
            from va_sdk.dataset.modal_train import ModalTrainer
            trainer = ModalTrainer(token=modal_token)
            result = trainer.train(train_path, test_path, model=model_name)
            _training_jobs[job_id]["status"] = "done"
            _training_jobs[job_id]["result"] = result
            if _collector:
                from va_sdk.telemetry import event_generate_complete
                _collector.emit(event_generate_complete({
                    "type": "training_complete",
                    "job_id": job_id,
                    "output_path": _training_jobs[job_id]["output_path"],
                }))
        except Exception as e:
            _training_jobs[job_id]["status"] = "failed"
            _training_jobs[job_id]["error"] = str(e)

    import threading
    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return {"job_id": job_id, "status": "submitted"}


@app.get("/api/train/{job_id}")
async def get_training_status(job_id: str):
    job = _training_jobs.get(job_id)
    if job is None:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return job


# ---------------------------------------------------------------------------
# Seeds (manual dataset creation)
# ---------------------------------------------------------------------------

@app.get("/api/seeds")
async def get_seeds(tool: str | None = None, source: str | None = None):
    if _storage is None:
        return {"conversations": [], "count": 0}
    convos = _storage.list(tool=tool, source=source)
    return {"conversations": convos, "count": len(convos)}


@app.post("/api/seeds")
async def add_seed(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    messages = body.get("messages", [])
    if not messages:
        return JSONResponse({"error": "messages required"}, status_code=400)

    tools = _load_toolkit().to_openai_tools()
    conv = {
        "messages": messages,
        "tools": tools,
        "source": body.get("source", "manual"),
        "tool": body.get("tool", ""),
    }

    from va_sdk.dataset.validator import validate_conversation
    errors = validate_conversation(conv, list(_load_toolkit().tools))
    if errors:
        return JSONResponse({"error": f"Validation failed: {errors[0]}", "errors": errors}, status_code=400)

    saved = _storage.add(conv)
    return {"id": saved["id"], "status": "saved"}


@app.put("/api/seeds/{seed_id}")
async def update_seed(seed_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    messages = body.get("messages", [])
    if not messages:
        return JSONResponse({"error": "messages required"}, status_code=400)

    tools = _load_toolkit().to_openai_tools()
    conv = {
        "messages": messages,
        "tools": tools,
        "source": body.get("source", "manual"),
        "tool": body.get("tool", ""),
    }

    ok = _storage.update(seed_id, conv)
    if not ok:
        return JSONResponse({"error": "Seed not found"}, status_code=404)
    return {"status": "updated"}


@app.delete("/api/seeds/{seed_id}")
async def delete_seed(seed_id: str):
    ok = _storage.delete(seed_id)
    if not ok:
        return JSONResponse({"error": "Seed not found"}, status_code=404)
    return {"status": "deleted"}


@app.post("/api/seed/transcribe")
async def seed_transcribe(audio: UploadFile):
    try:
        audio_data = await audio.read()
        if len(audio_data) < 1000:
            return JSONResponse({"error": "Audio too short"}, status_code=400)
    except Exception:
        return JSONResponse({"error": "Invalid audio"}, status_code=400)

    suffix = _audio_suffix(audio.filename, audio.content_type)

    import subprocess, tempfile
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_data)
        input_path = tmp.name

    wav_path = input_path + ".wav"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-ar", "16000", "-ac", "1", "-f", "s16le", "-",
        ], capture_output=True, check=True, stdout=subprocess.PIPE)
        pcm_data = subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-ar", "16000", "-ac", "1", "-f", "s16le", "-",
        ], capture_output=True, check=True).stdout
    except Exception:
        return JSONResponse({"error": "Audio decode failed. ffmpeg required."}, status_code=400)
    finally:
        try:
            os.unlink(input_path)
        except OSError:
            pass
        try:
            os.unlink(wav_path)
        except OSError:
            pass

    try:
        audio_np = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0

        asr_backend = os.environ.get("VA_SDK_ASR_BACKEND", "qwen-mlx")
        transcript = ""

        if asr_backend == "qwen-mlx":
            try:
                from va_sdk.asr import MLXQwenASR
                asr = MLXQwenASR()
                transcript = asr.transcribe(audio_np, 16000)
            except ImportError:
                return JSONResponse({"error": "MLXQwenASR not available. Install qwen_asr or use --asr-backend whisper"}, status_code=400)
        elif asr_backend == "qwen":
            try:
                from va_sdk.asr import Qwen3ASR
                asr = Qwen3ASR()
                transcript = asr.transcribe(audio_np, 16000)
            except ImportError:
                return JSONResponse({"error": "Qwen3ASR not available. Install qwen_asr"}, status_code=400)
        else:
            try:
                from va_sdk.asr import WhisperASR
                asr = WhisperASR()
                transcript = asr.transcribe(audio_np, 16000)
            except ImportError:
                return JSONResponse({"error": "No ASR backend available. Install openai-whisper"}, status_code=400)

        return {"transcript": transcript}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/seed/extract")
async def seed_extract(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    transcript = body.get("transcript", "")
    tool_name = body.get("tool_name", "")
    if not transcript or not tool_name:
        return JSONResponse({"error": "transcript and tool_name required"}, status_code=400)

    toolkit = _load_toolkit()
    tool = toolkit.get(tool_name)
    if tool is None:
        return JSONResponse({"error": f"Unknown tool: {tool_name}"}, status_code=400)

    api_key = _config.get("api_key", os.environ.get("OPENAI_API_KEY", ""))
    model = _config.get("model", "gpt-4o")

    try:
        from va_sdk.dataset.extractor import extract_params
        params = extract_params(transcript, tool_name, tool.to_openai_tool(), api_key=api_key, model=model)
        return {"arguments": params}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/seed/ai-assist")
async def seed_ai_assist(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    description = body.get("description", "")
    turns = body.get("turns", 4)
    include_asr_noise = body.get("include_asr_noise", True)
    prompt_template = body.get("prompt", None)

    if not description:
        return JSONResponse({"error": "description required"}, status_code=400)

    api_key = _config.get("api_key", os.environ.get("OPENAI_API_KEY", ""))
    model = _config.get("model", "gpt-4o")
    toolkit = _load_toolkit()
    tools = toolkit.to_openai_tools()

    try:
        from va_sdk.dataset.extractor import generate_conversation_draft
        conv = generate_conversation_draft(
            tools=tools,
            description=description,
            turns=turns,
            include_asr_noise=include_asr_noise,
            prompt_template=prompt_template,
            api_key=api_key,
            model=model,
        )
        return {"conversation": conv}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/seeds/export")
async def export_seeds(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    output_dir = body.get("output_dir", "./data")
    train_split = body.get("train_split", 0.8)

    result = _storage.export(output_dir, train_split=train_split)
    return result


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
