from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .api import MarketFiyatiError, search_products
from .product_types import load_product_types
from .units import Quantity, parse_quantity, unit_price

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "v0.4"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
PANEL_PATH = ROOT / "state" / "v0.4-panels.json"
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


def _word_matches(actual: str, expected: str) -> bool:
    """Match exact short words and safe Turkish suffix variants for longer words."""
    inflections = {
        "ekmek": {"ekmegi", "ekmegini"},
        "gevrek": {"gevregi", "gevregini"},
        "un": {"unu", "unlari"},
        "jel": {"jeli", "jeller", "jelleri"},
        "bal": {"bali", "ballari"},
        "su": {"suyu", "sulari"},
    }
    return (actual == expected or actual in inflections.get(expected, set())
            or (len(expected) >= 4 and actual.startswith(expected)))


def _phrase_matches(text: str, phrase: str) -> bool:
    words = _norm(text).split()
    expected = _norm(phrase).split()
    if not expected:
        return False
    width = len(expected)
    return any(
        all(_word_matches(actual, wanted) for actual, wanted in zip(words[start:start + width], expected))
        for start in range(len(words) - width + 1)
    )


def _rule_matches(text: str, expression: str) -> bool:
    return any(_phrase_matches(text, alternative) for alternative in expression.split("|"))


def _matched_category(item: dict[str, Any], spec: dict[str, Any]) -> str | None:
    level = str(spec.get("api_category_level") or "")
    expected = list(spec.get("api_categories") or [])
    if level == "menu_category":
        actual = [str(item.get("menu_category") or "")]
    elif level == "main_category":
        actual = [str(item.get("main_category") or "")]
    elif level == "sub_category":
        actual = [str(value) for value in (item.get("categories") or [])]
    else:
        return None
    actual_norm = {_norm(value) for value in actual if value}
    for value in expected:
        if _norm(value) in actual_norm:
            return value
    # The v2 endpoint applies canonical category filters server-side, but the
    # product's categories[] array is a heterogeneous collection of market
    # labels and often uses a singular/plural variant. Preserve and verify the
    # exact request provenance instead of pretending that noisy echo is absent.
    query_level = item.get("_query_category_level")
    query_values = {_norm(value) for value in (item.get("_query_category_values") or [])}
    if query_level == level:
        for value in expected:
            if _norm(value) in query_values:
                return value
    return None


def _title_matches(title: str, spec: dict[str, Any]) -> bool:
    excludes = list(spec.get("exclude_tokens") or [])
    if any(_rule_matches(title, token) for token in excludes):
        return False
    includes = list(spec.get("include_tokens") or [])
    return all(_rule_matches(title, token) for token in includes)


def _score(item: dict[str, Any], spec: dict[str, Any]) -> float:
    title = str(item.get("title") or "").strip()
    if not title or _matched_category(item, spec) is None:
        return -1.0
    includes = list(spec.get("include_tokens") or [])
    if not _title_matches(title, spec):
        return -1.0
    # All required rules are hard gates. Exact words only affect deterministic
    # ordering inside the accepted pool; they never rescue a partial match.
    exact = sum(_norm(token) in _norm(title).split() for token in includes if "|" not in token)
    return 1.0 + (exact / max(1, len(includes))) * 0.1


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
        try:
            api_unit_price = float(depot.get("unitPriceValue"))
            if not math.isfinite(api_unit_price) or api_unit_price <= 0:
                api_unit_price = None
        except (TypeError, ValueError):
            api_unit_price = None
        rows.append({
            "price": price,
            "api_unit_price": api_unit_price,
            "source_id": _source_key(depot),
            "market": str(depot.get("marketAdi") or "").strip(),
            "depot_name": str(depot.get("depotName") or "").strip(),
            "index_time": str(depot.get("indexTime") or "").strip(),
        })
    return rows


def _median_price(offers: list[dict[str, Any]]) -> float:
    return float(median(float(row["price"]) for row in offers))


def _median_api_unit_price(offers: list[dict[str, Any]]) -> float | None:
    values = [float(row["api_unit_price"]) for row in offers if row.get("api_unit_price")]
    return float(median(values)) if values else None


def _source_updated_at(offers: list[dict[str, Any]]) -> str:
    parsed: list[tuple[datetime, str]] = []
    for row in offers:
        raw = str(row.get("index_time") or "")
        try:
            parsed.append((datetime.strptime(raw, "%d.%m.%Y %H:%M"), raw))
        except ValueError:
            continue
    return max(parsed)[1] if parsed else ""


def _quantity(item: dict[str, Any], spec: dict[str, Any]) -> tuple[Quantity, str] | None:
    refined = str(item.get("refinedVolumeOrWeight") or "").strip()
    title = str(item.get("title") or "").strip()
    api_quantity = parse_quantity(refined, spec["unit"]) if refined else None
    title_quantity = parse_quantity(title, spec["unit"])
    if api_quantity is not None and title_quantity is not None:
        if api_quantity.unit != title_quantity.unit:
            return None
        relative_gap = abs(api_quantity.amount / title_quantity.amount - 1.0)
        if relative_gap > 0.05:
            return None
    if api_quantity is not None:
        return api_quantity, "api-refined"
    return (title_quantity, "title") if title_quantity is not None else None


def _geomean(values: list[float]) -> float:
    if not values or any(value <= 0 for value in values):
        raise ValueError("geometric mean requires positive values")
    return math.exp(sum(math.log(value) for value in values) / len(values))


def _base_candidate(item: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any] | None:
    score = _score(item, spec)
    if score < 1.0:
        return None
    title = str(item.get("title") or "").strip()
    quantity_result = _quantity(item, spec)
    if quantity_result is None:
        return None
    quantity, quantity_source = quantity_result
    offers = _offer_rows(item)
    if not offers:
        return None
    price = _median_price(offers)
    calculated_unit_price = unit_price(price, quantity)
    api_unit_price = _median_api_unit_price(offers)
    unit_price_gap = (
        abs(calculated_unit_price / api_unit_price - 1.0)
        if api_unit_price is not None else None
    )
    if unit_price_gap is not None and unit_price_gap > 0.05:
        return None
    return {
        "product_key": _product_key(item),
        "title": title,
        "quantity": quantity.amount,
        "unit": quantity.unit,
        "price": price,
        "unit_price": calculated_unit_price,
        "api_unit_price": api_unit_price,
        "unit_price_gap_pct": unit_price_gap * 100.0 if unit_price_gap is not None else None,
        "quantity_source": quantity_source,
        "matched_category": _matched_category(item, spec),
        "offer_count": len(offers),
        "score": score,
        "offers": offers,
    }


def _prices_by_source(offers: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for row in offers:
        source_id = row.get("source_id")
        if source_id:
            grouped.setdefault(str(source_id), []).append(float(row["price"]))
    return {key: float(median(values)) for key, values in grouped.items()}


def _initialize_sources(sku_state: dict[str, Any], offers: list[dict[str, Any]]) -> None:
    by_source = _prices_by_source(offers)
    if by_source:
        sku_state["source_mode"] = "pinned-relative"
        sku_state["source_ids"] = sorted(by_source)
        sku_state["source_anchor_prices"] = {key: round(value, 6) for key, value in sorted(by_source.items())}
        # Preserve the pre-migration all-offer price level on the adoption day.
        sku_state["source_anchor_level"] = round(_median_price(offers), 6)
    else:
        sku_state["source_mode"] = "unkeyed"


def _source_linked_package_price(
    sku_state: dict[str, Any], offers: list[dict[str, Any]]
) -> tuple[float, list[dict[str, Any]]] | None:
    if not sku_state.get("source_mode"):
        _initialize_sources(sku_state, offers)

    if sku_state.get("source_mode") == "unkeyed":
        return _median_price(offers), offers

    anchors = {
        str(key): float(value)
        for key, value in (sku_state.get("source_anchor_prices") or {}).items()
        if float(value) > 0
    }
    if not anchors:
        _initialize_sources(sku_state, offers)
        anchors = {
            str(key): float(value)
            for key, value in (sku_state.get("source_anchor_prices") or {}).items()
            if float(value) > 0
        }
    current = _prices_by_source(offers)
    common = sorted(set(anchors) & set(current))
    if not common:
        return None

    last_prices = sku_state.get("source_last_prices")
    if last_prices:
        overlap = sorted(set(last_prices) & set(common))
        if not overlap:
            return None
        ratios = [current[key] / float(last_prices[key]) for key in overlap]
        linked_package = float(sku_state["source_last_level"]) * _geomean(ratios)
    else:
        # One-time adoption of legacy state; historical per-depot prices were
        # not persisted. Preserve its existing anchor calculation on adoption.
        ratios = [current[key] / anchors[key] for key in common]
        anchor_level = float(sku_state.get("source_anchor_level") or _median_price(offers))
        linked_package = anchor_level * _geomean(ratios)
    sku_state["source_last_prices"] = {key: current[key] for key in common}
    sku_state["source_last_level"] = linked_package
    common_set = set(common)
    stable_offers = [row for row in offers if row.get("source_id") in common_set]
    return linked_package, stable_offers


def _row_for_state(item: dict[str, Any], spec: dict[str, Any], sku_state: dict[str, Any]) -> dict[str, Any] | None:
    base = _base_candidate(item, spec)
    if base is None:
        return None
    linked_result = _source_linked_package_price(sku_state, base["offers"])
    if linked_result is None:
        return None
    linked_package, stable_offers = linked_result
    quantity = Quantity(float(base["quantity"]), str(base["unit"]))

    observed_package = _median_price(stable_offers)
    observed_unit = unit_price(observed_package, quantity)
    api_unit_price = _median_api_unit_price(stable_offers)
    unit_price_gap_pct = (
        abs(observed_unit / api_unit_price - 1.0) * 100.0
        if api_unit_price is not None else None
    )
    link_factor = float(sku_state.get("link_factor", 1.0))
    linked_unit = unit_price(linked_package, quantity) * link_factor
    used_source_ids = sorted({str(row["source_id"]) for row in stable_offers if row.get("source_id")})
    markets = sorted({str(row["market"]) for row in stable_offers if row.get("market")})

    return {
        "product_key": base["product_key"],
        "slot_id": str(sku_state.get("slot_id") or base["product_key"]),
        "title": base["title"],
        "quantity": quantity.amount,
        "unit": quantity.unit,
        "price": round(observed_package, 4),
        "unit_price": round(observed_unit, 6),
        "linked_unit_price": round(linked_unit, 6),
        "api_unit_price": round(api_unit_price, 6) if api_unit_price is not None else "",
        "unit_price_gap_pct": round(unit_price_gap_pct, 4) if unit_price_gap_pct is not None else "",
        "quantity_source": base["quantity_source"],
        "matched_category": base["matched_category"],
        "category_level": spec["api_category_level"],
        "source_updated_at": _source_updated_at(stable_offers),
        "offer_count": len(stable_offers),
        "raw_offer_count": len(base["offers"]),
        "source_count": len(used_source_ids),
        "source_ids": json.dumps(used_source_ids, ensure_ascii=False, separators=(",", ":")),
        "markets": json.dumps(markets, ensure_ascii=False, separators=(",", ":")),
        "source_mode": str(sku_state.get("source_mode") or "unkeyed"),
        "generation": int(sku_state.get("generation", 0)),
        "score": round(base["score"], 4),
    }


def _load_panel() -> dict[str, Any]:
    if PANEL_PATH.exists():
        return json.loads(PANEL_PATH.read_text(encoding="utf-8"))
    return {"version": "v0.4", "types": {}}


def _historical_levels() -> dict[str, float]:
    levels: dict[str, float] = {}
    for path in reversed(sorted(SNAPSHOT_DIR.glob("*.csv"))):
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                raw = row.get("linked_unit_price") or row.get("unit_price")
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(value) or value <= 0:
                    continue
                product_key = str(row.get("product_key") or "")
                slot_id = str(row.get("slot_id") or product_key)
                if product_key:
                    levels.setdefault(product_key, value)
                if slot_id:
                    levels.setdefault(slot_id, value)
    return levels


def _migrate_sku_state(sku: dict[str, Any], historical_levels: dict[str, float] | None = None) -> None:
    product_key = str(sku.get("product_key") or "")
    slot_id = str(sku.get("slot_id") or product_key)
    sku.setdefault("slot_id", slot_id)
    sku.setdefault("generation", 0)
    sku.setdefault("link_factor", 1.0)
    sku.setdefault("missing_streak", 0)
    if sku.get("last_linked_unit_price") in (None, "") and historical_levels:
        level = historical_levels.get(slot_id) or historical_levels.get(product_key)
        if level is not None:
            sku["last_linked_unit_price"] = level


def _new_sku_state(
    row: dict[str, Any], today: str, *, slot_id: str | None = None, generation: int = 0
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "slot_id": slot_id or row["product_key"],
        "product_key": row["product_key"],
        "title": row["title"],
        "first_quantity": row["quantity"],
        "unit": row["unit"],
        "quantity_source": row.get("quantity_source", ""),
        "matched_category": row.get("matched_category", ""),
        "first_seen": today,
        "last_seen": today,
        "missing_streak": 0,
        "generation": generation,
        "link_factor": 1.0,
    }
    _initialize_sources(state, row["offers"])
    return state


def _initialize_type(
    candidates: list[dict[str, Any]], spec: dict[str, Any], claimed: set[str], today: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    items_by_key: dict[str, dict[str, Any]] = {}
    for item in candidates:
        row = _base_candidate(item, spec)
        if row is None or row["product_key"] in claimed:
            continue
        rows.append(row)
        items_by_key[row["product_key"]] = item
    rows.sort(key=lambda row: (row["score"], row["offer_count"]), reverse=True)

    selected = rows[: spec["target_skus"]]
    states: list[dict[str, Any]] = []
    observed: list[dict[str, Any]] = []
    for row in selected:
        claimed.add(row["product_key"])
        sku_state = _new_sku_state(row, today)
        states.append(sku_state)
        obs = _row_for_state(items_by_key[row["product_key"]], spec, sku_state)
        if obs is not None:
            sku_state["last_linked_unit_price"] = obs["linked_unit_price"]
            observed.append(obs)

    return {
        "initialized": today,
        "last_observed_date": today,
        "label": spec["label"],
        "group": spec["group"],
        "target_skus": spec["target_skus"],
        "low_coverage_streak": 0,
        "skus": states,
        "candidates": {},
    }, observed


def _update_shadow_candidates(
    state: dict[str, Any], rows: list[dict[str, Any]], active_keys: set[str], claimed: set[str], today: str
) -> dict[str, dict[str, Any]]:
    shadows = state.setdefault("candidates", {})
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    current: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row["product_key"]
        if key in active_keys or key in claimed:
            continue
        previous = shadows.get(key) or {}
        if previous.get("last_seen") == today:
            streak = int(previous.get("seen_streak", 1))
        else:
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


def _observe_type(
    candidates: list[dict[str, Any]],
    spec: dict[str, Any],
    state: dict[str, Any],
    claimed: set[str],
    today: str,
    historical_levels: dict[str, float],
) -> list[dict[str, Any]]:
    new_day = state.get("last_observed_date") != today
    state["last_observed_date"] = today
    for sku in state.get("skus") or []:
        _migrate_sku_state(sku, historical_levels)

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
            sku["missing_streak"] = int(sku.get("missing_streak", 0)) + int(new_day)
            continue
        sku["missing_streak"] = 0
        sku["last_seen"] = today
        sku["last_linked_unit_price"] = row["linked_unit_price"]
        observed.append(row)
        observed_slots.add(row["slot_id"])

    if len(active) < spec["min_skus"]:
        eligible_new = sorted(shadow_rows.values(), key=lambda r: (-r["score"], -r["offer_count"], r["product_key"]))
        for candidate in eligible_new:
            key = candidate["product_key"]
            if len(active) >= spec["target_skus"]:
                break
            if key in claimed or state["candidates"][key]["seen_streak"] < CANDIDATE_MIN_STREAK:
                continue
            sku = _new_sku_state(candidate, today)
            row = _row_for_state(items_by_key[key], spec, sku)
            if row is None:
                continue
            sku["last_linked_unit_price"] = row["linked_unit_price"]
            active.append(sku)
            claimed.add(key)
            observed.append(row)
            observed_slots.add(row["slot_id"])
            state["candidates"].pop(key, None)

    coverage = len(observed_slots) / len(active) if active else 0.0
    state["low_coverage_streak"] = (
        int(state.get("low_coverage_streak", 0)) + int(new_day)
        if active and coverage < LOW_COVERAGE_THRESHOLD else 0
    )
    if int(state.get("low_coverage_streak", 0)) < RENEWAL_AFTER_DAYS:
        return observed

    missing = sorted(
        [sku for sku in active if int(sku.get("missing_streak", 0)) >= RENEWAL_AFTER_DAYS],
        key=lambda sku: int(sku.get("missing_streak", 0)),
        reverse=True,
    )
    eligible = [
        shadow for shadow in state.get("candidates", {}).values()
        if shadow.get("last_seen") == today
        and int(shadow.get("seen_streak", 0)) >= CANDIDATE_MIN_STREAK
        and shadow.get("product_key") in shadow_rows
    ]
    eligible.sort(
        key=lambda row: (float(row.get("score", 0)), int(row.get("offer_count", 0))), reverse=True
    )
    max_replacements = max(1, math.ceil(len(active) * MAX_REPLACEMENT_SHARE)) if active else 0

    replacements = 0
    for old, candidate_meta in zip(missing, eligible):
        if replacements >= max_replacements:
            break
        old_level = old.get("last_linked_unit_price")
        if old_level in (None, ""):
            continue  # Never perform an unbridged substitution.

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
        if replacement_row is None or float(replacement_row["linked_unit_price"]) <= 0:
            continue

        provisional["link_factor"] = float(old_level) / float(replacement_row["linked_unit_price"])
        replacement_row = _row_for_state(item, spec, provisional)
        if replacement_row is None:
            continue

        provisional["previous_product_key"] = old_key
        provisional["replaced_on"] = today
        provisional["last_linked_unit_price"] = replacement_row["linked_unit_price"]
        active[active.index(old)] = provisional
        claimed.discard(old_key)
        claimed.add(new_key)
        state.get("candidates", {}).pop(new_key, None)
        observed.append(replacement_row)
        replacements += 1

    if replacements:
        state["last_renewal"] = today
        state["renewals"] = int(state.get("renewals", 0)) + replacements
    return observed


def collect(refresh: bool = False) -> Path:
    specs = load_product_types()
    panel_state = _load_panel()
    panel_state["version"] = "v0.4"
    panel_state["matching_policy"] = "market-category + all-required-title-rules + unit-price-check"
    panel_state["source_policy"] = "pinned-source-matched-chain"
    panel_state["renewal_policy"] = {
        "low_coverage_threshold": LOW_COVERAGE_THRESHOLD,
        "renewal_after_days": RENEWAL_AFTER_DAYS,
        "candidate_min_streak": CANDIDATE_MIN_STREAK,
        "max_replacement_share": MAX_REPLACEMENT_SHARE,
    }
    types_state = panel_state.setdefault("types", {})
    today = datetime.now(TR_TZ).date().isoformat()
    existing = SNAPSHOT_DIR / f"{today}.csv"
    if existing.exists():
        if not refresh:
            print(f"snapshot={existing.name} already published; preserving daily close")
            return existing
        if existing == min(SNAPSHOT_DIR.glob("*.csv")):
            raise SystemExit("Baseline gününün snapshot'ı yeniden yazılamaz")
        for state in types_state.values():
            state.setdefault("last_observed_date", today)
    historical_levels = _historical_levels()
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
            candidates = search_products(
                spec["query"],
                category_level=spec["api_category_level"],
                category_values=spec["api_categories"],
                session=session,
            )
            state = types_state.get(spec["id"])
            if not state or not state.get("skus"):
                state, observed = _initialize_type(candidates, spec, claimed, today)
                types_state[spec["id"]] = state
            else:
                observed = _observe_type(candidates, spec, state, claimed, today, historical_levels)

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
                    "api_unit_price": row["api_unit_price"],
                    "unit_price_gap_pct": row["unit_price_gap_pct"],
                    "quantity_source": row["quantity_source"],
                    "matched_category": row["matched_category"],
                    "category_level": row["category_level"],
                    "offer_count": row["offer_count"],
                    "raw_offer_count": row["raw_offer_count"],
                    "source_count": row["source_count"],
                    "source_ids": row["source_ids"],
                    "markets": row["markets"],
                    "source_mode": row["source_mode"],
                    "source_updated_at": row["source_updated_at"],
                    "generation": row["generation"],
                    "match_score": row["score"],
                })
        except MarketFiyatiError as exc:
            errors.append({"type_id": spec["id"], "error": str(exc)})

        time.sleep(0.15)

        if number % 20 == 0 or number == len(specs):
            observed_types = len({row["type_id"] for row in output_rows})
            print(f"progress={number}/{len(specs)} skus={len(output_rows)} types={observed_types} errors={len(errors)}")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out = SNAPSHOT_DIR / f"{today}.csv"
    fields = [
        "date", "group", "type_id", "type_label", "slot_id", "product_key", "title",
        "quantity", "unit", "price", "unit_price", "linked_unit_price", "offer_count",
        "api_unit_price", "unit_price_gap_pct", "quantity_source", "matched_category",
        "category_level", "raw_offer_count", "source_count", "source_ids", "markets",
        "source_mode", "source_updated_at", "generation", "match_score",
    ]
    if out.exists():
        revisions = DATA_DIR / "revisions"
        revisions.mkdir(exist_ok=True)
        stamp = datetime.now(TR_TZ).strftime("%Y%m%dT%H%M%S%f")
        (revisions / f"{today}-before-{stamp}.csv").write_bytes(out.read_bytes())
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)

    PANEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    PANEL_PATH.write_text(
        json.dumps(panel_state, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (DATA_DIR / "latest-errors.json").write_text(
        json.dumps({"date": today, "errors": errors}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    panel_skus = sum(len(state.get("skus") or []) for state in types_state.values())
    observed_types = len({row["type_id"] for row in output_rows})
    source_pinned = sum(row.get("source_mode") == "pinned-relative" for row in output_rows)
    renewals = sum(int(state.get("renewals", 0)) for state in types_state.values())
    print(
        f"snapshot={out.relative_to(ROOT)} observed_skus={len(output_rows)} panel_skus={panel_skus} "
        f"observed_types={observed_types}/{len(specs)} source_pinned={source_pinned} "
        f"renewals_total={renewals} errors={len(errors)}"
    )
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Refresh today, archiving its previous snapshot; never rewrite baseline")
    collect(refresh=parser.parse_args().refresh)
