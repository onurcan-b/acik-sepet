"""Protect published observations and index levels across prospective corrections."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
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


if __name__ == "__main__":
    verify_files()
    for filename in ("index.csv", "type_indices.csv", "category_indices.csv"):
        with (ROOT / "data/v0.4" / filename).open(newline="", encoding="utf-8") as handle:
            verify_rows(filename, list(csv.DictReader(handle)))
    print("Published history and the original baseline are unchanged")
