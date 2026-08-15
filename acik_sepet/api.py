from __future__ import annotations

import random
import time
from typing import Any

import requests

API_URL = "https://api.marketfiyati.org.tr/api/v2/search"

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


def _fetch_page(client: requests.Session, keywords: str, page: int, size: int, timeout: int, attempts: int) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    payload = {"keywords": keywords, "pages": page, "size": size}
    for attempt in range(1, attempts + 1):
        try:
            response = client.post(API_URL, headers=HEADERS, json=payload, timeout=timeout)
            if response.status_code == 418:
                raise MarketFiyatiError("Market Fiyatı bot koruması HTTP 418 döndürdü")
            response.raise_for_status()
            body = response.json()
            content = body.get("content") or []
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
    page_size: int = 50,
    max_pages: int = 2,
    timeout: int = 30,
    attempts: int = 3,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Return a deduplicated search pool for one product type.

    v0.3 makes one paginated search per product type, then builds a fixed SKU
    panel locally. This keeps request volume proportional to product types,
    not to the thousands of SKUs observed inside those types.
    """
    client = session or requests.Session()
    output: list[dict[str, Any]] = []
    seen: set[str] = set()

    for page in range(max_pages):
        content = _fetch_page(client, keywords, page, page_size, timeout, attempts)
        new_count = 0
        for item in content:
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
