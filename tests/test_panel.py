from statistics import median

from acik_sepet.collect import _migrate_sku_state, _pin_sources


def test_source_pinning_keeps_same_depots_and_bridges_adoption_level():
    state = {"product_key": "id:a"}
    first = [
        {"price": 100.0, "source_id": "depot:1", "market": "A", "depot_name": ""},
        {"price": 120.0, "source_id": "depot:2", "market": "B", "depot_name": ""},
        {"price": 140.0, "source_id": None, "market": "", "depot_name": ""},
    ]
    stable = _pin_sources(state, first)
    assert state["source_ids"] == ["depot:1", "depot:2"]
    assert [row["source_id"] for row in stable] == ["depot:1", "depot:2"]
    all_level = median(row["price"] for row in first)
    stable_level = median(row["price"] for row in stable)
    assert round(stable_level * state["source_bridge_factor"], 8) == round(all_level, 8)

    second = [
        {"price": 101.0, "source_id": "depot:1", "market": "A", "depot_name": ""},
        {"price": 999.0, "source_id": "depot:new", "market": "C", "depot_name": ""},
    ]
    stable_second = _pin_sources(state, second)
    assert len(stable_second) == 1
    assert stable_second[0]["source_id"] == "depot:1"


def test_legacy_panel_sku_migrates_without_changing_identity():
    sku = {"product_key": "id:legacy", "title": "Legacy"}
    _migrate_sku_state(sku)
    assert sku["slot_id"] == "id:legacy"
    assert sku["generation"] == 0
    assert sku["link_factor"] == 1.0
    assert sku["missing_streak"] == 0
