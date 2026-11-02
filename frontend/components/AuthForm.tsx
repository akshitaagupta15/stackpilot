"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, errorText } from "@/lib/api";
import { useAuth } from "./AuthProvider";
import { Card, Notice } from "./ui";

export default function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const { user, ready, refresh } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const signup = mode === "signup";

  useEffect(() => { if (ready && user) router.replace("/dashboard"); }, [ready, user, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await api(signup ? "/auth/signup" : "/auth/login", { body: { email, password } });
      await refresh();
      router.push("/dashboard");
    } catch (e2) { setErr(errorText(e2)); } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-sm space-y-4">
      <h1 className="text-lg font-semibold">{signup ? "Create your account" : "Log in"}</h1>
      <Card>
        <form onSubmit={submit} className="space-y-3">
          <div><label>Email</label>
            <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div><label>Password{signup && " (10 or more characters)"}</label>
            <input type="password" autoComplete={signup ? "new-password" : "current-password"} required minLength={signup ? 10 : 1}
              maxLength={128} value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          {err && <Notice tone="red">{err}</Notice>}
          <button disabled={busy} className="w-full rounded-lg bg-slate-900 py-2 text-sm font-medium text-white disabled:opacity-50">
            {busy ? "Please wait… (the free server may be waking up)" : signup ? "Sign up" : "Log in"}
          </button>
        </form>
      </Card>
      {signup && <Notice tone="amber">Portfolio demo: emails are not verified and there is no password reset.
        Please do not reuse a password from another site.</Notice>}
      <p className="text-sm text-slate-600">
        {signup ? <>Already have an account? <Link href="/login" className="underline">Log in</Link></>
                : <>New here? <Link href="/signup" className="underline">Create an account</Link></>}
      </p>
    </div>
  );
}
