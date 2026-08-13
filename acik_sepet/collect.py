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

from .api import Location, MarketFiyatiError, search_products

ROOT = Path(__file__).resolve().parents[1]
BASKET_PATH = ROOT / "config" / "basket.json"
LOCATIONS_PATH = ROOT / "config" / "locations.json"
MAP_PATH = ROOT / "state" / "product-map.json"
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
TR_TZ = ZoneInfo("Europe/Istanbul")


def _norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("ı", "i")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _candidate_score(item: dict[str, Any], include_tokens: list[str]) -> float:
    title = _norm(str(item.get("title") or ""))
    if not title:
        return -1.0
    tokens = [_norm(token) for token in include_tokens if _norm(token)]
    if not tokens:
        return 0.0
    hits = sum(1 for token in tokens if token in title)
    return hits / len(tokens)


def _product_key(item: dict[str, Any]) -> str:
    for field in ("id", "productId", "product_id", "barcode"):
        value = item.get(field)
        if value not in (None, ""):
            return f"{field}:{value}"
    return f"title:{_norm(str(item.get('title') or ''))}"


def _select_product(
    candidates: list[dict[str, Any]],
    basket_item: dict[str, Any],
    pinned: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if pinned:
        pinned_key = pinned.get("product_key")
        pinned_title = _norm(pinned.get("title"))
        for item in candidates:
            if pinned_key and _product_key(item) == pinned_key:
                return item
            if pinned_title and _norm(str(item.get("title") or "")) == pinned_title:
                return item
        return None

    scored = [
        (_candidate_score(item, basket_item.get("include_tokens") or []), item)
        for item in candidates
    ]
    scored = [pair for pair in scored if pair[0] >= float(basket_item.get("min_match", 0.66))]
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1]


def _offers(item: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for depot in item.get("productDepotInfoList") or []:
        try:
            price = float(depot.get("price"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(price) or price <= 0:
            continue
        row = {
            "market": depot.get("marketAdi"),
            "price": round(price, 2),
        }
        if depot.get("depotId") not in (None, ""):
            row["depot_id"] = str(depot.get("depotId"))
        if depot.get("depotName") not in (None, ""):
            row["depot_name"] = str(depot.get("depotName"))
        output.append(row)
    return output


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def collect() -> Path:
    basket = _load_json(BASKET_PATH, [])
    locations_raw = _load_json(LOCATIONS_PATH, [])
    product_map: dict[str, Any] = _load_json(MAP_PATH, {})
    locations = [Location(**row) for row in locations_raw]
    today = datetime.now(TR_TZ).date().isoformat()
    generated_at = datetime.now(TR_TZ).isoformat(timespec="seconds")

    snapshot: dict[str, Any] = {
        "date": today,
        "generated_at": generated_at,
        "source": "https://marketfiyati.org.tr/",
        "locations": {},
        "errors": [],
    }

    session = requests.Session()
    for location in locations:
        location_rows: dict[str, Any] = {}
        for item in basket:
            mapping_key = f"{location.id}:{item['id']}"
            try:
                candidates = search_products(item["query"], location, session=session)
                selected = _select_product(candidates, item, product_map.get(mapping_key))
                if not selected:
                    snapshot["errors"].append({
                        "location": location.id,
                        "item": item["id"],
                        "error": "pinned_or_matching_product_not_found",
                    })
                    continue
                offers = _offers(selected)
                if not offers:
                    snapshot["errors"].append({
                        "location": location.id,
                        "item": item["id"],
                        "error": "no_valid_offers",
                    })
                    continue

                product_map.setdefault(mapping_key, {
                    "product_key": _product_key(selected),
                    "title": selected.get("title"),
                    "first_seen": today,
                })
                prices = [offer["price"] for offer in offers]
                location_rows[item["id"]] = {
                    "basket_label": item["label"],
                    "selected_title": selected.get("title"),
                    "price_median": round(float(median(prices)), 2),
                    "offers": offers,
                }
            except MarketFiyatiError as exc:
                snapshot["errors"].append({
                    "location": location.id,
                    "item": item["id"],
                    "error": str(exc),
                })
        snapshot["locations"][location.id] = {
            "name": location.name,
            "items": location_rows,
        }

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out = SNAPSHOT_DIR / f"{today}.json"
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAP_PATH.write_text(json.dumps(product_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"snapshot={out.relative_to(ROOT)} errors={len(snapshot['errors'])}")
    return out


if __name__ == "__main__":
    collect()
