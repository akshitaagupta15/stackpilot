"""Print what each model actually answered, to diagnose bad scores.
Run:  python -m app.benchmark.show_run benchmark_runs\\<file>.json
Text is shown with ascii() so Hindi appears as \\uXXXX escapes (safe in any terminal)."""
import json
import sys
from pathlib import Path


def describe(run: dict, preview: int = 300) -> list[str]:
    lines = [f"model={run['model']}  dry_run={run['dry_run']}  items={len(run['items'])}"]
    for it in run["items"]:
        wrong = [f for f, ok in it["score"]["fields"].items() if not ok]
        raw = it["raw_output"] or ""
        lines.append(f"\n[{it['id']}] latency={it['latency_ms']}ms tokens_in={it['input_tokens']} "
                     f"tokens_out={it['output_tokens']} finish_reason={it.get('finish_reason')} retries={it.get('retries', 0)} error={it['error']}")
        lines.append(f"  json_valid={it['score']['json_valid']}  wrong_fields={wrong or 'none'}")
        lines.append(f"  raw_output_length={len(raw)}  preview={ascii(raw[:preview])}")
    return lines


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m app.benchmark.show_run <run_file.json>")
    print("\n".join(describe(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))))
