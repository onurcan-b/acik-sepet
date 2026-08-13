from __future__ import annotations

import csv
import json
from pathlib import Path

from .basket import load_basket, load_categories
from .index import snapshot_item_prices

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
OUTPUT = ROOT / "data" / "subindices.csv"


def build_subindices(snapshots, basket, categories, min_group_coverage=0.40):
    if not snapshots:
        return []
    snapshots = sorted(snapshots, key=lambda row: row["date"])
    baseline_snapshot = next((row for row in snapshots if snapshot_item_prices(row)), None)
    if baseline_snapshot is None:
        return []
    baseline = snapshot_item_prices(baseline_snapshot)
    groups = {row["id"]: [item for item in basket if item["group"] == row["id"]] for row in categories}
    rows = []

    for snapshot in snapshots:
        current = snapshot_item_prices(snapshot)
        for category in categories:
            target = groups[category["id"]]
            available = [item for item in target if item["id"] in baseline and item["id"] in current]
            coverage = len(available) / len(target) if target else 0.0
            value = None
            if available and coverage >= min_group_coverage:
                relatives = [current[item["id"]] / baseline[item["id"]] for item in available]
                value = round(100.0 * sum(relatives) / len(relatives), 4)
            rows.append({
                "date": snapshot["date"],
                "group_id": category["id"],
                "label": category["label"],
                "scope": category.get("scope", ""),
                "weight": category["weight"],
                "index": value,
                "coverage": round(coverage, 4),
                "items": len(available),
                "target_items": len(target),
                "baseline_date": baseline_snapshot["date"],
            })

        food_categories = [row for row in categories if row.get("scope") == "food"]
        food_weight_total = sum(float(row["weight"]) for row in food_categories)
        numerator = 0.0
        covered_weight = 0.0
        available_items = 0
        target_items = 0
        for category in food_categories:
            target = groups[category["id"]]
            target_items += len(target)
            available = [item for item in target if item["id"] in baseline and item["id"] in current]
            if not available:
                continue
            group_coverage = len(available) / len(target)
            if group_coverage < min_group_coverage:
                continue
            group_relative = sum(current[item["id"]] / baseline[item["id"]] for item in available) / len(available)
            weight = float(category["weight"])
            numerator += weight * group_relative
            covered_weight += weight
            available_items += len(available)
        food_coverage = covered_weight / food_weight_total if food_weight_total else 0.0
        food_value = round(100.0 * numerator / covered_weight, 4) if covered_weight > 0 and food_coverage >= 0.60 else None
        rows.append({
            "date": snapshot["date"],
            "group_id": "food_total",
            "label": "Gıda ve alkolsüz içecekler",
            "scope": "food_total",
            "weight": food_weight_total,
            "index": food_value,
            "coverage": round(food_coverage, 4),
            "items": available_items,
            "target_items": target_items,
            "baseline_date": baseline_snapshot["date"],
        })
    return rows


def main():
    basket = load_basket()
    categories = load_categories()
    snapshots = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(SNAPSHOT_DIR.glob("*.json"))]
    rows = build_subindices(snapshots, basket, categories)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fields = ["date", "group_id", "label", "scope", "weight", "index", "coverage", "items", "target_items", "baseline_date"]
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key, "") for key in fields})
    print(f"subindex_rows={len(rows)}")


if __name__ == "__main__":
    main()
