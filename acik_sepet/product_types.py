from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_TYPES_PATH = ROOT / "config" / "product_types.tsv"
CATEGORIES_PATH = ROOT / "config" / "categories.json"
API_CATEGORIES_PATH = ROOT / "config" / "api_categories.json"


def _tokens(value: str | None) -> list[str]:
    return [token.strip() for token in (value or "").split(",") if token.strip()]


def load_product_types(
    path: Path = PRODUCT_TYPES_PATH,
    api_categories_path: Path = API_CATEGORIES_PATH,
) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    api_categories = json.loads(api_categories_path.read_text(encoding="utf-8"))["types"]
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        row = {key: (value.strip() if isinstance(value, str) else value) for key, value in raw.items()}
        type_id = row["id"]
        if type_id in seen:
            raise ValueError(f"duplicate product type id: {type_id}")
        seen.add(type_id)
        category = api_categories.get(type_id)
        if not category:
            raise ValueError(f"missing API category mapping: {type_id}")
        output.append({
            "group": row["group"],
            "id": type_id,
            "label": row["label"],
            "query": row["query"],
            "unit": row["unit"],
            "target_skus": int(row.get("target_skus") or 20),
            "min_skus": int(row.get("min_skus") or 5),
            "include_tokens": _tokens(row.get("include_tokens")),
            "exclude_tokens": _tokens(row.get("exclude_tokens")),
            "type_weight": float(row.get("type_weight") or 1.0),
            "api_category_level": category["level"],
            "api_categories": list(category["values"]),
        })
    extra = sorted(set(api_categories) - seen)
    if extra:
        raise ValueError(f"unknown API category mappings: {extra}")
    return output


def load_categories(path: Path = CATEGORIES_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["categories"]
