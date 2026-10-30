import json
from functools import lru_cache
from pathlib import Path
from .schemas import ModelSpec


@lru_cache
def load_catalog() -> list[ModelSpec]:
    raw = json.loads((Path(__file__).parent / "data" / "catalog.json").read_text())
    return [ModelSpec(**m) for m in raw]
