import { ReactNode } from "react";

export function Card({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm ${className}`}>
      {title && <h2 className="mb-3 text-sm font-semibold text-slate-700">{title}</h2>}
      {children}
    </section>
  );
}

const TONES: Record<string, string> = {
  gray: "bg-slate-100 text-slate-700", green: "bg-emerald-100 text-emerald-800", amber: "bg-amber-100 text-amber-800",
  red: "bg-red-100 text-red-800", blue: "bg-sky-100 text-sky-800",
};
export function Badge({ tone = "gray", children }: { tone?: keyof typeof TONES; children: ReactNode }) {
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}>{children}</span>;
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}

export function Notice({ tone = "gray", children }: { tone?: "gray" | "amber" | "red" | "blue"; children: ReactNode }) {
  const t = { gray: "bg-slate-100 text-slate-700", amber: "bg-amber-50 text-amber-900 border-amber-200",
              red: "bg-red-50 text-red-900 border-red-200", blue: "bg-sky-50 text-sky-900 border-sky-200" }[tone];
  return <div className={`rounded-lg border px-3 py-2 text-sm ${t}`}>{children}</div>;
}

/** Shown while a request is slow: the free backend sleeps when idle. */
export function Wake({ slow }: { slow: boolean }) {
  return slow ? <Notice tone="blue">Waking up the demo server (free hosting sleeps when idle). This can take up to a minute…</Notice> : null;
}

export function StatusBadge({ status }: { status: string }) {
  const tone = status === "healthy" ? "green" : status === "degraded" ? "amber" : status === "down" ? "red" : "gray";
  return <Badge tone={tone}>{status}</Badge>;
}

export function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead><tr className="border-b border-slate-200 text-xs text-slate-500">
          {head.map((h) => <th key={h} className="whitespace-nowrap px-2 py-1.5 font-medium">{h}</th>)}
        </tr></thead>
        <tbody className="[&>tr]:border-b [&>tr]:border-slate-100 [&_td]:px-2 [&_td]:py-1.5">{children}</tbody>
      </table>
    </div>
  );
}
