"use client";
import Link from "next/link";
import { useState } from "react";
import { api, errorText } from "@/lib/api";
import { pct, usd } from "@/lib/fmt";
import type { CostEstimate, Recommendation, Weights, Workload } from "@/lib/types";
import { useAuth } from "@/components/AuthProvider";
import { Badge, Card, Notice, Table } from "@/components/ui";

const PICKS: [string, string][] = [["best_overall", "Best overall"], ["cheapest", "Cheapest"],
  ["highest_quality", "Highest quality"], ["lowest_latency", "Lowest latency"], ["fallback", "Fallback"]];
const DEFAULTS = { name: "support assistant", requests: "80000", tin: "1500", tout: "300", budget: "700",
                   p95: "2000", quality: "", sensitivity: "high", structured: true, en: true, hi: true };
const W0: Weights = { quality: 0.4, cost: 0.25, latency: 0.2, reliability: 0.15 };

export default function RecommendPage() {
  const { user, ready } = useAuth();
  const [f, setF] = useState(DEFAULTS);
  const [w, setW] = useState<Weights>(W0);
  const [source, setSource] = useState<"illustrative" | "measured">("illustrative");
  const [tab, setTab] = useState<"rec" | "cost">("rec");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [cost, setCost] = useState<CostEstimate[] | null>(null);
  const [budget, setBudget] = useState<number | null>(null);
  const set = (k: keyof typeof DEFAULTS, v: string | boolean) => setF({ ...f, [k]: v });

  function workload(): Workload {
    const num = (s: string) => (s.trim() === "" ? undefined : Number(s));
    const languages = [f.en && "en", f.hi && "hi"].filter(Boolean) as string[];
    return { name: f.name || "workload", monthly_requests: Number(f.requests), avg_input_tokens: Number(f.tin),
      avg_output_tokens: Number(f.tout), languages: languages.length ? languages : ["en"],
      requires_structured_output: f.structured, data_sensitivity: f.sensitivity as "low" | "high", regions: [],
      monthly_budget_usd: num(f.budget), p95_latency_ms: num(f.p95), quality_target: num(f.quality) };
  }

  async function run() {
    setBusy(true); setErr(null); setRec(null);
    const wl = workload();
    setBudget(wl.monthly_budget_usd ?? null);
    try {
      const [r, c] = await Promise.all([
        api<Recommendation>(source === "measured" ? "/measured/recommend" : "/recommend", { body: { workload: wl, weights: w } }),
        api<CostEstimate[]>("/cost", { body: wl }).catch(() => null),
      ]);
      setRec(r); setCost(c);
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }

  const slider = (k: keyof Weights) => (
    <div key={k}>
      <label className="flex justify-between capitalize"><span>{k}</span><span>{w[k].toFixed(2)}</span></label>
      <input type="range" min={0} max={1} step={0.05} value={w[k]} className="!p-0"
             onChange={(e) => setW({ ...w, [k]: Number(e.target.value) })} />
    </div>
  );
  const field = (k: keyof typeof DEFAULTS, label: string, ph = "") => (
    <div><label>{label}</label>
      <input value={String(f[k])} placeholder={ph} inputMode="decimal" onChange={(e) => set(k, e.target.value)} /></div>
  );

  return (
    <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
      <div className="space-y-4">
        <Card title="Workload">
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">{field("name", "Name")}</div>
            {field("requests", "Requests / month")}{field("budget", "Budget (USD / month)")}
            {field("tin", "Avg input tokens")}{field("tout", "Avg output tokens")}
            {field("p95", "P95 latency target (ms)")}{field("quality", "Min quality (0–1)", "optional")}
            <div><label>Data sensitivity</label>
              <select value={f.sensitivity} onChange={(e) => set("sensitivity", e.target.value)}>
                <option value="low">low</option><option value="high">high</option></select></div>
            <div className="space-y-1 pt-4 text-sm">
              <label className="flex items-center gap-2"><input type="checkbox" className="!w-auto" checked={f.structured}
                onChange={(e) => set("structured", e.target.checked)} />Structured output</label>
              <label className="flex items-center gap-2"><input type="checkbox" className="!w-auto" checked={f.en}
                onChange={(e) => set("en", e.target.checked)} />English</label>
              <label className="flex items-center gap-2"><input type="checkbox" className="!w-auto" checked={f.hi}
                onChange={(e) => set("hi", e.target.checked)} />Hindi</label>
            </div>
          </div>
        </Card>
        <Card title="Weights (normalized automatically)"><div className="space-y-2">{(Object.keys(W0) as (keyof Weights)[]).map(slider)}</div></Card>
        <Card title="Data source">
          <div className="space-y-1 text-sm">
            <label className="flex items-start gap-2"><input type="radio" className="!w-auto" checked={source === "illustrative"}
              onChange={() => setSource("illustrative")} /><span>Illustrative catalog <span className="text-slate-400">(placeholder numbers)</span></span></label>
            <label className="flex items-start gap-2"><input type="radio" className="!w-auto" checked={source === "measured"}
              onChange={() => setSource("measured")} /><span>Measured benchmarks <span className="text-slate-400">(my own runs)</span></span></label>
          </div>
        </Card>
        <button onClick={run} disabled={busy}
          className="w-full rounded-lg bg-slate-900 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "Working… (the free server may be waking up)" : "Get recommendation"}
        </button>
      </div>

      <div className="space-y-4">
        {ready && !user && <Notice tone="blue">Want to route your own requests? <Link href="/signup" className="font-medium underline">Create an account</Link> to
          make a project, API keys and routing policies, and see your own usage.</Notice>}
        {err && (
          <Notice tone="red">
            {err.replace(" See ignored_runs for why.", "")}
            {err.startsWith("No usable benchmark runs") && (<> <Link href="/benchmarks" className="underline">See why on the Benchmarks page.</Link></>)}
          </Notice>)}
        {!rec && !err && <Notice>Describe a workload and press the button. Hard constraints filter models first; the rest are ranked with the weights you set.</Notice>}
        {rec && (<>
          <div className="flex items-center gap-2 text-sm">
            <button onClick={() => setTab("rec")} className={tab === "rec" ? "font-semibold" : "text-slate-500"}>Recommendation</button>
            <span className="text-slate-300">|</span>
            <button onClick={() => setTab("cost")} className={tab === "cost" ? "font-semibold" : "text-slate-500"}>Cost ranges</button>
            <span className="ml-auto flex items-center gap-2">confidence
              <Badge tone={rec.confidence === "high" ? "green" : rec.confidence === "medium" ? "amber" : "red"}>{rec.confidence}</Badge></span>
          </div>
          {rec.caveats.map((c) => <Notice key={c} tone="amber">{c}</Notice>)}

          {tab === "rec" && (<>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              {PICKS.map(([k, label]) => (
                <div key={k} className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
                  <div className="text-xs text-slate-500">{label}</div>
                  <div className="mt-1 break-all text-sm font-semibold">{rec.picks[k] ?? "none"}</div>
                </div>))}
            </div>
            <Card title="Ranking (feasible models)">
              <Table head={["Model", "Score", "Quality", "Cost (relative)", "Latency (relative)", "Reliability", "Monthly cost"]}>
                {rec.ranked.map((c) => (
                  <tr key={c.model_id}>
                    <td className="font-medium">{c.model_id}</td><td>{c.score.toFixed(3)}</td>
                    {["quality", "cost", "latency", "reliability"].map((k) => <td key={k}>{pct(c.breakdown[k], 0)}</td>)}
                    <td>{usd(c.expected_monthly_cost_usd)}</td>
                  </tr>))}
              </Table>
              {rec.ranked.length === 0 && <p className="text-sm text-slate-500">No model satisfies every hard constraint.</p>}
              {rec.ranked.length > 0 && <p className="mt-2 text-xs text-slate-500">Cost and latency are scaled between the best and worst model that passed the filters
                (best = 100%, worst = 0%), so 0% means &quot;worst of these candidates&quot;, not zero, and with few candidates small real gaps look large.
                Quality and reliability are absolute values.</p>}
            </Card>
            <Card title="Rejected by hard constraints">
              <ul className="space-y-1 text-sm">
                {rec.rejected.map((r) => (
                  <li key={r.model_id}><span className="font-medium">{r.model_id}</span>
                    <span className="text-slate-500"> — {r.reasons.join("; ")}</span></li>))}
                {rec.rejected.length === 0 && <li className="text-slate-500">Nothing was rejected.</li>}
              </ul>
            </Card>
          </>)}

          {tab === "cost" && (
            <Card title="Monthly cost: low / expected / high usage">
              {cost ? (<>
                <Table head={["Model", "Low", "Expected", "High", "Per request (expected)", "Price date"]}>
                  {cost.map((c) => {
                    const s = Object.fromEntries(c.scenarios.map((x) => [x.name, x]));
                    const over = budget != null && s.high.monthly_cost_usd > budget;
                    return (
                      <tr key={c.model_id}>
                        <td className="font-medium">{c.model_id}</td><td>{usd(s.low.monthly_cost_usd)}</td>
                        <td>{usd(s.expected.monthly_cost_usd)}</td>
                        <td className={over ? "font-medium text-red-700" : ""}>{usd(s.high.monthly_cost_usd)}</td>
                        <td>{usd(s.expected.cost_per_request_usd, 4)}</td><td>{c.pricing_verified_on}</td>
                      </tr>);
                  })}
                </Table>
                <p className="mt-2 text-xs text-slate-500">Red = the high-usage scenario exceeds your budget. Scenarios: 0.7x / 1.0x / 1.4x volume with 0.9x / 1.0x / 1.2x token sizes.
                  Prices come from the illustrative catalog, so treat them as placeholders.</p>
              </>) : <p className="text-sm text-slate-500">Cost data unavailable.</p>}
            </Card>)}
        </>)}
      </div>
    </div>
  );
}
