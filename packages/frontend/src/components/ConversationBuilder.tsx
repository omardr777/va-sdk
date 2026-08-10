import { useState, useRef, useCallback } from "react";

const DEFAULT_SERVER = window.location.origin || "http://127.0.0.1:8766";

interface ToolInfo {
  name: string;
  description: string;
  params: { name: string; type: string; required: boolean; enum: string[] | null }[];
}

interface Turn {
  userText: string;
  functionName: string;
  arguments: Record<string, unknown>;
}

interface Props {
  tools: ToolInfo[];
  apiKey: string;
  model: string;
  onSave: (conversation: { messages: unknown[] }) => void;
  editingConversation?: Turn[] | null;
}

const RECORDING_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];

export default function ConversationBuilder({ tools, apiKey, model, onSave, editingConversation }: Props) {
  const [turns, setTurns] = useState<Turn[]>(editingConversation || []);
  const [recording, setRecording] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [selectedTool, setSelectedTool] = useState(tools[0]?.name || "");
  const [params, setParams] = useState<Record<string, string>>({});
  const [extracting, setExtracting] = useState(false);
  const [status, setStatus] = useState("");
  const mrRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const selectedToolInfo = tools.find((t) => t.name === selectedTool);

  const toggleRecording = useCallback(async () => {
    if (recording) {
      mrRef.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = RECORDING_TYPES.find((t) => MediaRecorder.isTypeSupported(t)) || "audio/webm";
      chunksRef.current = [];
      const mr = new MediaRecorder(stream, { mimeType });
      mrRef.current = mr;
      setRecording(true);
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        const blob = new Blob(chunksRef.current, { type: mimeType });
        const form = new FormData();
        form.append("audio", blob, "recording.webm");
        setStatus("Transcribing...");
        try {
          const res = await fetch(`${DEFAULT_SERVER}/api/seed/transcribe`, { method: "POST", body: form });
          const data = await res.json();
          setTranscript(data.transcript || data.error || "");
          setStatus(data.transcript ? "Transcribed." : `Error: ${data.error}`);
        } catch { setStatus("Transcription failed."); }
      };
      mr.start(250);
    } catch { setStatus("Mic access denied."); }
  }, [recording]);

  const extractParams = async () => {
    if (!transcript || !selectedTool) return;
    setExtracting(true);
    setStatus("Extracting params...");
    try {
      const res = await fetch(`${DEFAULT_SERVER}/api/seed/extract`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript, tool_name: selectedTool }),
      });
      const data = await res.json();
      if (data.arguments) {
        const p: Record<string, string> = {};
        for (const [k, v] of Object.entries(data.arguments)) p[k] = String(v ?? "");
        setParams(p);
        setStatus("Params extracted. Review and add turn.");
      } else { setStatus(`Error: ${data.error}`); }
    } catch { setStatus("Extraction failed."); }
    finally { setExtracting(false); }
  };

  const addTurn = () => {
    if (!transcript && !selectedTool) return;
    const cleanArgs: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(params)) {
      if (v === "" || v === "null" || v === "undefined") continue;
      const p = selectedToolInfo?.params.find((pp) => pp.name === k);
      cleanArgs[k] = p?.type === "number" ? parseFloat(v) : v;
    }
    setTurns((prev) => [...prev, { userText: transcript, functionName: selectedTool, arguments: cleanArgs }]);
    setTranscript("");
    setParams({});
    setStatus("");
  };

  const removeTurn = (i: number) => setTurns((prev) => prev.filter((_, idx) => idx !== i));

  const saveConversation = () => {
    const messages: unknown[] = [];
    for (const turn of turns) {
      messages.push({ role: "user", content: turn.userText });
      messages.push({
        role: "assistant",
        tool_calls: [{
          id: `call_${messages.length}`, type: "function",
          function: { name: turn.functionName, arguments: JSON.stringify(turn.arguments) },
        }],
      });
    }
    onSave({ messages });
    setTurns([]);
    setStatus("Saved.");
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button onClick={toggleRecording}
          className={`w-12 h-12 rounded-full flex items-center justify-center shadow-lg transition-all ${recording ? "bg-red-500 scale-110" : "bg-indigo-600 hover:bg-indigo-700"}`}>
          {recording ? <span className="w-3 h-3 bg-white rounded-full animate-ping" /> : <span className="text-white text-lg">🎤</span>}
        </button>
        <div className="flex-1">
          <textarea value={transcript} onChange={(e) => setTranscript(e.target.value)}
            placeholder="Speak or type the user's utterance..."
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm resize-none h-16" />
        </div>
      </div>

      {status && <div className="text-xs text-slate-500">{status}</div>}

      <div className="flex gap-3 items-end">
        <label className="flex-1">
          <span className="text-xs text-slate-500">Tool</span>
          <select value={selectedTool} onChange={(e) => { setSelectedTool(e.target.value); setParams({}); }}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm">
            {tools.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}
          </select>
        </label>
        <button onClick={extractParams} disabled={!transcript || extracting}
          className="px-4 py-2 rounded-lg bg-purple-600 text-white text-xs font-semibold hover:bg-purple-700 disabled:opacity-50">
          {extracting ? "Extracting..." : "Extract params"}
        </button>
      </div>

      {selectedToolInfo && selectedToolInfo.params.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {selectedToolInfo.params.map((p) => (
            <label key={p.name} className="block">
              <span className="text-[10px] text-slate-500">{p.name}{p.required ? "*" : ""}</span>
              {p.enum ? (
                <select value={params[p.name] || ""} onChange={(e) => setParams((pr) => ({ ...pr, [p.name]: e.target.value }))}
                  className="w-full rounded-lg border border-gray-200 px-2 py-1 text-xs">
                  <option value="">—</option>
                  {p.enum.map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              ) : (
                <input type={p.type === "number" ? "number" : "text"} value={params[p.name] || ""}
                  onChange={(e) => setParams((pr) => ({ ...pr, [p.name]: e.target.value }))}
                  className="w-full rounded-lg border border-gray-200 px-2 py-1 text-xs" />
              )}
            </label>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <button onClick={addTurn} disabled={!transcript}
          className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50">
          + Add turn
        </button>
        <button onClick={saveConversation} disabled={turns.length === 0}
          className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 disabled:opacity-50">
          Save conversation
        </button>
      </div>

      {turns.length > 0 && (
        <div className="bg-slate-50 rounded-lg p-3 space-y-2 max-h-64 overflow-y-auto">
          {turns.map((turn, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <span className="text-slate-400 mt-1 w-4">{i + 1}.</span>
              <div className="flex-1 bg-white rounded px-2 py-1 border">
                <span className="text-slate-600">{turn.userText || "(empty)"}</span>
                <span className="ml-2 text-purple-600 font-mono">{turn.functionName}</span>
                {Object.keys(turn.arguments).length > 0 && (
                  <span className="ml-1 text-amber-600">{JSON.stringify(turn.arguments)}</span>
                )}
              </div>
              <button onClick={() => removeTurn(i)} className="text-red-400 hover:text-red-600 shrink-0">✕</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
