from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Quantity:
    amount: float
    unit: str


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().replace("ı", "i").replace(",", ".")


def _convert(value: float, unit: str) -> Quantity | None:
    unit = unit.lower()
    if unit in {"kg", "kilogram"}:
        return Quantity(value, "kg")
    if unit in {"g", "gr", "gram"}:
        return Quantity(value / 1000.0, "kg")
    if unit in {"l", "lt", "litre", "liter"}:
        return Quantity(value, "l")
    if unit in {"ml", "mililitre", "mililiter"}:
        return Quantity(value / 1000.0, "l")
    return None


def parse_quantity(title: str, expected: str) -> Quantity | None:
    """Parse package size into kg, litre or count.

    The parser intentionally prefers explicit multipacks, then the first explicit
    quantity. It also handles common Turkish count forms such as 12'li / 10 adet.
    """
    text = _norm(title)

    if expected in {"mass", "volume"}:
        pattern = r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(kg|kilogram|g|gr|gram|ml|mililitre|mililiter|l|lt|litre|liter)\b"
        match = re.search(pattern, text)
        if match:
            count = float(match.group(1))
            each = _convert(float(match.group(2)), match.group(3))
            if each and ((expected == "mass" and each.unit == "kg") or (expected == "volume" and each.unit == "l")):
                return Quantity(count * each.amount, each.unit)

        pattern = r"(\d+(?:\.\d+)?)\s*(kg|kilogram|g|gr|gram|ml|mililitre|mililiter|l|lt|litre|liter)\b"
        for match in re.finditer(pattern, text):
            parsed = _convert(float(match.group(1)), match.group(2))
            if parsed and ((expected == "mass" and parsed.unit == "kg") or (expected == "volume" and parsed.unit == "l")):
                return parsed

        if expected == "mass" and re.search(r"\bkg\b", text):
            return Quantity(1.0, "kg")
        if expected == "volume" and re.search(r"\b(?:l|lt|litre|liter)\b", text):
            return Quantity(1.0, "l")
        return None

    if expected == "count":
        multipack = re.search(r"(\d+)\s*[x×]\s*(\d+)\s*(?:adet|ad\.?|li|lu|lu|li)\b", text)
        if multipack:
            return Quantity(float(int(multipack.group(1)) * int(multipack.group(2))), "count")

        patterns = [
            r"(\d+)\s*(?:adet|ad\.?)\b",
            r"(\d+)\s*['’]?\s*(?:li|lu|lu|li)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return Quantity(float(match.group(1)), "count")
        if re.search(r"\badet\b", text):
            return Quantity(1.0, "count")
        return None

    raise ValueError(f"unknown expected unit: {expected}")


def unit_price(price: float, quantity: Quantity) -> float:
    if price <= 0 or quantity.amount <= 0:
        raise ValueError("price and quantity must be positive")
    return price / quantity.amount
