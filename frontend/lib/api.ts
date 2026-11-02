// Same-origin by default: /api/* is forwarded to the backend by next.config.mjs.
export const API = (process.env.NEXT_PUBLIC_API_BASE || "/api").replace(/\/$/, "");
export const DEMO_KEY = process.env.NEXT_PUBLIC_DEMO_KEY || "";

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown, message: string) { super(message); }
}

/** Human-readable text for FastAPI error bodies (string, object, validation list, policy problems). */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail as any;
    if (typeof d === "string") return d;
    if (d?.problems) {
      const lines = Object.entries(d.problems as Record<string, string[]>).map(([m, r]) => `${m}: ${r.join(", ")}`);
      return `${d.message}. ${lines.join(" | ")}`;
    }
    if (d?.message) return d.message;
    if (Array.isArray(d)) return d.map((x) => `${(x.loc || []).slice(1).join(".")}: ${x.msg}`).join("; ");
    if (e.status >= 500) return `The server could not handle the request (HTTP ${e.status}). The backend may be down, asleep or still starting: wait a minute and try again.`;
    return `Request failed (${e.status})`;
  }
  if (e instanceof DOMException && e.name === "AbortError") return "The server took too long to respond. Please try again.";
  return "Could not reach the API. Is the backend running?";
}

type Opts = { method?: "GET" | "POST" | "DELETE"; body?: unknown; key?: boolean | string };

export async function api<T>(path: string, opts: Opts = {}): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 70_000); // free hosting can take about a minute to wake up
  const apiKey = typeof opts.key === "string" ? opts.key : opts.key ? DEMO_KEY : "";
  try {
    const res = await fetch(API + path, {
      method: opts.method ?? (opts.body ? "POST" : "GET"),
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Requested-With": "stackpilot", ...(apiKey ? { "X-API-Key": apiKey } : {}) },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      signal: ctrl.signal,
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(res.status, data?.detail ?? data, `HTTP ${res.status}`);
    return data as T;
  } finally { clearTimeout(timer); }
}

/** Fire-and-forget request so a sleeping free-tier backend starts waking while the visitor reads the page. */
export function wakeBackend() {
  if (typeof window !== "undefined") fetch(API + "/health").catch(() => {});
}
