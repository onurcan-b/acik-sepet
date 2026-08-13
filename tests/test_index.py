from acik_sepet.index import compute_series, snapshot_item_prices


def snap(date, a, b):
    return {
        "date": date,
        "locations": {
            "national": {"items": {"a": {"price_median": a}, "b": {"price_median": b}}},
        },
    }


def test_snapshot_item_prices_uses_snapshot_values():
    s = {"locations": {"national": {"items": {"a": {"price_median": 20}}}}}
    assert snapshot_item_prices(s)["a"] == 20


def test_index_is_100_on_baseline_and_110_after_uniform_rise():
    basket = [{"id": "a", "weight": 1}, {"id": "b", "weight": 1}]
    rows = compute_series([snap("2026-08-13", 10, 20), snap("2026-08-14", 11, 22)], basket)
    assert rows[0]["index"] == 100
    assert rows[1]["index"] == 110


def test_low_coverage_suppresses_value():
    basket = [{"id": "a", "weight": 1}, {"id": "b", "weight": 1}, {"id": "c", "weight": 1}]
    baseline = snap("2026-08-13", 10, 20)
    second = {"date": "2026-08-14", "locations": {"national": {"items": {"a": {"price_median": 11}}}}}
    rows = compute_series([baseline, second], basket, min_coverage=0.5)
    assert rows[-1]["index"] is None
