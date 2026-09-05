import json

import pytest

from acik_sepet import index


def setup_series(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "series.json").write_text(json.dumps({"baseline_date": "2026-09-05"}))
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    monkeypatch.setattr(index, "ROOT", tmp_path)
    monkeypatch.setattr(index, "SNAPSHOT_DIR", snapshots)
    for name in ("TYPE_PATH", "CATEGORY_PATH", "INDEX_PATH"):
        monkeypatch.setattr(index, name, tmp_path / (name + ".csv"))
    monkeypatch.setattr(index, "load_product_types", lambda: [{"id": "t", "label": "T", "group": "g", "min_skus": 1}])
    monkeypatch.setattr(index, "load_categories", lambda: [{"id": "g", "label": "G", "weight": 1}])
    monkeypatch.setattr(index, "load_snapshot", lambda p: [{"type_id": "t", "product_key": "a", "unit_price": 100 if p.stem == "2026-09-05" else 200}])
    return snapshots


def test_reset_excludes_older_days_and_starts_at_100(tmp_path, monkeypatch):
    snapshots = setup_series(tmp_path, monkeypatch)
    for day in ("2026-09-02", "2026-09-05", "2026-09-06"):
        (snapshots / (day + ".csv")).touch()
    rows = index.rebuild()
    assert [r["date"] for r in rows] == ["2026-09-05", "2026-09-06"]
    assert [r["index"] for r in rows] == [100, 200]
    assert all(r["baseline_date"] == "2026-09-05" for r in rows)


def test_missing_reset_baseline_fails_instead_of_silently_rebasing(tmp_path, monkeypatch):
    snapshots = setup_series(tmp_path, monkeypatch)
    (snapshots / "2026-09-06.csv").touch()
    with pytest.raises(ValueError, match="baseline snapshot is missing"):
        index.rebuild()
