from __future__ import annotations

import csv
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
from .product_types import load_product_types
from .units import parse_quantity, unit_price

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "v0.3"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
PANEL_PATH = ROOT / "state" / "v0.3-panels.json"
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


def _offers(item: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for depot in item.get("productDepotInfoList") or []:
        try:
            price = float(depot.get("price"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(price) and price > 0:
            values.append(price)
    return values


def _candidate_row(item: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any] | None:
    score = _score(item, spec)
    if score < 0.5:
        return None
    title = str(item.get("title") or "").strip()
    quantity = parse_quantity(title, spec["unit"])
    if quantity is None:
        return None
    offers = _offers(item)
    if not offers:
        return None
    price = float(median(offers))
    return {
        "product_key": _product_key(item),
        "title": title,
        "quantity": quantity.amount,
        "unit": quantity.unit,
        "price": round(price, 4),
        "unit_price": round(unit_price(price, quantity), 6),
        "offer_count": len(offers),
        "score": score,
    }


def _load_panel() -> dict[str, Any]:
    if PANEL_PATH.exists():
        return json.loads(PANEL_PATH.read_text(encoding="utf-8"))
    return {"version": "v0.3", "types": {}}


def _initialize_type(candidates: list[dict[str, Any]], spec: dict[str, Any], claimed: set[str], today: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = []
    for item in candidates:
        row = _candidate_row(item, spec)
        if row is None or row["product_key"] in claimed:
            continue
        rows.append(row)
    rows.sort(key=lambda row: (row["score"], row["offer_count"]), reverse=True)
    selected = rows[: spec["target_skus"]]
    for row in selected:
        claimed.add(row["product_key"])
    panel = {
        "initialized": today,
        "label": spec["label"],
        "group": spec["group"],
        "target_skus": spec["target_skus"],
        "skus": [
            {"product_key": row["product_key"], "title": row["title"], "first_quantity": row["quantity"], "unit": row["unit"]}
            for row in selected
        ],
    }
    return panel, selected


def _observe_pinned(candidates: list[dict[str, Any]], spec: dict[str, Any], panel: dict[str, Any]) -> list[dict[str, Any]]:
    wanted = {row["product_key"] for row in panel.get("skus") or []}
    observed: list[dict[str, Any]] = []
    for item in candidates:
        key = _product_key(item)
        if key not in wanted:
            continue
        row = _candidate_row(item, spec)
        if row is not None:
            observed.append(row)
    return observed


def collect() -> Path:
    specs = load_product_types()
    panel_state = _load_panel()
    types_state = panel_state.setdefault("types", {})
    today = datetime.now(TR_TZ).date().isoformat()
    claimed = {
        sku["product_key"]
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
            if spec["id"] not in types_state:
                state, observed = _initialize_type(candidates, spec, claimed, today)
                types_state[spec["id"]] = state
            else:
                observed = _observe_pinned(candidates, spec, types_state[spec["id"]])

            for row in observed:
                output_rows.append({
                    "date": today,
                    "group": spec["group"],
                    "type_id": spec["id"],
                    "type_label": spec["label"],
                    "product_key": row["product_key"],
                    "title": row["title"],
                    "quantity": row["quantity"],
                    "unit": row["unit"],
                    "price": row["price"],
                    "unit_price": row["unit_price"],
                    "offer_count": row["offer_count"],
                })
        except MarketFiyatiError as exc:
            errors.append({"type_id": spec["id"], "error": str(exc)})

        if number % 20 == 0 or number == len(specs):
            observed_types = len({row["type_id"] for row in output_rows})
            print(f"progress={number}/{len(specs)} skus={len(output_rows)} types={observed_types} errors={len(errors)}")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out = SNAPSHOT_DIR / f"{today}.csv"
    fields = ["date", "group", "type_id", "type_label", "product_key", "title", "quantity", "unit", "price", "unit_price", "offer_count"]
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
    print(f"snapshot={out.relative_to(ROOT)} observed_skus={len(output_rows)} panel_skus={panel_skus} observed_types={observed_types}/{len(specs)} errors={len(errors)}")
    return out


if __name__ == "__main__":
    collect()
