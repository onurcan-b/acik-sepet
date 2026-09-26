"""Prospective panel recovery, evidence and explicit shadow-rollout controls.

No imports of collection helpers at module load time: the collector uses this
module, while these pure policy functions reuse its unchanged matching gates.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

POLICY_VERSION = 1
RETENTION_DAYS = 14
QUALIFY_DATES = 3
SHADOW_DAYS = 7


def search_metadata(rows: list) -> dict:
    return dict(getattr(rows, "metadata", {"status": "complete", "pages": None,
                "raw_results": len(rows), "unique_results": len(rows), "exhausted": True,
                "reason": "legacy_test_or_adapter"}))


def discover_aliases(specs: list[dict], pools: dict, reports: dict, observed: dict,
                     session, search, aliases: dict, today: str, deadline: float) -> dict:
    """Primary work is finished; use only its remaining budget for discovery."""
    from .api import MarketFiyatiError, RequestBudget
    from .collect import _product_key
    group_counts = {}
    for spec in specs:
        value = group_counts.setdefault(spec["group"], [0, 0])
        value[0] += int(len(observed.get(spec["id"], [])) >= spec["min_skus"])
        value[1] += 1
    deficient = [spec for spec in specs if spec["id"] in pools and aliases.get(spec["id"])
                 and len(observed.get(spec["id"], [])) < spec["target_skus"]]
    # Three urgent slots and one rotating slot prevent healthy groups or later
    # type IDs from being starved indefinitely by fixed ordering and the cap.
    ordinal = date.fromisoformat(today).toordinal()
    ids = sorted(spec["id"] for spec in deficient)
    rotated = ids[ordinal % len(ids):] + ids[:ordinal % len(ids)] if ids else []
    positions = {key: i for i, key in enumerate(rotated)}
    priority = sorted(deficient, key=lambda spec: (
        group_counts[spec["group"]][0] / group_counts[spec["group"]][1],
        spec["group"] not in {"meat", "fruit", "vegetables"}, positions[spec["id"]]))
    fair = sorted(deficient, key=lambda spec: positions[spec["id"]])
    queue, seen = [], set()
    while priority or fair:
        for source in [priority, priority, priority, fair]:
            while source and source[0]["id"] in seen:
                source.pop(0)
            if source:
                spec = source.pop(0)
                queue.append(spec)
                seen.add(spec["id"])
    budget = RequestBudget(min(deadline, time.monotonic() + 300), max_requests=50)
    previous_budget = getattr(session, "_marketfiyati_budget", None)
    session._marketfiyati_budget = budget
    try:
        for spec in queue:
            for query in list(dict.fromkeys(aliases[spec["id"]]))[:2]:
                if query == spec["query"]:
                    continue
                if time.monotonic() >= budget.deadline or budget.used >= 50:
                    return {"requests": budget.used, "status": "budget_exhausted"}
                try:
                    results = search(query, category_level=spec["api_category_level"],
                                     category_values=spec["api_categories"], session=session)
                    meta = search_metadata(results)
                    merged = {_product_key(item): item for item in pools[spec["id"]]}
                    # Preserve the primary response on duplicate products.
                    for item in results:
                        merged.setdefault(_product_key(item), item)
                    pools[spec["id"]] = list(merged.values())
                except MarketFiyatiError as exc:
                    meta = getattr(exc, "search_metadata", {"status": "failed", "reason": str(exc)})
                    reports[spec["id"]]["aliases"].append({**meta, "query": query})
                    # Optional queries must not create another recovery storm.
                    return {"requests": budget.used, "status": "source_or_budget_failure"}
                reports[spec["id"]]["aliases"].append({**meta, "query": query})
        return {"requests": budget.used, "status": "finished"}
    finally:
        session._marketfiyati_budget = previous_budget


def read_json(path: Path, default: dict) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else copy.deepcopy(default)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_suffix(path.suffix + ".tmp")
    staged.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    staged.replace(path)


def write_collection_report(path: Path, report: dict) -> None:
    """Failed refresh metadata must not replace the published day's evidence."""
    previous = read_json(path, {})
    if previous.get("status") == "published" and report.get("status") != "published":
        path = path.parent / "attempts" / f"{path.stem}-{time.time_ns()}.json"
    write_json(path, report)


def load_rollout(root: Path) -> dict:
    config = read_json(root / "config/rollout.json", {"mode": "shadow", "policy_version": POLICY_VERSION})
    if config.get("mode") not in {"shadow", "active"} or config.get("policy_version") != POLICY_VERSION:
        raise ValueError("Unknown recovery rollout mode/version")
    if config["mode"] == "active":
        evidence = read_json(root / "state/v0.4-discovery.json", {})
        if not eligibility(evidence)["eligible"] or not config.get("activated_on"):
            raise ValueError("Recovery activation requires seven validated complete shadow dates")
    return config


def eligibility(evidence: dict) -> dict:
    dates = sorted(day for day, record in evidence.get("shadow_days", {}).items()
                   if record.get("complete") and record.get("validated") and record.get("shadow_validated"))
    return {"required_dates": SHADOW_DAYS, "complete_dates": dates,
            "eligible": len(dates) >= SHADOW_DAYS, "policy_version": POLICY_VERSION}


def finalize_shadow_day(root: Path, day: str, accepted: bool) -> dict:
    """Call only AFTER the whole publication pipeline validates its staging tree."""
    path = root / "state/v0.4-discovery.json"
    evidence = read_json(path, {"schema_version": 1, "types": {}, "shadow_days": {}})
    record = evidence.setdefault("shadow_days", {}).get(day)
    if record is not None:
        # A failed refresh cannot revoke a previously verified complete day.
        record["validated"] = bool(record.get("validated") or (accepted and record.get("pending_qualified")))
        if accepted:
            snapshot = root / "data/v0.4/snapshots" / f"{day}.csv"
            if not snapshot.exists():
                raise ValueError("Cannot finalize a day without its validated snapshot")
            with snapshot.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    entry = evidence.get("types", {}).get(row["type_id"], {}).get("products", {}).get(
                        row["product_key"], {}).get("dates", {}).get(day)
                    if entry is not None:
                        entry["published_linked_unit_price"] = float(row["linked_unit_price"])
        write_json(path, evidence)
    result = eligibility(evidence)
    diagnostics = root / "data/v0.4/collection-diagnostics" / f"{day}.json"
    if accepted and diagnostics.exists():
        report = read_json(diagnostics, {})
        report.setdefault("shadow", {}).update(result)
        write_json(diagnostics, report)
    return result


def activate(root: Path, effective_date: str) -> dict:
    """Explicit operator action; never auto-activate on a timer or threshold."""
    evidence = read_json(root / "state/v0.4-discovery.json", {})
    report = eligibility(evidence)
    if not report["eligible"]:
        raise ValueError("Seven complete, independently validated shadow dates are required")
    if date.fromisoformat(effective_date) <= date.fromisoformat(max(report["complete_dates"])):
        raise ValueError("Activation must start after the last validated shadow date")
    if not (root / "state/v0.4-shadow-panels.json").exists():
        raise ValueError("Shadow panel state is missing")
    config = {"policy_version": POLICY_VERSION, "mode": "active", "activated_on": effective_date,
              "reviewed_shadow_dates": report["complete_dates"]}
    write_json(root / "config/rollout.json", config)
    return config


def record_pool(evidence: dict, spec: dict, items: list[dict], today: str, complete: bool) -> dict:
    """Retain discovery even when publication later fails; qualify only complete dates."""
    from .collect import _base_candidate, _offer_rows, _product_key, _rejection_reason
    state = evidence.setdefault("types", {}).setdefault(spec["id"], {"products": {}})
    cutoff = (date.fromisoformat(today) - timedelta(days=RETENTION_DAYS - 1)).isoformat()
    rejections = dict.fromkeys(("category", "title", "quantity", "unit_price", "no_offers"), 0)
    products = state.setdefault("products", {})
    accepted = []
    participation = []
    rejected_products = []
    for item in {_product_key(item): item for item in items}.values():
        reason = _rejection_reason(item, spec)
        if reason:
            rejections[reason] += 1
            rejected_products.append({"product_key": _product_key(item), "reason": reason,
                "retailer_depot": [{"source_id": offer.get("source_id"), "market": offer.get("market", ""),
                                   "depot_name": offer.get("depot_name", "")} for offer in _offer_rows(item)]})
            continue
        row = _base_candidate(item, spec)
        accepted.append(row)
        product = products.setdefault(row["product_key"], {"dates": {}})
        product.update(title=row["title"], unit=row["unit"], quantity=row["quantity"])
        previous = product["dates"].get(today, {})
        # An incomplete later refresh must not erase a complete evidence row.
        if complete or not previous.get("complete"):
            product["dates"][today] = {"complete": complete, "unit_price": row["unit_price"],
                                       "quantity": row["quantity"], "offers": row["offers"],
                                       **({"linked_unit_price": previous["linked_unit_price"]}
                                          if "linked_unit_price" in previous else {}),
                                       **({"published_linked_unit_price": previous["published_linked_unit_price"]}
                                          if "published_linked_unit_price" in previous else {})}
        participation.extend({"product_key": row["product_key"], "source_id": offer.get("source_id"),
                              "market": offer.get("market", ""), "depot_name": offer.get("depot_name", "")}
                             for offer in row["offers"])
    for key in list(products):
        products[key]["dates"] = {day: value for day, value in products[key]["dates"].items() if day >= cutoff}
        if not products[key]["dates"]:
            del products[key]
    return {"complete": complete, "accepted_candidates": len(accepted), "rejections": rejections,
            "rejected_products": rejected_products,
            "retailer_depot": participation}


def qualified(product: dict, today: str) -> bool:
    return len([day for day, record in product.get("dates", {}).items()
                if day <= today and record.get("complete")]) >= QUALIFY_DATES


def _remember_link(evidence: dict, row: dict, today: str) -> None:
    record = evidence.get("products", {}).get(row["product_key"], {}).get("dates", {}).get(today)
    if record is not None:
        record["linked_unit_price"] = row["linked_unit_price"]


def _observe_with_depot_admission(item: dict, spec: dict, sku: dict, evidence: dict, today: str, complete: bool):
    from .collect import _base_candidate, _prices_by_source, _row_for_state
    # Sources admitted earlier in this calendar date must remain outside that
    # date's calculation even on subsequent scheduled refreshes.
    original = copy.deepcopy(sku)
    admitted_today = {key for key, day in sku.get("source_admitted_dates", {}).items() if day == today}
    anchors = sku.get("source_anchor_prices", {})
    last = sku.get("source_last_prices", {})
    today_anchors = {key: anchors.pop(key) for key in list(anchors) if key in admitted_today}
    for key in admitted_today:
        last.pop(key, None)
    row = _row_for_state(item, spec, sku)
    if row is None:
        sku.clear()
        sku.update(original)
        return None
    if complete:
        _remember_link(evidence, row, today)
    base = _base_candidate(item, spec)
    current = _prices_by_source(base["offers"])
    history = evidence.get("products", {}).get(row["product_key"], {}).get("dates", {})
    if complete:
        for source, value in current.items():
            if source in sku.get("source_anchor_prices", {}):
                continue
            dates = [day for day, entry in history.items() if day <= today and entry.get("complete")
                     and entry.get("linked_unit_price") is not None
                     and source in _prices_by_source(entry.get("offers", []))]
            if len(dates) >= QUALIFY_DATES:
                sku.setdefault("source_anchor_prices", {})[source] = value
                sku.setdefault("source_last_prices", {})[source] = value
                sku.setdefault("source_admitted_dates", {})[source] = today
    # Preserve admission while incomplete refreshes still have valid old overlap.
    for source, anchor in today_anchors.items():
        sku.setdefault("source_anchor_prices", {})[source] = anchor
        if source in current:
            sku.setdefault("source_last_prices", {})[source] = current[source]
    sku["source_ids"] = sorted(sku.get("source_anchor_prices", {}))
    return row


def replacement_level(old: dict, new_key: str, evidence: dict, today: str) -> tuple[float, str] | None:
    """Link at observed contemporaneous overlap, then chain the candidate forward."""
    from .collect import _geomean, _prices_by_source
    products = evidence.get("products", {})
    old_dates = products.get(old["product_key"], {}).get("dates", {})
    new_dates = products.get(new_key, {}).get("dates", {})
    common = sorted(day for day in set(old_dates) & set(new_dates) if day <= today
                    and old_dates[day].get("complete") and new_dates[day].get("complete")
                    and old_dates[day].get("linked_unit_price") is not None)
    if not common or today not in new_dates:
        return None
    overlap_day = common[-1]
    level = float(old_dates[overlap_day]["linked_unit_price"])
    previous = new_dates[overlap_day]
    for day in sorted(day for day in new_dates if overlap_day < day <= today):
        current = new_dates[day]
        if not current.get("complete"):
            continue
        before = _prices_by_source(previous["offers"])
        after = _prices_by_source(current["offers"])
        sources = sorted(set(before) & set(after))
        if not sources:
            return None
        # Quantity changes remain real unit-price changes.
        level *= _geomean([after[source] / before[source] for source in sources])
        level *= float(previous["quantity"]) / float(current["quantity"])
        previous = current
    if not new_dates[today].get("complete"):
        return None
    return level, overlap_day


def compare_policies(root: Path, today: str, published_rows: list[dict], proposed_rows: list[dict],
                     specs: list[dict]) -> dict:
    """Replay identical frozen history, swapping only accepted prospective shadow days."""
    from .index import build_category_indices, build_main_index, build_type_indices, load_snapshot
    categories_path = root / "config/categories.json"
    if not categories_path.exists():
        return {"status": "unknown", "reason": "category_configuration_unavailable"}
    categories = read_json(categories_path, {})["categories"]
    series = read_json(root / "config/series.json", {})
    baseline_date = series.get("baseline_date", "")
    frozen_through = series.get("locked_through", baseline_date)
    snapshots = {path.stem: load_snapshot(path) for path in sorted((root / "data/v0.4/snapshots").glob("*.csv"))
                 if baseline_date <= path.stem < today}
    snapshots[today] = published_rows
    shadow = dict(snapshots)
    for path in sorted((root / "data/v0.4/shadow").glob("*.csv")):
        if frozen_through < path.stem < today:
            shadow[path.stem] = load_snapshot(path)
    shadow[today] = proposed_rows

    def summarize_policy(observations):
        types = build_type_indices(sorted(observations.items()), specs)
        groups = build_category_indices(types, specs, categories)
        main = build_main_index(types, groups, categories)
        headline = next(row for row in main if row["date"] == today)
        current_groups = {row["group_id"]: row for row in groups if row["date"] == today}
        previous_main = next((row for row in reversed(main) if row["date"] < today and row["index"] is not None), None)
        prior_groups = {row["group_id"] for row in groups if previous_main and row["date"] == previous_main["date"]
                        and row["index"] is not None}
        available_groups = {key for key, row in current_groups.items() if row["index"] is not None}
        overlap = sum(float(group["weight"]) for group in categories if group["id"] in available_groups & prior_groups)
        total_weight = sum(float(group["weight"]) for group in categories)
        yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
        previous_day = next((row for row in main if row["date"] == yesterday), None)
        change = ((headline["index"] / previous_day["index"] - 1) * 100
                  if headline["index"] is not None and previous_day and previous_day["index"] is not None else None)
        current_types = {row["type_id"]: row for row in types if row["date"] == today}
        group_reports = {}
        for group in categories:
            key = group["id"]
            members = [spec for spec in specs if spec["group"] == key]
            previous_group = next((row for row in reversed(groups) if row["group_id"] == key and row["date"] < today
                                   and row["index"] is not None), None)
            previous_members = {row["type_id"] for row in types if previous_group and row["date"] == previous_group["date"]
                                and row["group"] == key and row["index"] is not None}
            common_weight = sum(float(spec.get("type_weight", 1)) for spec in members
                                if spec["id"] in previous_members and current_types[spec["id"]]["index"] is not None)
            weight = sum(float(spec.get("type_weight", 1)) for spec in members)
            group_reports[key] = {"index": current_groups[key]["index"], "available_coverage": current_groups[key]["coverage"],
                                  "comparison_overlap": common_weight / weight if weight else 0}
        return {"index": headline["index"], "daily_change_pct": change,
                "weighted_coverage": headline["coverage"],
                "weighted_comparison_overlap": overlap / total_weight if total_weight else 0,
                "publishable_categories": sorted(available_groups), "categories": group_reports,
                "type_overlap": {key: {"coverage": row["coverage"], "matched_slots": row["skus"],
                                       "publishable": row["index"] is not None} for key, row in current_types.items()}}

    legacy, proposed = summarize_policy(snapshots), summarize_policy(shadow)
    difference = (proposed["index"] - legacy["index"]
                  if proposed["index"] is not None and legacy["index"] is not None else None)
    return {"status": "valid" if proposed["index"] is not None else "shadow_unavailable",
            "baseline_date": baseline_date,
            "legacy": legacy, "proposed": proposed, "index_difference_points": difference,
            "weighted_coverage_difference": proposed["weighted_coverage"] - legacy["weighted_coverage"]}


def observe_type(items: list[dict], spec: dict, state: dict, claimed: set[str], today: str,
                 historical_levels: dict, evidence: dict, *, complete: bool,
                 absence_complete: bool | None = None) -> tuple[list[dict], dict]:
    from .collect import (_base_candidate, _migrate_sku_state, _new_sku_state, _prices_by_source,
                          _product_key, _row_for_state, _title_matches)
    active = state.setdefault("skus", [])
    absence_complete = complete if absence_complete is None else absence_complete
    new_day = absence_complete and state.get("last_absence_date") != today
    if complete:
        state["last_complete_date"] = today
    if absence_complete:
        state["last_absence_date"] = today
    # A persisted allowance survives same-day reruns and retained observations.
    if state.get("turnover_date") != today:
        state.update(turnover_date=today, additions_today=0, replacements_today=0)
    limit = math.ceil(int(spec["target_skus"]) * 0.20)
    allowance = max(0, limit - int(state["additions_today"]) - int(state["replacements_today"]))
    by_key = {_product_key(item): item for item in items}
    bases = {key: row for key, item in by_key.items() if (row := _base_candidate(item, spec)) is not None}
    rows, observed_slots = [], set()
    lost_connections = 0
    depot_gaps = []
    for sku in active:
        _migrate_sku_state(sku, historical_levels)
        key = sku["product_key"]
        item = by_key.get(key)
        if key in bases:
            current_sources = set(_prices_by_source(bases[key]["offers"]))
            established_sources = set(sku.get("source_ids", []))
            if current_sources != established_sources:
                depot_gaps.append({"product_key": key, "missing_source_ids": sorted(established_sources - current_sources),
                                   "new_source_ids": sorted(current_sources - established_sources)})
        row = _observe_with_depot_admission(item, spec, sku, evidence, today, complete) if key in bases else None
        if row is None:
            lost_connections += int(key in bases)
            if new_day:
                sku["missing_streak"] = int(sku.get("missing_streak", 0)) + 1
            if item and not _title_matches(str(item.get("title") or ""), spec):
                sku["retired_reason"] = "definition_mismatch"
            continue
        sku.update(missing_streak=0, last_seen=today, title=row["title"], last_linked_unit_price=row["linked_unit_price"])
        rows.append(row)
        observed_slots.add(row["slot_id"])
    active_keys = {sku["product_key"] for sku in active}
    eligible = [row for key, row in bases.items() if key not in active_keys and key not in claimed
                and qualified(evidence.get("products", {}).get(key, {}), today)] if complete else []
    eligible.sort(key=lambda row: (-row["score"], -row["offer_count"], row["product_key"]))
    ready = len(eligible)
    while eligible and len(active) < spec["target_skus"] and allowance:
        candidate = eligible.pop(0)
        sku = _new_sku_state(candidate, today)
        row = _row_for_state(by_key[candidate["product_key"]], spec, sku)
        if row is None:
            continue
        sku["last_linked_unit_price"] = row["linked_unit_price"]
        active.append(sku)
        claimed.add(candidate["product_key"])
        rows.append(row)
        observed_slots.add(row["slot_id"])
        _remember_link(evidence, row, today)
        state["additions_today"] += 1
        allowance -= 1
    missing = [sku for sku in active if sku["slot_id"] not in observed_slots and
               (int(sku.get("missing_streak", 0)) >= 7 or sku.get("retired_reason") == "definition_mismatch")]
    unavailable = 0
    for old in missing:
        if not complete or allowance <= 0:
            break
        linked_candidate = next(((candidate, bridge) for candidate in eligible
                                 if (bridge := replacement_level(old, candidate["product_key"], evidence, today))), None)
        if linked_candidate is None:
            unavailable += 1
            continue
        candidate, (level, overlap_day) = linked_candidate
        sku = _new_sku_state(candidate, today, slot_id=old["slot_id"], generation=int(old.get("generation", 0)) + 1)
        row = _row_for_state(by_key[candidate["product_key"]], spec, sku)
        if row is None:
            continue
        sku["link_factor"] = level / row["linked_unit_price"]
        row = _row_for_state(by_key[candidate["product_key"]], spec, sku)
        sku.update(previous_product_key=old["product_key"], replaced_on=today,
                   replacement_reason="evidenced_overlap", overlap_date=overlap_day,
                   last_linked_unit_price=row["linked_unit_price"])
        active[active.index(old)] = sku
        claimed.add(candidate["product_key"])
        eligible.remove(candidate)
        rows.append(row)
        observed_slots.add(row["slot_id"])
        _remember_link(evidence, row, today)
        state["replacements_today"] += 1
        allowance -= 1
    state["last_observed_date"] = today
    return rows, {"panel_size": len(active), "target_skus": spec["target_skus"], "min_skus": spec["min_skus"],
                  "observed_skus": len(rows), "missing_skus": len(active) - len(observed_slots),
                  "lost_depot_connections": lost_connections, "ready_candidates": ready,
                  "depot_gaps": depot_gaps, "insufficient_observed_products": len(rows) < spec["min_skus"],
                  "unavailable_replacements": unavailable, "below_target": len(active) < spec["target_skus"],
                  "additions_today": state["additions_today"], "replacements_today": state["replacements_today"],
                  "turnover_allowance": limit}


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or explicitly activate the shadow-tested recovery policy")
    parser.add_argument("command", nargs="?", choices=["status", "finalize-day"], default="status")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--date", help="Staged date to finalize; defaults to latest staged snapshot")
    parser.add_argument("--activate-from", help="Prospective YYYY-MM-DD; requires seven validated complete shadow days")
    args = parser.parse_args()
    if args.command == "finalize-day":
        snapshots = sorted((args.root / "data/v0.4/snapshots").glob("*.csv"))
        if not snapshots:
            raise SystemExit("No staged snapshots to finalize")
        result = finalize_shadow_day(args.root, args.date or snapshots[-1].stem, True)
    else:
        result = activate(args.root, args.activate_from) if args.activate_from else eligibility(
            read_json(args.root / "state/v0.4-discovery.json", {}))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
