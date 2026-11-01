type P = { label: string; total: number; fallbacks: number; failures: number };

/** Dependency-free SVG chart: grey = requests, orange = fallbacks, red = failures. */
export default function BarChart({ points }: { points: P[] }) {
  const W = 640, H = 150, pad = 4;
  const max = Math.max(1, ...points.map((p) => p.total));
  const bw = (W - pad * 2) / Math.max(1, points.length);
  const h = (v: number) => (v / max) * (H - 20);
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Requests over time">
        {points.map((p, i) => {
          const x = pad + i * bw;
          return (
            <g key={i}>
              <title>{`${p.label}: ${p.total} requests, ${p.fallbacks} fallbacks, ${p.failures} failures`}</title>
              <rect x={x + 1} y={H - 16 - h(p.total)} width={Math.max(1, bw - 2)} height={h(p.total)} className="fill-slate-300" />
              <rect x={x + 1} y={H - 16 - h(p.fallbacks)} width={Math.max(1, bw - 2)} height={h(p.fallbacks)} className="fill-amber-500" />
              <rect x={x + 1} y={H - 16 - h(p.failures)} width={Math.max(1, bw - 2)} height={h(p.failures)} className="fill-red-500" />
            </g>
          );
        })}
        <line x1={0} x2={W} y1={H - 16} y2={H - 16} className="stroke-slate-300" />
      </svg>
      <div className="mt-1 flex justify-between text-xs text-slate-400">
        <span>{points[0]?.label}</span><span>peak {max.toLocaleString()} per bucket</span><span>{points[points.length - 1]?.label}</span>
      </div>
      <div className="mt-1 flex gap-4 text-xs text-slate-500">
        <span><i className="mr-1 inline-block h-2 w-2 bg-slate-300" />requests</span>
        <span><i className="mr-1 inline-block h-2 w-2 bg-amber-500" />fallbacks</span>
        <span><i className="mr-1 inline-block h-2 w-2 bg-red-500" />failures</span>
      </div>
    </div>
  );
}
