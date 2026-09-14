from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict, Counter
from pathlib import Path

from .collect import _title_matches
from .product_types import load_product_types_for_date

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "data" / "v0.4" / "snapshots"


def validate(min_type_coverage: float = 0.60, min_skus: int = 300) -> None:
    paths = sorted(SNAPSHOT_DIR.glob("*.csv"))
    if not paths:
        raise SystemExit("v0.4 snapshot bulunamadı")
    latest = paths[-1]
    with latest.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    validate_rows(rows, latest.stem, min_type_coverage, min_skus)


def validate_rows(rows: list[dict], day: str, min_type_coverage: float = 0.60,
                  min_skus: int = 300, specs: list[dict] | None = None) -> None:
    specs = specs if specs is not None else load_product_types_for_date(day)
    effective = json.loads((ROOT / "config/series.json").read_text()).get("matching_effective_from")
    require_evidence = bool(effective and day >= effective)

    by_type: dict[str, int] = defaultdict(int)
    keys = Counter(row["product_key"] for row in rows)
    slots = Counter(row.get("slot_id") or row["product_key"] for row in rows)
    if any(n > 1 for n in keys.values()) or any(n > 1 for n in slots.values()):
        raise SystemExit("Tekrarlanan SKU/panel slotu")
    if any(row["date"] != day for row in rows):
        raise SystemExit("Snapshot tarihi ile satır tarihi uyuşmuyor")
    key_types: dict[str, set[str]] = defaultdict(set)
    slot_types: dict[str, set[str]] = defaultdict(set)
    bad_prices = 0
    bad_formulas = 0
    bad_matches: list[str] = []
    bad_categories: list[str] = []
    bad_api_units = 0
    api_unit_checks = 0
    source_relative = 0
    spec_by_id = {row["id"]: row for row in specs}
    for row in rows:
        if require_evidence and not all(row.get(key) for key in ("collected_at", "source_observations", "source_link")):
            raise SystemExit("Yeni gözlemde depot kanıtı veya tarama zamanı eksik")
        if row.get("source_observations"):
            validate_source_evidence(row)
        by_type[row["type_id"]] += 1
        key_types[row["product_key"]].add(row["type_id"])
        slot_id = row.get("slot_id") or row["product_key"]
        slot_types[slot_id].add(row["type_id"])
        try:
            linked = row.get("linked_unit_price") or row["unit_price"]
            price = float(row["price"])
            quantity = float(row["quantity"])
            observed_unit = float(row["unit_price"])
            if any(not math.isfinite(v) or v <= 0 for v in (observed_unit, float(linked), price, quantity)):
                bad_prices += 1
            elif not math.isclose(observed_unit, price / quantity, rel_tol=1e-6, abs_tol=1e-6):
                bad_formulas += 1
        except (TypeError, ValueError):
            bad_prices += 1
        api_unit = row.get("api_unit_price")
        if api_unit not in (None, ""):
            api_unit_checks += 1
            try:
                gap = abs(float(row["unit_price"]) / float(api_unit) - 1.0)
                if not math.isfinite(gap) or gap > 0.0501:
                    bad_api_units += 1
            except (TypeError, ValueError, ZeroDivisionError):
                bad_api_units += 1
        spec = spec_by_id.get(row["type_id"])
        if spec is None or not _title_matches(row.get("title", ""), spec):
            bad_matches.append(row.get("product_key", ""))
        elif row.get("matched_category") not in spec["api_categories"]:
            bad_categories.append(row.get("product_key", ""))
        elif row.get("category_level") != spec["api_category_level"]:
            bad_categories.append(row.get("product_key", ""))
        if row.get("source_mode") == "pinned-relative":
            source_relative += 1

    viable = [
        type_id
        for type_id, count in by_type.items()
        if type_id in spec_by_id and count >= spec_by_id[type_id]["min_skus"]
    ]
    type_coverage = len(viable) / max(1, len(specs))
    duplicate_products = [key for key, type_ids in key_types.items() if len(type_ids) > 1]
    duplicate_slots = [key for key, type_ids in slot_types.items() if len(type_ids) > 1]
    viable_set = set(viable)
    group_coverage = {
        group: sum(spec["id"] in viable_set for spec in specs if spec["group"] == group)
        / sum(1 for spec in specs if spec["group"] == group)
        for group in sorted({spec["group"] for spec in specs})
    }

    print(
        f"snapshot={day}.csv rows={len(rows)} observed_types={len(by_type)}/{len(specs)} "
        f"viable_types={len(viable)}/{len(specs)} viable_coverage={type_coverage:.1%} "
        f"duplicate_products={len(duplicate_products)} duplicate_slots={len(duplicate_slots)} "
        f"bad_prices={bad_prices} bad_formulas={bad_formulas} bad_matches={len(bad_matches)} "
        f"bad_categories={len(bad_categories)} api_unit_checks={api_unit_checks} "
        f"bad_api_units={bad_api_units} source_relative={source_relative}"
    )
    print("group_coverage=" + ",".join(f"{key}:{value:.0%}" for key, value in group_coverage.items()))
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
    if bad_formulas:
        raise SystemExit(f"Paket/birim fiyat formülü bozuk satır sayısı: {bad_formulas}")
    if bad_matches:
        raise SystemExit(f"Başlık kuralını geçemeyen SKU: {bad_matches[:5]}")
    if bad_categories:
        raise SystemExit(f"API kategori kuralını geçemeyen SKU: {bad_categories[:5]}")
    if bad_api_units:
        raise SystemExit(f"Market Fiyatı birim fiyatıyla uyuşmayan satır sayısı: {bad_api_units}")


def validate_source_evidence(row: dict) -> None:
    """Recompute the linked price from stored depot observations and link inputs."""
    import json
    from statistics import median
    observations = json.loads(row["source_observations"])
    link = json.loads(row["source_link"])
    prices: dict[str, list[float]] = defaultdict(list)
    for offer in observations:
        price = float(offer["price"])
        if not math.isfinite(price) or price <= 0:
            raise SystemExit("Geçersiz depot fiyatı")
        prices[offer["source_id"]].append(price)
    current = {key: median(values) for key, values in prices.items()}
    if link["mode"] == "pinned-relative":
        basis = link["previous_prices"]
        common = sorted(set(basis) & set(current))
        if not common:
            raise SystemExit("Depot bağlantısında ortak gözlem yok")
        ratios = [current[key] / float(basis[key]) for key in common]
        package = float(link["previous_level"]) * math.exp(sum(math.log(r) for r in ratios) / len(ratios))
    else:
        package = median(float(offer["price"]) for offer in observations)
    expected = package / float(row["quantity"]) * float(link["link_factor"])
    if not math.isclose(expected, float(row["linked_unit_price"]), rel_tol=1e-6, abs_tol=1e-6):
        raise SystemExit(f"Depot kanıtıyla bağlı fiyat uyuşmuyor: {row['product_key']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-type-coverage", type=float, default=0.60)
    parser.add_argument("--min-skus", type=int, default=300)
    args = parser.parse_args()
    validate(args.min_type_coverage, args.min_skus)


if __name__ == "__main__":
    main()
