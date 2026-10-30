import hashlib
import json
from pathlib import Path

DATA = Path(__file__).parent / "data"
REQUIRED = {"invoice_number", "invoice_date", "vendor_name", "total_amount", "currency"}


def load_dataset(name: str = "invoices_v1.jsonl") -> tuple[list[dict], str]:
    """Returns (items, sha256). Store the hash with every benchmark run for reproducibility."""
    raw = (DATA / name).read_bytes()
    items = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    ids = [i["id"] for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate ids in dataset")
    for it in items:
        if set(it["expected"]) != REQUIRED:
            raise ValueError(f"{it['id']}: expected fields must be exactly {sorted(REQUIRED)}")
    return items, hashlib.sha256(raw).hexdigest()
