"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "./AuthProvider";

const LINKS = [["/", "Recommend"], ["/benchmarks", "Benchmarks"], ["/gateway", "Gateway"], ["/monitor", "Demo monitoring"]];

export default function Nav() {
  const { user, ready, logout } = useAuth();
  const router = useRouter();
  return (
    <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 text-sm">
      <span className="font-bold tracking-tight">StackPilot</span>
      {LINKS.map(([href, label]) => <Link key={href} href={href} className="text-slate-600 hover:text-slate-900">{label}</Link>)}
      <span className="ml-auto flex items-center gap-4">
        {ready && user && (<>
          <Link href="/dashboard" className="font-medium text-slate-900">Dashboard</Link>
          <span className="hidden text-slate-500 sm:inline">{user.email}</span>
          <button onClick={async () => { await logout(); router.push("/"); }} className="text-slate-600 hover:text-slate-900">Log out</button>
        </>)}
        {ready && !user && (<>
          <Link href="/login" className="text-slate-600 hover:text-slate-900">Log in</Link>
          <Link href="/signup" className="rounded-lg bg-slate-900 px-3 py-1.5 font-medium text-white">Sign up</Link>
        </>)}
      </span>
    </nav>
  );
}
