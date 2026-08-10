from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class ASRBackend(Protocol):
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str: ...


# ---------------------------------------------------------------------------
# Qwen3-ASR-0.6B (PyTorch — production primary)
# ---------------------------------------------------------------------------

class Qwen3ASR:
    def __init__(self, model_path: str = "models/Qwen3-ASR-0.6B", device: str = "auto"):
        import torch
        from qwen_asr import Qwen3ASRModel

        self.model = Qwen3ASRModel.from_pretrained(
            model_path,
            dtype=torch.bfloat16,
            device_map=device,
        )

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        results = self.model.transcribe(audio=(audio, sample_rate))
        return results[0].text


# ---------------------------------------------------------------------------
# MLX Qwen3-ASR (Apple Silicon — production for Mac)
# ---------------------------------------------------------------------------

class MLXQwenASR:
    def __init__(self, base_url: str = "http://127.0.0.1:8007", timeout: float = 30.0):
        import httpx
        import soundfile as sf

        self.http = httpx.Client(base_url=base_url, timeout=timeout)
        self._sf = sf

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        import io

        buf = io.BytesIO()
        self._sf.write(buf, audio, sample_rate, format="WAV", subtype="PCM_16")
        response = self.http.post(
            "/v1/audio/transcriptions",
            files={"audio": ("audio.wav", buf.getvalue(), "audio/wav")},
        )
        response.raise_for_status()
        return response.json()["text"]


# ---------------------------------------------------------------------------
# Whisper (fallback — no GPU needed)
# ---------------------------------------------------------------------------

class WhisperASR:
    def __init__(self, model_size: str = "tiny.en", device: str = "cpu"):
        import whisper

        self.model = whisper.load_model(model_size)

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if audio.ndim > 1:
            audio = np.mean(audio.astype(np.float32), axis=1)
        result = self.model.transcribe(audio, language="en", fp16=False)
        return result["text"].strip()


# ---------------------------------------------------------------------------
# Dummy (no ASR installed)
# ---------------------------------------------------------------------------

class DummyASR:
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        return ""
