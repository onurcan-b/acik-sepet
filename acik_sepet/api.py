from __future__ import annotations

import random
import time
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Location:
    id: str
    name: str
    latitude: float
    longitude: float
    distance_km: float = 5.0


def search_products(
    keywords: str,
    location: Location,
    *,
    size: int = 24,
    timeout: int = 30,
    attempts: int = 3,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Search Market Fiyatı for a small, fixed MVP basket.

    This deliberately uses low request volume. It is not a bulk mirror.
    """
    client = session or requests.Session()
    payload = {
        "keywords": keywords,
        "pages": 0,
        "size": size,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "distance": location.distance_km,
    }

    last_error: Exception | None = None
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

    raise MarketFiyatiError(f"{keywords!r} sorgusu başarısız: {last_error}")
