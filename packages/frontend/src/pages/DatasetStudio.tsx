import { useState } from "react";

const DEFAULT_SERVER = window.location.origin || "http://127.0.0.1:8766";

interface GenerationConfig {
  tiers: number[];
  model: string;
  api_key: string;
  n_prompts: number;
  output_dir: string;
}

export default function DatasetStudio() {
  const [config, setConfig] = useState<GenerationConfig>({
    tiers: [1],
    model: "gpt-4o",
    api_key: "",
    n_prompts: 3,
    output_dir: "./data",
  });
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const runGenerate = async () => {
    setRunning(true);
    setResult(null);
    setLog(["Starting dataset generation..."]);

    try {
      const res = await fetch(`${DEFAULT_SERVER}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      const data = await res.json();
      if (res.ok) {
        setResult(data);
        setLog((prev) => [
          ...prev,
          `Single-turn prompts: ${data.single_turn_prompts || 0}`,
          `Multi-turn convos: ${data.multi_turn_conversations || 0}`,
          `Validated: ${data.valid || 0} valid, ${data.rejected || 0} rejected`,
          `Train: ${data.train_count || 0} → ${data.train_path || "./data/train.jsonl"}`,
          `Test: ${data.test_count || 0} → ${data.test_path || "./data/test.jsonl"}`,
          "Done.",
        ]);
      } else {
        setLog((prev) => [...prev, `Error: ${data.error || "Generation failed"}`]);
      }
    } catch (err) {
      setLog((prev) => [...prev, `Error: ${err instanceof Error ? err.message : "Failed"}`]);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Dataset Studio</h1>

      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
          <h2 className="text-lg font-semibold text-slate-800">Generation Config</h2>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">Tiers</span>
            <div className="flex gap-2 mt-1">
              {[1, 2].map((tier) => (
                <button key={tier} onClick={() =>
                  setConfig((c) => ({ ...c, tiers: c.tiers.includes(tier) ? c.tiers.filter((t) => t !== tier) : [...c.tiers, tier].sort() }))
                } className={`px-3 py-1.5 text-sm rounded-lg border ${config.tiers.includes(tier) ? "bg-indigo-50 border-indigo-300 text-indigo-700" : "bg-white border-gray-200 text-slate-600"}`}>
                  Tier {tier}: {tier === 1 ? "Single-turn" : "Multi-turn"}
                </button>
              ))}
            </div>
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">Teacher Model</span>
            <input type="text" value={config.model} onChange={(e) => setConfig((c) => ({ ...c, model: e.target.value }))} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">OpenAI API Key</span>
            <input type="password" value={config.api_key} onChange={(e) => setConfig((c) => ({ ...c, api_key: e.target.value }))} placeholder="sk-..." className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono" />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">Prompts per Invocation</span>
            <input type="number" value={config.n_prompts} min={1} max={10} onChange={(e) => setConfig((c) => ({ ...c, n_prompts: parseInt(e.target.value) || 1 }))} className="mt-1 w-24 rounded-lg border border-gray-200 px-3 py-2 text-sm" />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">Output Directory</span>
            <input type="text" value={config.output_dir} onChange={(e) => setConfig((c) => ({ ...c, output_dir: e.target.value }))} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
          </label>

          <button onClick={runGenerate} disabled={running} className="w-full py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50">
            {running ? "Generating..." : "Generate Dataset"}
          </button>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-slate-800 mb-3">Output</h2>
          <div className="bg-slate-900 rounded-lg p-4 min-h-[300px] max-h-[500px] overflow-y-auto font-mono text-xs">
            {log.length === 0 ? (
              <span className="text-slate-500">Configure generation settings and click Generate.</span>
            ) : (
              log.map((line, i) => (
                <div key={i} className="text-emerald-400 mb-1">{line}</div>
              ))
            )}

            {result && (
              <div className="mt-4 pt-4 border-t border-slate-700 text-amber-400">
                <div className="font-semibold mb-2">Result:</div>
                <pre className="whitespace-pre-wrap">{JSON.stringify(result, null, 2)}</pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
