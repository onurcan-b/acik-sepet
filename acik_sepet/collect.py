from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .api import MarketFiyatiError, search_products
from .basket import load_basket

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "state" / "product-map.json"
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
TR_TZ = ZoneInfo("Europe/Istanbul")


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


def _candidate_score(item: dict[str, Any], spec: dict[str, Any]) -> float:
    title = _norm(str(item.get("title") or ""))
    if not title:
        return -1.0

    exclude = [_norm(token) for token in spec.get("exclude_tokens") or [] if _norm(token)]
    if any(token in title for token in exclude):
        return -1.0

    include = [_norm(token) for token in spec.get("include_tokens") or [] if _norm(token)]
    base = 0.0 if not include else sum(token in title for token in include) / len(include)

    preferred = [_norm(token) for token in spec.get("preferred_tokens") or [] if _norm(token)]
    bonus = 0.08 * sum(token in title for token in preferred)
    return base + bonus


def _select_product(
    candidates: list[dict[str, Any]],
    spec: dict[str, Any],
    pinned: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if pinned:
        pinned_key = pinned.get("product_key")
        pinned_title = _norm(str(pinned.get("title") or ""))
        for candidate in candidates:
            if pinned_key and _product_key(candidate) == pinned_key:
                return candidate
            if pinned_title and _norm(str(candidate.get("title") or "")) == pinned_title:
                return candidate
        return None

    scored = [(_candidate_score(candidate, spec), candidate) for candidate in candidates]
    scored = [row for row in scored if row[0] >= float(spec.get("min_match", 0.5))]
    if not scored:
        return None
    scored.sort(key=lambda row: (row[0], len(str(row[1].get("title") or ""))), reverse=True)
    return scored[0][1]


def _offers(item: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for depot in item.get("productDepotInfoList") or []:
        try:
            price = float(depot.get("price"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(price) or price <= 0:
            continue

        market = str(depot.get("marketAdi") or "").strip()
        depot_id = str(depot.get("depotId") or "").strip()
        key = (market, depot_id)
        if key in seen:
            continue
        seen.add(key)

        row: dict[str, Any] = {"market": market or None, "price": round(price, 2)}
        if depot_id:
            row["depot_id"] = depot_id
        depot_name = str(depot.get("depotName") or "").strip()
        if depot_name:
            row["depot_name"] = depot_name
        rows.append(row)
    return rows


def _keep_stable_sources(offers: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    pinned = set(state.get("source_ids") or [])
    if pinned:
        return [row for row in offers if row.get("depot_id") in pinned]

    found = sorted({row["depot_id"] for row in offers if row.get("depot_id")})
    if found:
        state["source_ids"] = found
    return offers


def collect() -> Path:
    basket = load_basket()
    product_map = json.loads(MAP_PATH.read_text(encoding="utf-8")) if MAP_PATH.exists() else {}
    today = datetime.now(TR_TZ).date().isoformat()

    snapshot: dict[str, Any] = {
        "schema_version": 2,
        "basket_version": "v0.2-150",
        "date": today,
        "generated_at": datetime.now(TR_TZ).isoformat(timespec="seconds"),
        "source": "https://marketfiyati.org.tr/",
        "target_items": len(basket),
        "items": {},
        "errors": [],
    }

    session = requests.Session()
    for number, spec in enumerate(basket, start=1):
        try:
            candidates = search_products(spec["query"], session=session)
            state = product_map.get(spec["id"])
            selected = _select_product(candidates, spec, state)
            if not selected:
                snapshot["errors"].append({"item": spec["id"], "group": spec["group"], "error": "matching_product_not_found"})
                continue

            offers = _offers(selected)
            if not offers:
                snapshot["errors"].append({"item": spec["id"], "group": spec["group"], "error": "no_valid_offers"})
                continue

            state = product_map.setdefault(spec["id"], {
                "product_key": _product_key(selected),
                "title": selected.get("title"),
                "first_seen": today,
                "group": spec["group"],
            })
            stable_offers = _keep_stable_sources(offers, state)
            if not stable_offers:
                snapshot["errors"].append({"item": spec["id"], "group": spec["group"], "error": "stable_source_not_found"})
                continue

            snapshot["items"][spec["id"]] = {
                "group": spec["group"],
                "basket_label": spec["label"],
                "selected_title": selected.get("title"),
                "product_key": _product_key(selected),
                "price_median": round(float(median([offer["price"] for offer in stable_offers])), 2),
                "offers": stable_offers,
            }
        except MarketFiyatiError as exc:
            snapshot["errors"].append({"item": spec["id"], "group": spec["group"], "error": str(exc)})

        if number % 25 == 0:
            print(f"progress={number}/{len(basket)} matched={len(snapshot['items'])} errors={len(snapshot['errors'])}")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out = SNAPSHOT_DIR / f"{today}.json"
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAP_PATH.write_text(json.dumps(product_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    coverage = len(snapshot["items"]) / max(1, len(basket))
    print(
        f"snapshot={out.relative_to(ROOT)} items={len(snapshot['items'])}/{len(basket)} "
        f"coverage={coverage:.1%} errors={len(snapshot['errors'])}"
    )
    return out


if __name__ == "__main__":
    collect()
