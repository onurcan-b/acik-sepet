from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from .product_types import load_categories, load_product_types

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "v0.4"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
TYPE_PATH = DATA_DIR / "type_indices.csv"
CATEGORY_PATH = DATA_DIR / "category_indices.csv"
INDEX_PATH = DATA_DIR / "index.csv"


def geometric_mean(values: list[float]) -> float:
    if not values or any(value <= 0 for value in values):
        raise ValueError("geometric mean requires positive values")
    return math.exp(sum(math.log(value) for value in values) / len(values))


def load_snapshot(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["unit_price"] = float(row["unit_price"])
        linked = row.get("linked_unit_price")
        row["linked_unit_price"] = float(linked) if linked not in (None, "") else row["unit_price"]
        row["slot_id"] = row.get("slot_id") or row["product_key"]
        row["price"] = float(row["price"])
        row["quantity"] = float(row["quantity"])
        row["offer_count"] = int(row["offer_count"])
    return rows


def _by_type(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Map stable panel slots to continuity-adjusted unit prices."""
    output: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        price = float(row.get("linked_unit_price", row["unit_price"]))
        slot_id = str(row.get("slot_id") or row["product_key"])
        if price > 0:
            output[row["type_id"]][slot_id] = price
    return output


def build_type_indices(snapshots: list[tuple[str, list[dict[str, Any]]]], specs: list[dict[str, Any]], min_coverage: float = 0.50) -> list[dict[str, Any]]:
    if not snapshots:
        return []
    baseline_date, baseline_rows = snapshots[0]
    baseline = _by_type(baseline_rows)
    output: list[dict[str, Any]] = []

    for date, rows in snapshots:
        current = _by_type(rows)
        for spec in specs:
            base_prices = baseline.get(spec["id"], {})
            current_prices = current.get(spec["id"], {})
            common = sorted(set(base_prices) & set(current_prices))
            base_n = len(base_prices)
            coverage = len(common) / base_n if base_n else 0.0
            value = None
            if base_n >= spec["min_skus"] and len(common) >= spec["min_skus"] and coverage >= min_coverage:
                relatives = [current_prices[key] / base_prices[key] for key in common]
                value = round(100.0 * geometric_mean(relatives), 4)
            output.append({
                "date": date,
                "type_id": spec["id"],
                "label": spec["label"],
                "group": spec["group"],
                "index": value,
                "coverage": round(coverage, 4),
                "skus": len(common),
                "baseline_skus": base_n,
                "baseline_date": baseline_date,
            })
    return output


def build_category_indices(type_rows: list[dict[str, Any]], specs: list[dict[str, Any]], categories: list[dict[str, Any]], min_coverage: float = 0.60) -> list[dict[str, Any]]:
    dates = sorted({row["date"] for row in type_rows})
    by_date_type = {(row["date"], row["type_id"]): row for row in type_rows}
    output: list[dict[str, Any]] = []

    for date in dates:
        for category in categories:
            # The denominator is the configured basket, not merely the types
            # that happened to survive on baseline day. Missing types must be
            # visible as missing coverage.
            members = [spec for spec in specs if spec["group"] == category["id"]]
            total_weight = sum(float(spec.get("type_weight", 1.0)) for spec in members)
            available = []
            for spec in members:
                row = by_date_type.get((date, spec["id"]))
                if row and row["index"] is not None:
                    available.append((spec, row))
            available_weight = sum(float(spec.get("type_weight", 1.0)) for spec, _ in available)
            coverage = available_weight / total_weight if total_weight else 0.0
            value = None
            if available and coverage >= min_coverage:
                relative = sum(float(spec.get("type_weight", 1.0)) * (float(row["index"]) / 100.0) for spec, row in available) / available_weight
                value = round(100.0 * relative, 4)
            output.append({
                "date": date,
                "group_id": category["id"],
                "label": category["label"],
                "scope": category.get("scope", ""),
                "weight": float(category["weight"]),
                "index": value,
                "coverage": round(coverage, 4),
                "types": len(available),
                "baseline_types": len(members),
            })
    return output


def build_main_index(type_rows: list[dict[str, Any]], category_rows: list[dict[str, Any]], categories: list[dict[str, Any]], min_coverage: float = 0.60) -> list[dict[str, Any]]:
    dates = sorted({row["date"] for row in category_rows})
    category_map = {(row["date"], row["group_id"]): row for row in category_rows}
    type_by_date = defaultdict(list)
    for row in type_rows:
        type_by_date[row["date"]].append(row)
    baseline_date = dates[0] if dates else None
    output = []

    for date in dates:
        available = []
        total_weight = sum(float(category["weight"]) for category in categories)
        for category in categories:
            row = category_map.get((date, category["id"]))
            if row and row["index"] is not None:
                available.append((category, row))
        available_weight = sum(float(category["weight"]) for category, _ in available)
        coverage = available_weight / total_weight if total_weight else 0.0
        value = None
        if available and coverage >= min_coverage:
            relative = sum(float(category["weight"]) * (float(row["index"]) / 100.0) for category, row in available) / available_weight
            value = round(100.0 * relative, 4)
        active_types = [row for row in type_by_date[date] if row["index"] is not None]
        output.append({
            "date": date,
            "index": value,
            "coverage": round(coverage, 4),
            "types": len(active_types),
            "skus": sum(int(row["skus"]) for row in active_types),
            "baseline_date": baseline_date,
        })
    return output


def _write(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key, "") for key in fields})


def rebuild() -> list[dict[str, Any]]:
    specs = load_product_types()
    categories = load_categories()
    snapshots = [(path.stem, load_snapshot(path)) for path in sorted(SNAPSHOT_DIR.glob("*.csv"))]
    type_rows = build_type_indices(snapshots, specs)
    category_rows = build_category_indices(type_rows, specs, categories)
    index_rows = build_main_index(type_rows, category_rows, categories)
    _write(TYPE_PATH, type_rows, ["date", "type_id", "label", "group", "index", "coverage", "skus", "baseline_skus", "baseline_date"])
    _write(CATEGORY_PATH, category_rows, ["date", "group_id", "label", "scope", "weight", "index", "coverage", "types", "baseline_types"])
    _write(INDEX_PATH, index_rows, ["date", "index", "coverage", "types", "skus", "baseline_date"])
    print(f"type_rows={len(type_rows)} category_rows={len(category_rows)} index_rows={len(index_rows)}")
    return index_rows


if __name__ == "__main__":
    rebuild()
