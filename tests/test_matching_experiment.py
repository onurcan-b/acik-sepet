from acik_sepet.matching_experiment import legacy_candidate, strict_candidate


def spec(group: str, include: list[str], *, exclude: list[str] | None = None, unit: str = "mass"):
    return {
        "group": group,
        "include_tokens": include,
        "exclude_tokens": exclude or [],
        "unit": unit,
    }


def assert_strict(title: str, product_spec: dict, expected: bool):
    actual, _ = strict_candidate(title, product_spec)
    assert actual is expected


def test_banana_rejects_processed_products_but_keeps_real_fruit():
    banana = spec("fruit", ["muz"])
    assert_strict("Yerli Muz 1 Kg", banana, True)
    assert_strict("İthal Muz 1 Kg", banana, True)

    bad = [
        "Eti Hoşbeş Muz Kremalı Gofret 120 Gr",
        "Ülker Dankek Muz Kremalı Rulo Kek 28 Gr",
        "Gerber Organik Muz Yaban Mersini Elma Püre 90 Gr",
    ]
    for title in bad:
        assert legacy_candidate(title, banana) is True
        assert_strict(title, banana, False)


def test_carrot_rejects_cake_puree_and_tarator():
    carrot = spec("vegetables", ["havuç"])
    assert_strict("Havuç 1 Kg", carrot, True)
    assert_strict("Havuç Paket 350 Gr", carrot, True)

    bad = [
        "Ülker Dankek Lokmalık Havuçlu Tarçınlı 160 Gr",
        "Gerber Organik Muzlu Havuç Balkabağı Püresi 90 Gr",
        "Obur Chef Havuç Tarator 200 Gr",
        "Yoğurtlu Havuç 1 Kg",
    ]
    for title in bad:
        assert legacy_candidate(title, carrot) is True
        assert_strict(title, carrot, False)


def test_lemon_rejects_cleaning_and_snack_context():
    lemon = spec("fruit", ["limon"])
    assert_strict("Limon 1 Kg", lemon, True)
    assert_strict("Limon Lamas 1 Kg", lemon, True)

    bad = [
        "Pril Klasik Limon 4 Kg",
        "Doritos Acı Biber & Limon Mısır Cipsi 125 Gr",
    ]
    for title in bad:
        assert legacy_candidate(title, lemon) is True
        assert_strict(title, lemon, False)


def test_zucchini_rejects_seed_and_prepared_food():
    zucchini = spec("vegetables", ["kabak"], exclude=["çekirdek"])
    assert_strict("Kabak 1 Kg", zucchini, True)

    bad = [
        "Gurmepack Fırında Kabak Mücver 250 Gr",
        "Tadım Kabak Çekirdeği 180 Gr",
    ]
    for title in bad:
        assert legacy_candidate(title, zucchini) is True
        assert_strict(title, zucchini, False)


def test_exact_tokens_fix_morphological_false_positives_outside_fresh_produce():
    milk = spec("dairy_eggs", ["süt"], unit="volume")
    accepted, _ = strict_candidate("Süt 1 Litre", milk)
    assert accepted is True

    # Current substring logic considers "süt" present in "sütlü".
    assert legacy_candidate("Sütlü İçecek 1 Litre", milk) is True
    accepted, _ = strict_candidate("Sütlü İçecek 1 Litre", milk)
    assert accepted is False
