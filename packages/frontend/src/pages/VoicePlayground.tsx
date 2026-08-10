import { useState, useEffect, useRef } from "react";

interface ToolInfo {
  name: string;
  description: string;
  category: string;
  params: { name: string; type: string; required: boolean; enum: string[] | null }[];
}

interface LogEntry {
  type: "user" | "assistant" | "tool" | "error" | "stage";
  text: string;
  timestamp: number;
}

const DEFAULT_SERVER = window.location.origin || "http://127.0.0.1:8766";

export default function VoicePlayground() {
  const [serverUrl, setServerUrl] = useState(DEFAULT_SERVER);
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [apiKey, setApiKey] = useState("");
  const [backend, setBackend] = useState("openai");
  const [model, setModel] = useState("gpt-4o");
  const [connectionStatus, setConnectionStatus] = useState<"idle" | "connecting" | "ok" | "error">("idle");
  const [statusMsg, setStatusMsg] = useState("");
  const [log, setLog] = useState<LogEntry[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const seenTimestamps = useRef<Set<number>>(new Set());

  const fetchTools = async () => {
    try {
      const res = await fetch(`${serverUrl}/api/tools`);
      if (res.ok) {
        const data = await res.json();
        setTools(data.tools || []);
      }
    } catch { /* server not ready yet */ }
  };

  const configureBackend = async () => {
    setConnectionStatus("connecting");
    try {
      const res = await fetch(`${serverUrl}/api/configure`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ backend, api_key: apiKey, model }),
      });
      const data = await res.json();
      if (res.ok) {
        setConnectionStatus("ok");
        setStatusMsg(`Connected: ${data.backend} / ${data.model}`);
        fetchTools();
      } else {
        setConnectionStatus("error");
        setStatusMsg(data.error || "Configuration failed");
      }
    } catch (err) {
      setConnectionStatus("error");
      setStatusMsg(err instanceof Error ? err.message : "Connection failed");
    }
  };

  useEffect(() => {
    fetchTools();
  }, [serverUrl]);

  useEffect(() => {
    if (connectionStatus !== "ok") return;
    const poll = async () => {
      try {
        const res = await fetch(`${serverUrl}/events?limit=20&type=turn_complete,error,slm_call,tool_execute,slot_fill`);
        if (!res.ok) return;
        const data = await res.json();
        for (const evt of data.events || []) {
          const ts = evt.timestamp_ms;
          if (seenTimestamps.current.has(ts)) continue;
          seenTimestamps.current.add(ts);
          const d = evt.data || {};
          if (evt.type === "turn_complete") {
            if (d.transcript) setLog((p) => [...p, { type: "user", text: d.transcript, timestamp: ts }]);
            if (d.response) setLog((p) => [...p, { type: "assistant", text: d.response, timestamp: ts }]);
            if (d.timings) {
              const timingStr = Object.entries(d.timings).map(([k, v]) => `${k}: ${(v as number).toFixed(0)}ms`).join(" | ");
              setLog((p) => [...p, { type: "stage", text: `Timings: ${timingStr}`, timestamp: ts }]);
            }
          } else if (evt.type === "error") {
            setLog((p) => [...p, { type: "error", text: `${d.tool_name}: ${d.error_message}`, timestamp: ts }]);
          } else if (evt.type === "slm_call") {
            setLog((p) => [...p, { type: "tool", text: `SLM → ${d.tool_name}(${JSON.stringify(d.arguments)}) [${d.latency_ms?.toFixed(0)}ms]`, timestamp: ts }]);
          } else if (evt.type === "tool_execute") {
            setLog((p) => [...p, { type: "tool", text: `${d.success ? "✓" : "✗"} API ${d.tool_name} [${d.latency_ms?.toFixed(0)}ms]`, timestamp: ts }]);
          } else if (evt.type === "slot_fill") {
            setLog((p) => [...p, { type: "stage", text: `Slot: ${(d.missing_args || []).join(", ")} → "${d.elicitation_prompt}"`, timestamp: ts }]);
          }
        }
      } catch { /* poll error */ }
    };
    poll();
    pollRef.current = setInterval(poll, 1500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [connectionStatus, serverUrl]);

  const bubbleStyle = (type: string) => {
    switch (type) {
      case "user": return "justify-end bg-indigo-600 text-white rounded-br-sm";
      case "assistant": return "justify-start bg-gray-100 text-gray-800 rounded-bl-sm";
      case "tool": return "justify-center bg-purple-50 text-purple-700 text-xs font-mono";
      case "error": return "justify-center bg-red-50 text-red-600 text-xs";
      case "stage": return "justify-center bg-amber-50 text-amber-600 text-xs";
      default: return "";
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Voice Playground</h1>

      <div className="grid grid-cols-2 gap-6 mb-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
          <h2 className="text-lg font-semibold text-slate-800">Model Backend</h2>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">Backend</span>
            <select value={backend} onChange={(e) => setBackend(e.target.value)} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm">
              <option value="openai">OpenAI</option>
              <option value="mlx">MLX (local Apple Silicon)</option>
            </select>
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">Model</span>
            <input type="text" value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-4o" className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">API Key</span>
            <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono" />
          </label>

          <button onClick={configureBackend} disabled={connectionStatus === "connecting"} className="w-full py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50">
            {connectionStatus === "connecting" ? "Connecting..." : "Connect"}
          </button>

          {statusMsg && (
            <div className={`text-sm px-3 py-2 rounded-lg ${connectionStatus === "ok" ? "bg-emerald-50 text-emerald-700" : connectionStatus === "error" ? "bg-red-50 text-red-700" : ""}`}>
              {statusMsg}
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-slate-800 mb-3">Conversation Log</h2>
          <div className="bg-slate-50 rounded-lg p-3 min-h-[300px] max-h-[400px] overflow-y-auto space-y-2">
            {log.length === 0 ? (
              <p className="text-center text-slate-400 text-sm pt-10">Configure a backend and use the mic to start.</p>
            ) : (
              log.map((entry, i) => (
                <div key={i} className="flex">
                  <div className={`max-w-[90%] rounded-xl px-3 py-1.5 text-sm ${bubbleStyle(entry.type)}`}>
                    {entry.text}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">Tool Catalog ({tools.length} tools)</h2>
        {tools.length === 0 ? (
          <p className="text-slate-400 text-sm">Connect a backend to load tools.</p>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            {tools.map((tool) => (
              <div key={tool.name} className="border border-gray-100 rounded-lg p-4 hover:border-indigo-200 transition-colors">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700">{tool.category}</span>
                </div>
                <h3 className="text-sm font-semibold text-indigo-700 font-mono">{tool.name}</h3>
                <p className="text-xs text-slate-500 mt-1 line-clamp-2">{tool.description}</p>
                {tool.params.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {tool.params.map((p) => (
                      <span key={p.name} className={`text-[10px] px-1.5 py-0.5 rounded-full ${p.required ? "bg-amber-50 text-amber-700" : "bg-gray-50 text-gray-500"}`}>
                        {p.name}{p.required ? "*" : ""}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
