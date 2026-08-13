from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASKET_PATH = ROOT / "config" / "basket.tsv"
CATEGORIES_PATH = ROOT / "config" / "categories.json"


def _tokens(value: str | None) -> list[str]:
    return [token.strip() for token in (value or "").split(",") if token.strip()]


def load_basket(path: Path = BASKET_PATH) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    basket: list[dict[str, Any]] = []
    for row in rows:
        basket.append({
            "group": row["group"],
            "id": row["id"],
            "label": row["label"],
            "query": row["query"],
            "include_tokens": _tokens(row.get("include_tokens")),
            "exclude_tokens": _tokens(row.get("exclude_tokens")),
            "preferred_tokens": _tokens(row.get("preferred_tokens")),
            "min_match": float(row.get("min_match") or 0.5),
            "item_weight": 1.0,
        })
    return basket


def load_categories(path: Path = CATEGORIES_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["categories"]
