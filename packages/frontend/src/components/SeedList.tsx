import { useState, useEffect } from "react";

const DEFAULT_SERVER = window.location.origin || "http://127.0.0.1:8766";

interface ToolInfo {
  name: string;
  params: { name: string; type: string; required: boolean; enum: string[] | null }[];
}

interface Seed {
  id: string;
  source: string;
  tool: string;
  messages: { role: string; content?: string; tool_calls?: unknown[] }[];
}

interface Props {
  tools: ToolInfo[];
  onEdit: (seed: Seed) => void;
}

export default function SeedList({ tools, onEdit }: Props) {
  const [seeds, setSeeds] = useState<Seed[]>([]);
  const [filterTool, setFilterTool] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [loading, setLoading] = useState(true);

  const fetchSeeds = async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (filterTool) params.set("tool", filterTool);
    if (filterSource) params.set("source", filterSource);
    try {
      const res = await fetch(`${DEFAULT_SERVER}/api/seeds?${params}`);
      const data = await res.json();
      setSeeds(data.conversations || []);
    } catch { /* */ }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchSeeds(); }, [filterTool, filterSource]);

  const deleteSeed = async (id: string) => {
    if (!confirm("Delete this seed?")) return;
    await fetch(`${DEFAULT_SERVER}/api/seeds/${id}`, { method: "DELETE" });
    fetchSeeds();
  };

  const exportSeeds = async () => {
    await fetch(`${DEFAULT_SERVER}/api/seeds/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ output_dir: "./data" }),
    });
    alert("Exported to ./data/train.jsonl + ./data/test.jsonl");
  };

  const getPreview = (seed: Seed) => {
    const userMsgs = seed.messages.filter((m) => m.role === "user");
    const firstText = userMsgs[0]?.content?.slice(0, 60) || "(empty)";
    const toolCalls = seed.messages.filter((m) => m.tool_calls?.length);
    const toolNames = [...new Set(toolCalls.flatMap((m) => (m.tool_calls || []).map((tc: unknown) => (tc as { function: { name: string } }).function.name)))];
    return { text: firstText, toolNames, turnCount: userMsgs.length };
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-2 items-center">
        <select value={filterTool} onChange={(e) => setFilterTool(e.target.value)}
          className="rounded-lg border border-gray-200 px-2 py-1 text-xs">
          <option value="">All tools</option>
          {tools.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}
        </select>
        <select value={filterSource} onChange={(e) => setFilterSource(e.target.value)}
          className="rounded-lg border border-gray-200 px-2 py-1 text-xs">
          <option value="">All sources</option>
          <option value="manual">Manual</option>
          <option value="ai_assist">AI Assist</option>
        </select>
        <span className="text-xs text-slate-400 ml-auto">{seeds.length} seeds</span>
        <button onClick={fetchSeeds} className="text-xs text-indigo-600 hover:text-indigo-800">↻</button>
        <button onClick={exportSeeds} disabled={seeds.length === 0}
          className="px-3 py-1 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 disabled:opacity-50">
          Export
        </button>
      </div>

      {loading ? (
        <p className="text-xs text-slate-400">Loading...</p>
      ) : seeds.length === 0 ? (
        <p className="text-xs text-slate-400">No seeds yet. Build one in the Seed Builder or use AI Assist.</p>
      ) : (
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {seeds.map((seed) => {
            const p = getPreview(seed);
            return (
              <div key={seed.id} className="bg-white border border-gray-100 rounded-lg p-3 hover:border-indigo-200 transition-colors">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">{seed.source}</span>
                  <span className="text-[10px] text-slate-400">{p.turnCount} turns</span>
                </div>
                <p className="text-xs text-slate-700 mb-1 truncate">{p.text}</p>
                <div className="flex flex-wrap gap-1">
                  {p.toolNames.map((tn) => (
                    <span key={tn} className="text-[10px] px-1.5 py-0.5 rounded bg-purple-50 text-purple-600 font-mono">{tn}</span>
                  ))}
                </div>
                <div className="flex gap-2 mt-2">
                  <button onClick={() => onEdit(seed)} className="text-[10px] text-indigo-600 hover:underline">Edit</button>
                  <button onClick={() => deleteSeed(seed.id)} className="text-[10px] text-red-400 hover:underline">Delete</button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
