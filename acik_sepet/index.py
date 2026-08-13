from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASKET_PATH = ROOT / "config" / "basket.json"
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
INDEX_PATH = ROOT / "data" / "index.csv"


def load_basket(path: Path = BASKET_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_item_prices(snapshot: dict[str, Any]) -> dict[str, float]:
    """Collapse cities to a national item price using the median city price."""
    by_item: dict[str, list[float]] = {}
    for location in (snapshot.get("locations") or {}).values():
        for item_id, item in (location.get("items") or {}).items():
            price = item.get("price_median")
            if isinstance(price, (int, float)) and price > 0:
                by_item.setdefault(item_id, []).append(float(price))
    return {item_id: float(median(values)) for item_id, values in by_item.items() if values}


def compute_series(
    snapshots: list[dict[str, Any]],
    basket: list[dict[str, Any]],
    min_coverage: float = 0.5,
) -> list[dict[str, Any]]:
    if not snapshots:
        return []
    snapshots = sorted(snapshots, key=lambda row: row["date"])
    weights = {item["id"]: float(item.get("weight", 1.0)) for item in basket}

    baseline_prices: dict[str, float] | None = None
    baseline_date: str | None = None
    rows: list[dict[str, Any]] = []

    for snapshot in snapshots:
        prices = snapshot_item_prices(snapshot)
        if baseline_prices is None:
            if not prices:
                continue
            baseline_prices = prices.copy()
            baseline_date = snapshot["date"]

        comparable = [item_id for item_id in weights if item_id in prices and item_id in baseline_prices]
        total_items = max(1, len(weights))
        coverage = len(comparable) / total_items
        if coverage < min_coverage:
            rows.append({
                "date": snapshot["date"],
                "index": None,
                "coverage": round(coverage, 4),
                "items": len(comparable),
                "baseline_date": baseline_date,
            })
            continue

        weight_sum = sum(weights[item_id] for item_id in comparable)
        relative = sum(
            weights[item_id] * (prices[item_id] / baseline_prices[item_id])
            for item_id in comparable
        ) / weight_sum
        rows.append({
            "date": snapshot["date"],
            "index": round(100.0 * relative, 4),
            "coverage": round(coverage, 4),
            "items": len(comparable),
            "baseline_date": baseline_date,
        })
    return rows


def rebuild_index() -> list[dict[str, Any]]:
    basket = load_basket()
    snapshots = []
    for path in sorted(SNAPSHOT_DIR.glob("*.json")):
        snapshots.append(json.loads(path.read_text(encoding="utf-8")))
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
