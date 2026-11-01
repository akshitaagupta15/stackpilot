import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "StackPilot",
  description: "Evidence-driven AI stack optimization: benchmark, recommend, route, monitor.",
};

const LINKS = [["/", "Recommend"], ["/benchmarks", "Benchmarks"], ["/gateway", "Gateway"], ["/monitor", "Monitoring"]];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-slate-200 bg-white">
          <nav className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3 text-sm">
            <span className="font-bold tracking-tight">StackPilot</span>
            {LINKS.map(([href, label]) => (
              <Link key={href} href={href} className="text-slate-600 hover:text-slate-900">{label}</Link>
            ))}
          </nav>
        </header>
        <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-slate-400">
          Portfolio project. Gateway and monitoring data on the public demo are simulated.
        </footer>
      </body>
    </html>
  );
}
