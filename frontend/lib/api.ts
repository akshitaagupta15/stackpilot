export const API = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
export const DEMO_KEY = process.env.NEXT_PUBLIC_DEMO_KEY || "";

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown, message: string) { super(message); }
}

/** Human-readable text for FastAPI error bodies (detail can be a string, an object or a validation list). */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail as any;
    if (typeof d === "string") return d;
    if (d?.message) return d.message;
    if (Array.isArray(d)) return d.map((x) => `${(x.loc || []).slice(1).join(".")}: ${x.msg}`).join("; ");
    return `Request failed (${e.status})`;
  }
  if (e instanceof DOMException && e.name === "AbortError") return "The server took too long to respond.";
  return "Could not reach the API. Is the backend running and CORS configured?";
}

export async function api<T>(path: string, opts: { method?: "GET" | "POST"; body?: unknown; key?: boolean } = {}): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 70_000); // free hosting can take ~1 minute to wake up
  try {
    const res = await fetch(API + path, {
      method: opts.method ?? (opts.body ? "POST" : "GET"),
      headers: { "Content-Type": "application/json", ...(opts.key ? { "X-API-Key": DEMO_KEY } : {}) },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      signal: ctrl.signal,
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(res.status, data?.detail ?? data, `HTTP ${res.status}`);
    return data as T;
  } finally { clearTimeout(timer); }
}
