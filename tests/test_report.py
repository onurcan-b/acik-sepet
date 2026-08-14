from acik_sepet.report import _daily_movers_markdown


def snapshot(date, items, target=4):
    return {
        "date": date,
        "target_items": target,
        "items": {
            item_id: {"basket_label": item_id, "price_median": price}
            for item_id, price in items.items()
        },
    }


def test_daily_movers_counts_price_changes_and_missing_items():
    previous = snapshot("2026-08-13", {"a": 10, "b": 20, "c": 30})
    latest = snapshot("2026-08-14", {"a": 11, "b": 18, "d": 40})

    text = _daily_movers_markdown([previous, latest])

    assert "**↑ Zamlanan:** 1" in text
    assert "**↓ Ucuzlayan:** 1" in text
    assert "**= Değişmeyen:** 0" in text
    assert "**Yeni kaybolan:** 1" in text
    assert "**Geri dönen/yeni eşleşen:** 1" in text
    assert "+10.00%" in text
    assert "-10.00%" in text


def test_daily_movers_reports_unchanged_common_items():
    previous = snapshot("2026-08-13", {"a": 10, "b": 20})
    latest = snapshot("2026-08-14", {"a": 10, "b": 20})

    text = _daily_movers_markdown([previous, latest])

    assert "**= Değişmeyen:** 2" in text
    assert "fiyat değişimi gözlenmedi" in text
