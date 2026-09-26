import csv
import hashlib
import json

import pytest

from acik_sepet.history import canonical_bytes, freeze_through_latest, verify_files


def test_line_endings_do_not_hide_a_real_historical_edit(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    snapshot = tmp_path / "old.csv"
    snapshot.write_bytes(b"a,b\r\n1,2\r\n")
    spec = {"baseline_date": "2026-09-05", "locked_through": "2026-09-26"}
    (config / "series.json").write_text(json.dumps(spec))
    (config / "history-lock.json").write_text(json.dumps(dict(spec, files={
        "old.csv": hashlib.sha256(b"a,b\n1,2\n").hexdigest()})))
    verify_files(tmp_path)
    snapshot.write_bytes(b"a,b\r\n1,3\r\n")
    with pytest.raises(ValueError, match="Protected historical file"):
        verify_files(tmp_path)


def test_freeze_extends_to_latest_without_changing_values(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/series.json").write_text(json.dumps({"baseline_date": "2026-09-05"}))
    data = tmp_path / "data/v0.4"
    (data / "snapshots").mkdir(parents=True)
    for name in ("index.csv", "type_indices.csv", "category_indices.csv"):
        (data / name).write_bytes(b"date,index\r\n2026-09-05,100\r\n2026-09-26,101.5\r\n")
    (data / "snapshots/2026-09-26.csv").write_bytes(b"date,price\r\n2026-09-26,12\r\n")
    assert freeze_through_latest(tmp_path) == "2026-09-26"
    assert (data / "frozen-2026-09-26/index.csv").read_bytes() == canonical_bytes(data / "index.csv")
    assert b"\r" not in (data / "snapshots/2026-09-26.csv").read_bytes()
    verify_files(tmp_path)
    assert freeze_through_latest(tmp_path) == "2026-09-26"


def test_freeze_failure_cannot_leave_conflicting_metadata(tmp_path, monkeypatch):
    from acik_sepet import publish
    (tmp_path / "config").mkdir()
    original_series = json.dumps({"baseline_date": "2026-09-05"})
    (tmp_path / "config/series.json").write_text(original_series)
    data = tmp_path / "data/v0.4"
    (data / "snapshots").mkdir(parents=True)
    for name in ("index.csv", "type_indices.csv", "category_indices.csv"):
        (data / name).write_text("date,index\n2026-09-05,100\n2026-09-26,101.5\n")
    original_replace = publish.os.replace
    def interrupt(source, target):
        if str(target).endswith("series.json"):
            raise OSError("interrupted metadata installation")
        original_replace(source, target)
    monkeypatch.setattr(publish.os, "replace", interrupt)
    with pytest.raises(OSError, match="interrupted"):
        freeze_through_latest(tmp_path)
    assert (tmp_path / "config/series.json").read_text() == original_series
    assert not (tmp_path / "config/history-lock.json").exists()
    monkeypatch.setattr(publish.os, "replace", original_replace)
    assert freeze_through_latest(tmp_path) == "2026-09-26"
    verify_files(tmp_path)
