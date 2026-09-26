"""Prospective recovery invariants; synthetic evidence, no network or sleeps."""
import copy
import csv
import json
from datetime import date, datetime, timedelta

import pytest

from acik_sepet import collect, recovery
from acik_sepet.index import build_type_indices
from acik_sepet.validate import validate_source_evidence


def spec(**changes):
    return {"id": "beef_mince", "label": "Dana kıyma", "group": "meat", "query": "dana kıyma",
            "unit": "mass", "target_skus": 5, "min_skus": 1, "include_tokens": ["dana", "kıyma"],
            "exclude_tokens": [], "api_category_level": "sub_category", "api_categories": ["Kıyma"], **changes}


def item(key="old", price=100, extra=None):
    depots = [{"depotId": "one", "price": price, "unitPriceValue": price, "marketAdi": "A"}]
    if extra is not None:
        depots.append({"depotId": "two", "price": extra, "unitPriceValue": extra, "marketAdi": "B"})
    return {"id": key, "title": "Dana Kıyma 1 Kg", "refinedVolumeOrWeight": "1 KG",
            "categories": ["Kıyma"], "productDepotInfoList": depots}


def observe(state, evidence, items, day, settings=None, complete=True, absence_complete=None):
    settings = settings or spec()
    report = recovery.record_pool(evidence, settings, items, day, complete)
    claimed = {row["product_key"] for row in state["skus"]}
    rows, policy = recovery.observe_type(items, settings, state, claimed, day, {},
                                         evidence["types"][settings["id"]], complete=complete,
                                         absence_complete=absence_complete)
    for row in rows:
        validate_source_evidence(row)
        row["type_id"] = settings["id"]
    return rows, {**report, **policy}


def test_topups_above_minimum_need_three_distinct_complete_dates_and_daily_cap():
    settings = spec()
    state, original = collect._initialize_type([item()], settings, set(), "2026-09-26")
    evidence = {}
    pool = [item()] + [item(str(number), 900 + number) for number in range(6)]
    for day in ["2026-09-27", "2026-09-27", "2026-09-28"]:
        rows, report = observe(state, evidence, pool, day)
        assert len(rows) == 1
    # Truncated discovery does not qualify the third day.
    rows, _ = observe(state, evidence, pool, "2026-09-29", complete=False)
    assert len(rows) == 1
    rows, report = observe(state, evidence, pool, "2026-09-29")
    assert len(rows) == 2 and report["additions_today"] == 1
    rows_again, report_again = observe(state, evidence, pool, "2026-09-29")
    assert len(rows_again) == 2 and report_again["additions_today"] == 1
    # Expensive new slots cannot move the type index on their admission day.
    original[0]["type_id"] = settings["id"]
    indices = build_type_indices([("2026-09-26", original), ("2026-09-29", rows)], [settings])
    assert indices[-1]["index"] == 100
    following, _ = observe(state, evidence, pool, "2026-09-30")
    assert len(following) == 3


def test_depot_admission_has_no_jump_or_same_day_contamination_then_recovers_connection():
    state, _ = collect._initialize_type([item()], spec(), set(), "2026-09-26")
    evidence = {}
    for day in ["2026-09-27", "2026-09-28", "2026-09-29"]:
        rows, _ = observe(state, evidence, [item(extra=1000)], day)
        assert rows[0]["linked_unit_price"] == 100
    assert state["skus"][0]["source_last_prices"] == {"depot:one": 100, "depot:two": 1000}
    refreshed, _ = observe(state, evidence, [item(extra=2000)], "2026-09-29")
    assert refreshed[0]["linked_unit_price"] == 100
    new_only = item(extra=2200)
    new_only["productDepotInfoList"].pop(0)
    recovered, _ = observe(state, evidence, [new_only], "2026-09-30")
    assert recovered[0]["linked_unit_price"] == 110


def test_depot_admission_requires_real_overlap_and_failed_refresh_preserves_state():
    state, _ = collect._initialize_type([item()], spec(), set(), "2026-09-26")
    evidence = {}
    orphan = item(extra=1000)
    orphan["productDepotInfoList"].pop(0)
    for day in ["2026-09-27", "2026-09-28", "2026-09-29"]:
        rows, report = observe(state, evidence, [orphan], day)
        assert rows == [] and report["lost_depot_connections"] == 1
    assert state["skus"][0]["source_ids"] == ["depot:one"]


def test_overlap_replacement_preserves_intervening_change_and_shared_turnover_cap():
    settings = spec(target_skus=1)
    state, _ = collect._initialize_type([item()], settings, set(), "2026-09-26")
    evidence = {}
    for offset in range(3):
        day = (date(2026, 9, 27) + timedelta(days=offset)).isoformat()
        observe(state, evidence, [item(), item("replacement", 200)], day, settings)
    state["skus"][0]["missing_streak"] = 6
    rows, report = observe(state, evidence, [item("replacement", 220)], "2026-09-30", settings)
    assert len(rows) == 1 and rows[0]["product_key"] == "id:replacement"
    assert rows[0]["linked_unit_price"] == pytest.approx(110)
    assert rows[0]["slot_id"] == "id:old"
    assert state["skus"][0]["overlap_date"] == "2026-09-29"
    assert report["replacements_today"] == 1 and report["turnover_allowance"] == 1
    rows, report = observe(state, evidence, [item("replacement", 220)], "2026-09-30", settings)
    assert report["replacements_today"] == 1


def test_replacement_without_overlap_remains_missing_even_with_last_known_level():
    settings = spec(target_skus=1)
    state, _ = collect._initialize_type([item()], settings, set(), "2026-09-26")
    state["skus"][0]["missing_streak"] = 7
    evidence = {}
    for day in ["2026-09-27", "2026-09-28", "2026-09-29"]:
        rows, report = observe(state, evidence, [item("replacement", 220)], day, settings)
    assert not rows and report["unavailable_replacements"] == 1
    assert state["skus"][0]["product_key"] == "id:old"


def test_truncated_pool_does_not_count_absence_or_qualify_candidates():
    state, _ = collect._initialize_type([item()], spec(), set(), "2026-09-26")
    evidence = {}
    for day in ["2026-09-27", "2026-09-28", "2026-09-29"]:
        rows, report = observe(state, evidence, [item("candidate")], day, complete=False)
        assert not rows and report["ready_candidates"] == 0
    assert state["skus"][0]["missing_streak"] == 0
    legacy = copy.deepcopy(state)
    assert collect._observe_type([], spec(), legacy, {"id:old"}, "2026-09-30", {}, complete=False) == []
    assert legacy["skus"][0]["missing_streak"] == 0


def test_positive_evidence_from_successfully_capped_queries_qualifies_without_asserting_absence():
    state, _ = collect._initialize_type([item()], spec(), set(), "2026-09-26")
    evidence = {}
    for day in ["2026-09-27", "2026-09-28", "2026-09-29"]:
        rows, report = observe(state, evidence, [item("candidate")], day, complete=True, absence_complete=False)
    assert state["skus"][0]["missing_streak"] == 0
    assert [row["product_key"] for row in rows] == ["id:candidate"]
    assert report["ready_candidates"] == 1


def test_evidence_retention_is_fourteen_calendar_days_and_incomplete_refresh_cannot_erase_it():
    evidence = {}
    recovery.record_pool(evidence, spec(), [item("candidate")], "2026-09-01", True)
    recovery.record_pool(evidence, spec(), [item("candidate", 110)], "2026-09-01", False)
    assert evidence["types"][spec()["id"]]["products"]["id:candidate"]["dates"]["2026-09-01"]["unit_price"] == 100
    recovery.record_pool(evidence, spec(), [], "2026-09-15", True)
    assert evidence["types"][spec()["id"]]["products"] == {}


def test_matching_diagnostics_do_not_weaken_rules():
    cases = [item(str(index)) for index in range(5)]
    cases[0]["categories"] = ["Alakasız"]
    cases[1]["title"] = "Tavuk 1 Kg"
    cases[2]["refinedVolumeOrWeight"] = "2 Kg"
    cases[3]["productDepotInfoList"][0]["unitPriceValue"] = 200
    cases[4]["productDepotInfoList"] = []
    report = recovery.record_pool({}, spec(), cases, "2026-09-27", True)
    assert report["accepted_candidates"] == 0
    assert report["rejections"] == {"category": 1, "title": 1, "quantity": 1, "unit_price": 1, "no_offers": 1}


def test_activation_needs_seven_complete_validated_distinct_days_and_future_effective_date(tmp_path):
    evidence = {"shadow_days": {}}
    state_path = tmp_path / "state/v0.4-discovery.json"
    shadow_path = tmp_path / "state/v0.4-shadow-panels.json"
    recovery.write_json(shadow_path, {"types": {}})
    for offset in range(7):
        day = (date(2026, 9, 27) + timedelta(days=offset)).isoformat()
        evidence["shadow_days"][day] = {"complete": True, "shadow_validated": True, "validated": False, "pending_qualified": True}
    recovery.write_json(state_path, evidence)
    with pytest.raises(ValueError, match="Seven complete"):
        recovery.activate(tmp_path, "2026-10-04")
    for day in evidence["shadow_days"]:
        snapshot = tmp_path / "data/v0.4/snapshots" / f"{day}.csv"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text("type_id,product_key,linked_unit_price\n", encoding="utf-8")
        recovery.finalize_shadow_day(tmp_path, day, True)
        recovery.finalize_shadow_day(tmp_path, day, True)
    report = recovery.eligibility(recovery.read_json(state_path, {}))
    assert len(report["complete_dates"]) == 7 and report["eligible"]
    with pytest.raises(ValueError, match="after"):
        recovery.activate(tmp_path, "2026-10-03")
    assert recovery.activate(tmp_path, "2026-10-04")["mode"] == "active"


def test_incomplete_required_primary_cannot_qualify_shadow_day(tmp_path):
    recovery.write_json(tmp_path / "state/v0.4-discovery.json", {"shadow_days": {"2026-09-27": {
        "complete": False, "shadow_validated": True, "pending_qualified": False, "validated": False}}})
    path = tmp_path / "data/v0.4/snapshots/2026-09-27.csv"
    path.parent.mkdir(parents=True)
    path.write_text("type_id,product_key,linked_unit_price\n", encoding="utf-8")
    assert recovery.finalize_shadow_day(tmp_path, "2026-09-27", True)["complete_dates"] == []


def test_alias_search_is_shared_deduplicated_and_prioritizes_weak_meat_with_cap(monkeypatch):
    from types import SimpleNamespace
    from acik_sepet.api import MarketFiyatiError
    settings = [spec(), spec(id="apple", group="fruit", query="elma")]
    pools = {s["id"]: [item()] for s in settings}
    reports = {s["id"]: {"primary": {"status": "complete"}, "aliases": []} for s in settings}
    session = SimpleNamespace()
    queries = []
    def search(query, **kwargs):
        budget = kwargs["session"]._marketfiyati_budget
        for _ in range(30):
            budget.check()
            budget.used += 1
        queries.append(query)
        return [item(), item("new")]
    # Actual retries are counted by the API; this fake exercises the same cap.
    result = recovery.discover_aliases(settings, pools, reports, {"apple": [item()]}, session,
        search, {"beef_mince": ["kıyma", "dana"], "apple": ["elma kg"]}, "2026-09-27", recovery.time.monotonic() + 1000)
    assert result["requests"] == 50 and result["status"] == "source_or_budget_failure"
    assert queries == ["kıyma"]
    assert len(pools["beef_mince"]) == 2


def test_seven_bounded_primary_days_qualify_even_when_optional_alias_fails(tmp_path, monkeypatch):
    from acik_sepet.api import MarketFiyatiError, SearchResults
    import acik_sepet.validate as validation
    root = tmp_path
    data = root / "data/v0.4"
    snapshots = data / "snapshots"
    snapshots.mkdir(parents=True)
    recovery.write_json(root / "config/series.json", {"baseline_date": "2026-09-05", "locked_through": "2026-09-26"})
    recovery.write_json(root / "config/categories.json", {"categories": [{"id": "meat", "label": "Et", "weight": 1.0}]})
    recovery.write_json(root / "config/discovery.json", {"reviewed_aliases": {"beef_mince": ["optional"]}})
    for name, value in [("ROOT", root), ("DATA_DIR", data), ("SNAPSHOT_DIR", snapshots),
                        ("PANEL_PATH", root / "state/v0.4-panels.json")]:
        monkeypatch.setattr(collect, name, value)
    monkeypatch.setattr(collect, "load_product_types_for_date", lambda _: [spec()])
    real_validation = validation.validate_rows
    monkeypatch.setattr(validation, "validate_rows", lambda rows, day, specs: real_validation(rows, day, min_skus=1, specs=specs))
    class Clock(datetime):
        day = date(2026, 9, 27)

        @classmethod
        def now(cls, tz):
            return datetime(cls.day.year, cls.day.month, cls.day.day, 12, tzinfo=tz)
    monkeypatch.setattr(collect, "datetime", Clock)
    calls = []
    def search(query, **kwargs):
        calls.append(query)
        if query == "optional":
            raise MarketFiyatiError("optional failure")
        product = item()
        product["productDepotInfoList"][0]["indexTime"] = Clock.day.strftime("%d.%m.%Y 08:00")
        results = SearchResults()
        results.append(product)
        results.metadata.update(status="truncated", pages=8, raw_results=200, unique_results=200,
                                exhausted=False, reason="result_limit")
        return results
    monkeypatch.setattr(collect, "search_products", search)
    for offset in range(7):
        Clock.day = date(2026, 9, 27) + timedelta(days=offset)
        day = Clock.day.isoformat()
        collect.collect()
        result = recovery.finalize_shadow_day(root, day, True)
        assert len(result["complete_dates"]) == offset + 1
        report = recovery.read_json(data / "collection-diagnostics" / f"{day}.json", {})
        assert report["types"]["beef_mince"]["complete"] is True
        assert report["types"]["beef_mince"]["absence_complete"] is False
        assert report["shadow"]["comparison"]["legacy"]["index"] == 100
        assert report["shadow"]["comparison"]["index_difference_points"] == 0
    assert result["eligible"]
    assert calls.count(spec()["query"]) == 7 and calls.count("optional") == 7
    assert recovery.read_json(root / "config/rollout.json", {"mode": "shadow"})["mode"] == "shadow"


def test_failed_refresh_report_does_not_overwrite_published_diagnostic(tmp_path):
    path = tmp_path / "collection-diagnostics/2026-09-27.json"
    recovery.write_collection_report(path, {"status": "published", "types": {"meat": "good"}})
    recovery.write_collection_report(path, {"status": "rejected", "types": {"meat": "failed"}})
    assert recovery.read_json(path, {})["status"] == "published"
    attempts = list((path.parent / "attempts").glob("*.json"))
    assert len(attempts) == 1 and recovery.read_json(attempts[0], {})["status"] == "rejected"


def test_repeated_primary_page_retries_then_preserves_published_prices_panel_and_diagnostics(tmp_path, monkeypatch):
    from acik_sepet.api import SearchResults
    data = tmp_path / "data/v0.4"
    snapshots = data / "snapshots"
    snapshots.mkdir(parents=True)
    recovery.write_json(tmp_path / "config/series.json", {"baseline_date": "2026-09-05", "locked_through": "2026-09-26"})
    panel = tmp_path / "state/v0.4-panels.json"
    state, _ = collect._initialize_type([item()], spec(), set(), "2026-09-26")
    recovery.write_json(panel, {"types": {spec()["id"]: state}})
    (snapshots / "2026-09-26.csv").write_text("date,slot_id,product_key,linked_unit_price\n", encoding="utf-8")
    published = snapshots / "2026-09-27.csv"
    published.write_text("date,slot_id,product_key,linked_unit_price\n2026-09-27,id:old,id:old,100\n", encoding="utf-8")
    diagnostics = data / "collection-diagnostics/2026-09-27.json"
    recovery.write_collection_report(diagnostics, {"date": "2026-09-27", "status": "published", "types": {}})
    before = published.read_bytes(), panel.read_bytes(), diagnostics.read_bytes()
    for name, value in [("ROOT", tmp_path), ("DATA_DIR", data), ("SNAPSHOT_DIR", snapshots), ("PANEL_PATH", panel)]:
        monkeypatch.setattr(collect, name, value)
    monkeypatch.setattr(collect, "load_product_types_for_date", lambda _: [spec()])
    monkeypatch.setattr(collect, "RECOVERY_DELAYS", (0, 0, 0))
    class Clock(datetime):
        @classmethod
        def now(cls, tz):
            return datetime(2026, 9, 27, 12, tzinfo=tz)
    monkeypatch.setattr(collect, "datetime", Clock)
    calls = []
    def repeated(query, **kwargs):
        calls.append(query)
        result = SearchResults()
        result.append(item(price=999))
        result.metadata.update(status="incomplete", pages=2, raw_results=50, unique_results=25,
                               exhausted=False, reason="repeated_page")
        return result
    monkeypatch.setattr(collect, "search_products", repeated)
    with pytest.raises(SystemExit, match="Toplama eksik"):
        collect.collect(refresh=True)
    assert len(calls) == 4
    assert (published.read_bytes(), panel.read_bytes(), diagnostics.read_bytes()) == before
    attempts = [recovery.read_json(path, {}) for path in (diagnostics.parent / "attempts").glob("*.json")]
    rejected = next(report for report in attempts if report["status"] == "rejected")
    assert rejected["types"][spec()["id"]]["primary"]["status"] == "incomplete"
    assert rejected["types"][spec()["id"]]["primary"]["reason"] == "repeated_page"
    status = recovery.read_json(data / "collection-status.json", {})
    assert status["status"] == "rejected" and status["errors"][0]["retryable"] is True


def test_comparison_honors_declared_baseline_and_ignores_frozen_shadow_files(tmp_path):
    settings = spec()
    recovery.write_json(tmp_path / "config/series.json", {"baseline_date": "2026-09-05", "locked_through": "2026-09-06"})
    recovery.write_json(tmp_path / "config/categories.json", {"categories": [{"id": "meat", "label": "Et", "weight": 1.0}]})
    def rows_at(day, price):
        _, rows = collect._initialize_type([item(price=price)], settings, set(), day)
        rows[0].update(date=day, type_id=settings["id"])
        return rows
    def save(folder, day, rows):
        path = tmp_path / "data/v0.4" / folder / f"{day}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    for day, price in [("2026-09-04", 50), ("2026-09-05", 100), ("2026-09-06", 110)]:
        save("snapshots", day, rows_at(day, price))
        save("shadow", day, rows_at(day, 900))
    today = rows_at("2026-09-07", 110)
    result = recovery.compare_policies(tmp_path, "2026-09-07", today, today, [settings])
    assert result["baseline_date"] == "2026-09-05"
    assert result["legacy"]["index"] == 110
    assert result["proposed"]["index"] == 110


@pytest.mark.parametrize("group,type_id,name", [("meat", "beef_mince", "Kıyma"),
    ("fruit", "apple", "Elma"), ("vegetables", "tomato", "Domates")])
def test_fresh_food_recovery_fixtures_keep_price_level_on_slot_admission(group, type_id, name):
    settings = spec(id=type_id, group=group, query=name, include_tokens=[name], api_categories=[name])
    def product(key, price):
        row = item(key, price)
        row.update(title=f"{name} 1 Kg", categories=[name])
        return row
    old, new = product("old", 100), product("new", 1000)
    state, baseline = collect._initialize_type([old], settings, set(), "2026-09-26")
    evidence = {}
    for day in ["2026-09-27", "2026-09-28", "2026-09-29"]:
        rows, report = observe(state, evidence, [old, new], day, settings)
    baseline[0]["type_id"] = type_id
    result = build_type_indices([("2026-09-26", baseline), ("2026-09-29", rows)], [settings])
    assert report["additions_today"] == 1
    assert result[-1]["index"] == 100
