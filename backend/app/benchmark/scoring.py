"""Deterministic scoring for structured extraction. No LLM judge."""
import json
import re
import unicodedata
from dataclasses import dataclass
from statistics import mean

FIELDS = ["invoice_number", "invoice_date", "vendor_name", "total_amount", "currency"]


@dataclass
class ItemScore:
    json_valid: bool          # a JSON object could be recovered from the output
    clean_json: bool          # output was *only* JSON (no fences or extra prose)
    fields: dict[str, bool]   # per-field correctness
    field_accuracy: float
    exact_match: bool


def extract_json(text: str):
    """Return a dict if one can be recovered from model output, else None."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.IGNORECASE)
    for candidate in (t, t[t.find("{"): t.rfind("}") + 1] if "{" in t and "}" in t else ""):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _norm(v) -> str:
    return " ".join(unicodedata.normalize("NFC", str(v)).split()).casefold()


def _to_float(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        cleaned = re.sub(r"[^0-9.\-]", "", v)
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def field_correct(field: str, got, expected) -> bool:
    if got is None:
        return False
    if field == "total_amount":
        g = _to_float(got)
        return g is not None and abs(g - float(expected)) < 0.005
    return _norm(got) == _norm(expected)


def score_item(output_text: str, expected: dict) -> ItemScore:
    obj = extract_json(output_text)
    try:
        clean = isinstance(json.loads((output_text or "").strip()), dict)
    except (json.JSONDecodeError, ValueError):
        clean = False
    fields = {f: obj is not None and field_correct(f, obj.get(f), expected[f]) for f in FIELDS}
    return ItemScore(json_valid=obj is not None, clean_json=clean, fields=fields,
                     field_accuracy=sum(fields.values()) / len(FIELDS), exact_match=all(fields.values()))


def aggregate(scored: list[tuple[str, ItemScore]]) -> dict:
    """scored = [(language, ItemScore), ...] -> summary metrics."""
    def summarize(rows: list[ItemScore]) -> dict:
        return {"n": len(rows),
                "json_valid_rate": round(mean(r.json_valid for r in rows), 4),
                "clean_json_rate": round(mean(r.clean_json for r in rows), 4),
                "field_accuracy": round(mean(r.field_accuracy for r in rows), 4),
                "exact_match_rate": round(mean(r.exact_match for r in rows), 4),
                "per_field": {f: round(mean(r.fields[f] for r in rows), 4) for f in FIELDS}}
    out = {"overall": summarize([s for _, s in scored])}
    for lang in sorted({l for l, _ in scored}):
        out[lang] = summarize([s for l, s in scored if l == lang])
    return out
