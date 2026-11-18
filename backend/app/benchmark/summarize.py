"""One-screen summary of a saved benchmark run: the numbers you need for a README or a decision.
Run:  python -m app.benchmark.summarize benchmark_runs\\<file>.json      (plain ASCII output)"""
import json
import sys
from pathlib import Path
from statistics import mean

from .runner import percentile
from .scoring import FIELDS


def _pct(a: int, b: int) -> str:
    return "n/a" if b == 0 else f"{a}/{b} ({a / b:.1%})"


def describe(run: dict) -> list[str]:
    items = run["items"]
    ok = [i for i in items if i["error"] is None]
    failed = [i for i in items if i["error"] is not None]
    cut = [i for i in ok if i.get("finish_reason") == "length"]
    clean = [i for i in ok if i["score"]["clean_json"]]
    wrong = [i for i in ok if i["score"]["clean_json"] and not i["score"]["exact_match"]]
    st = run.get("settings", {})
    d = run["dataset"]
    lat = [i["latency_ms"] for i in ok if i["latency_ms"] is not None]
    out = [f"model:      {run['model']}   (dry run: {run['dry_run']})",
           f"when:       {run['timestamp_utc'][:19]} UTC   runner v{run['runner_version']}   prompt {run['prompt_version']}",
           f"dataset:    {d['name']}  {d['n']} items  sha256 {d['sha256'][:12]}...",
           f"settings:   max_tokens={st.get('max_tokens')}  timeout={st.get('timeout_s')}s  temperature={st.get('temperature')}",
           f"requests:   {len(items)} sent, {len(ok)} answered, {len(failed)} failed, {sum(i.get('retries', 0) for i in items)} retries",
           "",
           f"clean JSON:        {_pct(len(clean), len(items))}",
           f"exact match:       {_pct(sum(1 for i in items if i['score']['exact_match']), len(items))}",
           f"field accuracy:    {mean(i['score']['field_accuracy'] for i in items):.1%}  (failures count as wrong)",
           f"cut off at limit:  {len(cut)}" + (f"  ({', '.join(i['id'] for i in cut)})" if cut else ""),
           "", "by language:"]
    for lang in sorted({i["language"] for i in items}):
        rows = [i for i in items if i["language"] == lang]
        out.append(f"  {lang}: clean JSON {_pct(sum(1 for i in rows if i['score']['clean_json']), len(rows))}, "
                   f"field accuracy {mean(i['score']['field_accuracy'] for i in rows):.1%}")
    out += ["", "by field: " + ", ".join(f"{f} {mean(1 if i['score']['fields'][f] else 0 for i in items):.0%}" for f in FIELDS), ""]
    out.append(f"latency (answered requests): p50 {percentile(lat, 50)} ms, p95 {percentile(lat, 95)} ms, "
               f"mean {mean(lat):.0f} ms  [{len(lat)} samples: p95 is noisy]" if lat else "latency: no answered requests")
    tin = [i["input_tokens"] for i in ok if i["input_tokens"] is not None]
    tout = [i["output_tokens"] for i in ok if i["output_tokens"] is not None]
    if tin and tout:
        out.append(f"tokens:     avg {mean(tin):.0f} in, {mean(tout):.0f} out per request")
    if wrong:
        out.append("complete but wrong: " + "; ".join(
            f"{i['id']} ({', '.join(f for f, good in i['score']['fields'].items() if not good)})" for i in wrong))
    if failed:
        out.append("failed requests:   " + "; ".join(f"{i['id']} ({i['error'][:40]})" for i in failed[:8]))
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m app.benchmark.summarize <run_file.json>")
    print("\n".join(describe(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))))
