from acik_sepet.subindices import build_subindices


def snapshot(date, prices):
    return {
        "date": date,
        "items": {
            item_id: {"price_median": price}
            for item_id, price in prices.items()
        },
    }


def test_group_index_requires_sixty_percent_coverage():
    basket = [
        {"id": "a", "group": "g"},
        {"id": "b", "group": "g"},
        {"id": "c", "group": "g"},
        {"id": "d", "group": "g"},
        {"id": "e", "group": "g"},
    ]
    categories = [{"id": "g", "label": "Group", "weight": 1.0, "scope": "food"}]
    baseline = snapshot("2026-08-13", {"a": 10, "b": 10, "c": 10, "d": 10, "e": 10})
    too_sparse = snapshot("2026-08-14", {"a": 11, "b": 11})

    rows = build_subindices([baseline, too_sparse], basket, categories)
    row = next(row for row in rows if row["date"] == "2026-08-14" and row["group_id"] == "g")

    assert row["coverage"] == 0.4
    assert row["index"] is None


def test_group_index_renormalizes_when_coverage_is_sufficient():
    basket = [
        {"id": "a", "group": "g"},
        {"id": "b", "group": "g"},
        {"id": "c", "group": "g"},
        {"id": "d", "group": "g"},
        {"id": "e", "group": "g"},
    ]
    categories = [{"id": "g", "label": "Group", "weight": 1.0, "scope": "food"}]
    baseline = snapshot("2026-08-13", {"a": 10, "b": 10, "c": 10, "d": 10, "e": 10})
    sufficient = snapshot("2026-08-14", {"a": 11, "b": 11, "c": 11})

    rows = build_subindices([baseline, sufficient], basket, categories)
    row = next(row for row in rows if row["date"] == "2026-08-14" and row["group_id"] == "g")

    assert row["coverage"] == 0.6
    assert row["index"] == 110.0
