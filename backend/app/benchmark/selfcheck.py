"""Try the scoring with FAKE model outputs. No API key or internet needed.
Run:  python -m app.benchmark.selfcheck"""
import json
import random

from .dataset import load_dataset
from .scoring import aggregate, score_item


def fake_model(items, wrong_total=0.0, fenced=0.0, garbage=0.0, seed=1):
    rng = random.Random(seed)
    outs = {}
    for it in items:
        exp = dict(it["expected"])
        if rng.random() < wrong_total:
            exp["total_amount"] = round(exp["total_amount"] * 0.82, 2)  # picked the pre-tax amount
        text = json.dumps(exp, ensure_ascii=False)
        r = rng.random()
        if r < garbage:
            text = "Sorry, I could not read this invoice."
        elif r < garbage + fenced:
            text = f"```json\n{text}\n```"
        outs[it["id"]] = text
    return outs


if __name__ == "__main__":
    items, sha = load_dataset()
    print(f"dataset: {len(items)} items, sha256={sha[:12]}...\n")
    fakes = {"perfect_model": fake_model(items),
             "sloppy_model": fake_model(items, wrong_total=0.2, fenced=0.3, garbage=0.1)}
    for name, outs in fakes.items():
        agg = aggregate([(it["language"], score_item(outs[it["id"]], it["expected"])) for it in items])
        print(f"== {name} ==")
        for scope in ("overall", "en", "hi"):
            a = agg[scope]
            print(f"  {scope:8} n={a['n']:2}  valid={a['json_valid_rate']:.2f}  clean={a['clean_json_rate']:.2f}  "
                  f"field_acc={a['field_accuracy']:.2f}  exact={a['exact_match_rate']:.2f}")
        print()
