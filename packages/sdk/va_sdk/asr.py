from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class ASRBackend(Protocol):
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str: ...


class WhisperASR:
    def __init__(self, model_size: str = "tiny.en", device: str = "cpu"):
        import whisper

        self.model = whisper.load_model(model_size)
        self._device = device

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if audio.ndim == 1:
            audio = audio.astype(np.float32)
        else:
            audio = np.mean(audio.astype(np.float32), axis=1)

        result = self.model.transcribe(audio, language="en", fp16=False)
        return result["text"].strip()


class DummyASR:
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        return ""
