from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .api import MarketFiyatiError, search_products
from .product_types import load_product_types
from .units import parse_quantity, unit_price

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "v0.3"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
PANEL_PATH = ROOT / "state" / "v0.3-panels.json"
TR_TZ = ZoneInfo("Europe/Istanbul")
LOW_COVERAGE_THRESHOLD = 0.80
RENEWAL_AFTER_DAYS = 7
CANDIDATE_MIN_STREAK = 3
CANDIDATE_RETENTION_DAYS = 14
MAX_REPLACEMENT_SHARE = 0.20


def _norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower().replace("ı", "i")).strip()


def _product_key(item: dict[str, Any]) -> str:
    for field in ("id", "productId", "product_id", "barcode"):
        value = item.get(field)
        if value not in (None, ""):
            return f"{field}:{value}"
    return f"title:{_norm(str(item.get('title') or ''))}"


def _score(item: dict[str, Any], spec: dict[str, Any]) -> float:
    title = _norm(str(item.get("title") or ""))
    if not title:
        return -1.0
    excludes = [_norm(token) for token in spec.get("exclude_tokens") or []]
    if any(token and token in title for token in excludes):
        return -1.0
    includes = [_norm(token) for token in spec.get("include_tokens") or []]
    if not includes:
        return 1.0
    return sum(token in title for token in includes) / len(includes)


def _source_key(depot: dict[str, Any]) -> str | None:
    depot_id = depot.get("depotId")
    if depot_id not in (None, ""):
        return f"depot:{depot_id}"
    market = _norm(str(depot.get("marketAdi") or ""))
    name = _norm(str(depot.get("depotName") or ""))
    if market or name:
        return f"named:{market}|{name}"
    return None


def _offer_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for depot in item.get("productDepotInfoList") or []:
        try:
            price = float(depot.get("price"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(price) or price <= 0:
            continue
        rows.append({
            "price": price,
            "source_id": _source_key(depot),
            "market": str(depot.get("marketAdi") or "").strip(),
            "depot_name": str(depot.get("depotName") or "").strip(),
        })
    return rows


def _median_price(offers: list[dict[str, Any]]) -> float:
    return float(median([float(row["price"]) for row in offers]))


def _base_candidate(item: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any] | None:
    score = _score(item, spec)
    if score < 0.5:
        return None
    title = str(item.get("title") or "").strip()
    quantity = parse_quantity(title, spec["unit"])
    if quantity is None:
        return None
    offers = _offer_rows(item)
    if not offers:
        return None
    price = _median_price(offers)
    return {
        "product_key": _product_key(item),
        "title": title,
        "quantity": quantity.amount,
        "unit": quantity.unit,
        "price": price,
        "unit_price": unit_price(price, quantity),
        "offer_count": len(offers),
        "score": score,
        "offers": offers,
    }


def _pin_sources(sku_state: dict[str, Any], offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    saved = [str(value) for value in sku_state.get("source_ids") or [] if value]
    keyed = [row for row in offers if row.get("source_id")]

    if not saved:
        source_ids = sorted({str(row["source_id"]) for row in keyed})
        if source_ids:
            sku_state["source_ids"] = source_ids
            saved = source_ids
            sku_state["source_mode"] = "pinned"
        else:
            sku_state["source_mode"] = "unkeyed"
            sku_state.setdefault("source_bridge_factor", 1.0)
            return offers

    stable = [row for row in offers if row.get("source_id") in set(saved)]
    if not stable:
        return []

    if "source_bridge_factor" not in sku_state:
        # Preserve the old all-offer price level on the day source pinning is adopted.
        sku_state["source_bridge_factor"] = _median_price(offers) / _median_price(stable)
    return stable


def _row_for_state(item: dict[str, Any], spec: dict[str, Any], sku_state: dict[str, Any]) -> dict[str, Any] | None:
    base = _base_candidate(item, spec)
    if base is None:
        return None
    stable_offers = _pin_sources(sku_state, base["offers"])
    if not stable_offers:
        return None
    stable_price = _median_price(stable_offers)
    quantity = parse_quantity(base["title"], spec["unit"])
    if quantity is None:
        return None
    stable_unit_price = unit_price(stable_price, quantity)
    source_bridge = float(sku_state.get("source_bridge_factor", 1.0))
    link_factor = float(sku_state.get("link_factor", 1.0))
    linked = stable_unit_price * source_bridge * link_factor
    used_source_ids = sorted({str(row["source_id"]) for row in stable_offers if row.get("source_id")})
    markets = sorted({str(row["market"]) for row in stable_offers if row.get("market")})
    return {
        "product_key": base["product_key"],
        "slot_id": str(sku_state.get("slot_id") or base["product_key"]),
        "title": base["title"],
        "quantity": quantity.amount,
        "unit": quantity.unit,
        "price": round(stable_price, 4),
        "unit_price": round(stable_unit_price, 6),
        "linked_unit_price": round(linked, 6),
        "offer_count": len(stable_offers),
        "raw_offer_count": len(base["offers"]),
        "source_count": len(used_source_ids),
        "source_ids": json.dumps(used_source_ids, ensure_ascii=False, separators=(",", ":")),
        "markets": json.dumps(markets, ensure_ascii=False, separators=(",", ":")),
        "source_mode": str(sku_state.get("source_mode") or "unkeyed"),
        "generation": int(sku_state.get("generation", 0)),
        "score": base["score"],
    }


def _load_panel() -> dict[str, Any]:
    if PANEL_PATH.exists():
        return json.loads(PANEL_PATH.read_text(encoding="utf-8"))
    return {"version": "v0.3", "types": {}}


def _migrate_sku_state(sku: dict[str, Any]) -> None:
    product_key = str(sku.get("product_key") or "")
    sku.setdefault("slot_id", product_key)
    sku.setdefault("generation", 0)
    sku.setdefault("link_factor", 1.0)
    sku.setdefault("missing_streak", 0)


def _new_sku_state(row: dict[str, Any], today: str, *, slot_id: str | None = None, generation: int = 0, link_factor: float = 1.0) -> dict[str, Any]:
    state: dict[str, Any] = {
        "slot_id": slot_id or row["product_key"],
        "product_key": row["product_key"],
        "title": row["title"],
        "first_quantity": row["quantity"],
        "unit": row["unit"],
        "first_seen": today,
        "last_seen": today,
        "missing_streak": 0,
        "generation": generation,
        "link_factor": link_factor,
    }
    _pin_sources(state, row["offers"])
    return state


def _initialize_type(candidates: list[dict[str, Any]], spec: dict[str, Any], claimed: set[str], today: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    candidate_items: dict[str, dict[str, Any]] = {}
    for item in candidates:
        row = _base_candidate(item, spec)
        if row is None or row["product_key"] in claimed:
            continue
        rows.append(row)
        candidate_items[row["product_key"]] = item
    rows.sort(key=lambda row: (row["score"], row["offer_count"]), reverse=True)
    selected = rows[: spec["target_skus"]]
    states: list[dict[str, Any]] = []
    observed: list[dict[str, Any]] = []
    for row in selected:
        claimed.add(row["product_key"])
        sku_state = _new_sku_state(row, today)
        states.append(sku_state)
        obs = _row_for_state(candidate_items[row["product_key"]], spec, sku_state)
        if obs is not None:
            sku_state["last_linked_unit_price"] = obs["linked_unit_price"]
            observed.append(obs)
    panel = {
        "initialized": today,
        "label": spec["label"],
        "group": spec["group"],
        "target_skus": spec["target_skus"],
        "low_coverage_streak": 0,
        "skus": states,
        "candidates": {},
    }
    return panel, observed


def _update_shadow_candidates(state: dict[str, Any], rows: list[dict[str, Any]], active_keys: set[str], claimed: set[str], today: str) -> dict[str, dict[str, Any]]:
    shadows = state.setdefault("candidates", {})
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    current: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row["product_key"]
        if key in active_keys or key in claimed:
            continue
        previous = shadows.get(key) or {}
        streak = int(previous.get("seen_streak", 0)) + 1 if previous.get("last_seen") == yesterday else 1
        shadows[key] = {
            "product_key": key,
            "title": row["title"],
            "quantity": row["quantity"],
            "unit": row["unit"],
            "score": row["score"],
            "offer_count": row["offer_count"],
            "seen_streak": streak,
            "last_seen": today,
        }
        current[key] = row

    cutoff = date.fromisoformat(today) - timedelta(days=CANDIDATE_RETENTION_DAYS)
    for key in list(shadows):
        try:
            last_seen = date.fromisoformat(str(shadows[key].get("last_seen")))
        except (TypeError, ValueError):
            last_seen = cutoff - timedelta(days=1)
        if last_seen < cutoff:
            shadows.pop(key, None)
    return current


def _observe_type(candidates: list[dict[str, Any]], spec: dict[str, Any], state: dict[str, Any], claimed: set[str], today: str) -> list[dict[str, Any]]:
    for sku in state.get("skus") or []:
        _migrate_sku_state(sku)
    items_by_key = {_product_key(item): item for item in candidates}
    candidate_rows = [row for item in candidates if (row := _base_candidate(item, spec)) is not None]
    active = state.get("skus") or []
    active_keys = {str(sku.get("product_key") or "") for sku in active}
    shadow_rows = _update_shadow_candidates(state, candidate_rows, active_keys, claimed, today)

    observed: list[dict[str, Any]] = []
    observed_slots: set[str] = set()
    for sku in active:
        item = items_by_key.get(str(sku.get("product_key") or ""))
        row = _row_for_state(item, spec, sku) if item is not None else None
        if row is None:
            sku["missing_streak"] = int(sku.get("missing_streak", 0)) + 1
            continue
        sku["missing_streak"] = 0
        sku["last_seen"] = today
        sku["last_linked_unit_price"] = row["linked_unit_price"]
        observed.append(row)
        observed_slots.add(row["slot_id"])

    coverage = len(observed_slots) / len(active) if active else 0.0
    if active and coverage < LOW_COVERAGE_THRESHOLD:
        state["low_coverage_streak"] = int(state.get("low_coverage_streak", 0)) + 1
    else:
        state["low_coverage_streak"] = 0

    if int(state.get("low_coverage_streak", 0)) < RENEWAL_AFTER_DAYS:
        return observed

    missing = sorted(
        [sku for sku in active if int(sku.get("missing_streak", 0)) >= RENEWAL_AFTER_DAYS],
        key=lambda sku: int(sku.get("missing_streak", 0)),
        reverse=True,
    )
    eligible_candidates = [
        shadow for shadow in state.get("candidates", {}).values()
        if shadow.get("last_seen") == today
        and int(shadow.get("seen_streak", 0)) >= CANDIDATE_MIN_STREAK
        and shadow.get("product_key") in shadow_rows
    ]
    eligible_candidates.sort(key=lambda row: (float(row.get("score", 0)), int(row.get("offer_count", 0))), reverse=True)
    max_replacements = max(1, math.ceil(len(active) * MAX_REPLACEMENT_SHARE)) if active else 0

    replacements = 0
    for old, candidate_meta in zip(missing, eligible_candidates):
        if replacements >= max_replacements:
            break
        candidate = shadow_rows[str(candidate_meta["product_key"])]
        old_key = str(old.get("product_key") or "")
        new_key = str(candidate["product_key"])
        if new_key in claimed:
            continue

        provisional = _new_sku_state(
            candidate,
            today,
            slot_id=str(old.get("slot_id") or old_key),
            generation=int(old.get("generation", 0)) + 1,
        )
        item = items_by_key.get(new_key)
        replacement_row = _row_for_state(item, spec, provisional) if item is not None else None
        if replacement_row is None:
            continue
        old_level = old.get("last_linked_unit_price")
        if old_level not in (None, "") and float(replacement_row["linked_unit_price"]) > 0:
            provisional["link_factor"] = float(old_level) / (
                float(replacement_row["unit_price"]) * float(provisional.get("source_bridge_factor", 1.0))
            )
            replacement_row = _row_for_state(item, spec, provisional)
            if replacement_row is None:
                continue
        provisional["previous_product_key"] = old_key
        provisional["replaced_on"] = today
        provisional["last_linked_unit_price"] = replacement_row["linked_unit_price"]
        idx = active.index(old)
        active[idx] = provisional
        claimed.discard(old_key)
        claimed.add(new_key)
        state.get("candidates", {}).pop(new_key, None)
        observed.append(replacement_row)
        replacements += 1

    if replacements:
        state["last_renewal"] = today
        state["renewals"] = int(state.get("renewals", 0)) + replacements
    return observed


def collect() -> Path:
    specs = load_product_types()
    panel_state = _load_panel()
    panel_state["source_policy"] = "pinned-with-bridge"
    panel_state["renewal_policy"] = {
        "low_coverage_threshold": LOW_COVERAGE_THRESHOLD,
        "renewal_after_days": RENEWAL_AFTER_DAYS,
        "candidate_min_streak": CANDIDATE_MIN_STREAK,
        "max_replacement_share": MAX_REPLACEMENT_SHARE,
    }
    types_state = panel_state.setdefault("types", {})
    today = datetime.now(TR_TZ).date().isoformat()
    claimed = {
        str(sku.get("product_key"))
        for state in types_state.values()
        for sku in (state.get("skus") or [])
        if sku.get("product_key")
    }
    session = requests.Session()
    output_rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for number, spec in enumerate(specs, start=1):
        try:
            candidates = search_products(spec["query"], session=session)
            state = types_state.get(spec["id"])
            if not state or not state.get("skus"):
                state, observed = _initialize_type(candidates, spec, claimed, today)
                types_state[spec["id"]] = state
            else:
                observed = _observe_type(candidates, spec, state, claimed, today)

            for row in observed:
                output_rows.append({
                    "date": today,
                    "group": spec["group"],
                    "type_id": spec["id"],
                    "type_label": spec["label"],
                    "slot_id": row["slot_id"],
                    "product_key": row["product_key"],
                    "title": row["title"],
                    "quantity": row["quantity"],
                    "unit": row["unit"],
                    "price": row["price"],
                    "unit_price": row["unit_price"],
                    "linked_unit_price": row["linked_unit_price"],
                    "offer_count": row["offer_count"],
                    "raw_offer_count": row["raw_offer_count"],
                    "source_count": row["source_count"],
                    "source_ids": row["source_ids"],
                    "markets": row["markets"],
                    "source_mode": row["source_mode"],
                    "generation": row["generation"],
                })
        except MarketFiyatiError as exc:
            errors.append({"type_id": spec["id"], "error": str(exc)})

        if number % 20 == 0 or number == len(specs):
            observed_types = len({row["type_id"] for row in output_rows})
            print(f"progress={number}/{len(specs)} skus={len(output_rows)} types={observed_types} errors={len(errors)}")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out = SNAPSHOT_DIR / f"{today}.csv"
    fields = [
        "date", "group", "type_id", "type_label", "slot_id", "product_key", "title",
        "quantity", "unit", "price", "unit_price", "linked_unit_price", "offer_count",
        "raw_offer_count", "source_count", "source_ids", "markets", "source_mode", "generation",
    ]
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    PANEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    PANEL_PATH.write_text(json.dumps(panel_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    error_path = DATA_DIR / "latest-errors.json"
    error_path.write_text(json.dumps({"date": today, "errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    panel_skus = sum(len(state.get("skus") or []) for state in types_state.values())
    observed_types = len({row["type_id"] for row in output_rows})
    source_pinned = sum(row.get("source_mode") == "pinned" for row in output_rows)
    renewals = sum(int(state.get("renewals", 0)) for state in types_state.values())
    print(
        f"snapshot={out.relative_to(ROOT)} observed_skus={len(output_rows)} panel_skus={panel_skus} "
        f"observed_types={observed_types}/{len(specs)} source_pinned={source_pinned} "
        f"renewals_total={renewals} errors={len(errors)}"
    )
    return out


if __name__ == "__main__":
    collect()
