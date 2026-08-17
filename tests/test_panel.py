from acik_sepet.collect import (
    _initialize_sources,
    _migrate_sku_state,
    _source_linked_package_price,
)


def test_source_relatives_ignore_new_depots_and_subset_composition():
    state = {"product_key": "id:a"}
    first = [
        {"price": 100.0, "source_id": "depot:1", "market": "A", "depot_name": ""},
        {"price": 120.0, "source_id": "depot:2", "market": "B", "depot_name": ""},
        {"price": 140.0, "source_id": None, "market": "", "depot_name": ""},
    ]
    _initialize_sources(state, first)
    assert state["source_ids"] == ["depot:1", "depot:2"]
    assert state["source_anchor_level"] == 120.0

    initial = _source_linked_package_price(state, first)
    assert initial is not None
    assert round(initial[0], 8) == 120.0

    # Depot 2 disappears and a brand-new depot appears. With no price change at
    # depot 1, the linked level stays at 120 rather than moving with composition.
    subset = [
        {"price": 100.0, "source_id": "depot:1", "market": "A", "depot_name": ""},
        {"price": 999.0, "source_id": "depot:new", "market": "C", "depot_name": ""},
    ]
    linked = _source_linked_package_price(state, subset)
    assert linked is not None
    assert round(linked[0], 8) == 120.0
    assert [row["source_id"] for row in linked[1]] == ["depot:1"]

    # A real +10% move at the surviving pinned depot is still measured as +10%.
    moved = [
        {"price": 110.0, "source_id": "depot:1", "market": "A", "depot_name": ""},
        {"price": 999.0, "source_id": "depot:new", "market": "C", "depot_name": ""},
    ]
    linked_moved = _source_linked_package_price(state, moved)
    assert linked_moved is not None
    assert round(linked_moved[0], 8) == 132.0


def test_legacy_panel_sku_migrates_without_changing_identity_and_seeds_level():
    sku = {"product_key": "id:legacy", "title": "Legacy"}
    _migrate_sku_state(sku, {"id:legacy": 123.45})
    assert sku["slot_id"] == "id:legacy"
    assert sku["generation"] == 0
    assert sku["link_factor"] == 1.0
    assert sku["missing_streak"] == 0
    assert sku["last_linked_unit_price"] == 123.45
