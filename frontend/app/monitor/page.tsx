"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { ms, pct, usd } from "@/lib/fmt";
import { useLoad } from "@/lib/useLoad";
import type { ModelHealth, Point, RecentRequest, Summary } from "@/lib/types";
import BarChart from "@/components/BarChart";
import { Badge, Card, Notice, Stat, StatusBadge, Table, Wake } from "@/components/ui";

export default function MonitorPage() {
  const [hours, setHours] = useState(168);
  const { data, error, loading, slow } = useLoad(async () => {
    const bucket = hours > 72 ? "day" : "hour";
    const [s, m, t, r] = await Promise.all([
      api<{ summary: Summary; alerts: { level: string; message: string }[] }>(`/monitor/summary?hours=${hours}`, { key: true }),
      api<{ models: ModelHealth[] }>(`/monitor/models?hours=${hours}`, { key: true }),
      api<{ points: Point[] }>(`/monitor/timeseries?hours=${hours}&bucket=${bucket}`, { key: true }),
      api<{ requests: RecentRequest[] }>(`/monitor/recent?limit=8&hours=${hours}`, { key: true }),
    ]);
    return { s, m, t, r, bucket };
  }, [hours]);

  const label = (iso: string, bucket: string) =>
    new Date(iso).toLocaleString([], bucket === "hour" ? { month: "short", day: "numeric", hour: "2-digit" } : { month: "short", day: "numeric" });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Gateway monitoring</h1>
        <select className="!w-auto" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
          <option value={24}>Last 24 hours</option><option value={72}>Last 3 days</option><option value={168}>Last 7 days</option>
        </select>
      </div>
      <Wake slow={slow} />
      {loading && <p className="text-sm text-slate-500">Loading…</p>}
      {error && <Notice tone="red">{error}</Notice>}
      {data && (() => {
        const { summary: s, alerts } = data.s;
        return (<>
          {(s.simulated_share ?? 0) >= 0.5 && (
            <Notice tone="blue">Showing <b>simulated demo traffic</b>. It exists so the dashboard is not empty and is not real usage.
              Requests sent from the Gateway page deliberately start with a failing model, so <code>demo/fail-model</code> shows
              as down here. That is the alert system working, not an outage.</Notice>)}
          {alerts.map((a) => <Notice key={a.message} tone={a.level === "critical" ? "red" : "amber"}>{a.message}</Notice>)}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
            <Stat label="Requests" value={s.requests.toLocaleString()} />
            <Stat label="Success rate" value={pct(s.success_rate)} />
            <Stat label="Fallback rate" value={pct(s.fallback_rate)} />
            <Stat label="P95 latency" value={ms(s.latency_ms.p95)} hint={`P50 ${ms(s.latency_ms.p50)}`} />
            <Stat label="Cost (window)" value={usd(s.cost_usd.total, 4)} hint="estimated" />
            <Stat label="30-day projection" value={usd(s.cost_usd.projected_30_day)} hint="from this window" />
          </div>
          <Card title="Traffic">
            <BarChart points={data.t.points.map((p) => ({ label: label(p.bucket, data.bucket), total: p.requests, fallbacks: p.fallbacks, failures: p.failures }))} />
          </Card>
          <Card title="Model health (based on routing attempts)">
            <Table head={["Model", "Status", "Served", "P50", "P95", "Attempts", "Failed", "Est. cost"]}>
              {data.m.models.map((m) => (
                <tr key={m.model}>
                  <td className="font-medium">{m.model}</td><td><StatusBadge status={m.status} /></td>
                  <td>{m.requests_served}</td><td>{ms(m.latency_ms.p50)}</td><td>{ms(m.latency_ms.p95)}</td>
                  <td>{m.attempts}</td><td>{m.failed_attempts} ({pct(m.attempt_failure_rate, 0)})</td><td>{usd(m.cost_usd, 4)}</td>
                </tr>))}
            </Table>
          </Card>
          <Card title="Recent requests">
            <Table head={["Time", "Served by", "Result", "Latency", "Routing"]}>
              {data.r.requests.map((r) => (
                <tr key={r.request_id}>
                  <td className="whitespace-nowrap">{new Date(r.time).toLocaleString()}</td><td>{r.served_model ?? "–"}</td>
                  <td>{r.success ? <Badge tone={r.fallback_used ? "amber" : "green"}>{r.fallback_used ? "fallback" : "ok"}</Badge> : <Badge tone="red">failed</Badge>}</td>
                  <td>{ms(r.latency_ms)}</td><td className="text-xs text-slate-500">{r.reason}</td>
                </tr>))}
            </Table>
          </Card>
          <p className="text-xs text-slate-500">Percentiles use nearest-rank over successful requests. Costs are estimates from configured prices.</p>
        </>);
      })()}
    </div>
  );
}
