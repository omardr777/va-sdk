from __future__ import annotations

import os
import subprocess
import tempfile
import wave
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class TTSBackend(Protocol):
    def synthesize(self, text: str) -> tuple[np.ndarray, int]: ...


class KokoroTTS:
    def __init__(self, voice: str = "af_heart", device: str = "auto"):
        from kokoro import KPipeline

        if device == "auto":
            import torch

            device = "mps" if torch.backends.mps.is_available() else "cpu"

        self.pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M", device=device)
        self.voice = voice
        self.sample_rate = 24000

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        chunks = []
        for result in self.pipeline(text, voice=self.voice):
            audio = result.audio
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            chunks.append(np.asarray(audio, dtype=np.float32))

        if not chunks:
            return np.zeros(0, dtype=np.float32), self.sample_rate

        return np.concatenate(chunks), self.sample_rate


class MacSayTTS:
    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        aiff_path = None
        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp:
                aiff_path = tmp.name
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = tmp.name

            subprocess.run(
                ["say", "-o", aiff_path, text],
                check=True,
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ["afconvert", "-f", "WAVE", "-d", "LEI16", aiff_path, wav_path],
                check=True,
                capture_output=True,
                timeout=10,
            )

            with wave.open(wav_path, "rb") as audio_file:
                channels = audio_file.getnchannels()
                sample_width = audio_file.getsampwidth()
                sample_rate = audio_file.getframerate()
                frames = audio_file.readframes(audio_file.getnframes())

            if sample_width != 2:
                raise ValueError(f"Unsupported sample width: {sample_width}")

            samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
            if channels > 1:
                samples = samples.reshape(-1, channels).mean(axis=1)

            return samples, sample_rate
        finally:
            for path in (aiff_path, wav_path):
                if path:
                    try:
                        os.unlink(path)
                    except FileNotFoundError:
                        pass


class DummyTTS:
    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        return np.zeros(0, dtype=np.float32), 24000
