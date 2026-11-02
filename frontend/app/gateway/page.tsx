"use client";
import { useState } from "react";
import { DEMO_KEY, api, errorText } from "@/lib/api";
import { ms, usd } from "@/lib/fmt";
import type { Attempt, GatewayResult } from "@/lib/types";
import { Badge, Card, Notice } from "@/components/ui";

const TONE = { ok: "green", failed: "red", skipped: "gray" } as const;

export default function GatewayPage() {
  const [text, setText] = useState("Summarise this invoice in one line.");
  const [apiKey, setApiKey] = useState("");
  const [policy, setPolicy] = useState("default");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<GatewayResult | null>(null);

  async function send() {
    setBusy(true); setErr(null); setRes(null);
    try {
      setRes(await api<GatewayResult>("/gateway/chat", { key: apiKey.trim() || true, body: { policy: policy.trim() || "default", messages: [{ role: "user", content: text }] } }));
    } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        <h1 className="text-lg font-semibold">Gateway playground</h1>
        <Notice tone="blue">The demo policy is deliberately set up so the primary model (<code>demo/fail-model</code>) always fails
          in the simulator. Watch the gateway fall back to <code>demo/backup</code>. No real model is called and nothing costs money.</Notice>
        {!DEMO_KEY && !apiKey && <Notice tone="amber">NEXT_PUBLIC_DEMO_KEY is not set, so requests will be rejected. See .env.local.example.</Notice>}
        <Card>
          <div className="mb-3 grid grid-cols-2 gap-3">
            <div><label>Your API key (optional)</label><input type="password" autoComplete="off" placeholder="blank = public demo key" value={apiKey} onChange={(e) => setApiKey(e.target.value)} /></div>
            <div><label>Policy name</label><input value={policy} onChange={(e) => setPolicy(e.target.value)} /></div>
          </div>
          <label>Message</label>
          <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} />
          <button onClick={send} disabled={busy || !text.trim()}
            className="mt-3 w-full rounded-lg bg-slate-900 py-2 text-sm font-medium text-white disabled:opacity-50">
            {busy ? "Routing… (the free server may be waking up)" : "Send through the gateway"}
          </button>
        </Card>
        <p className="text-xs text-slate-500">Prompts and replies are never stored; only metadata (model, latency, tokens, cost, routing path) is logged.</p>
      </div>
      <div className="space-y-4">
        {err && <Notice tone="red">{err}</Notice>}
        {res && (<>
          <Card title="Routing path">
            <div className="flex flex-wrap items-center gap-2">
              {res.routing.attempts.map((a: Attempt, i: number) => (
                <span key={i} className="flex items-center gap-2">
                  {i > 0 && <span className="text-slate-400">→</span>}
                  <span className="rounded-lg border border-slate-200 px-2 py-1 text-sm">
                    {a.model} <Badge tone={TONE[a.status]}>{a.status}</Badge>
                    {a.detail && <span className="ml-1 text-xs text-slate-500">{a.detail}</span>}
                  </span>
                </span>))}
            </div>
            <p className="mt-3 text-sm text-slate-600">{res.routing.reason}</p>
          </Card>
          <Card title="Response">
            <p className="mb-3 rounded-md bg-slate-50 p-2 text-sm">{res.text}</p>
            <div className="flex flex-wrap gap-2 text-xs">
              <Badge tone="green">served by {res.model_used}</Badge>
              {res.fallback_used && <Badge tone="amber">fallback used</Badge>}
              {res.simulated && <Badge tone="blue">simulated</Badge>}
              <Badge>{ms(res.latency_ms)}</Badge>
              <Badge>{res.usage.input_tokens ?? "–"} in / {res.usage.output_tokens ?? "–"} out tokens</Badge>
              <Badge>est. {usd(res.cost_usd, 6)}</Badge>
              <Badge>id {res.request_id}</Badge>
            </div>
          </Card>
        </>)}
      </div>
    </div>
  );
}
