import { useState, useRef, useCallback } from "react";

type Status = "idle" | "listening" | "processing" | "speaking";

interface VoiceAssistantProps {
  voiceEndpoint?: string;
  authToken?: string | null;
  onTranscript?: (text: string) => void;
  onResponse?: (text: string) => void;
  onStatusChange?: (status: Status) => void;
  onError?: (error: string) => void;
  position?: "bottom-right" | "bottom-left" | "top-right" | "top-left";
}

const DEFAULT_ENDPOINT = "http://127.0.0.1:8766";
const RECORDING_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
const REQUEST_TIMEOUT = 100_000;

const STAGE_LABELS: Record<string, string> = {
  transcribing: "Transcribing...",
  thinking: "Understanding...",
  synthesizing: "Speaking...",
};

type Message = { type: "user" | "assistant"; text: string };

const POSITIONS: Record<string, string> = {
  "bottom-right": "bottom-6 right-6 items-end",
  "bottom-left": "bottom-6 left-6 items-start",
  "top-right": "top-6 right-6 items-end",
  "top-left": "top-6 left-6 items-start",
};

export default function VoiceAssistant({
  voiceEndpoint = DEFAULT_ENDPOINT,
  authToken,
  onTranscript,
  onResponse,
  onStatusChange,
  onError,
  position = "bottom-right",
}: VoiceAssistantProps) {
  const [status, setStatus] = useState<Status>("idle");
  const [messages, setMessages] = useState<Message[]>([]);
  const [partial, setPartial] = useState("");
  const mrRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const setStatusAndNotify = useCallback(
    (s: Status) => {
      setStatus(s);
      onStatusChange?.(s);
    },
    [onStatusChange]
  );

  const toggleRecording = useCallback(async () => {
    if (status === "idle") {
      try {
        if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
          throw new Error("Microphone not supported in this browser.");
        }
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mimeType = RECORDING_TYPES.find((t) => MediaRecorder.isTypeSupported(t));
        if (!mimeType) {
          stream.getTracks().forEach((t) => t.stop());
          throw new Error("No supported audio format.");
        }
        chunksRef.current = [];
        const mr = new MediaRecorder(stream, { mimeType });
        mrRef.current = mr;
        setStatusAndNotify("listening");
        setPartial("Listening...");

        mr.ondataavailable = (e) => {
          if (e.data.size > 0) chunksRef.current.push(e.data);
        };
        mr.onerror = () => {
          stream.getTracks().forEach((t) => t.stop());
          setStatusAndNotify("idle");
          setPartial("Recording failed.");
          onError?.("Recording failed.");
        };
        mr.onstop = async () => {
          stream.getTracks().forEach((t) => t.stop());
          mrRef.current = null;
          const chunks = chunksRef.current;
          chunksRef.current = [];
          if (chunks.length === 0) {
            setStatusAndNotify("idle");
            setPartial("No audio recorded.");
            return;
          }
          setStatusAndNotify("processing");
          setPartial("Processing...");
          const blob = new Blob(chunks, { type: mimeType });
          const ext = mimeType.startsWith("audio/mp4") ? "m4a" : "webm";
          const form = new FormData();
          form.append("audio", blob, `recording.${ext}`);

          let tid: number | undefined;
          try {
            const ctrl = new AbortController();
            tid = window.setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT);
            const headers: Record<string, string> = {};
            if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
            const res = await fetch(`${voiceEndpoint}/stream`, {
              method: "POST", body: form, signal: ctrl.signal, headers,
            });
            if (!res.ok) {
              const err = await res.json().catch(() => ({}));
              throw new Error(err.error || `Server returned ${res.status}`);
            }
            if (!res.body) throw new Error("Empty response stream.");

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buf = "";
            let resultData: { transcript?: string; response?: string; audio_base64?: string } | undefined;
            while (true) {
              const { value, done } = await reader.read();
              buf += decoder.decode(value || new Uint8Array(), { stream: !done });
              const lines = buf.split("\n");
              buf = lines.pop() || "";
              for (const line of lines) {
                if (!line.trim()) continue;
                const evt = JSON.parse(line);
                if (evt.type === "error") throw new Error(evt.error || "Request failed.");
                if (evt.type === "stage" && evt.stage)
                  setPartial(STAGE_LABELS[evt.stage] || evt.stage);
                if (evt.type === "complete") resultData = evt.result;
              }
              if (done) break;
            }
            if (buf.trim()) {
              const evt = JSON.parse(buf);
              if (evt.type === "complete") resultData = evt.result;
            }
            window.clearTimeout(tid);

            const data = resultData;
            if (!data) throw new Error("No response from server.");
            const transcript = data.transcript || "";
            const response = data.response || "";
            if (transcript) {
              setMessages((p: Message[]) => [...p, { type: "user", text: transcript }]);
              onTranscript?.(transcript);
            }
            if (response) {
              setMessages((p: Message[]) => [...p, { type: "assistant", text: response }]);
              onResponse?.(response);
            }
            if (data.audio_base64) {
              setStatusAndNotify("speaking");
              const binary = atob(data.audio_base64);
              const bytes = new Uint8Array(binary.length);
              for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
              const audioBlob = new Blob([bytes], { type: "audio/wav" });
              const url = URL.createObjectURL(audioBlob);
              if (audioRef.current) audioRef.current.pause();
              const audio = new Audio(url);
              audioRef.current = audio;
              audio.onended = () => { URL.revokeObjectURL(url); setStatusAndNotify("idle"); };
              await audio.play();
            } else {
              setStatusAndNotify("idle");
              setPartial("");
            }
          } catch (err) {
            if (tid !== undefined) window.clearTimeout(tid);
            const msg = err instanceof DOMException && err.name === "AbortError"
              ? "Request timed out."
              : err instanceof Error ? err.message : "Voice request failed.";
            setMessages((p: Message[]) => [...p, { type: "assistant", text: msg }]);
            setStatusAndNotify("idle");
            setPartial("");
            onError?.(msg);
          }
        };
        mr.start(250);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Could not access microphone.";
        setMessages((p) => [...p, { type: "assistant", text: msg }]);
        setStatusAndNotify("idle");
        setPartial("");
        onError?.(msg);
      }
    } else if (status === "listening") {
      mrRef.current?.stop();
    }
  }, [status, voiceEndpoint, authToken, onTranscript, onResponse, onError, setStatusAndNotify]);

  const isOpen = status !== "idle" || messages.length > 0;

  return (
    <div className={`fixed z-50 flex flex-col gap-3 ${POSITIONS[position] || POSITIONS["bottom-right"]}`}>
      {isOpen && (
        <div className="w-80 max-h-96 overflow-y-auto rounded-2xl bg-white shadow-2xl border border-gray-200 flex flex-col">
          <div className="px-4 py-3 border-b border-gray-100 bg-indigo-50 rounded-t-2xl flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${status === "idle" ? "bg-indigo-400" : status === "speaking" ? "bg-emerald-500 animate-pulse" : "bg-amber-500 animate-pulse"}`} />
              <span className="text-sm font-semibold text-indigo-700">Voice Assistant</span>
            </div>
            <button onClick={() => { setMessages([]); setStatusAndNotify("idle"); setPartial(""); }} className="text-xs text-gray-400 hover:text-gray-600">Clear</button>
          </div>
          <div className="flex-1 px-4 py-3 space-y-3 min-h-[120px] max-h-64 overflow-y-auto">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.type === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${m.type === "user" ? "bg-indigo-600 text-white rounded-br-sm" : "bg-gray-100 text-gray-800 rounded-bl-sm"}`}>{m.text}</div>
              </div>
            ))}
            {partial && (
              <div className="flex justify-start">
                <div className="bg-gray-50 text-gray-500 text-sm px-3 py-2 rounded-xl flex items-center gap-2">
                  <span className="flex gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "-0.2s" }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "-0.1s" }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce" />
                  </span>
                  <span>{partial}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
      <button
        onClick={toggleRecording}
        disabled={status === "processing"}
        className={`w-16 h-16 rounded-full flex items-center justify-center shadow-2xl transition-all duration-300 hover:scale-110 active:scale-95 ${
          status === "idle" ? "bg-indigo-600 hover:bg-indigo-700" :
          status === "listening" ? "bg-red-500 scale-110" :
          status === "processing" ? "bg-amber-500" :
          "bg-green-500 animate-pulse"
        }`}
        aria-label={status === "listening" ? "Stop recording" : "Start recording"}
      >
        {status === "listening" ? (
          <div className="flex items-end gap-[2px] h-6">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="w-[3px] bg-white rounded-full animate-pulse" style={{ height: `${6 + Math.random() * 14}px` }} />
            ))}
          </div>
        ) : (
          <svg className="w-7 h-7 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            {status === "idle" && <><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></>}
            {status === "processing" && <><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></>}
            {status === "speaking" && <><path d="M2 12h2"/><path d="M6 8v8"/><path d="M10 5v14"/><path d="M14 8v8"/><path d="M18 12h2"/><path d="M20 8v8"/></>}
          </svg>
        )}
      </button>
    </div>
  );
}
