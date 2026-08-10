import { useState } from "react";

interface GenerationConfig {
  tiers: number[];
  model: string;
  nPrompts: number;
  outputDir: string;
}

export default function DatasetStudio() {
  const [config, setConfig] = useState<GenerationConfig>({
    tiers: [1],
    model: "gpt-4o",
    nPrompts: 3,
    outputDir: "./data",
  });
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);

  const runGenerate = async () => {
    setRunning(true);
    setLog((prev) => [...prev, "Starting generation..."]);

    setTimeout(() => {
      setLog((prev) => [
        ...prev,
        "Run 'va-sdk generate --tiers 1,2 --output ./data' from the CLI.",
        "Generation runs locally and requires OPENAI_API_KEY.",
      ]);
      setRunning(false);
    }, 500);
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
                <button
                  key={tier}
                  onClick={() =>
                    setConfig((c) => ({
                      ...c,
                      tiers: c.tiers.includes(tier)
                        ? c.tiers.filter((t) => t !== tier)
                        : [...c.tiers, tier].sort(),
                    }))
                  }
                  className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                    config.tiers.includes(tier)
                      ? "bg-indigo-50 border-indigo-300 text-indigo-700"
                      : "bg-white border-gray-200 text-slate-600 hover:border-slate-300"
                  }`}
                >
                  Tier {tier}
                  <span className="block text-[10px] opacity-60">
                    {tier === 1 ? "Single-turn" : "Multi-turn"}
                  </span>
                </button>
              ))}
            </div>
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">Teacher Model</span>
            <input type="text" value={config.model}
              onChange={(e) => setConfig((c) => ({ ...c, model: e.target.value }))}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">Prompts per Invocation</span>
            <input type="number" value={config.nPrompts} min={1} max={10}
              onChange={(e) => setConfig((c) => ({ ...c, nPrompts: parseInt(e.target.value) || 1 }))}
              className="mt-1 w-24 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">Output Directory</span>
            <input type="text" value={config.outputDir}
              onChange={(e) => setConfig((c) => ({ ...c, outputDir: e.target.value }))}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </label>

          <button onClick={runGenerate} disabled={running}
            className="w-full py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors">
            {running ? "Generating..." : "Generate Dataset"}
          </button>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-slate-800 mb-3">Output Log</h2>
          <div className="bg-slate-900 rounded-lg p-4 min-h-[300px] max-h-[400px] overflow-y-auto font-mono text-xs">
            {log.length === 0 ? (
              <span className="text-slate-500">Run a generation to see output.</span>
            ) : (
              log.map((line, i) => (
                <div key={i} className="text-emerald-400 mb-1">{line}</div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
