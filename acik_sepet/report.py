from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "data" / "index.csv"
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
CHART_PATH = ROOT / "charts" / "index.svg"
README_PATH = ROOT / "README.md"
START = "<!-- STATS_START -->"
END = "<!-- STATS_END -->"
MOVERS_START = "<!-- MOVERS_START -->"
MOVERS_END = "<!-- MOVERS_END -->"


def _read_rows() -> list[dict[str, str]]:
    if not INDEX_PATH.exists():
        return []
    with INDEX_PATH.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_snapshots() -> list[dict]:
    if not SNAPSHOT_DIR.exists():
        return []
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(SNAPSHOT_DIR.glob("*.json"))
    ]


def _valid_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("index") not in (None, "")]


def _change(rows: list[dict[str, str]], days_back: int) -> float | None:
    valid = _valid_rows(rows)
    if len(valid) <= days_back:
        return None
    latest = float(valid[-1]["index"])
    previous = float(valid[-1 - days_back]["index"])
    return (latest / previous - 1.0) * 100.0


def _snapshot_items(snapshot: dict) -> dict[str, dict]:
    return snapshot.get("items") or ((snapshot.get("locations") or {}).get("national") or {}).get("items") or {}


def _daily_movers_markdown(snapshots: list[dict]) -> str:
    if len(snapshots) < 2:
        return "\n".join([
            "- **Durum:** En az iki günlük snapshot bekleniyor.",
            "- Fiyat hareketleri ikinci başarılı günlük çalışmadan sonra burada görünecek.",
        ])

    previous, latest = snapshots[-2], snapshots[-1]
    previous_items = _snapshot_items(previous)
    latest_items = _snapshot_items(latest)
    previous_ids = set(previous_items)
    latest_ids = set(latest_items)
    common = sorted(previous_ids & latest_ids)

    changes: list[dict] = []
    unchanged = 0
    for item_id in common:
        old = previous_items[item_id].get("price_median")
        new = latest_items[item_id].get("price_median")
        if not isinstance(old, (int, float)) or not isinstance(new, (int, float)) or old <= 0:
            continue
        pct = (float(new) / float(old) - 1.0) * 100.0
        if abs(pct) < 1e-9:
            unchanged += 1
            continue
        item = latest_items[item_id]
        changes.append({
            "id": item_id,
            "label": item.get("basket_label") or item.get("selected_title") or item_id,
            "old": float(old),
            "new": float(new),
            "pct": pct,
        })

    risers = sorted((row for row in changes if row["pct"] > 0), key=lambda row: row["pct"], reverse=True)
    fallers = sorted((row for row in changes if row["pct"] < 0), key=lambda row: row["pct"])
    target = int(latest.get("target_items") or max(len(latest_items), len(previous_items)))
    newly_missing = previous_ids - latest_ids
    newly_available = latest_ids - previous_ids

    lines = [
        f"- **Dönem:** {previous.get('date', '—')} → {latest.get('date', '—')}",
        f"- **↑ Zamlanan:** {len(risers)} · **↓ Ucuzlayan:** {len(fallers)} · **= Değişmeyen:** {unchanged}",
        f"- **Karşılaştırılan:** {len(common)}/{target} ürün · **Bugün gözlem dışı:** {max(0, target - len(latest_items))}",
        f"- **Yeni kaybolan:** {len(newly_missing)} · **Geri dönen/yeni eşleşen:** {len(newly_available)}",
    ]

    top = risers[:5] + fallers[:5]
    if top:
        lines.extend([
            "",
            "| Ürün | Önceki | Son | Değişim |",
            "|---|---:|---:|---:|",
        ])
        for row in top:
            lines.append(
                f"| {row['label']} | {row['old']:.2f} TL | {row['new']:.2f} TL | {row['pct']:+.2f}% |"
            )
    else:
        lines.extend(["", "Karşılaştırılabilen ürünlerde son 24 saatte fiyat değişimi gözlenmedi."])

    return "\n".join(lines)


def render_chart(rows: list[dict[str, str]]) -> None:
    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    valid = _valid_rows(rows)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    if valid:
        dates = [row["date"] for row in valid]
        values = [float(row["index"]) for row in valid]
        ax.plot(dates, values, linewidth=2)
        ax.axhline(100, linewidth=1, linestyle="--")
        ax.set_ylabel("Endeks (baz = 100)")
        ax.set_title("Açık Sepet Günlük Market Fiyat Endeksi")
        step = max(1, len(dates) // 8)
        ax.set_xticks(range(0, len(dates), step), [dates[i] for i in range(0, len(dates), step)], rotation=30, ha="right")
        ax.grid(True, alpha=0.2)
    else:
        ax.text(0.5, 0.55, "Henüz gerçek snapshot yok", ha="center", va="center", fontsize=16)
        ax.text(0.5, 0.43, "İlk GitHub Actions çalışmasından sonra grafik otomatik oluşacak.", ha="center", va="center")
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(CHART_PATH, format="svg")
    plt.close(fig)


def _replace_block(text: str, start: str, end: str, body: str) -> str:
    replacement = start + "\n" + body + "\n" + end
    before, marker, tail = text.partition(start)
    if not marker:
        raise RuntimeError(f"README başlangıç işareti bulunamadı: {start}")
    _, marker2, after = tail.partition(end)
    if not marker2:
        raise RuntimeError(f"README bitiş işareti bulunamadı: {end}")
    return before + replacement + after


def update_readme(rows: list[dict[str, str]], snapshots: list[dict]) -> None:
    text = README_PATH.read_text(encoding="utf-8")
    valid = _valid_rows(rows)
    if valid:
        latest = valid[-1]
        change_30 = _change(rows, 30)
        change_7 = _change(rows, 7)
        stats = [
            f"- **Son değer:** {float(latest['index']):.2f}",
            f"- **Son güncelleme:** {latest['date']}",
            f"- **Kapsama:** %{float(latest['coverage']) * 100:.0f} ({latest['items']} ürün)",
            f"- **7 günlük değişim:** {'—' if change_7 is None else f'{change_7:+.2f}%'}",
            f"- **30 günlük değişim:** {'—' if change_30 is None else f'{change_30:+.2f}%'}",
            f"- **Baz tarihi:** {latest['baseline_date']} = 100",
        ]
    else:
        stats = [
            "- **Durum:** İlk gerçek snapshot bekleniyor.",
            "- **Grafik:** İlk başarılı GitHub Actions koşusundan sonra otomatik güncellenecek.",
        ]

    text = _replace_block(text, START, END, "\n".join(stats))
    text = _replace_block(text, MOVERS_START, MOVERS_END, _daily_movers_markdown(snapshots))
    README_PATH.write_text(text, encoding="utf-8")


def main() -> None:
    rows = _read_rows()
    snapshots = _read_snapshots()
    render_chart(rows)
    update_readme(rows, snapshots)
    print(f"chart={CHART_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
