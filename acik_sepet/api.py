from __future__ import annotations

import math
import random
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests

API_URL = "https://api.marketfiyati.org.tr/api/v2/search"
CATEGORIES_URL = "https://api.marketfiyati.org.tr/api/v3/info/categories"
CATEGORY_FIELDS = {"menu_category", "main_category", "sub_category"}
REQUEST_INTERVAL_SECONDS = 1.25
MAX_PAGE_RETRY_WAIT_SECONDS = 30.0

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://marketfiyati.org.tr",
    "Referer": "https://marketfiyati.org.tr/",
    # Use requests' normal connection pool instead of opening a TCP/TLS
    # connection for every page. Pacing still applies to every HTTP request.
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}


class MarketFiyatiError(RuntimeError):
    def __init__(
        self, message: str, *, retryable: bool = True, retry_after: float | None = None,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            deadline = parsedate_to_datetime(value)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            seconds = deadline.timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


def _defer_request(client: requests.Session, delay: float) -> None:
    client._marketfiyati_next_request_at = max(
        getattr(client, "_marketfiyati_next_request_at", 0.0),
        time.monotonic() + delay,
    )


def _pace_request(client: requests.Session) -> None:
    delay = getattr(client, "_marketfiyati_next_request_at", 0.0) - time.monotonic()
    if delay > MAX_PAGE_RETRY_WAIT_SECONDS:
        # The collector owns long cooldowns and the overall run budget.
        # Do not issue another query during a server-requested cooldown.
        raise MarketFiyatiError("API yeniden deneme süresi bekleniyor", retry_after=delay)
    if delay > 0:
        time.sleep(delay)
    _defer_request(client, REQUEST_INTERVAL_SECONDS)


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
    payload = {"keywords": keywords, "pages": page, "size": size}
    if category_level:
        if category_level not in CATEGORY_FIELDS:
            raise ValueError(f"unknown Market Fiyatı category field: {category_level}")
        if not category_values:
            raise ValueError("category_values cannot be empty when category_level is set")
        payload[category_level] = category_values
    for attempt in range(1, attempts + 1):
        try:
            _pace_request(client)
            response = client.post(API_URL, headers=HEADERS, json=payload, timeout=timeout)
            status = response.status_code
            if status >= 400:
                retryable = status == 429 or 500 <= status < 600
                retry_after = _retry_after_seconds(getattr(response, "headers", {}).get("Retry-After"))
                raise MarketFiyatiError(
                    f"Market Fiyatı HTTP {status} döndürdü",
                    retryable=retryable,
                    retry_after=retry_after,
                )
            try:
                body = response.json()
            except ValueError as exc:
                raise MarketFiyatiError("Beklenmeyen API yanıtı: geçersiz JSON", retryable=False) from exc
            if not isinstance(body, dict) or "content" not in body:
                raise MarketFiyatiError("Beklenmeyen API yanıtı: content yok", retryable=False)
            content = body["content"]
            if not isinstance(content, list) or any(not isinstance(item, dict) for item in content):
                raise MarketFiyatiError("Beklenmeyen API yanıtı: content ürün listesi değil", retryable=False)
            return content
        except MarketFiyatiError as exc:
            error = exc
        except requests.RequestException as exc:
            retryable = isinstance(exc, (
                requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError,
            )) and not isinstance(exc, requests.exceptions.SSLError)
            error = MarketFiyatiError(str(exc), retryable=retryable)

        if error.retry_after is not None:
            _defer_request(client, error.retry_after)
        if not error.retryable or attempt == attempts or (error.retry_after or 0) > MAX_PAGE_RETRY_WAIT_SECONDS:
            raise MarketFiyatiError(
                f"{keywords!r} sayfa {page} başarısız: {error}",
                retryable=error.retryable,
                retry_after=error.retry_after,
            ) from error
        _defer_request(client, max(
            (2 ** (attempt - 1)) + random.uniform(0.2, 0.8),
            error.retry_after or 0.0,
        ))
    raise ValueError("attempts must be positive")


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
    """Return a complete, deduplicated, category-filtered pool for one type.

    A failed page raises instead of returning earlier pages as a partial pool.
    Reusing a session shares request pacing across product types as well as
    pages. Long Retry-After waits are handed to the collector via the error.
    """
    if attempts < 1:
        raise ValueError("attempts must be positive")
    client = session if session is not None else requests.Session()
    output: list[dict[str, Any]] = []
    seen: set[str] = set()

    try:
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
        return output
    finally:
        if session is None:
            client.close()
