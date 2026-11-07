from datetime import date
import csv
import json

import pytest

from acik_sepet.ecb_repricing import (
    compute_day, exclude_confirmed_sales, load_observations, run,
)


def _key(sku, store="depot:one", size=1.0):
    return ("rice", sku, store, "kg", size)


CATEGORIES = [
    {"id": "bread_cereals", "label": "Grains", "scope": "food", "weight": 0.8},
    {"id": "personal_paper", "label": "Personal care", "scope": "nonfood", "weight": 0.2},
]


def test_frequency_magnitude_and_food_breadth():
    old = {
        _key("a"): ("bread_cereals", 100.0),
        _key("b"): ("bread_cereals", 200.0),
        _key("c"): ("bread_cereals", 300.0),
        _key("d"): ("bread_cereals", 400.0),
    }
    new = {
        _key("a"): ("bread_cereals", 110.0),
        _key("b"): ("bread_cereals", 180.0),
        _key("c"): ("bread_cereals", 300.0),
        _key("d"): ("bread_cereals", 400.0),
    }
    headline, category = compute_day(
        {date(2026, 9, 30): old, date(2026, 10, 1): new},
        CATEGORIES, date(2026, 10, 1), min_category_quotes=1)
    assert headline["comparable_quotes"] == 4
    assert headline["up_frequency_pct"] == pytest.approx(25)
    assert headline["down_frequency_pct"] == pytest.approx(25)
    assert headline["unchanged_frequency_pct"] == pytest.approx(50)
    assert headline["avg_increase_pct"] == pytest.approx(10)
    assert headline["avg_decrease_pct"] == pytest.approx(-10)
    assert headline["net_change_pct"] == pytest.approx(0)
    assert headline["category_coverage_pct"] == pytest.approx(80)
    assert headline["breadth_10pct_food_pct"] == pytest.approx(100)
    assert len(category) == 1


def test_unchanged_sku_but_changed_store_or_pack_is_not_repricing():
    observations = {
        date(2026, 9, 30): {_key("a"): ("bread_cereals", 100.0)},
        date(2026, 10, 1): {
            _key("a", store="depot:two"): ("bread_cereals", 500.0),
            _key("a", size=0.5): ("bread_cereals", 200.0),
        },
    }
    result, _ = compute_day(observations, CATEGORIES, date(2026, 10, 1),
                            min_category_quotes=1)
    assert result is None


def test_confirmed_temporary_sale_drops_discount_not_rebound():
    observations = {
        date(2026, 9, 30): {_key("a"): ("bread_cereals", 100.0)},
        date(2026, 10, 1): {_key("a"): ("bread_cereals", 80.0)},
        date(2026, 10, 2): {_key("a"): ("bread_cereals", 80.0)},
        date(2026, 10, 3): {_key("a"): ("bread_cereals", 100.0)},
    }
    filtered, count = exclude_confirmed_sales(observations)
    assert count == 2
    assert _key("a") not in filtered[date(2026, 10, 1)]
    assert _key("a") not in filtered[date(2026, 10, 2)]
    assert _key("a") in filtered[date(2026, 10, 3)]


def test_active_discount_is_not_prematurely_removed():
    observations = {
        date(2026, 9, 30): {_key("a"): ("bread_cereals", 100.0)},
        date(2026, 10, 1): {_key("a"): ("bread_cereals", 80.0)},
    }
    filtered, count = exclude_confirmed_sales(observations)
    assert count == 0
    assert _key("a") in filtered[date(2026, 10, 1)]


def test_load_store_quotes_rejects_stale_and_unknown_store(tmp_path):
    day = tmp_path / "2026-10-01.csv"
    columns = ["group", "type_id", "product_key", "quantity", "unit",
               "source_count", "source_observations"]
    rows = [
        {"group": "bread_cereals", "type_id": "rice", "product_key": "a",
         "quantity": "1", "unit": "kg", "source_count": "2",
         "source_observations": json.dumps([
             {"source_id": "depot:one", "api_unit_price": 100, "index_time": "01.10.2026 08:00"},
             {"source_id": "depot:two", "api_unit_price": 150, "index_time": "28.09.2026 08:00"},
         ])},
    ]
    with day.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, columns)
        writer.writeheader()
        writer.writerows(rows)
    loaded = load_observations(tmp_path)
    assert loaded[date(2026, 10, 1)] == {_key("a"): ("bread_cereals", 100.0)}


def test_full_offline_rebuild_writes_csv_json_and_svg(tmp_path):
    snapshots = tmp_path / "snapshots"
    output = tmp_path / "out"
    snapshots.mkdir()
    categories_file = tmp_path / "categories.json"
    categories_file.write_text(json.dumps({"categories": CATEGORIES}))
    columns = ["group", "type_id", "product_key", "quantity", "unit",
               "source_count", "source_observations"]
    for day, factor in [("2026-09-30", 1.0), ("2026-10-01", 1.1)]:
        with (snapshots / f"{day}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, columns)
            writer.writeheader()
            for i in range(6):
                writer.writerow({
                    "group": "bread_cereals", "type_id": "rice",
                    "product_key": f"p{i}", "quantity": 1, "unit": "kg",
                    "source_count": 1, "source_observations": json.dumps([{
                        "source_id": f"depot:{i}", "api_unit_price": 100 * factor,
                        "index_time": day[8:10] + "." + day[5:7] + "." + day[:4] + " 08:00",
                    }]),
                })
    result = run(snapshots, categories_file, output)
    assert result["latest"]["comparable_quotes"] == 6
    assert result["latest"]["up_frequency_pct"] == pytest.approx(100)
    assert (output / "daily_repricing.csv").exists()
    assert (output / "category_repricing.csv").exists()
    assert (output / "repricing.svg").exists()
    assert (output / "latest.md").exists()


def test_raw_quality_audit_flags_large_jumps_and_source_concentration():
    from acik_sepet.ecb_repricing import audit_current_month
    obs = {
        date(2026, 10, 31): {
            _key("a", "depot:migros-1"): ("bread_cereals", 100),
            _key("b", "depot:migros-1"): ("bread_cereals", 100),
        },
        date(2026, 11, 6): {
            _key("a", "depot:migros-1"): ("bread_cereals", 200),
            _key("b", "depot:migros-1"): ("bread_cereals", 100),
        },
    }
    audit = audit_current_month(obs, date(2026, 11, 6))
    assert audit["matched_quotes_before_outlier_exclusion"] == 2
    assert audit["large_moves_20pct_count"] == 1
    assert audit["large_moves_20pct_share"] == pytest.approx(50)
    assert audit["near_exact_2x_count"] == 1
    assert audit["by_retailer"]["migros"]["matched"] == 2


def test_equal_elapsed_month_comparison_and_root_readme_not_mutated(tmp_path):
    from acik_sepet.ecb_repricing import run
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    categories_file = tmp_path / "categories.json"
    categories_file.write_text(json.dumps({"categories": CATEGORIES}))
    cols = ["group", "type_id", "product_key", "quantity", "unit",
            "source_count", "source_observations"]
    for day, factor in [
        ("2026-09-30", 1), ("2026-10-06", 1.2),
        ("2026-10-31", 1.2), ("2026-11-06", 1.3),
    ]:
        with (snapshots / (day + ".csv")).open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, cols)
            writer.writeheader()
            for i in range(5):
                writer.writerow({
                    "group": "bread_cereals", "type_id": "rice",
                    "product_key": f"p{i}", "quantity": 1, "unit": "kg",
                    "source_count": 1, "source_observations": json.dumps([{
                        "source_id": f"depot:{i}", "api_unit_price": 100 * factor,
                        "index_time": day[8:10] + "." + day[5:7] + "." + day[:4] + " 08:00",
                    }]),
                })
    result = run(snapshots, categories_file, tmp_path / "out")
    latest = result["latest"]
    assert latest["prior_month_comparison_date"] == "2026-10-06"
    assert latest["up_vs_prior_month_same_day_pp"] is not None
    assert (tmp_path / "out" / "breadth.svg").exists()
    assert (tmp_path / "out" / "quality.json").exists()
