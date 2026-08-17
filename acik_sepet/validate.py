from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from .product_types import load_product_types

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "data" / "v0.3" / "snapshots"


def validate(min_type_coverage: float = 0.60, min_skus: int = 300) -> None:
    specs = load_product_types()
    paths = sorted(SNAPSHOT_DIR.glob("*.csv"))
    if not paths:
        raise SystemExit("v0.3 snapshot bulunamadı")
    latest = paths[-1]
    with latest.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    by_type: dict[str, int] = defaultdict(int)
    key_types: dict[str, set[str]] = defaultdict(set)
    slot_types: dict[str, set[str]] = defaultdict(set)
    bad_prices = 0
    source_relative = 0
    for row in rows:
        by_type[row["type_id"]] += 1
        key_types[row["product_key"]].add(row["type_id"])
        slot_id = row.get("slot_id") or row["product_key"]
        slot_types[slot_id].add(row["type_id"])
        try:
            linked = row.get("linked_unit_price") or row["unit_price"]
            if float(row["unit_price"]) <= 0 or float(linked) <= 0:
                bad_prices += 1
        except (TypeError, ValueError):
            bad_prices += 1
        if row.get("source_mode") == "pinned-relative":
            source_relative += 1

    spec_by_id = {row["id"]: row for row in specs}
    viable = [
        type_id
        for type_id, count in by_type.items()
        if type_id in spec_by_id and count >= spec_by_id[type_id]["min_skus"]
    ]
    type_coverage = len(viable) / max(1, len(specs))
    duplicate_products = [key for key, type_ids in key_types.items() if len(type_ids) > 1]
    duplicate_slots = [key for key, type_ids in slot_types.items() if len(type_ids) > 1]

    print(
        f"snapshot={latest.name} rows={len(rows)} observed_types={len(by_type)}/{len(specs)} "
        f"viable_types={len(viable)}/{len(specs)} viable_coverage={type_coverage:.1%} "
        f"duplicate_products={len(duplicate_products)} duplicate_slots={len(duplicate_slots)} "
        f"bad_prices={bad_prices} source_relative={source_relative}"
    )
    if len(rows) < min_skus:
        raise SystemExit(f"SKU sayısı düşük: {len(rows)} < {min_skus}")
    if type_coverage < min_type_coverage:
        raise SystemExit(f"Ürün tipi kapsaması düşük: {type_coverage:.1%} < {min_type_coverage:.1%}")
    if duplicate_products:
        raise SystemExit(f"Aynı SKU birden fazla ürün tipinde: {duplicate_products[:5]}")
    if duplicate_slots:
        raise SystemExit(f"Aynı panel slotu birden fazla ürün tipinde: {duplicate_slots[:5]}")
    if bad_prices:
        raise SystemExit(f"Geçersiz birim/linked fiyat sayısı: {bad_prices}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-type-coverage", type=float, default=0.60)
    parser.add_argument("--min-skus", type=int, default=300)
    args = parser.parse_args()
    validate(args.min_type_coverage, args.min_skus)


if __name__ == "__main__":
    main()
