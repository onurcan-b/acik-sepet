from acik_sepet.units import parse_quantity, unit_price


def test_mass_units():
    q = parse_quantity("Barilla Spaghetti 500 Gr", "mass")
    assert q is not None
    assert q.unit == "kg"
    assert q.amount == 0.5
    assert unit_price(45.0, q) == 90.0


def test_volume_multipack():
    q = parse_quantity("Meyve Suyu 6 x 200 ml", "volume")
    assert q is not None
    assert q.unit == "l"
    assert round(q.amount, 6) == 1.2


def test_count_turkish_pack():
    q = parse_quantity("Tuvalet Kağıdı 12'li", "count")
    assert q is not None
    assert q.unit == "count"
    assert q.amount == 12


def test_count_adet():
    q = parse_quantity("Yumurta 10 Adet", "count")
    assert q is not None
    assert q.amount == 10
