"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { ms, pct } from "@/lib/fmt";
import { useLoad } from "@/lib/useLoad";
import type { MeasuredModel } from "@/lib/types";
import { Badge, Card, Notice, Table, Wake } from "@/components/ui";

type Resp = { models: MeasuredModel[]; ignored_runs: { file: string; reason: string }[] };

export default function BenchmarksPage() {
  const [smoke, setSmoke] = useState(false);
  const { data, error, loading, slow } = useLoad(() => api<Resp>(`/measured/catalog?min_items=${smoke ? 1 : 20}`), [smoke]);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">Measured benchmarks</h1>
        <label className="flex items-center gap-2 !text-sm"><input type="checkbox" className="!w-auto" checked={smoke}
          onChange={(e) => setSmoke(e.target.checked)} />Include small smoke-test runs</label>
      </div>
      <Notice>Invoice extraction in English and Hindi. Quality is strict: the output must be clean JSON with correct fields.
        Failed requests count toward reliability, not quality. Runs on a different dataset version, dry runs and tiny samples are ignored.</Notice>
      <Wake slow={slow} />
      {loading && <p className="text-sm text-slate-500">Loading…</p>}
      {error && <Notice tone="red">{error}</Notice>}
      {data && (<>
        {data.models.length === 0 ? (
          <Card><p className="text-sm text-slate-600">No full benchmark runs have been published yet, so there is nothing measured to show.
            This page never fills the gap with made-up numbers.</p></Card>
        ) : (
          <Card title="Models">
            <Table head={["Model", "Samples", "Quality (strict)", "English", "Hindi", "Lenient", "P95 latency", "Reliability"]}>
              {data.models.map((m) => (
                <tr key={m.id}>
                  <td className="font-medium">{m.id} {m.free_tier && <Badge tone="amber">free tier</Badge>}</td>
                  <td>{m.metrics.n_samples}</td><td>{pct(m.metrics.quality)}</td>
                  <td>{pct(m.metrics.quality_by_language.en)}</td><td>{pct(m.metrics.quality_by_language.hi)}</td>
                  <td>{pct(m.metrics.quality_lenient)}</td><td>{ms(m.metrics.latency_p95_ms)}</td><td>{pct(m.metrics.reliability)}</td>
                </tr>))}
            </Table>
            <p className="mt-2 text-xs text-slate-500">P95 from tens of samples is noisy. Free-tier models were measured on shared, rate-limited capacity.</p>
          </Card>)}
        {data.ignored_runs.length > 0 && (
          <Card title="Runs not used, and why">
            <Table head={["File", "Reason"]}>
              {data.ignored_runs.map((r) => <tr key={r.file}><td className="font-mono text-xs">{r.file}</td><td>{r.reason}</td></tr>)}
            </Table>
          </Card>)}
      </>)}
    </div>
  );
}
