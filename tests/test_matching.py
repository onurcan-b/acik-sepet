from acik_sepet.collect import _base_candidate, _score, _title_matches


def _spec(**overrides):
    spec = {
        "unit": "mass",
        "include_tokens": ["muz"],
        "exclude_tokens": [],
        "api_category_level": "sub_category",
        "api_categories": ["Muz"],
    }
    spec.update(overrides)
    return spec


def _item(title, *, categories=None, refined="1 KG", price=69.0, unit_price=69.0):
    return {
        "id": "sku-1",
        "title": title,
        "refinedVolumeOrWeight": refined,
        "categories": categories or ["Muz"],
        "main_category": "Meyve",
        "menu_category": "Meyve ve Sebze",
        "productDepotInfoList": [
            {
                "depotId": "d-1",
                "price": price,
                "unitPriceValue": unit_price,
                "marketAdi": "market",
                "indexTime": "01.09.2026 09:00",
            }
        ],
    }


def test_api_category_rejects_banana_wafer():
    assert _score(_item("Muzlu Gofret 40 Gr", categories=["Gofret"]), _spec()) < 0
    assert _score(_item("Yerli Muz 1 Kg"), _spec()) >= 1


def test_server_side_category_provenance_handles_noisy_category_echo():
    item = _item("Yerli Pilavlık Pirinç 1 Kg", categories=["Pirinç", "Pilavlık"])
    item["_query_category_level"] = "sub_category"
    item["_query_category_values"] = ["Pirinçler"]
    spec = _spec(include_tokens=["pirinç"], api_categories=["Pirinçler"])
    assert _score(item, spec) >= 1


def test_every_required_rule_is_a_hard_gate():
    spec = _spec(include_tokens=["dana", "kıyma"], api_categories=["Dana Kıyma"])
    item = _item("Dana Kuşbaşı 500 Gr", categories=["Dana Kıyma"], refined="500 GR")
    assert _score(item, spec) < 0


def test_short_words_do_not_match_longer_words():
    spec = _spec(include_tokens=["bal"], api_category_level="main_category", api_categories=["Bal ve Reçel"])
    assert not _title_matches("Balık Krakeri 100 Gr", spec)
    assert _title_matches("Süzme Bal 460 Gr", spec)


def test_alternatives_and_turkish_suffixes_are_supported():
    spec = _spec(include_tokens=["cherry|çeri|kokteyl", "domates"])
    assert _title_matches("Kokteyl Domates 500 Gr", spec)
    assert _title_matches("Çeri Domates 500 Gr", spec)
    assert _title_matches("Domatesler 1 Kg", _spec(include_tokens=["domates"]))


def test_refined_quantity_and_api_unit_price_are_verified():
    candidate = _base_candidate(_item("Yerli Muz", refined="1 KG"), _spec())
    assert candidate is not None
    assert candidate["quantity"] == 1.0
    assert candidate["quantity_source"] == "api-refined"
    assert candidate["api_unit_price"] == 69.0


def test_inconsistent_api_unit_price_is_rejected():
    assert _base_candidate(_item("Yerli Muz", price=69.0, unit_price=10.0), _spec()) is None


def test_conflicting_api_and_title_quantities_are_rejected():
    item = _item(
        "Pril Limon Sıvı Bulaşık Deterjanı 2.418 Lt",
        categories=["Elde Yıkama Deterjanı"],
        refined="2.418 ML",
        price=179.95,
        unit_price=74421.42,
    )
    spec = _spec(
        unit="volume",
        include_tokens=["bulaşık"],
        api_categories=["Elde Yıkama Deterjanı"],
    )
    assert _base_candidate(item, spec) is None
