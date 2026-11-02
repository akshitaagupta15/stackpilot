import type { Metadata } from "next";
import AuthProvider from "@/components/AuthProvider";
import Nav from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "StackPilot",
  description: "Evidence-driven AI stack optimization: benchmark, recommend, route, monitor.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <header className="border-b border-slate-200 bg-white"><Nav /></header>
          <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">{children}</main>
        </AuthProvider>
        <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-slate-400">
          Portfolio project. Gateway and monitoring data on the public demo are simulated.
        </footer>
      </body>
    </html>
  );
}
