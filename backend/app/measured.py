"""Turns saved benchmark runs into catalog entries with MEASURED metrics.
Rules (so weak evidence never sneaks into a ranking):
  - dry runs are ignored; runs on a different dataset version are ignored;
  - a model needs an entry in model_profiles.json (context window, regions, ... come from you);
  - quality is measured over requests that returned an answer, strictly (JSON must be clean);
    failed requests are counted in reliability instead, so they are not penalised twice;
  - runs with fewer than `min_items` successful requests are ignored; the newest valid run per model wins."""
import json
from pathlib import Path
from statistics import mean

from .benchmark.dataset import load_dataset
from .schemas import Metrics, ModelSpec

BASE = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = BASE / "benchmark_runs"
DEFAULT_PROFILES = BASE / "model_profiles.json"
PROFILE_KEYS = ["provider", "context_window", "structured_output", "regions", "languages", "data_policy"]


def load_profiles(path: Path) -> dict:
    if not Path(path).exists():
        return {}
    return {p["slug"]: p for p in json.loads(Path(path).read_text(encoding="utf-8"))["models"]}


def _strict(item: dict) -> float:
    s = item["score"]
    return s["field_accuracy"] if s["clean_json"] else 0.0


def metrics_from_run(run: dict) -> Metrics | None:
    ok = [i for i in run["items"] if i["error"] is None]
    p95 = run["summary"]["latency_ms"]["p95"]
    if not ok or p95 is None:
        return None
    by_lang = {l: round(mean(_strict(i) for i in ok if i["language"] == l), 4)
               for l in sorted({i["language"] for i in ok})}
    return Metrics(quality=round(mean(_strict(i) for i in ok), 4), latency_p95_ms=p95,
                   reliability=run["summary"]["reliability"]["success_rate"], source="benchmark",
                   n_samples=len(ok), quality_by_language=by_lang,
                   quality_lenient=round(mean(i["score"]["field_accuracy"] for i in ok), 4))


def load_measured_catalog(runs_dir=None, profiles_path=None, min_items: int = 20):
    runs_dir = Path(runs_dir or DEFAULT_RUNS)
    profiles = load_profiles(profiles_path or DEFAULT_PROFILES)
    _, sha = load_dataset()
    ignored, best = [], {}
    for f in sorted(runs_dir.glob("*.json")) if runs_dir.exists() else []:
        def skip(reason):
            ignored.append({"file": f.name, "reason": reason})
        try:
            run = json.loads(f.read_text(encoding="utf-8"))
            slug, ts = run["model"], run["timestamp_utc"]
        except (OSError, ValueError, KeyError):
            skip("unreadable run file"); continue
        if run.get("dry_run"):
            skip("dry run (simulated data)"); continue
        if run["dataset"]["sha256"] != sha:
            skip("dataset version differs from the current dataset"); continue
        if slug not in profiles:
            skip(f"no entry for '{slug}' in model_profiles.json"); continue
        missing = [k for k in PROFILE_KEYS if k not in profiles[slug]]
        if missing:
            skip(f"profile missing: {', '.join(missing)}"); continue
        m = metrics_from_run(run)
        if m is None:
            skip("no successful requests"); continue
        if m.n_samples < min_items:
            skip(f"only {m.n_samples} successful requests (need {min_items})"); continue
        if slug in best:
            older = best[slug] if best[slug][0] < ts else (ts, f.name, run, m)
            ignored.append({"file": older[1], "reason": "superseded by a newer run of the same model"})
            if best[slug][0] >= ts:
                continue
        best[slug] = (ts, f.name, run, m)

    models = []
    for slug, (ts, fname, run, m) in best.items():
        p = profiles[slug]
        po = p.get("pricing_override")
        pin, pout, ver = ((po["input_per_mtok"], po["output_per_mtok"], po["verified_on"]) if po else
                          (run["pricing"]["input_per_mtok"], run["pricing"]["output_per_mtok"],
                           run["pricing"]["checked_on"] or "unknown"))
        models.append(ModelSpec(id=slug, provider=p["provider"], name=p.get("name", slug),
                                context_window=p["context_window"], price_input_per_mtok=pin,
                                price_output_per_mtok=pout, pricing_verified_on=ver,
                                structured_output=p["structured_output"], regions=p["regions"],
                                languages=p["languages"], data_policy=p["data_policy"],
                                metrics=m, free_tier=bool(p.get("free_tier", False)), source_run=fname))
    return models, ignored
