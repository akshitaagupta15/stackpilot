"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorText } from "@/lib/api";
import { useRequireAuth } from "@/components/AuthProvider";
import type { Project } from "@/lib/types";
import { Card, Notice, Wake } from "@/components/ui";

export default function DashboardPage() {
  const { user, ready } = useRequireAuth();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setProjects(await api<Project[]>("/account/projects")); } catch (e) { setErr(errorText(e)); }
  }, []);
  useEffect(() => { if (user) load(); }, [user, load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { await api("/account/projects", { body: { name } }); setName(""); await load(); }
    catch (e2) { setErr(errorText(e2)); } finally { setBusy(false); }
  }

  if (!ready || !user) return <p className="text-sm text-slate-500">Loading…</p>;
  return (
    <div className="space-y-4">
      <div><h1 className="text-lg font-semibold">Your projects</h1>
        <p className="text-sm text-slate-500">A project groups API keys, routing policies and usage. You can create up to 3.</p></div>
      {err && <Notice tone="red">{err}</Notice>}
      {!projects && !err && <Wake slow />}
      <div className="grid gap-3 md:grid-cols-3">
        {projects?.map((p) => (
          <Link key={p.id} href={`/dashboard/${p.id}`} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-slate-400">
            <div className="font-medium">{p.name}</div><div className="mt-1 break-all text-xs text-slate-400">{p.slug}</div>
          </Link>))}
        {projects?.length === 0 && <Notice>No projects yet. Create your first one below.</Notice>}
      </div>
      <Card title="New project">
        <form onSubmit={create} className="flex gap-2">
          <input placeholder="e.g. Support assistant" maxLength={60} required value={name} onChange={(e) => setName(e.target.value)} />
          <button disabled={busy || !name.trim()} className="whitespace-nowrap rounded-lg bg-slate-900 px-4 text-sm font-medium text-white disabled:opacity-50">
            Create project</button>
        </form>
      </Card>
    </div>
  );
}
