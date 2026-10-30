import json
from app.benchmark.dataset import load_dataset
from app.benchmark.make_dataset import OUT, build
from app.benchmark.scoring import aggregate, extract_json, score_item

EXP = {"invoice_number": "INV-2025-0412", "invoice_date": "2025-03-15",
       "vendor_name": "शर्मा ट्रेडर्स", "total_amount": 125000.0, "currency": "INR"}


def test_perfect_output():
    s = score_item(json.dumps(EXP, ensure_ascii=False), EXP)
    assert s.exact_match and s.clean_json and s.field_accuracy == 1.0


def test_fenced_json_valid_but_not_clean():
    s = score_item("```json\n" + json.dumps(EXP, ensure_ascii=False) + "\n```", EXP)
    assert s.json_valid and not s.clean_json and s.exact_match


def test_prose_around_json_recovered():
    assert extract_json("Here you go: " + json.dumps(EXP) + " hope it helps") is not None


def test_garbage_scores_zero():
    s = score_item("I cannot help with that", EXP)
    assert not s.json_valid and s.field_accuracy == 0.0


def test_amount_formats_and_tolerance():
    for v in ("1,25,000.00", "₹1,25,000", 125000, 125000.004):
        assert score_item(json.dumps({**EXP, "total_amount": v}, ensure_ascii=False), EXP).fields["total_amount"]
    assert not score_item(json.dumps({**EXP, "total_amount": 102500.0}), EXP).fields["total_amount"]


def test_whitespace_and_case_normalized_but_content_matters():
    ok = score_item(json.dumps({**EXP, "vendor_name": "  शर्मा   ट्रेडर्स "}, ensure_ascii=False), EXP)
    bad = score_item(json.dumps({**EXP, "invoice_date": "2025-15-03"}), EXP)
    assert ok.fields["vendor_name"] and not bad.fields["invoice_date"]


def test_dataset_loads_and_is_balanced():
    items, sha = load_dataset()
    assert len(items) == 40 and len(sha) == 64
    assert sum(i["language"] == "hi" for i in items) == 20


def test_dataset_file_matches_generator():
    assert OUT.read_text(encoding="utf-8") == "\n".join(json.dumps(x, ensure_ascii=False) for x in build()) + "\n"


def test_total_is_in_the_text_and_is_not_the_subtotal():
    items, _ = load_dataset()
    for it in items:
        assert it["expected"]["invoice_number"] in it["text"]
        assert it["expected"]["vendor_name"] in it["text"]


def test_aggregate_by_language():
    items, _ = load_dataset()
    rows = [(i["language"], score_item(json.dumps(i["expected"], ensure_ascii=False), i["expected"])) for i in items]
    agg = aggregate(rows)
    assert agg["overall"]["exact_match_rate"] == 1.0 and agg["hi"]["n"] == 20
