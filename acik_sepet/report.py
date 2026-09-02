from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt

from .product_types import load_categories, load_product_types

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "v0.4"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
INDEX_PATH = DATA_DIR / "index.csv"
TYPE_PATH = DATA_DIR / "type_indices.csv"
CATEGORY_PATH = DATA_DIR / "category_indices.csv"
PANEL_PATH = ROOT / "state" / "v0.4-panels.json"
CHART_DIR = ROOT / "charts"
README_PATH = ROOT / "README.md"

INK = "#172554"
BLUE = "#2563eb"
TEAL = "#0f766e"
ORANGE = "#ea580c"
GRID = "#cbd5e1"


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _latest_snapshot() -> list[dict[str, str]]:
    paths = sorted(SNAPSHOT_DIR.glob("*.csv"))
    return _read(paths[-1]) if paths else []


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
    return (float(valid[-1]["index"]) / float(valid[-1 - days]["index"]) - 1.0) * 100.0


def _save(fig: plt.Figure, name: str) -> None:
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    path = CHART_DIR / name
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)
    # Matplotlib's SVG paths contain harmless trailing spaces that make
    # `git diff --check` noisy. Normalize generated assets at the source.
    normalized = "\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n"
    path.write_text(normalized, encoding="utf-8")


def render_charts(
    index_rows: list[dict[str, str]],
    category_rows: list[dict[str, str]],
    snapshot_rows: list[dict[str, str]],
) -> None:
    plt.rcParams.update({"font.size": 10, "axes.titleweight": "bold", "axes.edgecolor": GRID})

    valid = [row for row in index_rows if row.get("index")]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    if valid:
        dates = [row["date"] for row in valid]
        values = [float(row["index"]) for row in valid]
        ax.plot(dates, values, color=BLUE, linewidth=2.4, marker="o", markersize=5)
        ax.axhline(100, color=INK, linewidth=1, linestyle="--", alpha=0.55)
        ax.set_ylabel("Endeks (baz = 100)")
        ax.set_title("Açık Sepet v0.4 — günlük fiyat endeksi", color=INK)
        step = max(1, len(dates) // 8)
        ticks = list(range(0, len(dates), step))
        ax.set_xticks(ticks, [dates[i] for i in ticks], rotation=30, ha="right")
        ax.grid(axis="y", color=GRID, alpha=0.55)
        ax.grid(axis="x", visible=False)
        if len(valid) == 1:
            ax.annotate(f"{values[0]:.2f}", (0, values[0]), xytext=(8, 8), textcoords="offset points", color=INK)
            ax.set_ylim(99.5, 100.5)
    else:
        ax.text(0.5, 0.5, "İlk v0.4 gözlemi bekleniyor", ha="center", va="center", fontsize=15)
        ax.set_axis_off()
    _save(fig, "index.svg")

    latest_date = max((row["date"] for row in category_rows), default="")
    latest_categories = [row for row in category_rows if row["date"] == latest_date]
    labels = [row["label"] for row in latest_categories]
    coverage = [float(row["coverage"]) * 100 for row in latest_categories]
    colors = [TEAL if value >= 80 else BLUE if value >= 60 else ORANGE for value in coverage]
    fig, ax = plt.subplots(figsize=(9, 6.2))
    bars = ax.barh(labels[::-1], coverage[::-1], color=colors[::-1])
    ax.axvline(60, color=INK, linewidth=1, linestyle="--", alpha=0.6)
    ax.set_xlim(0, 105)
    ax.set_xlabel("Yeterli SKU bulunan ürün tipi (%)")
    ax.set_title("Kategori kapsaması — eksik tipler paydadan saklanmıyor", color=INK)
    ax.grid(axis="x", color=GRID, alpha=0.5)
    ax.grid(axis="y", visible=False)
    for bar, value in zip(bars, coverage[::-1]):
        ax.text(min(value + 1.2, 100), bar.get_y() + bar.get_height() / 2, f"%{value:.0f}", va="center", fontsize=9)
    _save(fig, "coverage.svg")

    categories = load_categories()
    sku_counts = Counter(row["group"] for row in snapshot_rows)
    labels = [category["label"] for category in categories]
    counts = [sku_counts[category["id"]] for category in categories]
    fig, ax = plt.subplots(figsize=(9, 6.2))
    bars = ax.barh(labels[::-1], counts[::-1], color=TEAL)
    ax.set_xlabel("Gerçek ve sıkı eşleşmiş SKU")
    ax.set_title("Sepetin kategori dağılımı", color=INK)
    ax.grid(axis="x", color=GRID, alpha=0.5)
    ax.grid(axis="y", visible=False)
    offset = max(counts + [1]) * 0.012
    for bar, value in zip(bars, counts[::-1]):
        ax.text(value + offset, bar.get_y() + bar.get_height() / 2, str(value), va="center", fontsize=9)
    _save(fig, "basket.svg")


def _stats(index_rows: list[dict[str, str]]) -> str:
    valid = [row for row in index_rows if row.get("index")]
    if not valid:
        return "İlk v0.4 gözlemi bekleniyor."
    latest = valid[-1]
    change_7 = _change(index_rows, 7)
    change_30 = _change(index_rows, 30)
    return "\n".join([
        "| Endeks | Tarih | Aktif tip | Endeks SKU | Kategori kapsaması | 7 gün | 30 gün | Baz |",
        "|---:|---|---:|---:|---:|---:|---:|---|",
        f"| **{float(latest['index']):.2f}** | {latest['date']} | {latest['types']} | {latest['skus']} | %{float(latest['coverage']) * 100:.0f} | "
        f"{'—' if change_7 is None else f'{change_7:+.2f}%'} | {'—' if change_30 is None else f'{change_30:+.2f}%'} | {latest['baseline_date']} = 100 |",
    ])


def _movers(type_rows: list[dict[str, str]]) -> str:
    dates = sorted({row["date"] for row in type_rows})
    if len(dates) < 2:
        return "İkinci gözlemden sonra günlük hareketler burada belirecek. Baseline gününde dramatik hikâye çıkarmıyoruz."
    previous_date, latest_date = dates[-2], dates[-1]
    previous = {row["type_id"]: row for row in type_rows if row["date"] == previous_date and row.get("index")}
    latest = {row["type_id"]: row for row in type_rows if row["date"] == latest_date and row.get("index")}
    changes = []
    for type_id in sorted(set(previous) & set(latest)):
        old = float(previous[type_id]["index"])
        new = float(latest[type_id]["index"])
        changes.append(((new / old - 1.0) * 100.0, latest[type_id]))
    up = sum(pct > 0.005 for pct, _ in changes)
    down = sum(pct < -0.005 for pct, _ in changes)
    flat = len(changes) - up - down
    lines = [
        f"{previous_date} → {latest_date}: **{up} yukarı**, **{down} aşağı**, **{flat} yatay**. Karşılaştırılan tip: {len(changes)}.",
        "",
        "| Ürün tipi | SKU | Değişim |",
        "|---|---:|---:|",
    ]
    for pct, row in sorted(changes, key=lambda value: abs(value[0]), reverse=True)[:10]:
        lines.append(f"| {row['label']} | {row['skus']} | {pct:+.2f}% |")
    return "\n".join(lines)


def _category_table(
    type_rows: list[dict[str, str]],
    category_rows: list[dict[str, str]],
    snapshot_rows: list[dict[str, str]],
) -> str:
    if not category_rows:
        return "Kategori tablosu ilk gözlemle üretilecek."
    specs = load_product_types()
    latest_date = max(row["date"] for row in category_rows)
    type_latest = [row for row in type_rows if row["date"] == latest_date]
    category_latest = {row["group_id"]: row for row in category_rows if row["date"] == latest_date}
    sku_counts = Counter(row["group"] for row in snapshot_rows)
    lines = [
        "| Kategori | Endeks | Yeterli tip | Kapsama | SKU |",
        "|---|---:|---:|---:|---:|",
    ]
    for category in load_categories():
        group = category["id"]
        row = category_latest[group]
        members = [spec for spec in specs if spec["group"] == group]
        active = sum(item["group"] == group and bool(item.get("index")) for item in type_latest)
        index = f"{float(row['index']):.2f}" if row.get("index") else "—"
        lines.append(
            f"| {category['label']} | {index} | {active}/{len(members)} | %{float(row['coverage']) * 100:.0f} | {sku_counts[group]} |"
        )
    return "\n".join(lines)


def _gaps(type_rows: list[dict[str, str]], snapshot_rows: list[dict[str, str]]) -> str:
    if not type_rows:
        return "İlk gözlem bekleniyor."
    specs = load_product_types()
    latest_date = max(row["date"] for row in type_rows)
    latest = {row["type_id"]: row for row in type_rows if row["date"] == latest_date}
    observed = Counter(row["type_id"] for row in snapshot_rows)
    missing = [spec for spec in specs if not latest[spec["id"]].get("index")]
    missing.sort(key=lambda spec: (observed[spec["id"]] - spec["min_skus"], spec["label"]))
    if not missing:
        return "Bütün ürün tipleri kendi minimum SKU eşiğini geçti."
    lines = [
        f"**{len(missing)} ürün tipi** minimum eşiğin altında. Yanlış ürünle doldurulmadılar; endekse girmiyorlar.",
        "",
        "| Ürün tipi | Gözlenen | Minimum | API kategori filtresi |",
        "|---|---:|---:|---|",
    ]
    for spec in missing[:18]:
        categories = ", ".join(spec["api_categories"])
        lines.append(f"| {spec['label']} | {observed[spec['id']]} | {spec['min_skus']} | {categories} |")
    if len(missing) > 18:
        lines.append(f"\nTabloda en zayıf 18 tip var; toplam eksik tip sayısı {len(missing)}.")
    return "\n".join(lines)


def _quality(snapshot_rows: list[dict[str, str]]) -> str:
    if not snapshot_rows:
        return "İlk kalite ölçümü bekleniyor."
    pinned = sum(row.get("source_mode") == "pinned-relative" for row in snapshot_rows)
    refined = sum(row.get("quantity_source") == "api-refined" for row in snapshot_rows)
    api_units = sum(bool(row.get("api_unit_price")) for row in snapshot_rows)
    markets = set()
    for row in snapshot_rows:
        try:
            markets.update(json.loads(row.get("markets") or "[]"))
        except json.JSONDecodeError:
            pass
    renewals = 0
    if PANEL_PATH.exists():
        state = json.loads(PANEL_PATH.read_text(encoding="utf-8"))
        renewals = sum(int(item.get("renewals", 0)) for item in (state.get("types") or {}).values())
    return "\n".join([
        f"- **{len(snapshot_rows)}** sıkı eşleşmiş SKU, **{len(markets)}** market etiketi",
        f"- **{refined}/{len(snapshot_rows)}** miktar doğrudan API'nin normalize alanından",
        f"- **{api_units}/{len(snapshot_rows)}** satırda birim fiyat API değeriyle ayrıca kontrol edildi",
        f"- **{pinned}/{len(snapshot_rows)}** gözlem sabit depot relatifleriyle bağlı",
        f"- **{renewals}** bridge edilmiş panel yenilemesi (yeni baseline'da doğal olarak sıfır)",
    ])


def main() -> None:
    index_rows = _read(INDEX_PATH)
    type_rows = _read(TYPE_PATH)
    category_rows = _read(CATEGORY_PATH)
    snapshot_rows = _latest_snapshot()
    render_charts(index_rows, category_rows, snapshot_rows)
    text = README_PATH.read_text(encoding="utf-8")
    text = _replace(text, "<!-- STATS_START -->", "<!-- STATS_END -->", _stats(index_rows))
    text = _replace(text, "<!-- MOVERS_START -->", "<!-- MOVERS_END -->", _movers(type_rows))
    text = _replace(
        text,
        "<!-- CATEGORY_TABLE_START -->",
        "<!-- CATEGORY_TABLE_END -->",
        _category_table(type_rows, category_rows, snapshot_rows),
    )
    text = _replace(text, "<!-- GAPS_START -->", "<!-- GAPS_END -->", _gaps(type_rows, snapshot_rows))
    text = _replace(text, "<!-- QUALITY_START -->", "<!-- QUALITY_END -->", _quality(snapshot_rows))
    README_PATH.write_text(text, encoding="utf-8")
    print("charts=" + ",".join(str(path.relative_to(ROOT)) for path in sorted(CHART_DIR.glob("*.svg"))))


if __name__ == "__main__":
    main()
