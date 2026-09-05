"""Auditable freshness and sample turnover diagnostics; no price imputation."""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "v0.4"


def summarize(rows, previous=()):
    day = max((row["date"] for row in rows), default="")
    ages = []
    unknown = 0
    for row in rows:
        try:
            stamp = datetime.strptime(row["source_updated_at"], "%d.%m.%Y %H:%M").date()
            ages.append((date.fromisoformat(day) - stamp).days)
        except (ValueError, KeyError, TypeError):
            unknown += 1
    old = {row["slot_id"]: row for row in previous}
    current = {row["slot_id"]: row for row in rows}
    common = sorted(set(old) & set(current))
    moves = []
    for key in common:
        a, b = old[key], current[key]
        change = (float(b["linked_unit_price"]) / float(a["linked_unit_price"]) - 1) * 100
        if abs(change) >= 20:
            moves.append({"slot_id": key, "title": b["title"], "change_pct": round(change, 2)})
    warnings = []
    today = sum(age == 0 for age in ages)
    recent = sum(0 <= age <= 3 for age in ages)
    if rows and today / len(rows) < 0.5:
        warnings.append("Gözlemlerin çoğunda kaynak güncelleme tarihi bugünden eski veya bilinmiyor.")
    if old and len(common) / len(old) < 0.8:
        warnings.append("Önceki ölçümdeki panel slotlarının %20'den fazlası bugün gözlenemedi.")
    return {
        "date": day, "rows": len(rows), "source_updated_today": today,
        "source_within_3_days": recent, "source_date_unknown": unknown,
        "source_date_future": sum(age < 0 for age in ages),
        "source_age_days": dict(sorted(Counter(ages).items())),
        "freshness_basis": "Her SKU'nun kullanılan depotları arasındaki en yeni kaynak tarihi; tüm depotların güncelliğini kanıtlamaz.",
        "previous_date": max((row["date"] for row in previous), default=None),
        "matched_slots": len(common), "missing_slots": len(set(old) - set(current)),
        "new_slots": len(set(current) - set(old)),
        "large_price_moves": sorted(moves, key=lambda r: -abs(r["change_pct"])),
        "warnings": warnings,
    }


def rebuild():
    previous = []
    history = []
    for path in sorted((DATA / "snapshots").glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        history.append(summarize(rows, previous))
        previous = rows
    (DATA / "health.json").write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history:
        latest = history[-1]
        print(json.dumps({k: v for k, v in latest.items() if k != "large_price_moves"}, ensure_ascii=False))
        if latest["source_date_future"] or latest["source_within_3_days"] < latest["rows"] * 0.60:
            raise SystemExit("Kaynak güncelliği yayın eşiğini geçemedi")
    return history


if __name__ == "__main__":
    rebuild()
