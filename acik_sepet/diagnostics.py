"""Versioned, observational quality diagnostics for the published series.

The CSVs remain authoritative.  In particular, this module does not recalculate
or repair historical indices.  Contributor sets follow the same three nested
chain links as the index, including their last *successful* publication dates.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
ESSENTIAL_CATEGORIES = frozenset({"meat", "fruit", "vegetables"})


def _read_csv(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def _json(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _source_day(value: Any) -> date | None:
    if not value:
        return None
    for pattern in ("%d.%m.%Y %H:%M", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(str(value), pattern).date()
        except ValueError:
            continue
    return None


def _source_age(row: dict, day: str) -> int | None:
    # This is the newest source date used for a SKU, not a statement that every
    # contributing depot is fresh. Keep that established method explicit.
    stamp = _source_day(row.get("source_updated_at"))
    if stamp is None:
        dates = [_source_day(offer.get("index_time"))
                 for offer in json.loads(row.get("source_observations") or "[]")]
        known = [value for value in dates if value is not None]
        stamp = max(known) if known else None
    return (date.fromisoformat(day) - stamp).days if stamp else None


def _freshness(rows: list[dict], day: str) -> dict:
    ages = [_source_age(row, day) for row in rows]
    known = sum(age is not None for age in ages)
    fresh = sum(age is not None and 0 <= age <= 1 for age in ages)
    recent = sum(age is not None and 0 <= age <= 3 for age in ages)
    return {
        "fresh_within_1_day_share": round(fresh / len(rows), 6) if rows and known else None,
        "fresh_within_1_day_skus": fresh if known else None,
        "freshness_unknown_skus": len(rows) - known,
        "source_within_3_days_share": round(recent / len(rows), 6) if rows and known else None,
        "future_source_skus": sum(age is not None and age < 0 for age in ages),
    }


def _sources(rows: list[dict]) -> dict:
    """Count actual recorded participation; absent historical evidence is null."""
    retailer_slots: dict[str, set] = defaultdict(set)
    retailer_depots: dict[str, set] = defaultdict(set)
    depot_slots: dict[str, set] = defaultdict(set)
    depot_labels: dict[str, tuple[str, str]] = {}
    source_counts = []
    audited = 0
    mapped = True
    for row in rows:
        key = (row["type_id"], row.get("slot_id") or row["product_key"])
        source_ids = set(json.loads(row.get("source_ids") or "[]"))
        markets = set(json.loads(row.get("markets") or "[]"))
        evidence = json.loads(row.get("source_observations") or "[]")
        if evidence:
            audited += 1
            for offer in evidence:
                source_id, market = offer.get("source_id"), offer.get("market")
                if source_id:
                    source_ids.add(source_id)
                    depot_labels[source_id] = (market or "", offer.get("depot_name", ""))
                if market:
                    markets.add(market)
                    if source_id:
                        retailer_depots[market].add(source_id)
        else:
            mapped = False
        for source_id in source_ids:
            depot_slots[source_id].add(key)
        for market in markets:
            retailer_slots[market].add(key)
        count = len(source_ids) or _number(row.get("source_count"))
        source_counts.append(int(count) if count is not None else None)
    known_counts = sum(count is not None for count in source_counts)
    return {
        "skus": len(rows),
        "retailer_count": len(retailer_slots) if retailer_slots else None,
        "depot_count": len(depot_slots) if depot_slots else None,
        "single_depot_skus": sum(count == 1 for count in source_counts) if known_counts else None,
        "single_depot_share": (round(sum(count == 1 for count in source_counts) / len(rows), 6)
                               if rows and known_counts == len(rows) else None),
        "auditable_skus": audited,
        "source_evidence_share": round(audited / len(rows), 6) if rows else None,
        "retailers": [
            {"market": market, "skus": len(slots),
             "depots": len(retailer_depots[market]) if mapped else None}
            for market, slots in sorted(retailer_slots.items())
        ],
        "depots": ([{"source_id": source_id, "market": depot_labels.get(source_id, ("", ""))[0],
                     "depot_name": depot_labels.get(source_id, ("", ""))[1], "skus": len(slots)}
                    for source_id, slots in sorted(depot_slots.items())] if mapped and rows else None),
    }


def calendar_change(rows: list[dict], day: str, days: int) -> float | None:
    """A calendar-period change exists only when both exact endpoints exist."""
    before = (date.fromisoformat(day) - timedelta(days=days)).isoformat()
    levels = {row["date"]: _number(row.get("index")) for row in rows}
    start, finish = levels.get(before), levels.get(day)
    if start is None or finish is None or start <= 0:
        return None
    return round((finish / start - 1) * 100, 6)


def _collection_reasons(metadata: dict | None) -> list[str]:
    if metadata is None:
        return []
    reasons = []
    primary = metadata.get("primary", {})
    if primary.get("status") in {"failed", "incomplete", "truncated"}:
        reasons.append("search_" + primary["status"])
    for alias in metadata.get("aliases", []):
        if alias.get("status") in {"failed", "incomplete", "truncated"}:
            reason = "alias_search_" + alias["status"]
            if reason not in reasons:
                reasons.append(reason)
    if metadata.get("lost_depot_connections", 0):
        reasons.append("lost_depot_connections")
    if metadata.get("unavailable_replacements", 0):
        reasons.append("unavailable_replacements")
    for key, count in metadata.get("rejections", {}).items():
        if count:
            reasons.append("rejected_" + key)
    return reasons


def build(root: Path) -> dict:
    root = Path(root)
    data = root / "data" / "v0.4"
    specs = [{key: value.strip() if isinstance(value, str) else value for key, value in spec.items()}
             for spec in _read_csv(root / "config" / "product_types.tsv", "\t")]
    categories = _json(root / "config" / "categories.json", {}).get("categories", [])
    series = _json(root / "config" / "series.json", {})
    indices = _read_csv(data / "index.csv")
    type_indices = {(row["date"], row["type_id"]): row for row in _read_csv(data / "type_indices.csv")}
    category_indices = {(row["date"], row["group_id"]): row for row in _read_csv(data / "category_indices.csv")}
    total_weight = sum(float(category["weight"]) for category in categories)
    previous_types: dict[str, tuple[str, set[str]]] = {}
    previous_categories: dict[str, tuple[str, set[str]]] = {}
    previous_headline: tuple[str, set[str]] | None = None
    days = []
    for index_row in sorted(indices, key=lambda row: row["date"]):
        day = index_row["date"]
        snapshot_path = data / "snapshots" / f"{day}.csv"
        snapshot = _read_csv(snapshot_path)
        collection = _json(data / "collection-diagnostics" / f"{day}.json")
        by_type: dict[str, dict[str, dict]] = defaultdict(dict)
        for row in snapshot:
            by_type[row["type_id"]][row.get("slot_id") or row["product_key"]] = row
        type_details, type_matches = [], {}
        for spec in specs:
            key = spec["id"]
            observed = by_type.get(key, {})
            published = type_indices.get((day, key), {})
            value = _number(published.get("index"))
            previous = previous_types.get(key)
            common = set(observed) & previous[1] if previous else set(observed)
            common_coverage = len(common) / len(previous[1]) if previous and previous[1] else (1.0 if value is not None else 0.0)
            matched_rows = [observed[slot] for slot in sorted(common)] if value is not None else []
            type_matches[key] = matched_rows
            metadata = (collection.get("types", {}).get(key) if collection else None)
            reasons = _collection_reasons(metadata)
            minimum, target = int(spec["min_skus"]), int(spec["target_skus"])
            if len(observed) < minimum:
                reasons.append("insufficient_observed_skus")
            elif value is None and len(common) < minimum:
                reasons.append("insufficient_matched_skus")
            elif value is None and common_coverage < 0.5:
                reasons.append("insufficient_matched_coverage")
            if len(observed) < target:
                reasons.append("below_target")
            detail = {
                "type_id": key, "label": spec["label"], "group": spec["group"], "index": value,
                "observed_skus": len(observed), "matched_skus": len(common) if previous or value is not None else 0,
                "min_skus": minimum, "target_skus": target,
                "coverage": _number(published.get("coverage")), "common_coverage": round(common_coverage, 6),
                "previous_date": previous[0] if previous else None,
                "contributing_skus": 0, "headline_contributor": False,
                "reasons": reasons, "collection": metadata,
                "candidate_readiness": metadata.get("ready_candidates") if metadata else None,
                **_freshness(matched_rows, day),
            }
            type_details.append(detail)
            if value is not None:
                previous_types[key] = (day, set(observed))

        category_details, category_matches = [], {}
        for category in categories:
            key = category["id"]
            members = [spec for spec in specs if spec["group"] == key]
            weights = {spec["id"]: float(spec.get("type_weight") or 1) for spec in members}
            available = {row["type_id"] for row in type_details if row["group"] == key and row["index"] is not None}
            published = category_indices.get((day, key), {})
            value = _number(published.get("index"))
            previous = previous_categories.get(key)
            common = available & previous[1] if previous else available
            available_weight = sum(weights[k] for k in available)
            common_weight = sum(weights[k] for k in common)
            member_weight = sum(weights.values())
            contributing = common if value is not None else set()
            category_matches[key] = contributing
            matching_rows = [row for type_id in sorted(contributing) for row in type_matches[type_id]]
            category_details.append({
                "group_id": key, "label": category["label"], "index": value, "weight": float(category["weight"]),
                "coverage": round(available_weight / member_weight, 6) if member_weight else 0.0,
                "common_coverage": round(common_weight / member_weight, 6) if member_weight else 0.0,
                "available_types": len(available), "contributing_types": len(contributing),
                "configured_types": len(members), "contributing_skus": len(matching_rows),
                "previous_date": previous[0] if previous else None,
                "headline_contributor": False, **_freshness(matching_rows, day),
            })
            if value is not None:
                previous_categories[key] = (day, available)

        available_categories = {row["group_id"] for row in category_details if row["index"] is not None}
        missing = [category["id"] for category in categories if category["id"] not in available_categories]
        common_categories = (available_categories & previous_headline[1] if previous_headline else available_categories)
        value = _number(index_row.get("index"))
        contributors = {key for group in common_categories for key in category_matches[group]} if value is not None else set()
        contributing_rows = [row for key in sorted(contributors) for row in type_matches[key]]
        for detail in type_details:
            key = detail["type_id"]
            detail["headline_contributor"] = key in contributors
            detail["contributing_skus"] = len(type_matches[key]) if key in contributors else 0
            if detail["index"] is not None and key not in contributors:
                detail["reasons"].append("outside_headline_link")
        for detail in category_details:
            detail["headline_contributor"] = value is not None and detail["group_id"] in common_categories
        coverage = (sum(category["weight"] for category in categories if category["id"] in available_categories)
                    / total_weight if total_weight else 0.0)
        common_coverage = (sum(category["weight"] for category in categories if category["id"] in common_categories)
                           / total_weight if total_weight else 0.0)
        freshness = _freshness(contributing_rows, day)
        snapshot_freshness = _freshness(snapshot, day)
        fresh_share = freshness["fresh_within_1_day_share"]
        recent_share = snapshot_freshness["source_within_3_days_share"]
        freshness_failed = bool(snapshot_freshness["future_source_skus"]) or (recent_share is not None and recent_share < 0.60)
        daily = {
            "date": day, "index": value,
            "coverage": round(coverage, 6), "common_coverage": round(common_coverage, 6),
            "previous_date": previous_headline[0] if previous_headline else None,
            "headline_types": len(contributors), "headline_skus": len(contributing_rows),
            "collected_skus": len(snapshot), "available_types": sum(row["index"] is not None for row in type_details),
            "configured_types": len(specs), "missing_categories": missing,
            "partial_coverage": bool(missing),
            "coverage_alert": round(coverage, 6) < 0.90 or bool(ESSENTIAL_CATEGORIES.intersection(missing)),
            "freshness_alert": fresh_share < 0.90 if fresh_share is not None else None,
            "unavailable": value is None or freshness_failed or not snapshot_path.exists(),
            "publication_checks": {"mathematical": value is not None,
                                   "freshness": not freshness_failed if recent_share is not None else None,
                                   "snapshot_present": snapshot_path.exists()},
            "categories": category_details, "types": type_details,
            "sources": _sources(contributing_rows), "collected_sources": _sources(snapshot),
            "collection_report": f"collection-diagnostics/{day}.json" if collection else None,
            "shadow": collection.get("shadow") if collection else None,
            "daily_change_pct": calendar_change(indices, day, 1),
            "change_7d_pct": calendar_change(indices, day, 7),
            "change_30d_pct": calendar_change(indices, day, 30),
            **freshness,
        }
        days.append(daily)
        if value is not None:
            previous_headline = (day, available_categories)
    latest = days[-1] if days else None
    return {
        "schema_version": SCHEMA_VERSION,
        "baseline_date": series.get("baseline_date"),
        "thresholds": {"coverage_alert": 0.90, "freshness_alert": 0.90,
                       "fresh_within_days": 1, "essential_categories": sorted(ESSENTIAL_CATEGORIES)},
        "freshness_basis": "Newest recorded source date among depots used for each contributing SKU; future dates excluded.",
        "contribution_basis": "Intersection at all three successful chain links; new members enter subsequent comparisons.",
        "days": days, "latest": latest,
        "categories": latest["categories"] if latest else [],
        "sources": latest["sources"] if latest else None,
        # An attempt is not a published observation. Never let a failed retry
        # change the quality classification of an existing published snapshot.
        "latest_attempt": _json(data / "collection-status.json"),
    }


def rebuild(root: Path | None = None) -> dict:
    root = Path(root) if root is not None else ROOT
    result = build(root)
    path = root / "data" / "v0.4" / "quality.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return result


if __name__ == "__main__":
    result = rebuild()
    print(f"quality_days={len(result['days'])} schema_version={SCHEMA_VERSION}")
