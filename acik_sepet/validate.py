from __future__ import annotations

import argparse
import json
from pathlib import Path

from .basket import load_basket, load_categories

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "data" / "snapshots"


def validate(min_coverage=0.60):
    basket = load_basket()
    categories = load_categories()
    ids = [item["id"] for item in basket]
    assert len(basket) == 150, f"expected 150 items, got {len(basket)}"
    assert len(ids) == len(set(ids)), "duplicate item IDs"
    assert abs(sum(float(c["weight"]) for c in categories) - 1.0) < 1e-9, "weights must sum to 1"
    assert {item["group"] for item in basket} == {c["id"] for c in categories}, "group mismatch"
    paths = sorted(SNAPSHOT_DIR.glob("*.json"))
    assert paths, "no snapshot"
    snapshot = json.loads(paths[-1].read_text(encoding="utf-8"))
    items = snapshot.get("items") or {}
    assert all(isinstance(row.get("price_median"), (int, float)) and row["price_median"] > 0 for row in items.values()), "invalid price"
    coverage = len(items) / len(basket)
    errors = snapshot.get("errors") or []
    counts = {}
    for row in errors:
        key = row.get("error", "unknown")
        counts[key] = counts.get(key, 0) + 1
    print(f"basket={len(basket)} matched={len(items)} coverage={coverage:.1%} errors={len(errors)}")
    if counts:
        print("error_counts=" + json.dumps(counts, ensure_ascii=False))
    assert coverage >= min_coverage, f"coverage {coverage:.1%} below {min_coverage:.0%}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-coverage", type=float, default=0.60)
    args = parser.parse_args()
    validate(args.min_coverage)
