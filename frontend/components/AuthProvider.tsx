"use client";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, wakeBackend } from "@/lib/api";
import type { User } from "@/lib/types";

type Ctx = { user: User | null; ready: boolean; refresh: () => Promise<void>; logout: () => Promise<void> };
const AuthCtx = createContext<Ctx>({ user: null, ready: false, refresh: async () => {}, logout: async () => {} });
export const useAuth = () => useContext(AuthCtx);

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const refresh = useCallback(async () => {
    try { setUser(await api<User>("/auth/me")); } catch { setUser(null); }
    setReady(true);
  }, []);
  useEffect(() => { wakeBackend(); refresh(); }, [refresh]);
  const logout = useCallback(async () => {
    try { await api("/auth/logout", { method: "POST" }); } catch { /* the cookie is cleared server-side if it got through */ }
    setUser(null);
  }, []);
  return <AuthCtx.Provider value={{ user, ready, refresh, logout }}>{children}</AuthCtx.Provider>;
}

/** For pages that need a login: sends visitors to /login once we know they are logged out. */
export function useRequireAuth() {
  const auth = useAuth();
  const router = useRouter();
  useEffect(() => { if (auth.ready && !auth.user) router.replace("/login"); }, [auth.ready, auth.user, router]);
  return auth;
}
