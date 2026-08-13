from acik_sepet.basket import load_basket, load_categories
from acik_sepet.index import compute_series


def test_basket_has_150_unique_items_and_weights_sum_to_one():
    basket = load_basket()
    categories = load_categories()
    assert len(basket) == 150
    assert len({item["id"] for item in basket}) == 150
    assert abs(sum(float(row["weight"]) for row in categories) - 1.0) < 1e-9
    assert {item["group"] for item in basket} == {row["id"] for row in categories}


def test_two_stage_weighting_respects_category_weights():
    basket = [{"id": "a", "group": "g1", "item_weight": 1.0}, {"id": "b", "group": "g2", "item_weight": 1.0}]
    categories = [{"id": "g1", "label": "G1", "weight": 0.75, "scope": "food"}, {"id": "g2", "label": "G2", "weight": 0.25, "scope": "nonfood"}]
    snapshots = [{"date": "2026-08-13", "items": {"a": {"price_median": 100}, "b": {"price_median": 100}}}, {"date": "2026-08-14", "items": {"a": {"price_median": 110}, "b": {"price_median": 100}}}]
    rows, subrows = compute_series(snapshots, basket, categories)
    assert rows[0]["index"] == 100
    assert rows[1]["index"] == 107.5
    assert rows[1]["food_index"] == 110
    assert len(subrows) == 4
