from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "v0.3"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
INDEX_PATH = DATA_DIR / "index.csv"
TYPE_PATH = DATA_DIR / "type_indices.csv"
CATEGORY_PATH = DATA_DIR / "category_indices.csv"
PANEL_PATH = ROOT / "state" / "v0.3-panels.json"
CHART_PATH = ROOT / "charts" / "index.svg"
README_PATH = ROOT / "README.md"


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _replace(text: str, start: str, end: str, body: str) -> str:
    before, marker, tail = text.partition(start)
    if not marker:
        raise RuntimeError(f"README marker not found: {start}")
    _, marker2, after = tail.partition(end)
    if not marker2:
        raise RuntimeError(f"README marker not found: {end}")
    return before + start + "\n" + body.rstrip() + "\n" + end + after


def _change(rows: list[dict[str, str]], days: int) -> float | None:
    valid = [row for row in rows if row.get("index")]
    if len(valid) <= days:
        return None
    latest = float(valid[-1]["index"])
    old = float(valid[-1 - days]["index"])
    return (latest / old - 1.0) * 100.0


def render_chart(rows: list[dict[str, str]]) -> None:
    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    valid = [row for row in rows if row.get("index")]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    if valid:
        dates = [row["date"] for row in valid]
        values = [float(row["index"]) for row in valid]
        ax.plot(dates, values, linewidth=2)
        ax.axhline(100, linewidth=1, linestyle="--")
        ax.set_ylabel("Endeks (baz = 100)")
        ax.set_title("Açık Sepet v0.3 — Günlük Market Fiyat Endeksi")
        step = max(1, len(dates) // 8)
        ax.set_xticks(range(0, len(dates), step), [dates[i] for i in range(0, len(dates), step)], rotation=30, ha="right")
        ax.grid(True, alpha=0.2)
    else:
        ax.text(0.5, 0.5, "İlk v0.3 gözlemi bekleniyor", ha="center", va="center", fontsize=16)
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(CHART_PATH, format="svg")
    plt.close(fig)


def _stats(index_rows: list[dict[str, str]]) -> str:
    valid = [row for row in index_rows if row.get("index")]
    if not valid:
        return "- **Durum:** İlk v0.3 gözlemi bekleniyor."
    latest = valid[-1]
    change_7 = _change(index_rows, 7)
    change_30 = _change(index_rows, 30)
    return "\n".join([
        f"- **Son değer:** {float(latest['index']):.2f}",
        f"- **Son güncelleme:** {latest['date']}",
        f"- **Aktif ürün tipi:** {latest['types']}",
        f"- **Karşılaştırılabilir SKU:** {latest['skus']}",
        f"- **Kategori ağırlık kapsaması:** %{float(latest['coverage']) * 100:.0f}",
        f"- **7 günlük değişim:** {'—' if change_7 is None else f'{change_7:+.2f}%'}",
        f"- **30 günlük değişim:** {'—' if change_30 is None else f'{change_30:+.2f}%'}",
        f"- **Baz tarihi:** {latest['baseline_date']} = 100",
    ])


def _movers(type_rows: list[dict[str, str]]) -> str:
    dates = sorted({row["date"] for row in type_rows})
    if len(dates) < 2:
        return "İkinci v0.3 gözlemi geldikten sonra ürün tipi hareketleri burada gösterilecek."
    previous_date, latest_date = dates[-2], dates[-1]
    previous = {row["type_id"]: row for row in type_rows if row["date"] == previous_date and row.get("index")}
    latest = {row["type_id"]: row for row in type_rows if row["date"] == latest_date and row.get("index")}
    changes = []
    for type_id in sorted(set(previous) & set(latest)):
        old = float(previous[type_id]["index"])
        new = float(latest[type_id]["index"])
        pct = (new / old - 1.0) * 100.0
        changes.append((pct, latest[type_id]))
    up = sum(pct > 0.005 for pct, _ in changes)
    down = sum(pct < -0.005 for pct, _ in changes)
    flat = len(changes) - up - down
    lines = [
        f"- **Dönem:** {previous_date} → {latest_date}",
        f"- **↑ Yükselen ürün tipi:** {up} · **↓ Düşen:** {down} · **= Yatay:** {flat}",
        f"- **Karşılaştırılan ürün tipi:** {len(changes)}",
    ]
    meaningful = sorted(changes, key=lambda row: abs(row[0]), reverse=True)[:10]
    if meaningful and any(abs(pct) >= 0.01 for pct, _ in meaningful):
        lines += ["", "| Ürün tipi | SKU | Değişim |", "|---|---:|---:|"]
        for pct, row in meaningful:
            if abs(pct) < 0.01:
                continue
            lines.append(f"| {row['label']} | {row['skus']} | {pct:+.2f}% |")
    else:
        lines += ["", "Karşılaştırılabilir ürün tiplerinde anlamlı günlük hareket gözlenmedi."]
    return "\n".join(lines)


def _source_and_renewal_stats() -> tuple[int, int, int]:
    latest_paths = sorted(SNAPSHOT_DIR.glob("*.csv"))
    rows = _read(latest_paths[-1]) if latest_paths else []
    pinned = sum(row.get("source_mode") == "pinned" for row in rows)
    source_aware = sum(bool(row.get("source_mode")) for row in rows)
    renewals = 0
    if PANEL_PATH.exists():
        state = json.loads(PANEL_PATH.read_text(encoding="utf-8"))
        renewals = sum(int(item.get("renewals", 0)) for item in (state.get("types") or {}).values())
    return pinned, source_aware, renewals


def _quality(type_rows: list[dict[str, str]], category_rows: list[dict[str, str]]) -> str:
    if not type_rows:
        return "İlk kalite ölçümü bekleniyor."
    latest_date = max(row["date"] for row in type_rows)
    latest_types = [row for row in type_rows if row["date"] == latest_date]
    active = [row for row in latest_types if row.get("index")]
    low = [row for row in active if float(row["coverage"]) < 0.70]
    total_baseline_skus = sum(int(row["baseline_skus"]) for row in active)
    current_skus = sum(int(row["skus"]) for row in active)
    category_latest = [row for row in category_rows if row["date"] == latest_date and row.get("index")]
    pinned, source_aware, renewals = _source_and_renewal_stats()
    source_line = (
        f"- **Sabit kaynak kimliği olan gözlem:** {pinned}/{source_aware}"
        if source_aware else
        "- **Kaynak sabitleme:** legacy snapshot; source-aware toplama bir sonraki çalışmada başlayacak."
    )
    return "\n".join([
        f"- **Aktif ürün tipi:** {len(active)}/{len(latest_types)}",
        f"- **SKU panel kapsaması:** {current_skus}/{total_baseline_skus} ({(current_skus / total_baseline_skus * 100 if total_baseline_skus else 0):.1f}%)",
        f"- **%70'in altında panel kapsaması olan tip:** {len(low)}",
        f"- **Yayımlanan ana kategori:** {len(category_latest)}",
        source_line,
        f"- **Köprülenmiş otomatik SKU yenilemesi:** {renewals}",
        "- Kaynak/depo değişimi sessiz fiyat değişimi sayılmaz; kaynaklar SKU bazında sabitlenir. Panel yenilemesi ancak kalıcı kapsama kaybında ve bridge factor ile yapılır.",
    ])


def main() -> None:
    index_rows = _read(INDEX_PATH)
    type_rows = _read(TYPE_PATH)
    category_rows = _read(CATEGORY_PATH)
    render_chart(index_rows)
    text = README_PATH.read_text(encoding="utf-8")
    text = _replace(text, "<!-- STATS_START -->", "<!-- STATS_END -->", _stats(index_rows))
    text = _replace(text, "<!-- MOVERS_START -->", "<!-- MOVERS_END -->", _movers(type_rows))
    text = _replace(text, "<!-- QUALITY_START -->", "<!-- QUALITY_END -->", _quality(type_rows, category_rows))
    README_PATH.write_text(text, encoding="utf-8")
    print(f"chart={CHART_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
