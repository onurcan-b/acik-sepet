import json
from pathlib import Path

import pytest

from acik_sepet import publish


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_install_failure_restores_existing_and_removes_new_files(tmp_path, monkeypatch):
    root, stage = tmp_path / "root", tmp_path / "stage"
    old = write(root, "data/old.csv", "old bytes")
    write(stage, "data/old.csv", "new bytes")
    write(stage, "data/new.csv", "new file")
    original_replace = publish.os.replace
    calls = []
    def fail_second(source, target):
        if Path(target).name != "journal.json":
            calls.append(target)
            if len(calls) == 2:
                raise OSError("disk full")
        original_replace(source, target)
    monkeypatch.setattr(publish.os, "replace", fail_second)
    with pytest.raises(OSError, match="disk full"):
        publish.install(root, stage, ["data/old.csv", "data/new.csv"])
    assert old.read_text() == "old bytes"
    assert not (root / "data/new.csv").exists()
    assert not (root / ".publication-transaction/journal.json").exists()


def test_crash_journal_recovery_is_repeatable(tmp_path):
    root = tmp_path / "root"
    write(root, "data/a.csv", "partially installed")
    write(root, "data/new.csv", "created")
    write(root, ".publication-transaction/backup/data/a.csv", "original")
    write(root, ".publication-transaction/journal.json", json.dumps([
        {"path": "data/a.csv", "existed": True},
        {"path": "data/new.csv", "existed": False},
    ]))
    publish._recover(root)
    publish._recover(root)
    assert (root / "data/a.csv").read_text() == "original"
    assert not (root / "data/new.csv").exists()


def test_transaction_rejects_paths_outside_workspace(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        publish.install(tmp_path / "root", tmp_path / "stage", ["../elsewhere"])


def fixture_publication(root):
    for name in ("data/v0.4/index.csv", "data/v0.4/snapshots/2026-09-26.csv",
                 "state/v0.4-panels.json", "charts/index.svg", "README.md"):
        write(root, name, "original " + name)
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_downstream_failure_only_publishes_diagnostics_and_failure_status(tmp_path, monkeypatch):
    original = fixture_publication(tmp_path)
    calls = []
    def run(stage, args):
        calls.append(args)
        if args == ["-m", "acik_sepet.collect", "--refresh"]:
            write(stage, "data/v0.4/index.csv", "bad index")
            write(stage, "state/v0.4-panels.json", "changed panel")
            write(stage, "state/v0.4-shadow-panels.json", "not yet validated")
            write(stage, "state/v0.4-discovery.json", "candidate evidence")
        if args == ["-m", "acik_sepet.report"]:
            raise RuntimeError("chart failed")
        if args == ["-m", "acik_sepet.report", "--status-only"]:
            assert (stage / "data/v0.4/index.csv").read_bytes() == original["data/v0.4/index.csv"]
            write(stage, "README.md", "failure status; old publication")
    monkeypatch.setattr(publish, "_run", run)
    with pytest.raises(RuntimeError, match="chart failed"):
        publish.publish(tmp_path)
    for name, content in original.items():
        if name != "README.md":
            assert (tmp_path / name).read_bytes() == content
    assert not (tmp_path / "state/v0.4-shadow-panels.json").exists()
    assert (tmp_path / "state/v0.4-discovery.json").read_text() == "candidate evidence"
    assert json.loads((tmp_path / "data/v0.4/collection-status.json").read_text())["status"] == "rejected"
    assert ["-m", "acik_sepet.recovery", "finalize-day"] not in calls


def test_finalize_shadow_day_happens_after_validation_and_tests(tmp_path, monkeypatch):
    fixture_publication(tmp_path)
    calls = []
    def run(stage, args):
        calls.append(args)
        if args == ["-m", "acik_sepet.recovery", "finalize-day"]:
            assert ["-m", "pytest", "-q", "-p", "no:cacheprovider",
                    "--basetemp", str(stage / ".pytest-tmp")] in calls
            write(stage, "state/v0.4-shadow-panels.json", "validated day")
    monkeypatch.setattr(publish, "_run", run)
    publish.publish(tmp_path)
    assert (tmp_path / "state/v0.4-shadow-panels.json").read_text() == "validated day"


def test_offline_rebuild_neither_collects_nor_qualifies_shadow_day(tmp_path, monkeypatch):
    fixture_publication(tmp_path)
    calls = []
    monkeypatch.setattr(publish, "_run", lambda stage, args: calls.append(args))
    publish.publish(tmp_path, offline=True)
    assert not any("acik_sepet.collect" in args or "finalize-day" in args for args in calls)


def test_failed_install_cannot_leak_finalized_day_through_discovery_audit(tmp_path, monkeypatch):
    fixture_publication(tmp_path)
    before_finalization = {"observed": "new source evidence", "validated": False}
    def run(stage, args):
        if args == ["-m", "acik_sepet.collect", "--refresh"]:
            write(stage, "state/v0.4-discovery.json", json.dumps(before_finalization))
        if args == ["-m", "acik_sepet.recovery", "finalize-day"]:
            write(stage, "state/v0.4-discovery.json", json.dumps({
                **before_finalization, "validated": True, "published_linked_unit_price": 123}))
    original_install = publish.install
    calls = []
    def fail_first(root, stage, paths):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("publication promotion failed")
        return original_install(root, stage, paths)
    monkeypatch.setattr(publish, "_run", run)
    monkeypatch.setattr(publish, "install", fail_first)
    with pytest.raises(OSError, match="promotion failed"):
        publish.publish(tmp_path)
    assert json.loads((tmp_path / "state/v0.4-discovery.json").read_text()) == before_finalization


def test_interrupted_journal_preparation_does_not_block_next_publication(tmp_path):
    root, stage = tmp_path / "root", tmp_path / "stage"
    write(root, ".publication-transaction/journal.tmp", '[{"path":')
    write(root, "data/a.csv", "old")
    write(stage, "data/a.csv", "new")
    publish.install(root, stage, ["data/a.csv"])
    assert (root / "data/a.csv").read_text() == "new"


def test_downstream_failure_preserves_successful_collection_diagnostics(tmp_path, monkeypatch):
    fixture_publication(tmp_path)
    name = "data/v0.4/collection-diagnostics/2026-09-26.json"
    previous = json.dumps({"status": "published", "evidence": "last successful publication"})
    write(tmp_path, name, previous)
    def run(stage, args):
        if args == ["-m", "acik_sepet.collect", "--refresh"]:
            write(stage, name, json.dumps({"status": "published", "evidence": "new crawl"}))
        if args == ["-m", "acik_sepet.report"]:
            raise RuntimeError("chart failed")
    monkeypatch.setattr(publish, "_run", run)
    with pytest.raises(RuntimeError, match="chart failed"):
        publish.publish(tmp_path)
    assert (tmp_path / name).read_text() == previous
    attempts = list((tmp_path / "data/v0.4/collection-diagnostics/attempts").glob("*.json"))
    assert len(attempts) == 1
    attempt = json.loads(attempts[0].read_text())
    assert attempt["status"] == "rejected" and attempt["publication_failed"]
    assert attempt["evidence"] == "new crawl"
