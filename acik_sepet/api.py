from __future__ import annotations

import random
import time
from typing import Any

import requests

API_URL = "https://api.marketfiyati.org.tr/api/v2/search"
CATEGORIES_URL = "https://api.marketfiyati.org.tr/api/v3/info/categories"
CATEGORY_FIELDS = {"menu_category", "main_category", "sub_category"}

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://marketfiyati.org.tr",
    "Referer": "https://marketfiyati.org.tr/",
    "Connection": "close",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}


class MarketFiyatiError(RuntimeError):
    pass


def _fetch_page(
    client: requests.Session,
    keywords: str,
    page: int,
    size: int,
    timeout: int,
    attempts: int,
    category_level: str | None,
    category_values: list[str] | None,
) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    payload = {"keywords": keywords, "pages": page, "size": size}
    if category_level:
        if category_level not in CATEGORY_FIELDS:
            raise ValueError(f"unknown Market Fiyatı category field: {category_level}")
        if not category_values:
            raise ValueError("category_values cannot be empty when category_level is set")
        payload[category_level] = category_values
    for attempt in range(1, attempts + 1):
        try:
            response = client.post(API_URL, headers=HEADERS, json=payload, timeout=timeout)
            if response.status_code == 418:
                raise MarketFiyatiError("Market Fiyatı bot koruması HTTP 418 döndürdü")
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict) or "content" not in body:
                raise MarketFiyatiError("Beklenmeyen API yanıtı: content yok")
            content = body["content"]
            if not isinstance(content, list):
                raise MarketFiyatiError("Beklenmeyen API yanıtı: content liste değil")
            return content
        except (requests.RequestException, ValueError, MarketFiyatiError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep((2 ** (attempt - 1)) + random.uniform(0.2, 0.8))
    raise MarketFiyatiError(f"{keywords!r} sayfa {page} başarısız: {last_error}")


def search_products(
    keywords: str,
    *,
    category_level: str | None = None,
    category_values: list[str] | None = None,
    page_size: int = 25,
    max_pages: int = 8,
    timeout: int = 30,
    attempts: int = 3,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Return a deduplicated, category-filtered pool for one product type.

    Market Fiyatı's own category filter narrows the pool first. The collector
    still verifies every returned product locally; API taxonomy is evidence,
    not an instruction to accept the product blindly.
    """
    client = session or requests.Session()
    output: list[dict[str, Any]] = []
    seen: set[str] = set()

    for page in range(max_pages):
        content = _fetch_page(
            client,
            keywords,
            page,
            page_size,
            timeout,
            attempts,
            category_level,
            category_values,
        )
        new_count = 0
        for item in content:
            item = dict(item)
            if category_level and category_values:
                # Keep provenance of the server-side filter. Market Fiyatı's
                # free-form categories[] does not consistently echo the
                # canonical sub-category label used by the search endpoint.
                item["_query_category_level"] = category_level
                item["_query_category_values"] = list(category_values)
            key = str(item.get("id") or item.get("productId") or item.get("product_id") or item.get("barcode") or item.get("title") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(item)
            new_count += 1
        if len(content) < page_size or new_count == 0:
            break
        time.sleep(random.uniform(0.05, 0.15))
    return output

