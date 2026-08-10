import { useState, useEffect, useRef } from "react";
import ConversationBuilder from "../components/ConversationBuilder";
import SeedList from "../components/SeedList";

const DEFAULT_SERVER = window.location.origin || "http://127.0.0.1:8766";

interface ToolInfo {
  name: string;
  description: string;
  params: { name: string; type: string; required: boolean; enum: string[] | null }[];
}

interface GenerationConfig {
  tiers: number[];
  model: string;
  api_key: string;
  n_prompts: number;
  output_dir: string;
}

interface TrainConfig {
  modal_token: string;
  model: string;
  train_path: string;
  test_path: string;
}

export default function DatasetStudio() {
  const [tab, setTab] = useState<"generate" | "seeds" | "train">("seeds");
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [config, setConfig] = useState<GenerationConfig>({
    tiers: [1], model: "gpt-4o", api_key: "", n_prompts: 3, output_dir: "./data",
  });
  const [trainCfg, setTrainCfg] = useState<TrainConfig>({
    modal_token: "", model: "Qwen/Qwen2.5-0.5B-Instruct", train_path: "./data/train.jsonl", test_path: "./data/test.jsonl",
  });
  const [running, setRunning] = useState(false);
  const [training, setTraining] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [editingSeed, setEditingSeed] = useState<{ userText: string; functionName: string; arguments: Record<string, unknown> }[] | null>(null);

  const [aiDesc, setAiDesc] = useState("");
  const [aiTurns, setAiTurns] = useState(4);
  const [aiAsrNoise, setAiAsrNoise] = useState(true);
  const [aiPrompt, setAiPrompt] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);

  useEffect(() => {
    fetch(`${DEFAULT_SERVER}/api/tools`).then((r) => r.json()).then((d) => setTools(d.tools || [])).catch(() => {});
  }, []);

  const runGenerate = async () => {
    setRunning(true); setResult(null); setLog(["Starting generation..."]);
    try {
      const res = await fetch(`${DEFAULT_SERVER}/api/generate`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config),
      });
      const data = await res.json();
      if (res.ok) {
        setResult(data);
        setLog((p) => [...p, `Single-turn: ${data.single_turn_prompts || 0}`, `Multi-turn: ${data.multi_turn_conversations || 0}`, `Valid: ${data.valid || 0}, Rejected: ${data.rejected || 0}`, `Train: ${data.train_count} → ${data.train_path}`, `Test: ${data.test_count} → ${data.test_path}`, "Done."]);
        setTrainCfg((c) => ({ ...c, train_path: (data.train_path as string) || c.train_path, test_path: (data.test_path as string) || c.test_path }));
      } else setLog((p) => [...p, `Error: ${data.error}`]);
    } catch (err) { setLog((p) => [...p, `Error: ${err instanceof Error ? err.message : "Failed"}`]); }
    finally { setRunning(false); }
  };

  const runTrain = async () => {
    setTraining(true); setJobStatus("submitted"); setLog((p) => [...p, "Submitting to Modal..."]);
    try {
      const res = await fetch(`${DEFAULT_SERVER}/api/train`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(trainCfg),
      });
      const data = await res.json();
      if (res.ok) { setJobId(data.job_id); setLog((p) => [...p, `Job ${data.job_id} submitted.`]); }
      else { setLog((p) => [...p, `Error: ${data.error}`]); setTraining(false); }
    } catch (err) { setLog((p) => [...p, `Error: ${err instanceof Error ? err.message : "Failed"}`]); setTraining(false); }
  };

  useEffect(() => {
    if (!jobId) return;
    const poll = async () => {
      try {
        const res = await fetch(`${DEFAULT_SERVER}/api/train/${jobId}`);
        const data = await res.json();
        setJobStatus(data.status);
        if (data.status === "done") { setTraining(false); setJobId(null); setLog((p) => [...p, `Training complete. Model in ${data.output_path || "./models/"}`]); }
        else if (data.status === "failed") { setTraining(false); setJobId(null); setLog((p) => [...p, `Training failed: ${data.error}`]); }
      } catch {}
    };
    poll(); pollRef.current = setInterval(poll, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [jobId]);

  const saveSeed = async (conv: { messages: unknown[] }) => {
    try {
      const res = await fetch(`${DEFAULT_SERVER}/api/seeds`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: conv.messages, source: "manual" }),
      });
      const data = await res.json();
      if (data.error) setLog((p) => [...p, `Save error: ${data.error}`]);
      else setLog((p) => [...p, `Seed saved: ${data.id}`]);
    } catch (err) { setLog((p) => [...p, `Save failed: ${err instanceof Error ? err.message : "Failed"}`]); }
  };

  const runAiAssist = async () => {
    setAiLoading(true);
    setLog((p) => [...p, "AI generating draft..."]);
    try {
      const res = await fetch(`${DEFAULT_SERVER}/api/seed/ai-assist`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: aiDesc, turns: aiTurns, include_asr_noise: aiAsrNoise, prompt: aiPrompt || undefined }),
      });
      const data = await res.json();
      if (data.conversation) {
        const turns: { userText: string; functionName: string; arguments: Record<string, unknown> }[] = [];
        for (const msg of data.conversation.messages || []) {
          if (msg.role === "user") {
            const nextMsg = data.conversation.messages[data.conversation.messages.indexOf(msg) + 1];
            const tc = nextMsg?.tool_calls?.[0]?.function;
            turns.push({ userText: msg.content, functionName: tc?.name || "intent_unclear", arguments: tc?.arguments ? (typeof tc.arguments === "string" ? JSON.parse(tc.arguments) : tc.arguments) : {} });
          }
        }
        setEditingSeed(turns);
        setLog((p) => [...p, `AI draft ready: ${turns.length} turns. Review and save.`]);
      } else { setLog((p) => [...p, `AI error: ${data.error}`]); }
    } catch (err) { setLog((p) => [...p, `AI failed: ${err instanceof Error ? err.message : "Failed"}`]); }
    finally { setAiLoading(false); }
  };

  const handleEditSeed = (seed: { messages: { role: string; content?: string; tool_calls?: unknown[] }[] }) => {
    const turns: { userText: string; functionName: string; arguments: Record<string, unknown> }[] = [];
    for (let i = 0; i < seed.messages.length; i++) {
      const msg = seed.messages[i];
      if (msg.role === "user" && msg.content) {
        const nextMsg = seed.messages[i + 1];
        const tc = nextMsg?.tool_calls?.[0] as { function?: { name?: string; arguments?: string } } | undefined;
        let args: Record<string, unknown> = {};
        if (tc?.function?.arguments) {
          try { args = JSON.parse(tc.function.arguments); } catch {}
        }
        turns.push({ userText: msg.content, functionName: tc?.function?.name || "intent_unclear", arguments: args });
      }
    }
    setEditingSeed(turns);
  };

  const tabs = [
    { id: "seeds", label: "Seeds" },
    { id: "generate", label: "Generate" },
    { id: "train", label: "Train" },
  ] as const;

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-4">Dataset Studio</h1>

      <div className="flex gap-1 mb-6 bg-slate-100 rounded-lg p-1 w-fit">
        {tabs.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${tab === t.id ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "seeds" && (
        <div className="grid grid-cols-2 gap-6">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-slate-800 mb-4">Seed Builder</h2>
            {editingSeed ? (
              <>
                <ConversationBuilder tools={tools} apiKey={config.api_key} model={config.model}
                  onSave={saveSeed} editingConversation={editingSeed} />
                <button onClick={() => setEditingSeed(null)} className="mt-2 text-xs text-slate-400 hover:text-slate-600">Clear</button>
              </>
            ) : (
              <ConversationBuilder tools={tools} apiKey={config.api_key} model={config.model} onSave={saveSeed} />
            )}
          </div>
          <div className="space-y-6">
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-slate-800 mb-3">My Seeds</h2>
              <SeedList tools={tools} onEdit={handleEditSeed} />
            </div>
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-slate-800 mb-3">AI Assist</h2>
              <textarea value={aiDesc} onChange={(e) => setAiDesc(e.target.value)}
                placeholder="Describe the conversation you want... (e.g. 'a user who lost their credit card and wants to cancel it')"
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm resize-none h-20" />
              <div className="flex gap-3 mt-2 items-center">
                <label className="text-xs text-slate-500">Turns:</label>
                <input type="number" value={aiTurns} min={2} max={10} onChange={(e) => setAiTurns(parseInt(e.target.value) || 4)} className="w-16 rounded-lg border border-gray-200 px-2 py-1 text-xs" />
                <label className="flex items-center gap-1 text-xs text-slate-500">
                  <input type="checkbox" checked={aiAsrNoise} onChange={(e) => setAiAsrNoise(e.target.checked)} /> ASR noise
                </label>
                <button onClick={() => setShowAdvanced(!showAdvanced)} className="text-xs text-slate-400 hover:text-slate-600">{showAdvanced ? "Hide" : "Advanced"}</button>
                <button onClick={runAiAssist} disabled={!aiDesc || aiLoading}
                  className="ml-auto px-4 py-2 rounded-lg bg-purple-600 text-white text-xs font-semibold hover:bg-purple-700 disabled:opacity-50">
                  {aiLoading ? "Generating..." : "Generate Draft"}
                </button>
              </div>
              {showAdvanced && (
                <textarea value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)}
                  placeholder="Custom prompt override (optional — appended to the AI generator prompt)..."
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-xs resize-none h-20 mt-2 font-mono" />
              )}
            </div>
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-slate-800 mb-3">Log</h2>
              <div className="bg-slate-900 rounded-lg p-3 max-h-48 overflow-y-auto font-mono text-xs">
                {log.length === 0 ? (
                  <span className="text-slate-500">Actions appear here.</span>
                ) : (
                  log.map((l, i) => <div key={i} className="text-emerald-400 mb-1">{l}</div>)
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === "generate" && (
        <div className="grid grid-cols-2 gap-6">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
            <h2 className="text-lg font-semibold text-slate-800">Generate Dataset</h2>
            <div className="flex gap-2">
              {[1, 2].map((tier) => (
                <button key={tier} onClick={() => setConfig((c) => ({ ...c, tiers: c.tiers.includes(tier) ? c.tiers.filter((t) => t !== tier) : [...c.tiers, tier].sort() }))}
                  className={`px-3 py-1.5 text-sm rounded-lg border ${config.tiers.includes(tier) ? "bg-indigo-50 border-indigo-300 text-indigo-700" : "bg-white border-gray-200 text-slate-600"}`}>
                  Tier {tier}: {tier === 1 ? "Single-turn" : "Multi-turn"}
                </button>
              ))}
            </div>
            <input type="text" value={config.model} onChange={(e) => setConfig((c) => ({ ...c, model: e.target.value }))} placeholder="gpt-4o" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
            <input type="password" value={config.api_key} onChange={(e) => setConfig((c) => ({ ...c, api_key: e.target.value }))} placeholder="OpenAI API key" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono" />
            <div className="flex gap-4">
              <label className="flex-1"><span className="text-xs text-slate-500">Prompts</span>
                <input type="number" value={config.n_prompts} min={1} max={10} onChange={(e) => setConfig((c) => ({ ...c, n_prompts: parseInt(e.target.value) || 1 }))} className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
              </label>
              <label className="flex-1"><span className="text-xs text-slate-500">Output</span>
                <input type="text" value={config.output_dir} onChange={(e) => setConfig((c) => ({ ...c, output_dir: e.target.value }))} className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
              </label>
            </div>
            <button onClick={runGenerate} disabled={running} className="w-full py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50">
              {running ? "Generating..." : "Generate Dataset"}
            </button>
          </div>
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-slate-800 mb-3">Output</h2>
            <div className="bg-slate-900 rounded-lg p-4 min-h-[300px] overflow-y-auto font-mono text-xs">
              {log.map((l, i) => <div key={i} className="text-emerald-400 mb-1">{l}</div>)}
              {result && <div className="mt-4 pt-4 border-t border-slate-700 text-amber-400"><div className="font-semibold mb-2">Result:</div><pre className="whitespace-pre-wrap">{JSON.stringify(result, null, 2)}</pre></div>}
            </div>
          </div>
        </div>
      )}

      {tab === "train" && (
        <div className="grid grid-cols-2 gap-6">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
            <h2 className="text-lg font-semibold text-slate-800">Train on Modal</h2>
            <input type="password" value={trainCfg.modal_token} onChange={(e) => setTrainCfg((c) => ({ ...c, modal_token: e.target.value }))} placeholder="Modal API token" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono" />
            <input type="text" value={trainCfg.model} onChange={(e) => setTrainCfg((c) => ({ ...c, model: e.target.value }))} placeholder="Base model (HuggingFace)" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
            <div className="flex gap-2">
              <input type="text" value={trainCfg.train_path} onChange={(e) => setTrainCfg((c) => ({ ...c, train_path: e.target.value }))} className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-xs" />
              <input type="text" value={trainCfg.test_path} onChange={(e) => setTrainCfg((c) => ({ ...c, test_path: e.target.value }))} className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-xs" />
            </div>
            <button onClick={runTrain} disabled={training} className="w-full py-2.5 rounded-lg bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50">
              {jobStatus === "running" ? "Training..." : jobStatus === "done" ? "Done ✓" : "Train on Modal"}
            </button>
          </div>
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-slate-800 mb-3">Output</h2>
            <div className="bg-slate-900 rounded-lg p-4 min-h-[300px] overflow-y-auto font-mono text-xs">
              {log.map((l, i) => <div key={i} className="text-emerald-400 mb-1">{l}</div>)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
