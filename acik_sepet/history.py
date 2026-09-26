"""Protect published observations and index levels across prospective corrections."""
from __future__ import annotations

import csv
import argparse
import hashlib
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def canonical_bytes(path: Path) -> bytes:
    """Git text hashes use LF; tolerate an existing Windows CRLF checkout."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def verify_files(root: Path = ROOT) -> None:
    path = root / "config/history-lock.json"
    if not path.exists():
        return
    lock = json.loads(path.read_text())
    series = json.loads((root / "config/series.json").read_text())
    for key in ("baseline_date", "locked_through"):
        if series.get(key) != lock[key]:
            raise ValueError(f"Protected series setting changed: {key}")
    for name, expected in lock["files"].items():
        target = root / name
        if not target.exists() or hashlib.sha256(canonical_bytes(target)).hexdigest() != expected:
            raise ValueError(f"Protected historical file changed: {name}")


def verify_rows(name: str, computed: list[dict], root: Path = ROOT) -> None:
    series = json.loads((root / "config/series.json").read_text())
    cutoff = series.get("locked_through")
    if not cutoff:
        return
    path = root / "data/v0.4" / f"frozen-{cutoff}" / name
    with path.open(newline="", encoding="utf-8") as handle:
        expected = list(csv.DictReader(handle))
    current = [row for row in computed if row["date"] <= cutoff]
    if len(current) != len(expected):
        raise ValueError(f"Protected history row count changed: {name}")
    for old, new in zip(expected, current):
        if any(old[key] != ("" if new[key] is None else str(new[key])) for key in old):
            raise ValueError(f"Protected historical index changed: {name} {old['date']}")


def freeze_through_latest(root: Path = ROOT) -> str:
    """Extend, never replace, immutable history before a prospective rollout."""
    from .publish import _recover, publication_lock
    with publication_lock(root):
        # Recover an interrupted pair of metadata writes before verifying it.
        _recover(root)
        return _freeze_through_latest(root)


def _freeze_through_latest(root: Path) -> str:
    verify_files(root)
    series_path = root / "config/series.json"
    series = json.loads(series_path.read_text(encoding="utf-8"))
    data = root / "data/v0.4"
    names = ("index.csv", "type_indices.csv", "category_indices.csv")
    for name in names:
        with (data / name).open(encoding="utf-8", newline="") as handle:
            verify_rows(name, list(csv.DictReader(handle)), root)
    with (data / "index.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Cannot freeze an empty published series")
    cutoff = max(row["date"] for row in rows)
    if cutoff < series.get("locked_through", ""):
        raise ValueError("Cannot shorten protected history")
    lock_path = root / "config/history-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.exists() else {"files": {}}
    frozen = data / f"frozen-{cutoff}"
    frozen.mkdir(parents=True, exist_ok=True)
    protected = [p for p in (data / "snapshots").glob("*.csv") if p.stem <= cutoff]
    for name in names:
        target = frozen / name
        content = canonical_bytes(data / name)
        if target.exists() and canonical_bytes(target) != content:
            raise ValueError(f"Refusing to overwrite frozen index: {name}")
        target.write_bytes(content)
        protected.append(target)
    for path in protected:
        content = canonical_bytes(path)
        path.write_bytes(content)
        lock["files"][path.relative_to(root).as_posix()] = hashlib.sha256(content).hexdigest()
    lock.update(baseline_date=series["baseline_date"], locked_through=cutoff)
    series["locked_through"] = cutoff
    # A half-written pair would stop every future verifier. Use the publication
    # journal for the two small metadata files, just like a daily installation.
    from .publish import install
    with tempfile.TemporaryDirectory(prefix="acik-sepet-freeze-") as directory:
        stage = Path(directory)
        (stage / "config").mkdir()
        for path, payload in ((lock_path, lock), (series_path, series)):
            (stage / "config" / path.name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                                     encoding="utf-8", newline="\n")
        install(root, stage, ["config/history-lock.json", "config/series.json"])
    return cutoff


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-through-latest", action="store_true")
    args = parser.parse_args()
    if args.freeze_through_latest:
        print(f"History protected through {freeze_through_latest()}")
    verify_files()
    for filename in ("index.csv", "type_indices.csv", "category_indices.csv"):
        with (ROOT / "data/v0.4" / filename).open(newline="", encoding="utf-8") as handle:
            verify_rows(filename, list(csv.DictReader(handle)))
    print("Published history and the original baseline are unchanged")


if __name__ == "__main__":
    main()
