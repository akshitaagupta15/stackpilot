"use client";
import { useEffect, useState } from "react";
import { errorText } from "./api";

/** Loads data when deps change. `slow` flips on after 4s so the UI can say the free server is waking up. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    let alive = true;
    setLoading(true); setError(null); setSlow(false);
    const t = setTimeout(() => alive && setSlow(true), 4000);
    fn().then((d) => alive && setData(d)).catch((e) => alive && setError(errorText(e)))
      .finally(() => { clearTimeout(t); if (alive) { setLoading(false); setSlow(false); } });
    return () => { alive = false; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, loading, slow };
}
