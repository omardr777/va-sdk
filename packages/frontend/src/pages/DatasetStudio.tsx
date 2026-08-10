import { useState, useEffect, useRef } from "react";

const DEFAULT_SERVER = window.location.origin || "http://127.0.0.1:8766";

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

  const runGenerate = async () => {
    setRunning(true); setResult(null);
    setLog(["Starting dataset generation..."]);
    try {
      const res = await fetch(`${DEFAULT_SERVER}/api/generate`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      const data = await res.json();
      if (res.ok) {
        setResult(data);
        setLog((p) => [...p,
          `Single-turn: ${data.single_turn_prompts || 0}`,
          `Multi-turn: ${data.multi_turn_conversations || 0}`,
          `Valid: ${data.valid || 0}, Rejected: ${data.rejected || 0}`,
          `Train: ${data.train_count} → ${data.train_path}`,
          `Test: ${data.test_count} → ${data.test_path}`,
          "Done.",
        ]);
        setTrainCfg((c) => ({ ...c, train_path: (data.train_path as string) || c.train_path, test_path: (data.test_path as string) || c.test_path }));
      } else { setLog((p) => [...p, `Error: ${data.error}`]); }
    } catch (err) { setLog((p) => [...p, `Error: ${err instanceof Error ? err.message : "Failed"}`]); }
    finally { setRunning(false); }
  };

  const runTrain = async () => {
    setTraining(true); setJobStatus("submitted");
    setLog((p) => [...p, "Submitting training job to Modal..."]);
    try {
      const res = await fetch(`${DEFAULT_SERVER}/api/train`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(trainCfg),
      });
      const data = await res.json();
      if (res.ok) {
        setJobId(data.job_id);
        setLog((p) => [...p, `Job ${data.job_id} submitted to Modal.`]);
      } else { setLog((p) => [...p, `Error: ${data.error}`]); setTraining(false); }
    } catch (err) { setLog((p) => [...p, `Error: ${err instanceof Error ? err.message : "Failed"}`]); setTraining(false); }
  };

  useEffect(() => {
    if (!jobId) return;
    const poll = async () => {
      try {
        const res = await fetch(`${DEFAULT_SERVER}/api/train/${jobId}`);
        const data = await res.json();
        setJobStatus(data.status);
        if (data.status === "done") {
          setTraining(false);
          setLog((p) => [...p, `Training complete! Model saved to ${data.output_path || "./models/"}`]);
          setJobId(null);
        } else if (data.status === "failed") {
          setTraining(false);
          setLog((p) => [...p, `Training failed: ${data.error}`]);
          setJobId(null);
        }
      } catch { /* poll error */ }
    };
    poll();
    pollRef.current = setInterval(poll, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [jobId]);

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Dataset Studio</h1>

      <div className="space-y-6">
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
            <input type="password" value={config.api_key} onChange={(e) => setConfig((c) => ({ ...c, api_key: e.target.value }))} placeholder="OpenAI API key (sk-...)" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono" />
            <div className="flex gap-4">
              <label className="flex-1"><span className="text-xs text-slate-500">Prompts/invocation</span>
                <input type="number" value={config.n_prompts} min={1} max={10} onChange={(e) => setConfig((c) => ({ ...c, n_prompts: parseInt(e.target.value) || 1 }))} className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
              </label>
              <label className="flex-1"><span className="text-xs text-slate-500">Output dir</span>
                <input type="text" value={config.output_dir} onChange={(e) => setConfig((c) => ({ ...c, output_dir: e.target.value }))} className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
              </label>
            </div>
            <button onClick={runGenerate} disabled={running} className="w-full py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50">
              {running ? "Generating..." : "Generate Dataset"}
            </button>
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
            <h2 className="text-lg font-semibold text-slate-800">Train on Modal</h2>
            <input type="password" value={trainCfg.modal_token} onChange={(e) => setTrainCfg((c) => ({ ...c, modal_token: e.target.value }))} placeholder="Modal API token" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono" />
            <input type="text" value={trainCfg.model} onChange={(e) => setTrainCfg((c) => ({ ...c, model: e.target.value }))} placeholder="Qwen/Qwen2.5-0.5B-Instruct" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
            <div className="flex gap-2">
              <input type="text" value={trainCfg.train_path} onChange={(e) => setTrainCfg((c) => ({ ...c, train_path: e.target.value }))} className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-xs" />
              <input type="text" value={trainCfg.test_path} onChange={(e) => setTrainCfg((c) => ({ ...c, test_path: e.target.value }))} className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-xs" />
            </div>
            <button onClick={runTrain} disabled={training} className="w-full py-2.5 rounded-lg bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50">
              {jobStatus === "running" ? "Training on Modal..." : jobStatus === "done" ? "Done ✓" : "Train on Modal"}
            </button>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-slate-800 mb-3">Output Log</h2>
          <div className="bg-slate-900 rounded-lg p-4 min-h-[300px] max-h-[500px] overflow-y-auto font-mono text-xs">
            {log.length === 0 ? (
              <span className="text-slate-500">Generate a dataset or train a model to see output here.</span>
            ) : (
              log.map((line, i) => <div key={i} className="text-emerald-400 mb-1">{line}</div>)
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
