import csv
import hashlib
import json
from pathlib import Path

import pytest

from acik_sepet.diagnostics import build, calendar_change, rebuild
from acik_sepet.index import build_category_indices, build_main_index, build_type_indices


def _write_csv(path, rows, delimiter=","):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter=delimiter, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _spec(key, group="g", minimum=1, target=3):
    return {"id": key, "group": group, "label": key, "min_skus": minimum, "target_skus": target}


def _row(day, key, slot=None, price=100, age=0, evidence=True):
    from datetime import date, timedelta
    stamp = ((date.fromisoformat(day) - timedelta(days=age)).strftime("%d.%m.%Y") + " 12:00"
             if age is not None else "")
    source = {"source_id": "depot:shop-1", "market": "shop", "depot_name": "Test depot",
              "price": price, "index_time": stamp}
    return {"date": day, "type_id": key, "product_key": slot or key, "slot_id": slot or key,
            "unit_price": price, "linked_unit_price": price, "source_updated_at": stamp,
            "source_ids": '["depot:shop-1"]', "markets": '["shop"]', "source_count": 1,
            "source_observations": json.dumps([source]) if evidence else ""}


def _fixture(root, specs, snapshots, categories=None):
    categories = categories or [{"id": "g", "label": "Category", "weight": 1.0}]
    config = root / "config"
    config.mkdir()
    _write_csv(config / "product_types.tsv", specs, delimiter="\t")
    (config / "categories.json").write_text(json.dumps({"categories": categories}), encoding="utf-8")
    (config / "series.json").write_text(json.dumps({"baseline_date": snapshots[0][0]}), encoding="utf-8")
    data = root / "data" / "v0.4"
    for day, rows in snapshots:
        _write_csv(data / "snapshots" / f"{day}.csv", rows)
    types = build_type_indices(snapshots, specs)
    cats = build_category_indices(types, specs, categories)
    indices = build_main_index(types, cats, categories)
    for name, rows in (("index.csv", indices), ("type_indices.csv", types), ("category_indices.csv", cats)):
        _write_csv(data / name, rows)
    return data


def test_published_history_is_observed_without_rewriting_and_counts_chain_contributors():
    root = Path(__file__).resolve().parents[1]
    data = root / "data" / "v0.4"
    paths = [data / "index.csv", data / "type_indices.csv", data / "category_indices.csv",
             data / "snapshots" / "2026-09-05.csv", data / "snapshots" / "2026-09-26.csv"]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    result = build(root)
    latest = next(day for day in result["days"] if day["date"] == "2026-09-26")
    assert result["baseline_date"] == "2026-09-05"
    assert latest["coverage"] == 0.66
    assert latest["common_coverage"] == 0.66
    # 81 types are available in the included categories. Cola has returned but
    # does not enter that day's category link; only 80 types actually contribute.
    assert latest["headline_types"] == 80
    assert latest["headline_skus"] == 1354
    assert latest["available_types"] == 102
    assert latest["collected_skus"] == 1605
    assert latest["missing_categories"] == ["meat", "fruit", "vegetables"]
    assert latest["fresh_within_1_day_share"] == 1.0
    assert latest["partial_coverage"] and latest["coverage_alert"]
    assert not latest["unavailable"]
    cola = next(row for row in latest["types"] if row["type_id"] == "cola")
    assert cola["index"] is not None and not cola["headline_contributor"]
    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def test_new_category_type_and_slot_only_contribute_on_subsequent_comparison(tmp_path):
    specs = [_spec("a", "g1"), _spec("b", "g1"), _spec("c", "g1"), _spec("d", "g2")]
    categories = [{"id": "g1", "label": "One", "weight": 0.6},
                  {"id": "g2", "label": "Two", "weight": 0.4}]
    d1, d2, d3 = "2026-09-05", "2026-09-06", "2026-09-07"
    snapshots = [(d1, [_row(d1, "a"), _row(d1, "b")])]
    for day in (d2, d3):
        snapshots.append((day, [_row(day, "a"), _row(day, "a", "a2"), _row(day, "b"),
                                _row(day, "c"), _row(day, "d")]))
    _fixture(tmp_path, specs, snapshots, categories)
    result = build(tmp_path)
    day2 = result["days"][1]
    assert day2["coverage"] == 1.0
    assert day2["common_coverage"] == 0.6
    assert day2["headline_types"] == 2
    assert day2["headline_skus"] == 2
    assert not next(row for row in day2["types"] if row["type_id"] == "d")["headline_contributor"]
    assert result["latest"]["headline_types"] == 4
    assert result["latest"]["headline_skus"] == 5


def test_missing_calendar_day_is_not_a_daily_comparison(tmp_path):
    d1, d3 = "2026-09-05", "2026-09-07"
    _fixture(tmp_path, [_spec("a")], [(d1, [_row(d1, "a")]), (d3, [_row(d3, "a", price=110)])])
    result = build(tmp_path)
    assert result["latest"]["daily_change_pct"] is None
    assert result["latest"]["previous_date"] == d1
    assert calendar_change(result["days"], d3, 2) == pytest.approx(10)
    assert calendar_change(result["days"], d3, 7) is None


def test_legacy_recorded_freshness_retained_but_depot_evidence_stays_unknown(tmp_path):
    day = "2026-09-05"
    _fixture(tmp_path, [_spec("a")], [(day, [_row(day, "a", evidence=False)])])
    latest = build(tmp_path)["latest"]
    assert latest["fresh_within_1_day_share"] == 1.0
    assert latest["sources"]["auditable_skus"] == 0
    assert latest["sources"]["depots"] is None
    assert latest["sources"]["retailers"][0]["depots"] is None
    assert latest["types"][0]["collection"] is None
    assert latest["types"][0]["candidate_readiness"] is None


def test_missing_source_dates_do_not_invent_historical_freshness_or_failure(tmp_path):
    day = "2026-09-05"
    _fixture(tmp_path, [_spec("a")], [(day, [_row(day, "a", age=None, evidence=False)])])
    latest = build(tmp_path)["latest"]
    assert latest["fresh_within_1_day_share"] is None
    assert latest["freshness_alert"] is None
    assert latest["publication_checks"]["freshness"] is None
    assert latest["freshness_unknown_skus"] == 1


@pytest.mark.parametrize("age,share,unavailable", [(1, 1.0, False), (2, 0.0, False), (4, 0.0, True), (-1, 0.0, True)])
def test_freshness_thresholds_and_future_dates(tmp_path, age, share, unavailable):
    day = "2026-09-05"
    _fixture(tmp_path, [_spec("a")], [(day, [_row(day, "a", age=age)])])
    latest = build(tmp_path)["latest"]
    assert latest["fresh_within_1_day_share"] == share
    assert latest["freshness_alert"] == (share < 0.9)
    assert latest["unavailable"] == unavailable


def test_observed_and_matched_shortfalls_are_distinct_and_failed_search_is_not_disappearance(tmp_path):
    d1, d2 = "2026-09-05", "2026-09-06"
    specs = [_spec("a", minimum=2), _spec("b", minimum=2)]
    _fixture(tmp_path, specs, [
        (d1, [_row(d1, "a", "a1"), _row(d1, "a", "a2"), _row(d1, "b", "b1"), _row(d1, "b", "b2")]),
        (d2, [_row(d2, "a", "a1"), _row(d2, "b", "b2"), _row(d2, "b", "b3")]),
    ])
    report = tmp_path / "data" / "v0.4" / "collection-diagnostics" / f"{d2}.json"
    report.parent.mkdir()
    report.write_text(json.dumps({"schema_version": 1, "date": d2, "types": {
        "a": {"primary": {"status": "failed"}, "rejections": {"category": 2}, "ready_candidates": 0}
    }}), encoding="utf-8")
    latest = build(tmp_path)["latest"]
    by_type = {row["type_id"]: row for row in latest["types"]}
    assert "insufficient_observed_skus" in by_type["a"]["reasons"]
    assert "search_failed" in by_type["a"]["reasons"]
    assert "rejected_category" in by_type["a"]["reasons"]
    assert "insufficient_matched_skus" in by_type["b"]["reasons"]
    assert latest["unavailable"]


def test_failed_retry_does_not_replace_published_quality_and_serialization_is_lf(tmp_path):
    day = "2026-09-05"
    data = _fixture(tmp_path, [_spec("a")], [(day, [_row(day, "a")])])
    (data / "collection-status.json").write_text(json.dumps({"date": day, "status": "failed"}), encoding="utf-8")
    result = rebuild(tmp_path)
    assert result["latest_attempt"]["status"] == "failed"
    assert result["latest"]["unavailable"] is False
    raw = (data / "quality.json").read_bytes()
    assert b"\r\n" not in raw
    assert json.loads(raw)["schema_version"] == 1


def test_subpublication_gap_preserves_last_successful_type_comparison(tmp_path):
    d1, d2, d3 = "2026-09-05", "2026-09-06", "2026-09-07"
    _fixture(tmp_path, [_spec("a", minimum=2)], [
        (d1, [_row(d1, "a", "a1"), _row(d1, "a", "a2")]),
        (d2, [_row(d2, "a", "a1")]),
        (d3, [_row(d3, "a", "a1"), _row(d3, "a", "a2")]),
    ])
    result = build(tmp_path)
    assert result["days"][1]["unavailable"]
    assert result["latest"]["types"][0]["previous_date"] == d1
    assert result["latest"]["headline_skus"] == 2
    assert result["latest"]["daily_change_pct"] is None
