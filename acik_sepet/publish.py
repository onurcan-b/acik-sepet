"""Build a complete publication in isolation, then install with crash recovery.

GitHub only commits a completed transaction. Local failures roll back all changed
files; a durable journal also recovers a process killed during installation.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_DIRS = ("data/v0.4", "state", "charts")
AUDIT_PATHS = (
    "data/v0.4/collection-status.json", "data/v0.4/latest-errors.json",
    "data/v0.4/attempts", "data/v0.4/collection-diagnostics",
    "state/v0.4-discovery.json",
)


@contextlib.contextmanager
def publication_lock(root: Path):
    path = root / ".publication.lock"
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _within(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Publication path escapes workspace")
    return target


def _recover(root: Path) -> None:
    directory = root / ".publication-transaction"
    journal = directory / "journal.json"
    if not journal.exists():
        return
    entries = json.loads(journal.read_text(encoding="utf-8"))
    for entry in reversed(entries):
        target = _within(root, entry["path"])
        if entry["existed"]:
            backup = _within(directory / "backup", entry["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            # Keep backups until the journal is gone: recovery is repeatable.
            shutil.copyfile(backup, target)
        elif target.exists():
            target.unlink()
    journal.unlink()


def install(root: Path, stage: Path, paths: list[str]) -> None:
    """Install the reviewed allowlist, restoring all bytes on any write failure."""
    _recover(root)
    transaction = root / ".publication-transaction"
    backup_root = transaction / "backup"
    entries = []
    for relative in sorted(set(paths)):
        source, target = _within(stage, relative), _within(root, relative)
        if not source.is_file():
            continue
        if target.exists() and target.read_bytes() == source.read_bytes():
            continue
        if target.exists():
            backup = _within(backup_root, relative)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, backup)
        entries.append({"path": relative, "existed": target.exists()})
    if not entries:
        return
    transaction.mkdir(parents=True, exist_ok=True)
    journal = transaction / "journal.json"
    pending_journal = transaction / "journal.tmp"
    with pending_journal.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(entries, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(pending_journal, journal)
    try:
        for entry in entries:
            source = _within(stage, entry["path"])
            target = _within(root, entry["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".publish.tmp")
            shutil.copyfile(source, temporary)
            os.replace(temporary, target)
        journal.unlink()  # Commit marker: no recovery after every file is installed.
    except BaseException:
        _recover(root)
        raise


def _paths(stage: Path, names) -> list[str]:
    output = []
    for name in names:
        path = stage / name
        if path.is_file():
            output.append(name)
        elif path.is_dir():
            output.extend(p.relative_to(stage).as_posix() for p in path.rglob("*")
                          if p.is_file() and not p.name.endswith(".tmp"))
    return output


def _copy_workspace(root: Path, stage: Path) -> None:
    for name in ("acik_sepet", "config", "tests", *PUBLICATION_DIRS):
        source = root / name
        if source.exists():
            shutil.copytree(source, stage / name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.tmp"))
    for name in ("README.md", "METHOD.md", "pyproject.toml", "requirements.txt"):
        if (root / name).exists():
            shutil.copyfile(root / name, stage / name)


def _run(stage: Path, args: list[str]) -> None:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(stage), PYTHONUTF8="1")
    subprocess.run([sys.executable, *args], cwd=stage, env=env, check=True)


def _record_failure(stage: Path, reason: str) -> None:
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    data = stage / "data/v0.4"
    path = data / "collection-status.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    status = dict(previous, date=now.date().isoformat(), checked_at=now.isoformat(),
                  status="rejected", reason=reason, publication_failed=True)
    if previous.get("date") != status["date"]:
        status["errors"] = []
        status.pop("retained_same_day_types", None)
    for name in ("collection-status.json", "latest-errors.json",
                 f"attempts/{now.strftime('%Y%m%dT%H%M%S%f')}-publication.json"):
        target = data / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8", newline="\n")


def _retain_published_diagnostics(root: Path, stage: Path, reason: str) -> None:
    """A successful crawl is still only an attempt if downstream validation fails."""
    directory = stage / "data/v0.4/collection-diagnostics"
    for current in directory.glob("*.json"):
        original = root / current.relative_to(stage)
        content = current.read_bytes()
        if original.exists() and original.read_bytes() == content:
            continue
        report = json.loads(content)
        report.update(status="rejected", publication_failed=True, publication_failure_reason=reason)
        if original.exists() and json.loads(original.read_bytes()).get("status") == "published":
            attempt = directory / "attempts" / f"{current.stem}-publication-{datetime.now().strftime('%Y%m%dT%H%M%S%f')}.json"
            attempt.parent.mkdir(parents=True, exist_ok=True)
            current.write_bytes(original.read_bytes())
        else:
            attempt = current
        attempt.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")


def _verify_artifacts(stage: Path) -> None:
    # Read the declared artifact contract from the staged code, not old filenames.
    script = "from acik_sepet.report import CHART_FILENAMES; from pathlib import Path; " \
             "assert all((Path('charts') / n).is_file() and (Path('charts') / n).stat().st_size > 1000 for n in CHART_FILENAMES)"
    _run(stage, ["-c", script])


def publish(root: Path = ROOT, *, offline: bool = False, test_staged: bool = True) -> None:
    root = root.resolve()
    with publication_lock(root):
        _recover(root)
        with tempfile.TemporaryDirectory(prefix="acik-sepet-publication-") as folder:
            stage = Path(folder)
            _copy_workspace(root, stage)
            pre_finalize_audits = None
            try:
                if not offline:
                    _run(stage, ["-m", "acik_sepet.collect", "--refresh"])
                for module in ("validate", "health", "index", "diagnostics", "report", "history"):
                    _run(stage, ["-m", f"acik_sepet.{module}"])
                _verify_artifacts(stage)
                if test_staged:
                    # Isolate pytest from temp directories owned by another
                    # Windows account (for example the sandbox runner).
                    _run(stage, ["-m", "pytest", "-q", "-p", "no:cacheprovider",
                                 "--basetemp", str(stage / ".pytest-tmp")])
                if not offline:
                    # Only a fully validated publication advances rollout eligibility.
                    audit_names = ["state/v0.4-discovery.json", *_paths(stage, ["data/v0.4/collection-diagnostics"])]
                    pre_finalize_audits = {name: (stage / name).read_bytes() if (stage / name).exists() else None
                                           for name in audit_names}
                    _run(stage, ["-m", "acik_sepet.recovery", "finalize-day"])
                    # Reflect this accepted day in the visible rollout counter.
                    for module in ("diagnostics", "report"):
                        _run(stage, ["-m", f"acik_sepet.{module}"])
                    _verify_artifacts(stage)
                install(root, stage, _paths(stage, (*PUBLICATION_DIRS, "README.md")))
            except (Exception, SystemExit) as exc:
                if offline:
                    # A failed local rebuild is not a source collection attempt.
                    # Installation already rolls back; leave operational status intact.
                    raise
                # A failed installation is NOT a validated publication. Keep
                # discovery observations, but never leak its qualification or
                # published price anchors through the failure audit path.
                if pre_finalize_audits is not None:
                    for name, content in pre_finalize_audits.items():
                        evidence = stage / name
                        if content is not None:
                            evidence.write_bytes(content)
                        elif evidence.exists():
                            evidence.unlink()
                reason = f"Staged publication rejected: {exc}"
                _record_failure(stage, reason)
                _retain_published_diagnostics(root, stage, reason)
                # Use OLD published data to render failure status; never failed staged data.
                with tempfile.TemporaryDirectory(prefix="acik-sepet-status-") as failure_folder:
                    failure = Path(failure_folder)
                    _copy_workspace(root, failure)
                    audit_paths = _paths(stage, AUDIT_PATHS)
                    for name in audit_paths:
                        target = failure / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(stage / name, target)
                    try:
                        _run(failure, ["-m", "acik_sepet.report", "--status-only"])
                    except Exception:
                        # Diagnostics remain available even if the report code itself failed.
                        pass
                    install(root, failure, audit_paths + ["README.md"])
                raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Rebuild recorded data without source requests")
    parser.add_argument("--skip-tests", action="store_true", help="Skip staged tests for local development only")
    args = parser.parse_args()
    publish(offline=args.offline, test_staged=not args.skip_tests)


if __name__ == "__main__":
    main()
