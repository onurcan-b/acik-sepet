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

ROOT = Path(__file__).resolve().parents[1]
BASKET_PATH = ROOT / "config" / "basket.json"
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


def _score(item: dict[str, Any], tokens: list[str]) -> float:
    title = _norm(str(item.get("title") or ""))
    normalized = [_norm(token) for token in tokens if _norm(token)]
    if not title or not normalized:
        return 0.0
    return sum(token in title for token in normalized) / len(normalized)


def _select(candidates: list[dict[str, Any]], spec: dict[str, Any], pinned: dict[str, Any] | None) -> dict[str, Any] | None:
    if pinned:
        for candidate in candidates:
            if _product_key(candidate) == pinned.get("product_key"):
                return candidate
            if _norm(str(candidate.get("title") or "")) == _norm(str(pinned.get("title") or "")):
                return candidate
        return None
    scored = [(_score(candidate, spec.get("include_tokens") or []), candidate) for candidate in candidates]
    scored = [row for row in scored if row[0] >= float(spec.get("min_match", 0.5))]
    return max(scored, key=lambda row: row[0])[1] if scored else None


def _offers(item: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for depot in item.get("productDepotInfoList") or []:
        try:
            price = float(depot.get("price"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(price) or price <= 0:
            continue
        row = {"market": depot.get("marketAdi"), "price": round(price, 2)}
        if depot.get("depotId") not in (None, ""):
            row["depot_id"] = str(depot.get("depotId"))
        if depot.get("depotName") not in (None, ""):
            row["depot_name"] = str(depot.get("depotName"))
        rows.append(row)
    return rows


def collect() -> Path:
    basket = json.loads(BASKET_PATH.read_text(encoding="utf-8"))
    product_map = json.loads(MAP_PATH.read_text(encoding="utf-8")) if MAP_PATH.exists() else {}
    today = datetime.now(TR_TZ).date().isoformat()
    snapshot: dict[str, Any] = {
        "date": today,
        "generated_at": datetime.now(TR_TZ).isoformat(timespec="seconds"),
        "source": "https://marketfiyati.org.tr/",
        "items": {},
        "errors": [],
    }

    session = requests.Session()
    for spec in basket:
        try:
            candidates = search_products(spec["query"], session=session)
            selected = _select(candidates, spec, product_map.get(spec["id"]))
            if not selected:
                snapshot["errors"].append({"item": spec["id"], "error": "matching_product_not_found"})
                continue
            offers = _offers(selected)
            if not offers:
                snapshot["errors"].append({"item": spec["id"], "error": "no_valid_offers"})
                continue
            product_map.setdefault(spec["id"], {
                "product_key": _product_key(selected),
                "title": selected.get("title"),
                "first_seen": today,
            })
            snapshot["items"][spec["id"]] = {
                "basket_label": spec["label"],
                "selected_title": selected.get("title"),
                "price_median": round(float(median([offer["price"] for offer in offers])), 2),
                "offers": offers,
            }
        except MarketFiyatiError as exc:
            snapshot["errors"].append({"item": spec["id"], "error": str(exc)})

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out = SNAPSHOT_DIR / f"{today}.json"
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAP_PATH.write_text(json.dumps(product_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"snapshot={out.relative_to(ROOT)} items={len(snapshot['items'])} errors={len(snapshot['errors'])}")
    return out


if __name__ == "__main__":
    collect()
