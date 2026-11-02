"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, errorText } from "@/lib/api";
import { ms, pct, usd } from "@/lib/fmt";
import { useRequireAuth } from "@/components/AuthProvider";
import { useLoad } from "@/lib/useLoad";
import type { ModelProfile, Point, ProjectDetail, RecentRequest, Summary } from "@/lib/types";
import BarChart from "@/components/BarChart";
import { Badge, Card, Notice, Stat, Table, Wake } from "@/components/ui";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const { user, ready } = useRequireAuth();
  const [version, setVersion] = useState(0);
  const reload = () => setVersion((v) => v + 1);
  const detail = useLoad(() => (user ? api<ProjectDetail>(`/account/projects/${id}`) : Promise.resolve(null)), [user?.id, id, version]);
  const models = useLoad(() => (user ? api<ModelProfile[]>("/account/models") : Promise.resolve([])), [user?.id]);
  const slug = detail.data?.slug;
  const usage = useLoad(async () => {
    if (!slug) return null;
    const q = `project=${encodeURIComponent(slug)}&hours=24`;
    const [s, t, r] = await Promise.all([
      api<{ summary: Summary }>(`/monitor/summary?${q}`), api<{ points: Point[] }>(`/monitor/timeseries?${q}&bucket=hour`),
      api<{ requests: RecentRequest[] }>(`/monitor/recent?${q}&limit=5`)]);
    return { s: s.summary, t: t.points, r: r.requests };
  }, [slug, version]);

  const [msg, setMsg] = useState<{ tone: "red" | "blue"; text: string } | null>(null);
  const [keyName, setKeyName] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);
  const [pol, setPol] = useState({ name: "default", primary: "", fallbacks: [] as string[], high: false, structured: false });
  const [origin, setOrigin] = useState("");
  useEffect(() => setOrigin(window.location.origin), []);

  async function run(fn: () => Promise<unknown>, after?: () => void) {
    setMsg(null);
    try { await fn(); after?.(); reload(); } catch (e) { setMsg({ tone: "red", text: errorText(e) }); }
  }

  if (!ready || !user) return <p className="text-sm text-slate-500">Loading…</p>;
  if (detail.error) return <div className="space-y-3"><Notice tone="red">{detail.error}</Notice><Link href="/dashboard" className="text-sm underline">Back to your projects</Link></div>;
  const p = detail.data;
  if (!p) return <Wake slow={detail.slow} />;
  const available = models.data ?? [];
  const primary = pol.primary || available[0]?.slug || "";
  const firstPolicy = p.policies[0]?.name ?? "default";

  return (
    <div className="space-y-4">
      <div><Link href="/dashboard" className="text-xs text-slate-500 underline">← Projects</Link>
        <h1 className="text-lg font-semibold">{p.name}</h1><div className="text-xs text-slate-400">{p.slug}</div></div>
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}

      <Card title="Usage, last 24 hours (this project only)">
        {usage.data && usage.data.s.requests > 0 ? (<div className="space-y-3">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="Requests" value={usage.data.s.requests} /><Stat label="Success rate" value={pct(usage.data.s.success_rate)} />
            <Stat label="Fallback rate" value={pct(usage.data.s.fallback_rate)} />
            <Stat label="P95 latency" value={ms(usage.data.s.latency_ms.p95)} /><Stat label="Est. cost" value={usd(usage.data.s.cost_usd.total, 6)} />
          </div>
          <BarChart points={usage.data.t.map((x) => ({ label: new Date(x.bucket).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit" }),
            total: x.requests, fallbacks: x.fallbacks, failures: x.failures }))} />
          <Table head={["Time", "Served by", "Result", "Latency"]}>
            {usage.data.r.map((r) => (<tr key={r.request_id}><td>{new Date(r.time).toLocaleTimeString()}</td><td>{r.served_model ?? "–"}</td>
              <td>{r.success ? <Badge tone={r.fallback_used ? "amber" : "green"}>{r.fallback_used ? "fallback" : "ok"}</Badge> : <Badge tone="red">failed</Badge>}</td>
              <td>{ms(r.latency_ms)}</td></tr>))}
          </Table></div>
        ) : <p className="text-sm text-slate-500">No requests yet. Create a key and a policy below, then send a request with the example at the bottom.</p>}
      </Card>

      <Card title="API keys">
        {newKey && (<div className="mb-3 space-y-2"><Notice tone="amber">Copy this key now. It is shown only once; we store just a hash of it.</Notice>
          <div className="flex gap-2"><input readOnly value={newKey} className="font-mono !text-xs" onFocus={(e) => e.currentTarget.select()} />
            <button onClick={() => navigator.clipboard?.writeText(newKey)} className="rounded-lg border border-slate-300 px-3 text-sm">Copy</button>
            <button onClick={() => setNewKey(null)} className="rounded-lg border border-slate-300 px-3 text-sm">Done</button></div></div>)}
        <Table head={["Name", "Created", "Status", ""]}>
          {p.keys.map((k) => (<tr key={k.id}><td className="font-medium">{k.name}</td><td>{new Date(k.created_at).toLocaleDateString()}</td>
            <td>{k.active ? <Badge tone="green">active</Badge> : <Badge>revoked</Badge>}</td>
            <td className="text-right">{k.active && <button className="text-xs text-red-700 underline"
              onClick={() => confirm(`Revoke "${k.name}"? Apps using it will stop working.`) && run(() => api(`/account/projects/${id}/keys/${k.id}`, { method: "DELETE" }))}>Revoke</button>}</td></tr>))}
        </Table>
        {p.keys.length === 0 && <p className="mt-2 text-sm text-slate-500">No keys yet.</p>}
        <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); run(async () => { const r = await api<{ api_key: string }>(`/account/projects/${id}/keys`, { body: { name: keyName } }); setNewKey(r.api_key); }, () => setKeyName("")); }}>
          <input placeholder="Key name, e.g. production server" maxLength={100} required value={keyName} onChange={(e) => setKeyName(e.target.value)} />
          <button className="whitespace-nowrap rounded-lg bg-slate-900 px-4 text-sm font-medium text-white">Create key</button>
        </form>
      </Card>

      <Card title="Routing policies">
        <Table head={["Name", "Primary", "Fallbacks", "Rules", ""]}>
          {p.policies.map((x) => (<tr key={x.name}><td className="font-medium">{x.name}</td><td>{x.config.primary}</td><td>{x.config.fallbacks.join(", ") || "–"}</td>
            <td className="text-xs text-slate-500">{x.config.data_sensitivity === "high" ? "sensitive data" : "normal data"}{x.config.require_structured_output ? ", structured output" : ""}</td>
            <td className="text-right"><button className="text-xs text-red-700 underline"
              onClick={() => run(() => api(`/account/projects/${id}/policies/${encodeURIComponent(x.name)}`, { method: "DELETE" }))}>Delete</button></td></tr>))}
        </Table>
        {p.policies.length === 0 && <p className="mt-2 text-sm text-slate-500">No policies yet. The gateway needs one to route requests.</p>}
        <form className="mt-4 grid gap-3 border-t border-slate-100 pt-4 md:grid-cols-2" onSubmit={(e) => { e.preventDefault();
          run(() => api(`/account/projects/${id}/policies`, { body: { name: pol.name, primary, fallbacks: pol.fallbacks.filter((f) => f !== primary),
            data_sensitivity: pol.high ? "high" : "low", require_structured_output: pol.structured } })); }}>
          <div><label>Policy name</label><input value={pol.name} maxLength={100} required onChange={(e) => setPol({ ...pol, name: e.target.value })} /></div>
          <div><label>Primary model</label>
            <select value={primary} onChange={(e) => setPol({ ...pol, primary: e.target.value })}>
              {available.map((m) => <option key={m.slug} value={m.slug}>{m.slug}</option>)}</select></div>
          <div className="md:col-span-2"><label>Fallbacks, tried in this order</label>
            <div className="flex flex-wrap gap-3 text-sm">{available.filter((m) => m.slug !== primary).map((m) => (
              <label key={m.slug} className="flex items-center gap-1"><input type="checkbox" className="!w-auto" checked={pol.fallbacks.includes(m.slug)}
                onChange={(e) => setPol({ ...pol, fallbacks: e.target.checked ? [...pol.fallbacks, m.slug] : pol.fallbacks.filter((f) => f !== m.slug) })} />{m.slug}</label>))}
              {available.length < 2 && <span className="text-slate-400">No other models available.</span>}</div></div>
          <label className="flex items-center gap-2"><input type="checkbox" className="!w-auto" checked={pol.high} onChange={(e) => setPol({ ...pol, high: e.target.checked })} />
            Sensitive data (only models that do not train on inputs)</label>
          <label className="flex items-center gap-2"><input type="checkbox" className="!w-auto" checked={pol.structured} onChange={(e) => setPol({ ...pol, structured: e.target.checked })} />
            Require structured-output support</label>
          <div className="md:col-span-2"><button disabled={!primary} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Save policy</button>
            <span className="ml-3 text-xs text-slate-500">Models that break these rules are refused, and are never used as a fallback.</span></div>
        </form>
      </Card>

      <Card title="Send a request">
        <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">{`curl -X POST ${origin || "https://YOUR-SITE"}/api/gateway/chat \\
  -H "X-API-Key: YOUR_KEY" -H "Content-Type: application/json" \\
  -d '{"policy":"${firstPolicy}","messages":[{"role":"user","content":"hello"}]}'`}</pre>
        <p className="mt-2 text-xs text-slate-500">Or try it from the <Link href="/gateway" className="underline">Gateway page</Link> by pasting your key.
          On this public demo the provider is a simulator, so nothing costs money. Prompts and replies are never stored.</p>
      </Card>
    </div>
  );
}
