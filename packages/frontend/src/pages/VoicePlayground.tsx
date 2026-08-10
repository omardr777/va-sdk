import { useState, useEffect, useRef } from "react";

interface ToolInfo {
  name: string;
  description: string;
  params: { name: string; type: string; required: boolean }[];
}

const SAMPLE_TOOLS: ToolInfo[] = [
  { name: "check_balance", description: "Check account balance", params: [{ name: "account_type", type: "string", required: true }] },
  { name: "transfer_money", description: "Transfer between accounts", params: [{ name: "amount", type: "number", required: true }, { name: "from_account", type: "string", required: true }, { name: "to_account", type: "string", required: true }] },
  { name: "cancel_card", description: "Cancel a card", params: [{ name: "card_type", type: "string", required: true }, { name: "card_last_four", type: "string", required: true }] },
];

const DEFAULT_BACKEND = "http://127.0.0.1:8766";

interface LogEntry {
  type: "user" | "assistant" | "tool" | "error" | "stage";
  text: string;
  timestamp: number;
}

export default function VoicePlayground() {
  const [backendUrl, setBackendUrl] = useState(DEFAULT_BACKEND);
  const [token, setToken] = useState("");
  const [connectionStatus, setConnectionStatus] = useState<"idle" | "testing" | "ok" | "error">("idle");
  const [statusMsg, setStatusMsg] = useState("");
  const [log, setLog] = useState<LogEntry[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const seenTimestamps = useRef<Set<number>>(new Set());

  const testConnection = async () => {
    setConnectionStatus("testing");
    try {
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${backendUrl}/health`, { headers });
      if (res.ok) {
        setConnectionStatus("ok");
        setStatusMsg("Connected. Use the mic button.");
      } else {
        setConnectionStatus("error");
        setStatusMsg(`Server returned ${res.status}`);
      }
    } catch (err) {
      setConnectionStatus("error");
      setStatusMsg(err instanceof Error ? err.message : "Connection failed");
    }
  };

  useEffect(() => {
    if (connectionStatus !== "ok" && connectionStatus !== "testing") return;

    const poll = async () => {
      try {
        const res = await fetch(`${backendUrl}/events?limit=20&type=turn_complete,error,slm_call,tool_execute,slot_fill`);
        if (!res.ok) return;
        const data = await res.json();
        const events = data.events || [];

        for (const evt of events) {
          const ts = evt.timestamp_ms;
          if (seenTimestamps.current.has(ts)) continue;
          seenTimestamps.current.add(ts);

          const d = evt.data || {};
          if (evt.type === "turn_complete") {
            if (d.transcript) {
              setLog((prev) => [...prev, { type: "user", text: d.transcript, timestamp: ts }]);
            }
            if (d.response) {
              setLog((prev) => [...prev, { type: "assistant", text: d.response, timestamp: ts }]);
            }
            if (d.timings) {
              const timingStr = Object.entries(d.timings as Record<string, number>)
                .map(([k, v]) => `${k.replace(/_ms$/, "")}: ${v.toFixed(0)}ms`)
                .join(" | ");
              setLog((prev) => [...prev, { type: "stage", text: `Timings: ${timingStr}`, timestamp: ts }]);
            }
          } else if (evt.type === "error") {
            setLog((prev) => [...prev, {
              type: "error",
              text: `${d.tool_name || "tools"}: ${d.error_message}`,
              timestamp: ts,
            }]);
          } else if (evt.type === "slm_call") {
            setLog((prev) => [...prev, {
              type: "tool",
              text: `SLM → ${d.tool_name}(${JSON.stringify(d.arguments)}) [${d.latency_ms?.toFixed(0)}ms]`,
              timestamp: ts,
            }]);
          } else if (evt.type === "tool_execute") {
            const icon = d.success ? "✓" : "✗";
            setLog((prev) => [...prev, {
              type: "tool",
              text: `${icon} API ${d.tool_name} [${d.latency_ms?.toFixed(0)}ms]`,
              timestamp: ts,
            }]);
          } else if (evt.type === "slot_fill") {
            setLog((prev) => [...prev, {
              type: "stage",
              text: `Slot fill: missing ${(d.missing_args || []).join(", ")} → "${d.elicitation_prompt}"`,
              timestamp: ts,
            }]);
          }
        }
      } catch {
        // ignore poll errors
      }
    };

    poll();
    pollRef.current = setInterval(poll, 1500);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [connectionStatus, backendUrl]);

  const threadStyle = (entry: LogEntry) => {
    switch (entry.type) {
      case "user": return "justify-end";
      case "assistant": return "justify-start";
      case "tool": return "justify-center";
      case "error": return "justify-center";
      case "stage": return "justify-center";
    }
  };

  const bubbleStyle = (entry: LogEntry) => {
    switch (entry.type) {
      case "user": return "bg-indigo-600 text-white rounded-br-sm";
      case "assistant": return "bg-gray-100 text-gray-800 rounded-bl-sm";
      case "tool": return "bg-purple-50 text-purple-700 text-xs font-mono";
      case "error": return "bg-red-50 text-red-600 text-xs";
      case "stage": return "bg-amber-50 text-amber-600 text-xs";
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Voice Playground</h1>

      <div className="grid grid-cols-2 gap-6 mb-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
          <h2 className="text-lg font-semibold text-slate-800">Backend Connection</h2>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">Voice Server URL</span>
            <input type="text" value={backendUrl}
              onChange={(e) => setBackendUrl(e.target.value)}
              placeholder="http://127.0.0.1:8766"
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">Auth Token (optional)</span>
            <input type="password" value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="JWT token or API key"
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </label>

          <button onClick={testConnection} disabled={connectionStatus === "testing"}
            className="w-full py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors">
            {connectionStatus === "testing" ? "Testing..." : "Test Connection"}
          </button>

          {statusMsg && (
            <div className={`text-sm px-3 py-2 rounded-lg ${
              connectionStatus === "ok" ? "bg-emerald-50 text-emerald-700" :
              connectionStatus === "error" ? "bg-red-50 text-red-700" : ""
            }`}>
              {statusMsg}
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-slate-800 mb-3">Conversation Log</h2>
          <div className="bg-slate-50 rounded-lg p-3 min-h-[300px] max-h-[400px] overflow-y-auto space-y-2">
            {log.length === 0 ? (
              <p className="text-center text-slate-400 text-sm pt-10">
                Connect and use the mic button to see live events.
              </p>
            ) : (
              log.map((entry, i) => (
                <div key={i} className={`flex ${threadStyle(entry)}`}>
                  <div className={`max-w-[90%] rounded-xl px-3 py-1.5 text-sm ${bubbleStyle(entry)}`}>
                    {entry.text}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">Tool Catalog</h2>
        <div className="grid grid-cols-3 gap-4">
          {SAMPLE_TOOLS.map((tool) => (
            <div key={tool.name} className="border border-gray-100 rounded-lg p-4 hover:border-indigo-200 transition-colors">
              <h3 className="text-sm font-semibold text-indigo-700 font-mono">{tool.name}</h3>
              <p className="text-xs text-slate-500 mt-1">{tool.description}</p>
              {tool.params.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {tool.params.map((p) => (
                    <span key={p.name} className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                      p.required ? "bg-amber-50 text-amber-700" : "bg-gray-50 text-gray-500"
                    }`}>
                      {p.name}
                      {p.required ? "*" : ""}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
