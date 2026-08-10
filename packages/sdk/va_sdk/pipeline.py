from __future__ import annotations

import base64
import io
import os
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from va_sdk.asr import ASRBackend, WhisperASR
from va_sdk.orchestrator import VoiceOrchestrator
from va_sdk.tts import KokoroTTS, TTSBackend


@dataclass
class PipelineResult:
    transcript: str
    response: str | None
    audio_base64: str | None = None
    sample_rate: int = 24000
    timings: dict[str, float] = field(default_factory=dict)


class SessionStore(Protocol):
    def load(self, session_id: str) -> dict | None: ...
    def save(self, session_id: str, data: dict) -> None: ...
    def delete(self, session_id: str) -> None: ...


class InMemoryStore:
    def __init__(self):
        self._store: dict[str, dict] = {}

    def load(self, session_id: str) -> dict | None:
        return self._store.get(session_id)

    def save(self, session_id: str, data: dict) -> None:
        self._store[session_id] = data

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)


class VoicePipeline:
    def __init__(
        self,
        orchestrator: VoiceOrchestrator,
        *,
        asr: ASRBackend | None = None,
        tts: TTSBackend | None = None,
        session_store: SessionStore | None = None,
    ):
        self.orchestrator = orchestrator
        self.asr = asr
        self.tts = tts
        self.sessions = session_store or InMemoryStore()

    def process(
        self,
        audio_bytes: bytes,
        *,
        session_id: str = "default",
        auth_context: dict | None = None,
        audio_suffix: str = ".webm",
    ) -> PipelineResult:
        started = time.perf_counter()
        timings: dict[str, float] = {}

        pcm_data = self._decode_audio(audio_bytes, audio_suffix)
        decoded_at = time.perf_counter()
        timings["decode_ms"] = (decoded_at - started) * 1000

        transcript = ""
        if self.asr is not None:
            audio_np = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
            transcript = self.asr.transcribe(audio_np, 16000)

        asr_at = time.perf_counter()
        timings["asr_ms"] = (asr_at - decoded_at) * 1000

        if not transcript.strip():
            return PipelineResult(
                transcript="",
                response="I didn't catch that.",
                timings=timings,
            )

        response = self.orchestrator.process_utterance(transcript, auth_context or {})
        orch_at = time.perf_counter()
        timings["orchestrator_ms"] = (orch_at - asr_at) * 1000
        timings.update(self.orchestrator.last_timings)

        audio_base64 = None
        sample_rate = 24000

        if response and self.tts is not None:
            tts_audio, tts_sr = self.tts.synthesize(response)
            sample_rate = tts_sr

            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(tts_sr)
                wf.writeframes(
                    (np.asarray(tts_audio, dtype=np.float32) * 32767)
                    .astype(np.int16)
                    .tobytes()
                )
            audio_base64 = base64.b64encode(buf.getvalue()).decode()

        tts_at = time.perf_counter()
        timings["tts_ms"] = (tts_at - orch_at) * 1000
        timings["total_ms"] = (tts_at - started) * 1000

        return PipelineResult(
            transcript=transcript,
            response=response,
            audio_base64=audio_base64,
            sample_rate=sample_rate,
            timings=timings,
        )

    @staticmethod
    def _decode_audio(audio_data: bytes, suffix: str) -> bytes:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_data)
                tmp_path = tmp.name

            result = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner", "-loglevel", "error",
                    "-y", "-i", tmp_path,
                    "-f", "s16le", "-acodec", "pcm_s16le",
                    "-ar", "16000", "-ac", "1", "-",
                ],
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0 or not result.stdout:
                detail = result.stderr.decode("utf-8", errors="replace").strip()
                detail = f": {detail[:200]}" if detail else ""
                raise ValueError(f"Audio decode failed{detail}")
            return result.stdout
        except OSError as exc:
            raise ValueError(f"ffmpeg is unavailable: {exc}") from exc
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except FileNotFoundError:
                    pass
