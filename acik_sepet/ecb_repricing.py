"""ECB-inspired supermarket repricing indicators (experimental; never alters v0.4 indices).

Uses same-SKU, same-store normalized price quotes from existing daily snapshots.
Monthly baseline = latest fresh, non-promotional quote in previous month
(up to seven calendar days before month-end); current quote = latest within
one day of the analysis date. This is an ECB-inspired proxy, not the ECB DPD.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = (
    "as_of", "month", "comparable_quotes", "category_coverage_pct",
    "up_frequency_pct", "down_frequency_pct", "unchanged_frequency_pct",
    "avg_increase_pct", "avg_decrease_pct", "net_change_pct",
    "breadth_10pct_food_pct", "up_vs_previous_month_pp",
)


def _as_date(raw: str) -> date | None:
    if not raw:
        return None
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:16] if fmt.endswith("%H:%M") else raw[:10], fmt).date()
        except ValueError:
            pass
    return None


def _positive_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def load_observations(snapshot_dir: Path, max_source_age_days: int = 1):
    """Map day -> (type, actual SKU, store, unit, size) -> (group, unit price)."""
    days = {}
    for path in sorted(snapshot_dir.glob("????-??-??.csv")):
        day = date.fromisoformat(path.stem)
        quotes = {}
        with path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                type_id = row.get("type_id")
                sku = row.get("product_key")
                group = row.get("group")
                size = _positive_float(row.get("quantity"))
                unit = row.get("unit")
                if not all((type_id, sku, group, size, unit)):
                    continue
                try:
                    sources = json.loads(row.get("source_observations") or "[]")
                except (ValueError, TypeError):
                    sources = []
                if not isinstance(sources, list):
                    sources = []
                if not sources:
                    # Legacy snapshots have no store-level observations. Only
                    # single-store aggregates are genuinely comparable.
                    if str(row.get("source_count", "")) != "1":
                        continue
                    try:
                        ids = json.loads(row.get("source_ids") or "[]")
                    except (ValueError, TypeError):
                        ids = []
                    if len(ids) != 1:
                        continue
                    sources = [{
                        "source_id": ids[0], "api_unit_price": row.get("unit_price"),
                        "index_time": row.get("source_updated_at", ""),
                    }]
                for source in sources:
                    if not isinstance(source, dict):
                        continue
                    store = source.get("source_id")
                    source_date = _as_date(source.get("index_time") or row.get("source_updated_at") or "")
                    if not store or source_date is None or not 0 <= (day - source_date).days <= max_source_age_days:
                        continue
                    unit_price = _positive_float(source.get("api_unit_price"))
                    if unit_price is None:
                        price = _positive_float(source.get("price"))
                        unit_price = price / size if price is not None else None
                    if unit_price is None:
                        continue
                    key = (type_id, sku, str(store), unit, size)
                    # Duplicate source/SKU quotes in one snapshot are not
                    # independent evidence; retain a single quote.
                    quotes.setdefault(key, (group, unit_price))
        days[day] = quotes
    return days


def exclude_confirmed_sales(observations, min_drop: float = 0.03,
                            recovery_tolerance: float = 0.01,
                            max_duration_days: int = 7):
    """Suppress V-shaped temporary reductions only after recovery is observed.

    Active discounts cannot reliably be labelled as sales until the rebound;
    current-month estimates should therefore be treated as provisional.
    """
    series = defaultdict(list)
    for day, quotes in sorted(observations.items()):
        for key, (group, price) in quotes.items():
            series[key].append((day, price))
    excluded = set()
    for key, points in series.items():
        for i in range(1, len(points) - 1):
            before_day, before_price = points[i - 1]
            start_day, low_price = points[i]
            if low_price > before_price * (1 - min_drop):
                continue
            for j in range(i + 1, len(points)):
                end_day, end_price = points[j]
                if (end_day - start_day).days > max_duration_days:
                    break
                if abs(end_price / before_price - 1) <= recovery_tolerance:
                    # The discount and its observed continuation are omitted;
                    # the rebound is normal pricing, not an increase.
                    for k in range(i, j):
                        if points[k][1] < before_price * (1 - min_drop):
                            excluded.add((points[k][0], key))
                    break
    return {
        day: {key: value for key, value in quotes.items()
              if (day, key) not in excluded}
        for day, quotes in observations.items()
    }, len(excluded)


def _month_before(day: date) -> tuple[int, int]:
    first = day.replace(day=1)
    prev = first - timedelta(days=1)
    return prev.year, prev.month


def _latest_quotes(observations, cutoff: date, start: date):
    latest = {}
    for day in sorted(d for d in observations if start <= d <= cutoff):
        latest.update(observations[day])
    return latest


def _metrics(returns):
    n = len(returns)
    if not n:
        return None
    increased = [value for value in returns if value > 0.001]
    decreased = [value for value in returns if value < -0.001]
    return {
        "comparable_quotes": n,
        "up_frequency_pct": 100 * len(increased) / n,
        "down_frequency_pct": 100 * len(decreased) / n,
        "unchanged_frequency_pct": 100 * (n - len(increased) - len(decreased)) / n,
        "avg_increase_pct": (100 * sum(increased) / len(increased)) if increased else None,
        "avg_decrease_pct": (100 * sum(decreased) / len(decreased)) if decreased else None,
        "net_change_pct": 100 * sum(returns) / n,
    }


def compute_day(observations, categories, as_of: date, min_category_quotes: int = 5):
    """Produce category rows and weighted food-scope headline, no missing-as-zero."""
    prev_year, prev_month = _month_before(as_of)
    prev_end = as_of.replace(day=1) - timedelta(days=1)
    prev_start = max(prev_end.replace(day=1), prev_end - timedelta(days=7))
    baseline = _latest_quotes(observations, prev_end, prev_start)
    current = _latest_quotes(observations, as_of, max(as_of.replace(day=1),
                                                       as_of - timedelta(days=1)))
    returns_by_group = defaultdict(list)
    for key in baseline.keys() & current.keys():
        group1, old = baseline[key]
        group2, new = current[key]
        if group1 != group2 or old <= 0:
            continue
        change = new / old - 1
        # Exclude extreme errors such as missed unit or pack-size conversions.
        if not math.isfinite(change) or not -0.5 <= change <= 1:
            continue
        returns_by_group[group1].append(change)

    all_food_weight = sum(float(c["weight"]) for c in categories if c.get("scope") == "food")
    all_weight = sum(float(c["weight"]) for c in categories)
    covered_weight = 0.0
    broad_weight = 0.0
    included = []
    category_rows = []
    for category in categories:
        group = category["id"]
        stats = _metrics(returns_by_group[group])
        if stats is None or stats["comparable_quotes"] < min_category_quotes:
            continue
        weight = float(category["weight"])
        covered_weight += weight
        if category.get("scope") == "food" and stats["up_frequency_pct"] >= 10:
            broad_weight += weight
        included.append((weight, stats))
        category_rows.append({
            "as_of": as_of.isoformat(), "month": as_of.strftime("%Y-%m"),
            "group_id": group, "label": category["label"], **stats,
        })
    if not included:
        return None, category_rows
    effective_weight = sum(weight for weight, _ in included)
    headline = {
        "as_of": as_of.isoformat(),
        "month": as_of.strftime("%Y-%m"),
        "comparable_quotes": sum(stats["comparable_quotes"] for _, stats in included),
        "category_coverage_pct": 100 * covered_weight / all_weight if all_weight else None,
        "breadth_10pct_food_pct": 100 * broad_weight / all_food_weight if all_food_weight else None,
        "up_vs_previous_month_pp": None,
    }
    for field in ("up_frequency_pct", "down_frequency_pct", "unchanged_frequency_pct",
                  "net_change_pct"):
        headline[field] = sum(weight * stats[field] for weight, stats in included) / effective_weight
    # Weight conditional average sizes only over groups in which a price
    # increase/decrease occurred, not groups with no such observations.
    for field in ("avg_increase_pct", "avg_decrease_pct"):
        relevant = [(weight, stats[field]) for weight, stats in included if stats[field] is not None]
        headline[field] = (sum(weight * value for weight, value in relevant) /
                           sum(weight for weight, _ in relevant)) if relevant else None
    return headline, category_rows


def _write_csv(path: Path, rows: list[dict], fields):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else
                             round(row[field], 4) if isinstance(row[field], float) else row.get(field, "")
                             for field in fields})


def _chart(rows, output: Path):
    if not rows:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    dates = [date.fromisoformat(row["as_of"]) for row in rows]
    fig, ax = plt.subplots(figsize=(10, 4.3))
    ax.plot(dates, [row["up_frequency_pct"] for row in rows],
            label="Price increases", linewidth=2)
    ax.plot(dates, [row["down_frequency_pct"] for row in rows],
            label="Price decreases", linewidth=2)
    ax.set_title("Açık Sepet · ECB-inspired repricing frequencies (month-to-date)")
    ax.set_ylabel("% of matched quotes (category-weighted)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.2)
    ax.legend(loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, format="svg")
    plt.close(fig)


def run(snapshot_dir: Path, categories_path: Path, output_dir: Path):
    categories = json.loads(categories_path.read_text(encoding="utf-8"))["categories"]
    observations = load_observations(snapshot_dir)
    headline_rows = []
    category_rows = []
    excluded_count = 0
    # Compute each historical estimate using only information available by
    # that date; never use a future rebound to classify an earlier sale.
    for day in sorted(observations):
        as_known = {observed_day: quotes for observed_day, quotes in observations.items()
                    if observed_day <= day}
        cleaned, excluded_count = exclude_confirmed_sales(as_known)
        headline, per_category = compute_day(cleaned, categories, day)
        if headline:
            headline_rows.append(headline)
            category_rows.extend(per_category)
    if not headline_rows:
        raise ValueError("No month-on-month matched quotes available; need snapshots in two months")
    # Compare month-to-date repricing frequency with the immediately prior
    # completed month's last estimate, where available.
    month_ends = {}
    for row in headline_rows:
        month_ends[row["month"]] = row
    for row in headline_rows:
        y, m = _month_before(date.fromisoformat(row["as_of"]))
        previous = month_ends.get(f"{y:04d}-{m:02d}")
        if previous:
            row["up_vs_previous_month_pp"] = row["up_frequency_pct"] - previous["up_frequency_pct"]
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "daily_repricing.csv", headline_rows, FIELDS)
    cat_fields = ["as_of", "month", "group_id", "label", "comparable_quotes",
                  "up_frequency_pct", "down_frequency_pct", "unchanged_frequency_pct",
                  "avg_increase_pct", "avg_decrease_pct", "net_change_pct"]
    _write_csv(output_dir / "category_repricing.csv", category_rows, cat_fields)
    latest = headline_rows[-1]
    payload = {
        "method": "ECB-inspired matched-store-SKU month-on-month repricing proxy",
        "source": "Açık Sepet v0.4 snapshots from main; no independent scraping",
        "excluded_confirmed_temporary_sale_quotes": excluded_count,
        "provisional": True,
        "latest": {key: round(value, 4) if isinstance(value, float) else value
                   for key, value in latest.items()},
    }
    (output_dir / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    categories_today = [row for row in category_rows if row["as_of"] == latest["as_of"]]
    lines = [
        "# Açık Sepet · ECB repricing experiment",
        "",
        f"**Latest: {latest['as_of']} (provisional month-to-date)** · "
        f"{latest['comparable_quotes']} comparable store-SKU quotes · "
        f"{latest['category_coverage_pct']:.1f}% basket-weight coverage.",
        "",
        f"**Increased:** {latest['up_frequency_pct']:.2f}% · "
        f"**Decreased:** {latest['down_frequency_pct']:.2f}% · "
        f"**Unchanged:** {latest['unchanged_frequency_pct']:.2f}%.",
        "",
        f"**Food breadth (categories with ≥10% increasing):** "
        f"{latest['breadth_10pct_food_pct']:.1f}% of configured food weight.",
        "",
        "![Monthly repricing frequency](repricing.svg)",
        "",
        "| Category | Quotes | Increases | Decreases | Avg rise | Avg fall |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in categories_today:
        def pct(value):
            return "—" if value is None else f"{value:+.2f}%"
        lines.append(
            f"| {row['label']} | {row['comparable_quotes']} | "
            f"{row['up_frequency_pct']:.1f}% | {row['down_frequency_pct']:.1f}% | "
            f"{pct(row['avg_increase_pct'])} | {pct(row['avg_decrease_pct'])} |"
        )
    lines += [
        "",
        "Method: matched product **and** store, normalized price, same pack size;",
        "fresh source (≤1 day), previous month-end price within seven days,",
        "short-lived reductions excluded **only when a rebound confirms a sale**.",
        "Current unconfirmed promotions may remain. Excludes extreme changes",
        "(below −50% or above +100%). Category weighting uses Açık Sepet",
        "**research weights**, not official TÜİK/HICP weights.",
        "Coverage is based on categories with at least five comparable quotes.",
        "This is not official inflation or the ECB Daily Price Dataset.",
        "",
    ]
    (output_dir / "latest.md").write_text("\n".join(lines), encoding="utf-8")
    _chart(headline_rows, output_dir / "repricing.svg")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshots-dir", type=Path,
                        default=ROOT / "data/v0.4/snapshots")
    parser.add_argument("--categories", type=Path,
                        default=ROOT / "config/categories.json")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "research/ecb/output")
    args = parser.parse_args()
    result = run(args.snapshots_dir, args.categories, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
