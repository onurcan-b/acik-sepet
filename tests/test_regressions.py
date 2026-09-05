import math

import pytest

from acik_sepet.collect import _initialize_sources, _source_linked_package_price, _update_shadow_candidates
from acik_sepet.health import summarize
from acik_sepet.index import build_type_indices, build_category_indices, build_main_index, geometric_mean
from acik_sepet.report import _change


def test_sku_disappearance_does_not_reverse_previous_inflation():
    spec = [{"id": "t", "label": "T", "group": "g", "min_skus": 1}]
    def rows(a, b=None):
        return [{"type_id": "t", "product_key": k, "unit_price": v}
                for k, v in (("a", a), ("b", b)) if v is not None]
    result = build_type_indices([("2026-09-01", rows(100, 100)),
                                ("2026-09-02", rows(100, 144)),
                                ("2026-09-03", rows(100))], spec)
    assert [r["index"] for r in result] == [100, 120, 120]


def test_type_missing_on_first_day_can_enter_later():
    spec = [{"id": "t", "label": "T", "group": "g", "min_skus": 1}]
    result = build_type_indices([("2026-09-01", []), ("2026-09-02", [
        {"type_id": "t", "product_key": "a", "unit_price": 12}])], spec)
    assert result[0]["index"] is None
    assert result[1]["index"] == 100
    assert result[1]["baseline_date"] == "2026-09-02"


def test_category_dropout_does_not_undo_inflation():
    specs = [{"id": k, "group": "g"} for k in ("a", "b", "c")]
    categories = [{"id": "g", "label": "G", "weight": 1}]
    rows = [{"date": day, "type_id": k, "index": value}
            for day, prices in [("2026-09-01", [100, 100, 100]),
                                ("2026-09-02", [100, 100, 130]),
                                ("2026-09-03", [100, 100, None])]
            for k, value in zip(("a", "b", "c"), prices)]
    result = build_category_indices(rows, specs, categories)
    assert [r["index"] for r in result] == [100, 110, 110]


def test_headline_category_dropout_does_not_undo_inflation():
    cats = [{"id": k, "weight": 1} for k in ("a", "b", "c")]
    rows = [{"date": day, "group_id": k, "index": value}
            for day, prices in [("2026-09-01", [100, 100, 100]),
                                ("2026-09-02", [100, 100, 130]),
                                ("2026-09-03", [100, 100, None])]
            for k, value in zip(("a", "b", "c"), prices)]
    result = build_main_index([], rows, cats)
    assert [r["index"] for r in result] == [100, 110, 110]


def test_depot_dropout_does_not_reverse_earlier_price_move():
    def offers(a, b=None):
        return [{"price": v, "source_id": k} for k, v in (("a", a), ("b", b)) if v is not None]
    state = {}
    _initialize_sources(state, offers(100, 100))
    assert _source_linked_package_price(state, offers(100, 100))[0] == 100
    assert _source_linked_package_price(state, offers(100, 144))[0] == pytest.approx(120)
    assert _source_linked_package_price(state, offers(100))[0] == pytest.approx(120)
    assert _source_linked_package_price(state, offers(110))[0] == pytest.approx(132)


def test_seven_days_uses_calendar_not_observation_count():
    rows = [{"date": "2026-09-01", "index": "100"}, {"date": "2026-09-08", "index": "110"}]
    assert _change(rows, 7) == pytest.approx(10)
    assert _change(rows, 1) is None
    assert _change(rows + [{"date": "2026-09-09", "index": ""}], 7) is None


def test_stale_source_is_not_reported_as_fresh():
    result = summarize([{"date": "2026-09-03", "slot_id": "a", "source_updated_at": "02.09.2026 08:05"}])
    assert result["source_updated_today"] == 0
    assert result["source_within_3_days"] == 1
    assert result["warnings"]


def test_same_day_candidate_retry_preserves_streak():
    state = {"candidates": {"a": {"last_seen": "2026-09-02", "seen_streak": 3}}}
    row = {"product_key": "a", "title": "A", "quantity": 1, "unit": "kg", "score": 1, "offer_count": 1}
    _update_shadow_candidates(state, [row], set(), set(), "2026-09-02")
    assert state["candidates"]["a"]["seen_streak"] == 3
    _update_shadow_candidates(state, [row], set(), set(), "2026-09-03")
    assert state["candidates"]["a"]["seen_streak"] == 4


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, 0])
def test_nonfinite_and_nonpositive_values_rejected(bad):
    with pytest.raises(ValueError):
        geometric_mean([1, bad])


def test_search_reaches_second_page_and_deduplicates():
    from acik_sepet.api import search_products
    class Response:
        status_code = 200
        def __init__(self, rows): self.rows = rows
        def raise_for_status(self): pass
        def json(self): return {"content": self.rows}
    class Session:
        def post(self, url, **kwargs):
            return Response(([{"id": "a"}, {"id": "b"}], [{"id": "b"}, {"id": "c"}], [])[kwargs["json"]["pages"]])
    assert [r["id"] for r in search_products("q", page_size=2, session=Session())] == ["a", "b", "c"]


@pytest.mark.parametrize("title, token", [("Tost Ekmeği 500 G", "ekmek"),
    ("Buğday Unu 1 Kg", "un"), ("Duş Jeli 500 Ml", "jel"),
    ("Mısır Gevreği 250 G", "gevrek")])
def test_turkish_inflections_keep_real_products(title, token):
    from acik_sepet.collect import _title_matches
    assert _title_matches(title, {"include_tokens": [token]})


def test_short_word_expansion_does_not_admit_unrelated_products():
    from acik_sepet.collect import _title_matches
    assert not _title_matches("Balık", {"include_tokens": ["bal"]})
    assert not _title_matches("Jelatin", {"include_tokens": ["jel"]})
    assert not _title_matches("Unlu Mamuller", {"include_tokens": ["un"]})
