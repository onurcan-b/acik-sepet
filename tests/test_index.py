from acik_sepet.index import build_category_indices, build_type_indices, geometric_mean


def test_geometric_mean():
    assert round(geometric_mean([1.0, 1.21]), 6) == 1.1


def test_type_index_uses_same_sku_relatives():
    specs = [{
        "id": "shampoo", "label": "Şampuan", "group": "personal_paper",
        "min_skus": 2, "target_skus": 3, "type_weight": 1.0,
    }]
    baseline = [
        {"type_id": "shampoo", "product_key": "a", "unit_price": 100.0},
        {"type_id": "shampoo", "product_key": "b", "unit_price": 200.0},
        {"type_id": "shampoo", "product_key": "c", "unit_price": 300.0},
    ]
    current = [
        {"type_id": "shampoo", "product_key": "a", "unit_price": 110.0},
        {"type_id": "shampoo", "product_key": "b", "unit_price": 220.0},
    ]
    rows = build_type_indices([("2026-08-16", baseline), ("2026-08-17", current)], specs, min_coverage=0.5)
    assert rows[0]["index"] == 100.0
    assert rows[1]["index"] == 110.0
    assert rows[1]["skus"] == 2
    assert rows[1]["coverage"] == 0.6667


def test_type_index_suppressed_when_too_few_skus():
    specs = [{
        "id": "pasta", "label": "Makarna", "group": "bread_cereals",
        "min_skus": 2, "target_skus": 3, "type_weight": 1.0,
    }]
    baseline = [
        {"type_id": "pasta", "product_key": "a", "unit_price": 10.0},
        {"type_id": "pasta", "product_key": "b", "unit_price": 20.0},
        {"type_id": "pasta", "product_key": "c", "unit_price": 30.0},
    ]
    current = [{"type_id": "pasta", "product_key": "a", "unit_price": 11.0}]
    rows = build_type_indices([("2026-08-16", baseline), ("2026-08-17", current)], specs, min_coverage=0.5)
    assert rows[-1]["index"] is None


def test_replacement_keeps_original_slot_identity():
    specs = [{
        "id": "shampoo", "label": "Şampuan", "group": "personal_paper",
        "min_skus": 2, "target_skus": 2, "type_weight": 1.0,
    }]
    baseline = [
        {"type_id": "shampoo", "product_key": "old-a", "unit_price": 100.0},
        {"type_id": "shampoo", "product_key": "b", "unit_price": 200.0},
    ]
    current = [
        {
            "type_id": "shampoo",
            "slot_id": "old-a",
            "product_key": "replacement-a",
            "unit_price": 300.0,
            "linked_unit_price": 110.0,
        },
        {
            "type_id": "shampoo",
            "slot_id": "b",
            "product_key": "b",
            "unit_price": 220.0,
            "linked_unit_price": 220.0,
        },
    ]
    rows = build_type_indices([("2026-08-16", baseline), ("2026-08-24", current)], specs, min_coverage=0.5)
    assert rows[-1]["index"] == 110.0
    assert rows[-1]["skus"] == 2


def test_linked_price_falls_back_to_legacy_unit_price():
    specs = [{
        "id": "rice", "label": "Pirinç", "group": "bread_cereals",
        "min_skus": 1, "target_skus": 1, "type_weight": 1.0,
    }]
    baseline = [{"type_id": "rice", "product_key": "rice-a", "unit_price": 80.0}]
    current = [{"type_id": "rice", "product_key": "rice-a", "unit_price": 84.0}]
    rows = build_type_indices([("2026-08-16", baseline), ("2026-08-17", current)], specs)
    assert rows[0]["index"] == 100.0
    assert rows[1]["index"] == 105.0


def test_category_coverage_uses_all_configured_types():
    specs = [
        {"id": "present", "label": "Var", "group": "g", "min_skus": 1, "target_skus": 1, "type_weight": 1.0},
        {"id": "missing", "label": "Yok", "group": "g", "min_skus": 1, "target_skus": 1, "type_weight": 1.0},
    ]
    type_rows = build_type_indices(
        [("2026-09-01", [{"type_id": "present", "product_key": "a", "unit_price": 10.0}])],
        specs,
    )
    categories = [{"id": "g", "label": "Grup", "scope": "food", "weight": 1.0}]
    rows = build_category_indices(type_rows, specs, categories, min_coverage=0.60)
    assert rows[0]["coverage"] == 0.5
    assert rows[0]["baseline_types"] == 2
    assert rows[0]["index"] is None
