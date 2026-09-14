from acik_sepet.product_types import load_product_types
from acik_sepet.semantic_audit import audit_rows


def _row(type_id: str, title: str, *, generation: int = 0) -> dict[str, str]:
    return {
        "type_id": type_id,
        "type_label": type_id,
        "product_key": f"id:{type_id}",
        "slot_id": f"slot:{type_id}",
        "title": title,
        "generation": str(generation),
    }


def test_curated_rule_flags_instant_coffee_premix():
    findings = audit_rows([_row("instant_coffee", "Nescafé 3'ü 1 Arada Sütlü Köpüklü Hazır Kahve 17 Gr")])
    assert any(item.get("rule_id") == "instant-coffee-premix" and item["severity"] == "high" for item in findings)


def test_curated_rule_flags_specialty_bread_under_white_bread():
    findings = audit_rows([_row("bread_white", "Uno Çok Tahıllı Ekmek 460 Gr")])
    assert any(item.get("rule_id") == "bread-white-specialty" for item in findings)


def test_same_group_overlap_catches_lactose_free_milk_in_plain_milk():
    findings = audit_rows([_row("milk", "Dost Laktozsuz Süt 1 Lt")], specs=load_product_types())
    overlaps = [item for item in findings if item["kind"] == "same_group_title_overlap"]
    assert overlaps
    assert "milk_lactosefree" in overlaps[0]["overlaps_with"]


def test_bridged_replacement_is_always_reviewed():
    findings = audit_rows([_row("rice", "Yerli Pilavlık Pirinç 1 Kg", generation=1)])
    assert any(item["kind"] == "bridged_replacement" and item["severity"] == "review" for item in findings)


def test_clean_plain_milk_has_no_high_finding():
    findings = audit_rows([_row("milk", "Sek Yağlı Süt 1 Lt")])
    assert not any(item["severity"] == "high" for item in findings)
