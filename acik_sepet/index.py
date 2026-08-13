from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .basket import load_basket, load_categories
from .grouping import allocate

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
INDEX_PATH = ROOT / "data" / "index.csv"


def snapshot_item_prices(snapshot: dict[str, Any]) -> dict[str, float]:
    rows = snapshot.get("items") or ((snapshot.get("locations") or {}).get("national") or {}).get("items") or {}
    return {item_id: float(item["price_median"]) for item_id, item in rows.items() if isinstance(item.get("price_median"), (int, float)) and item["price_median"] > 0}


def compute_series(snapshots: list[dict[str, Any]], basket: list[dict[str, Any]], min_coverage: float = 0.60) -> list[dict[str, Any]]:
    if not snapshots:
        return []
    snapshots = sorted(snapshots, key=lambda row: row["date"])
    weights = {item["id"]: float(item.get("weight", 1.0)) for item in basket}
    baseline_prices = None
    baseline_date = None
    rows = []
    for snapshot in snapshots:
        prices = snapshot_item_prices(snapshot)
        if baseline_prices is None:
            if not prices:
                continue
            baseline_prices = prices.copy()
            baseline_date = snapshot["date"]
        comparable = [item_id for item_id in weights if item_id in prices and item_id in baseline_prices]
        available_weight = sum(weights[item_id] for item_id in comparable)
        total_weight = sum(weights.values()) or 1.0
        coverage = available_weight / total_weight
        value = None
        if comparable and coverage >= min_coverage:
            relative = sum(weights[item_id] * prices[item_id] / baseline_prices[item_id] for item_id in comparable) / available_weight
            value = round(100 * relative, 4)
        rows.append({"date": snapshot["date"], "index": value, "coverage": round(coverage, 4), "items": len(comparable), "baseline_date": baseline_date})
    return rows


def rebuild_index() -> list[dict[str, Any]]:
    basket = allocate(load_basket(), load_categories())
    snapshots = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(SNAPSHOT_DIR.glob("*.json"))]
    rows = compute_series(snapshots, basket)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "index", "coverage", "items", "baseline_date"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "index": "" if row["index"] is None else row["index"]})
    print(f"index_rows={len(rows)}")
    return rows


if __name__ == "__main__":
    rebuild_index()
