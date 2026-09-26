from __future__ import annotations

import csv
import hashlib
import json
import math
import textwrap
from datetime import date, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from .product_types import load_product_types

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "v0.4"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
INDEX_PATH = DATA_DIR / "index.csv"
TYPE_PATH = DATA_DIR / "type_indices.csv"
CATEGORY_PATH = DATA_DIR / "category_indices.csv"
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
    if not rows:
        return None
    latest = max(rows, key=lambda row: row["date"])
    target = (date.fromisoformat(latest["date"]) - timedelta(days=days)).isoformat()
    old = next((_number(row.get("index")) for row in rows if row["date"] == target), None)
    new = _number(latest.get("index"))
    if old is None or old <= 0 or new is None:
        return None
    return (new / old - 1.0) * 100.0


def _save(fig: plt.Figure, name: str) -> None:
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(pad=1.3)
    path = CHART_DIR / name
    fig.savefig(path, format="svg", bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)
    # Matplotlib's SVG paths contain harmless trailing spaces that make
    # `git diff --check` noisy. Normalize generated assets at the source.
    normalized = "\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n"
    path.write_text(normalized, encoding="utf-8", newline="\n")



RENDERER_VERSION = "grocery-dashboard-1"
CHART_FILENAMES = ("index.svg", "categories.svg", "category-heatmap.svg", "movers.svg", "quality.svg", "retailers.svg")
SHORT_LABELS = {"bread_cereals": "Ekmek ve tahıllar", "meat": "Et ürünleri", "fish": "Balık",
                "dairy_eggs": "Süt ve yumurta", "oils_fats": "Yağlar", "fruit": "Meyve",
                "vegetables": "Sebze", "sugar_snacks": "Tatlı ve atıştırmalık", "other_food": "Diğer gıda",
                "drinks": "İçecekler", "household_cleaning": "Ev temizliği", "personal_paper": "Kişisel bakım / kağıt"}
MUTED = "#64748b"


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def _pct(value):
    return "—" if value is None else f"{value:+.2f}%"


def _calendar(end, count):
    last = date.fromisoformat(end)
    return [(last - timedelta(days=i)).isoformat() for i in range(count - 1, -1, -1)]


def _style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(length=0, pad=7)
    ax.set_axisbelow(True)


def _date_axis(ax, days):
    # Evenly spaced ticks include both endpoints without a near-end collision.
    ticks = sorted({round(i * (len(days) - 1) / 4) for i in range(5)})
    ax.set_xticks(ticks, [date.fromisoformat(days[i]).strftime("%d.%m") for i in ticks])
    ax.set_xlim(-.4, max(.4, len(days) - .6))


def _empty(ax, text="Karşılaştırılabilir gözlem yok"):
    ax.text(.5, .5, text, ha="center", va="center", transform=ax.transAxes, color=MUTED)
    ax.set_axis_off()


def _quality_days(quality):
    return {day["date"]: day for day in (quality or {}).get("days", [])}


def _fresh(row):
    share = _number(row.get("fresh_within_1_day_share"))
    return share is not None and share >= .9


def render_charts(index_rows, category_rows, snapshot_rows, type_rows=None, quality=None):
    """Fingerprint all evidence and renderer code, including changes to quality flags."""
    plt.rcParams.update({"font.size": 11.5, "axes.titlesize": 14, "axes.titleweight": "bold",
                         "axes.labelcolor": INK, "text.color": INK, "axes.edgecolor": GRID,
                         "svg.hashsalt": "acik-sepet-dashboard", "svg.fonttype": "none"})
    type_rows, quality = type_rows or [], quality or {}
    payload = {"renderer": RENDERER_VERSION, "source": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "index": index_rows, "categories": category_rows, "types": type_rows,
               "snapshot": snapshot_rows, "quality": quality}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    stamp = CHART_DIR / "index-input.sha256"
    if stamp.exists() and stamp.read_text().strip() == fingerprint and all((CHART_DIR / name).exists() for name in CHART_FILENAMES):
        return
    _render_index_chart(index_rows, quality)
    _render_categories(category_rows, quality)
    _render_heatmap(category_rows, quality)
    _render_movers(type_rows, quality)
    _render_quality(index_rows, quality)
    _render_retailers(quality)
    stamp.write_text(fingerprint + "\n", encoding="utf-8", newline="\n")


def _render_index_chart(index_rows, quality=None):
    fig, ax = plt.subplots(figsize=(7.2, 4.3))
    if index_rows:
        ordered = sorted(index_rows, key=lambda r: r["date"])
        by_date, diagnostics = {row["date"]: row for row in ordered}, _quality_days(quality)
        count = (date.fromisoformat(ordered[-1]["date"]) - date.fromisoformat(ordered[0]["date"])).days + 1
        days = _calendar(ordered[-1]["date"], count)
        values = [_number(by_date.get(day, {}).get("index")) for day in days]
        ax.plot(range(len(days)), [float("nan") if v is None else v for v in values], color=BLUE, linewidth=2.4, label="Gözlenen endeks")
        partial = [i for i, day in enumerate(days) if values[i] is not None and
                   diagnostics.get(day, {}).get("partial_coverage", (_number(by_date.get(day, {}).get("coverage")) or 0) < .9999)]
        if partial:
            ax.scatter(partial, [values[i] for i in partial], s=30, marker="o", facecolors="white",
                       edgecolors=ORANGE, linewidths=1.4, zorder=3, label="Kısmi kapsam")
        ax.axhline(100, color=MUTED, linewidth=1, linestyle="--")
        _date_axis(ax, days)
        ax.set_title("Açık Sepet · günlük fiyat endeksi", loc="left", pad=13)
        ax.set_ylabel(f"{ordered[-1].get('baseline_date') or '2026-09-05'} = 100")
        ax.grid(axis="y", color=GRID)
        ax.legend(loc="upper left", frameon=False, fontsize=10)
        valid = [(i, value) for i, value in enumerate(values) if value is not None]
        if valid:
            i, value = valid[-1]
            ax.annotate(f"{value:.2f}", (i, value), xytext=(-4, 11), textcoords="offset points",
                        ha="right", color=BLUE, fontweight="bold")
            ax.margins(y=.22)
        _style(ax)
    else:
        _empty(ax, "İlk gözlem bekleniyor")
    _save(fig, "index.svg")


def _category_changes(rows, end, days=7):
    current = [r for r in rows if r["date"] == end]
    return [(row, _change([r for r in rows if r["group_id"] == row["group_id"] and r["date"] <= end], days)) for row in current]


def _render_categories(rows, quality):
    fig, ax = plt.subplots(figsize=(7.2, 5.4))
    end = max((r["date"] for r in rows), default="")
    if end:
        changes = _category_changes(rows, end)
        quality_days = _quality_days(quality)
        diag = {r["group_id"]: r for r in quality_days.get(end, {}).get("categories", [])}
        old_date = (date.fromisoformat(end) - timedelta(days=7)).isoformat()
        old_diag = {r["group_id"]: r for r in quality_days.get(old_date, {}).get("categories", [])}
        limit = max([abs(v) for _, v in changes if v is not None] + [1]) * 1.45
        for i, (row, value) in enumerate(changes):
            if value is None:
                ax.text(0, i, "  — ölçüm yok", va="center", color=MUTED, fontsize=10.5)
            else:
                fresh = _fresh(diag.get(row["group_id"], {})) and _fresh(old_diag.get(row["group_id"], {}))
                ax.barh(i, value, color=ORANGE if value > 0 else TEAL, alpha=1 if fresh else .4, hatch=None if fresh else "//")
                ax.annotate(_pct(value), (value, i), xytext=(4 if value >= 0 else -4, 0), textcoords="offset points",
                            ha="left" if value >= 0 else "right", va="center", fontsize=10.5)
        ax.set_yticks(range(len(changes)), [SHORT_LABELS.get(row["group_id"], row["label"]) for row, _ in changes])
        ax.invert_yaxis()
        ax.set_xlim(-limit, limit)
        ax.axvline(0, color=MUTED, linewidth=.8)
        ax.grid(axis="x", color=GRID)
        ax.set_xlabel("7 takvim günlük değişim (%)")
        ax.set_title(f"Kategoriler · {end}", loc="left", pad=13)
        _style(ax)
    else:
        _empty(ax)
    _save(fig, "categories.svg")


def _heatmap_values(rows, days):
    groups = list(dict.fromkeys(row["group_id"] for row in rows))
    lookup = {(r["group_id"], r["date"]): _number(r.get("index")) for r in rows}
    matrix = []
    for group in groups:
        series = []
        for day in days:
            previous = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
            old, new = lookup.get((group, previous)), lookup.get((group, day))
            series.append((new / old - 1) * 100 if new is not None and old is not None and old > 0 else float("nan"))
        matrix.append(series)
    return groups, matrix


def _render_heatmap(rows, quality):
    fig, ax = plt.subplots(figsize=(7.2, 5.1))
    end = max((r["date"] for r in rows), default="")
    if end:
        days = _calendar(end, 30)
        groups, matrix = _heatmap_values(rows, days)
        cmap = LinearSegmentedColormap.from_list("daily", [TEAL, "#fafafa", ORANGE])
        cmap.set_bad("#d9e1eb")
        limit = max([abs(v) for series in matrix for v in series if math.isfinite(v)] + [.25])
        chart = ax.imshow(matrix, aspect="auto", cmap=cmap, vmin=-limit, vmax=limit, interpolation="nearest")
        diag = _quality_days(quality)
        for x, day in enumerate(days):
            category_diag = {r["group_id"]: r for r in diag.get(day, {}).get("categories", [])}
            previous_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
            previous_diag = {r["group_id"]: r for r in diag.get(previous_day, {}).get("categories", [])}
            for y, group in enumerate(groups):
                if math.isfinite(matrix[y][x]) and not (_fresh(category_diag.get(group, {})) and _fresh(previous_diag.get(group, {}))):
                    ax.plot(x, y, ".", color=INK, markersize=2.5)
        ax.set_yticks(range(len(groups)), [SHORT_LABELS.get(g, g) for g in groups])
        _date_axis(ax, days)
        ax.set_title(f"Günlük hareket · {end} itibarıyla 30 gün", loc="left", pad=13)
        bar = fig.colorbar(chart, ax=ax, orientation="horizontal", pad=.12, fraction=.04)
        bar.set_label("Ardışık günler arası değişim (%)")
        ax.tick_params(length=0)
        ax.spines[:].set_visible(False)
    else:
        _empty(ax)
    _save(fig, "category-heatmap.svg")


def _daily_moves(type_rows, quality=None):
    """Include the entire configured basket; stale zero changes are not confirmed flat."""
    end = max((r["date"] for r in type_rows), default="")
    counts = {"up": 0, "down": 0, "flat": 0, "limited": 0, "unavailable": 0}
    if not end:
        return end, [], counts
    previous_day = (date.fromisoformat(end) - timedelta(days=1)).isoformat()
    current = {r["type_id"]: r for r in type_rows if r["date"] == end}
    previous = {r["type_id"]: r for r in type_rows if r["date"] == previous_day}
    diag_days = _quality_days(quality)
    diag = {r["type_id"]: r for r in diag_days.get(end, {}).get("types", [])}
    old_diag = {r["type_id"]: r for r in diag_days.get(previous_day, {}).get("types", [])}
    configured = {spec["id"] for spec in load_product_types()}
    changes = []
    for key in sorted(configured | set(current)):
        row = current.get(key, {})
        old, new = _number(previous.get(key, {}).get("index")), _number(row.get("index"))
        if old is None or new is None or old <= 0:
            counts["unavailable"] += 1
            continue
        value = (new / old - 1) * 100
        fresh = _fresh(diag.get(key, {})) and _fresh(old_diag.get(key, {}))
        bucket = "limited" if not fresh else "up" if value > .005 else "down" if value < -.005 else "flat"
        counts[bucket] += 1
        changes.append({"type_id": key, "label": row.get("label", key), "change": value, "fresh": fresh})
    return end, changes, counts


def _render_movers(rows, quality):
    end, changes, counts = _daily_moves(rows, quality)
    fig, (ax, breadth) = plt.subplots(2, 1, figsize=(7.2, 6.3), gridspec_kw={"height_ratios": [5, 1.2]})
    selected = sorted((r for r in changes if r["change"] > .005), key=lambda r: -r["change"])[:5]
    selected += sorted((r for r in changes if r["change"] < -.005), key=lambda r: r["change"])[:5]
    if selected:
        limit = max(abs(row["change"]) for row in selected) * 1.4
        for i, row in enumerate(selected):
            value = row["change"]
            ax.barh(i, value, color=ORANGE if value > 0 else TEAL, alpha=1 if row["fresh"] else .4, hatch=None if row["fresh"] else "//")
            ax.annotate(_pct(value), (value, i), xytext=(4 if value >= 0 else -4, 0), textcoords="offset points",
                        ha="left" if value >= 0 else "right", va="center", fontsize=10.5)
        ax.set_yticks(range(len(selected)), [textwrap.fill(r["label"], 20) for r in selected])
        ax.invert_yaxis()
        ax.set_xlim(-limit, limit)
        ax.axvline(0, color=MUTED, linewidth=.8)
        ax.grid(axis="x", color=GRID)
        ax.set_xlabel("Günlük değişim (%)")
        _style(ax)
    else:
        _empty(ax, "Karşılaştırılabilir belirgin hareket yok")
    ax.set_title(f"Günün hareketleri · {end or 'ölçüm bekleniyor'}", loc="left", pad=13)
    labels = [("up", "Yükselen", ORANGE), ("down", "Düşen", TEAL), ("flat", "Yatay*", BLUE),
              ("limited", "Güncellik\nsınırlı", MUTED), ("unavailable", "Kıyas\nyok", MUTED)]
    for i, (key, label, color) in enumerate(labels):
        breadth.text(i, .67, str(counts[key]), ha="center", color=color, fontsize=20, fontweight="bold")
        breadth.text(i, .05, label, ha="center", fontsize=10.5)
    breadth.set_xlim(-.6, 4.6)
    breadth.set_ylim(-.2, 1.05)
    breadth.set_axis_off()
    _save(fig, "movers.svg")


def _render_quality(index_rows, quality):
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 6), sharex=True)
    diag = _quality_days(quality)
    end = max([row["date"] for row in index_rows] + list(diag), default="")
    if end:
        days = _calendar(end, 60)
        index = {row["date"]: row for row in index_rows}
        def values(key):
            return [float("nan") if _number(diag.get(day, {}).get(key)) is None else float(diag[day][key]) * 100 for day in days]
        coverage = [_number(diag.get(day, {}).get("coverage", index.get(day, {}).get("coverage"))) for day in days]
        axes[0].plot([float("nan") if v is None else v * 100 for v in coverage], color=BLUE, linewidth=2, label="Mevcut kategori ağırlığı")
        axes[0].plot(values("common_coverage"), color=TEAL, linewidth=1.6, linestyle="--", label="Karşılaştırma örtüşmesi")
        axes[1].plot(values("fresh_within_1_day_share"), color=TEAL, linewidth=2, label="Kaynak tarihi ≤ 1 gün")
        counts_ax = axes[1].twinx()
        counts = [_number(diag.get(day, {}).get("headline_skus")) for day in days]
        counts_ax.plot([float("nan") if value is None else value for value in counts], color=MUTED,
                       linewidth=1.2, linestyle="--", label="Katkı veren SKU (sağ)")
        counts_ax.set_ylim(0, max([value for value in counts if value is not None] + [1]) * 1.15)
        counts_ax.set_ylabel("Katkı veren SKU", color=MUTED, fontsize=10)
        counts_ax.spines["top"].set_visible(False)
        counts_ax.tick_params(length=0, labelsize=9, colors=MUTED)
        for ax in axes:
            ax.axhline(90, color=ORANGE, linewidth=1, linestyle=":", label="%90 uyarı eşiği")
            ax.set_ylim(0, 108)
            ax.set_ylabel("Pay (%)")
            ax.grid(axis="y", color=GRID)
            _style(ax)
        axes[0].set_title(f"Kapsama ve güncellik · {end}", loc="left", pad=13)
        axes[0].legend(loc="lower left", frameon=False, fontsize=9.5)
        lines, labels = axes[1].get_legend_handles_labels()
        count_lines, count_labels = counts_ax.get_legend_handles_labels()
        axes[1].legend(lines + count_lines, labels + count_labels, loc="lower left", frameon=False, fontsize=9)
        last = diag.get(end, {})
        axes[1].set_title(f"Başlığa katkı: {last.get('headline_types', '—')} tip / {last.get('headline_skus', '—')} SKU",
                          loc="left", fontsize=11, fontweight="normal", pad=10)
        _date_axis(axes[1], days)
    else:
        for ax in axes:
            _empty(ax)
    _save(fig, "quality.svg")


def _retailer_rows(quality):
    days = _quality_days(quality)
    if not days:
        return "", [], {}
    end = max(days)
    sources = days[end].get("sources", {})
    previous = (date.fromisoformat(end) - timedelta(days=7)).isoformat()
    old_sources = days.get(previous, {}).get("sources", {})
    before = {row["market"]: row for row in old_sources.get("retailers", [])}
    current = {row["market"]: row for row in sources.get("retailers", [])}
    rows = []
    for market in sorted(set(current) | set(before)):
        row = current.get(market, {"market": market, "skus": 0, "depots": 0 if sources.get("depot_count") is not None else None})
        past = before.get(market, {"skus": 0, "depots": 0 if old_sources.get("depot_count") is not None else None}) if before else None
        delta = row["skus"] - past["skus"] if past and past.get("skus") is not None else None
        depot_delta = row.get("depots") - past["depots"] if past and row.get("depots") is not None and past.get("depots") is not None else None
        rows.append({**row, "delta": delta, "depot_delta": depot_delta})
    return end, sorted(rows, key=lambda r: (-r["skus"], r["market"])), sources


def _render_retailers(quality):
    end, rows, sources = _retailer_rows(quality)
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    if rows:
        limit = max(row["skus"] for row in rows) or 1
        for i, row in enumerate(rows):
            ax.barh(i, row["skus"], color=BLUE, height=.58)
            change = "—" if row["delta"] is None else f"{row['delta']:+d}"
            depot_delta = "—" if row["depot_delta"] is None else f"{row['depot_delta']:+d}"
            label = f"{row['skus']} ({change})  ·  {row.get('depots') if row.get('depots') is not None else '—'} ({depot_delta})"
            ax.text(limit * 1.03, i, label, va="center", fontsize=10)
        market_names = {"a101": "A101", "bim": "BİM", "carrefour": "CarrefourSA", "hakmar": "Hakmar",
                        "migros": "Migros", "sok": "ŞOK", "tarim_kredi": "Tarım Kredi"}
        ax.set_yticks(range(len(rows)), [market_names.get(row["market"], row["market"]) for row in rows])
        ax.invert_yaxis()
        ax.set_xlim(0, limit * 2.5)
        ax.set_xticks([0, round(limit / 2), limit])
        ax.set_xlabel("Başlığa katkı veren SKU · etiketler örtüşebilir", fontsize=10)
        ax.text(limit * 1.03, -.8, "SKU (7g Δ) · depot (7g Δ)", color=MUTED, fontsize=9.5)
        share = _number(sources.get("single_depot_share"))
        subtitle = "Tek depot SKU payı: " + ("—" if share is None else f"%{share * 100:.1f}")
        subtitle += f" · {sources.get('retailer_count', '—')} market / {sources.get('depot_count') if sources.get('depot_count') is not None else '—'} depot"
        ax.set_title(f"Market / depot katılımı · {end}\n{subtitle}", loc="left", pad=20, fontsize=12)
        _style(ax)
    else:
        _empty(ax, "Market / depot kanıtı henüz yok")
    _save(fig, "retailers.svg")


def _stats(index_rows, quality=None):
    valid = [row for row in index_rows if _number(row.get("index")) is not None]
    if not valid:
        return "İlk gözlem bekleniyor."
    latest = max(index_rows, key=lambda r: r["date"])
    if _number(latest.get("index")) is None:
        return f"{latest['date']}: kapsama yetersiz; güncel endeks yayımlanmadı. Son geçerli ölçüm: {valid[-1]['date']}."
    diag = _quality_days(quality).get(latest["date"], {})
    baseline = next((_number(r.get("index")) for r in index_rows if r["date"] == latest.get("baseline_date")), None)
    since = (float(latest["index"]) / baseline - 1) * 100 if baseline else None
    coverage = _number(diag.get("coverage", latest.get("coverage")))
    coverage_label = "—" if coverage is None else f"%{coverage * 100:.0f}"
    return "\n".join([
        "| Endeks | Günlük | 7 gün | 30 gün | Bazdan beri |",
        "|---:|---:|---:|---:|---:|",
        f"| **{float(latest['index']):.2f}** | {_pct(_change(index_rows, 1))} | {_pct(_change(index_rows, 7))} | {_pct(_change(index_rows, 30))} | {_pct(since)} |",
        "", f"**{coverage_label}** kategori ağırlığı · **{diag.get('headline_types', '—')} tip / {diag.get('headline_skus', '—')} SKU** başlığa katkı · **{diag.get('collected_skus', '—')} SKU** toplandı."
    ])


def _movers(type_rows, quality=None):
    end, _, counts = _daily_moves(type_rows, quality)
    return f"{end}: {counts['up']} yükselen, {counts['down']} düşen, {counts['flat']} yatay; {counts['limited']} güncellik sınırlı, {counts['unavailable']} karşılaştırılamıyor."


def _status(index_rows, category_rows, snapshot_rows, quality=None, compact=False) -> str:
    from .health import summarize
    if not index_rows:
        return "İlk gözlem bekleniyor."
    latest = index_rows[-1]
    health = summarize(snapshot_rows)
    attempt_path = DATA_DIR / "collection-status.json"
    if not attempt_path.exists():
        attempt_path = DATA_DIR / "latest-errors.json"
    attempt = json.loads(attempt_path.read_text()) if attempt_path.exists() else {}
    rejected = attempt.get("status") in {"rejected", "failed"}
    failed_types = [e["type_id"] for e in attempt.get("errors", []) if not e.get("not_scanned")]
    deferred_types = [e["type_id"] for e in attempt.get("errors", []) if e.get("not_scanned")]
    retained = attempt.get("retained_same_day_types", [])
    missing = [r["label"] for r in category_rows if r["date"] == latest["date"] and not r.get("index")]
    partial = bool(missing or failed_types or deferred_types)
    label = ("Tarama başarısız; önceki yayın korundu" if rejected else
             "Kısmi güncelleme; bazı tiplerde gün içindeki önceki ölçüm korundu" if retained else
             "Eksik kapsam" if partial else "Yayınlandı")
    diag = _quality_days(quality).get(latest["date"], {})
    if diag.get("unavailable") and not rejected:
        label = "Yayımlanamadı"
    lines = [f"> **Veri durumu: {label}.** Son seri noktası: **{latest['date']}**. "
             f"Kategori ağırlığı kapsaması: **%{float(latest['coverage']) * 100:.0f}**."]
    fresh = _number(diag.get("fresh_within_1_day_share"))
    if quality is not None:
        lines[0] += " Güncel kaynak (≤1 gün): **" + ("—" if fresh is None else f"%{fresh * 100:.1f}") + "**."
    if diag.get("coverage_alert") or diag.get("freshness_alert"):
        alerts = [label for flag, label in [(diag.get("coverage_alert"), "kapsama"), (diag.get("freshness_alert"), "güncellik")] if flag]
        lines.append("> **Kalite uyarısı: " + " ve ".join(alerts) + ".** [Ayrıntı](data/v0.4/quality.json).")
    if attempt.get("checked_at") and (rejected or not compact):
        lines.append(f"> Son tarama girişimi: {attempt['checked_at']}.")
    if failed_types:
        lines.append(f"> **{len(failed_types)} ürün tipinde API hatası** var; bu, ürünlerin katalogda bulunmadığı anlamına gelmez.")
    if deferred_types:
        lines.append(f"> **{len(deferred_types)} ürün tipi taranamadı**: kaynak hatası veya süre sınırı nedeniyle kalan sorgular durduruldu.")
    if retained:
        labels = "; ".join(f"{row['label']} ({', '.join(row['collected_at'])})" for row in retained)
        lines.append(f"> {len(retained)} tipte önceki ölçüm korundu; [tarama zamanı ve durum](data/v0.4/collection-status.json)." if compact else "> Aynı günün önceki ölçümü kullanılan tipler: " + labels + ". Diğer tipler son taramayla güncellendi.")
    if rejected and attempt.get("reason"):
        lines.append("> Başarısız tarama gözlemleri endekse eklenmedi; ayrıntı: [tarama durumu](data/v0.4/collection-status.json).")
    if missing:
        lines.append("> Yayımlanamayan kategoriler: " + "; ".join(missing) + ".")
    if not compact and health["source_updated_today"] < len(snapshot_rows) * 0.5:
        lines.append(f"> Kaynak tarihi seri günüyle aynı olan SKU: **{health['source_updated_today']}/{len(snapshot_rows)}**. "
                     "Yatay çizgi, raf fiyatlarının bugün yeniden teyit edildiğini göstermez.")
    lines.append("> Baz: **2026-09-05 = 100**.")
    return "\n".join(lines)


def main(status_only=False):
    from .diagnostics import build
    index_rows, type_rows, category_rows = _read(INDEX_PATH), _read(TYPE_PATH), _read(CATEGORY_PATH)
    snapshot_rows = _latest_snapshot()
    quality = build(ROOT)
    text = README_PATH.read_text(encoding="utf-8")
    text = _replace(text, "<!-- STATUS_START -->", "<!-- STATUS_END -->", _status(index_rows, category_rows, snapshot_rows, quality, compact=True))
    if not status_only:
        render_charts(index_rows, category_rows, snapshot_rows, type_rows, quality)
        text = _replace(text, "<!-- STATS_START -->", "<!-- STATS_END -->", _stats(index_rows, quality))
    README_PATH.write_text(text, encoding="utf-8", newline="\n")
    print("status-only" if status_only else "charts=" + ",".join("charts/" + name for name in CHART_FILENAMES))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--status-only", action="store_true")
    main(status_only=parser.parse_args().status_only)
