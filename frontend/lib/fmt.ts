export const pct = (x: number | null | undefined, d = 1) => (x == null ? "–" : `${(x * 100).toFixed(d)}%`);
export const ms = (x: number | null | undefined) => (x == null ? "–" : `${Math.round(x).toLocaleString()} ms`);
export const usd = (x: number | null | undefined, d = 2) =>
  x == null ? "–" : x !== 0 && Math.abs(x) < 0.01 ? `$${x.toPrecision(2)}` : `$${x.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })}`;
