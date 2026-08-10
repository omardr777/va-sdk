from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class TelemetryEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp_ms: float = field(default_factory=lambda: time.time() * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "data": self.data,
            "timestamp_ms": self.timestamp_ms,
        }


class TelemetryBackend(Protocol):
    def emit(self, event: TelemetryEvent) -> None: ...


class NoopTelemetry:
    def emit(self, event: TelemetryEvent) -> None:
        pass


class ConsoleTelemetry:
    def emit(self, event: TelemetryEvent) -> None:
        print(f"[telemetry] {event.type}: {json.dumps(event.data)}")


class PostHogTelemetry:
    def __init__(self, api_key: str, host: str = "https://us.i.posthog.com"):
        try:
            import posthog
            self.client = posthog
            self.client.api_key = api_key
            self.client.host = host
            self._available = True
        except ImportError:
            self._available = False

    def emit(self, event: TelemetryEvent) -> None:
        if not self._available:
            return
        try:
            distinct_id = event.data.get("session_id", "anonymous")
            props = {k: v for k, v in event.data.items() if k != "session_id"}
            self.client.capture(distinct_id, event.type, properties=props)
        except Exception:
            pass


class InMemoryCollector:
    def __init__(self, max_events: int = 500, delegate: TelemetryBackend | None = None):
        self._events: deque[TelemetryEvent] = deque(maxlen=max_events)
        self._delegate = delegate

    def emit(self, event: TelemetryEvent) -> None:
        self._events.append(event)
        if self._delegate is not None:
            self._delegate.emit(event)

    def recent(self, limit: int = 50, event_types: list[str] | None = None) -> list[dict[str, Any]]:
        events = list(self._events)
        if event_types:
            events = [e for e in events if e.type in event_types]
        return [e.to_dict() for e in events[-limit:]]

    def clear(self) -> None:
        self._events.clear()


# ---------------------------------------------------------------------------
# Event factory helpers for the orchestrator / pipeline
# ---------------------------------------------------------------------------

def event_slm_call(tool_name: str, arguments: dict, latency_ms: float, model: str = "") -> TelemetryEvent:
    return TelemetryEvent(type="slm_call", data={
        "tool_name": tool_name,
        "arguments": arguments,
        "latency_ms": latency_ms,
        "model": model,
    })

def event_tool_execute(tool_name: str, arguments: dict, result: dict, latency_ms: float, success: bool) -> TelemetryEvent:
    return TelemetryEvent(type="tool_execute", data={
        "tool_name": tool_name,
        "arguments": arguments,
        "result": result,
        "latency_ms": latency_ms,
        "success": success,
    })

def event_slot_fill(tool_name: str, missing_args: list[str], prompt: str) -> TelemetryEvent:
    return TelemetryEvent(type="slot_fill", data={
        "tool_name": tool_name,
        "missing_args": missing_args,
        "elicitation_prompt": prompt,
    })

def event_error(tool_name: str, error_message: str, error_kind: str) -> TelemetryEvent:
    return TelemetryEvent(type="error", data={
        "tool_name": tool_name,
        "error_message": error_message,
        "error_kind": error_kind,
    })

def event_turn_complete(transcript: str, response: str | None, timings: dict) -> TelemetryEvent:
    return TelemetryEvent(type="turn_complete", data={
        "transcript": transcript,
        "response": response,
        "timings": timings,
    })

def event_asr(transcript: str, latency_ms: float) -> TelemetryEvent:
    return TelemetryEvent(type="asr_transcribe", data={
        "transcript": transcript,
        "latency_ms": latency_ms,
    })

def event_tts(text: str, latency_ms: float) -> TelemetryEvent:
    return TelemetryEvent(type="tts_synthesize", data={
        "text_preview": text[:100],
        "latency_ms": latency_ms,
    })

def event_generate_start(config: dict) -> TelemetryEvent:
    return TelemetryEvent(type="generate_start", data=config)

def event_generate_complete(stats: dict) -> TelemetryEvent:
    return TelemetryEvent(type="generate_complete", data=stats)
