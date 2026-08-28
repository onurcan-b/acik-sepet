from __future__ import annotations

import argparse
import json
import re
import unicodedata
from typing import Any

from .api import search_products
from .product_types import load_product_types
from .units import parse_quantity

FRESH_GROUPS = {"fruit", "vegetables"}
FRESH_MIN_MASS_KG = 0.25

# Experiment only: broaden candidate discovery without weakening eligibility.
EXPANDED_QUERIES: dict[str, list[str]] = {
    "banana": ["yerli muz", "ithal muz", "muz 1 kg", "muz paket"],
    "carrot": ["havuç paket", "taze havuç", "havuç 1 kg"],
    "lemon": ["taze limon", "lamas limon", "limon 1 kg"],
    "zucchini": ["sakız kabak", "dolmalık kabak", "kabak 1 kg"],
    "tomato": ["domates 1 kg", "salkım domates", "kokteyl domates"],
    "pear": ["deveci armut", "santa maria armut", "armut 1 kg", "naşi armut"],
}

FRESH_REJECT_STEMS = {
    "baby",
    "bebek",
    "cips",
    "corba",
    "deterjan",
    "dogranmis",
    "dondurulmus",
    "dolgulu",
    "gofret",
    "hazir",
    "icecek",
    "karisim",
    "kek",
    "konserve",
    "kremali",
    "kurutulmus",
    "mucver",
    "pril",
    "protein",
    "puding",
    "pure",
    "recel",
    "rende",
    "sabun",
    "salca",
    "sampuan",
    "seker",
    "sos",
    "suyu",
    "tarator",
    "temizleyici",
    "toz",
    "yogurtlu",
    # Turkish consonant softening: çekirdek -> çekirdeği.
    "cekirdeg",
}


def norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower().replace("ı", "i")).strip()


def tokens(value: str | None) -> tuple[str, ...]:
    return tuple(norm(value).split())


def product_key(item: dict[str, Any]) -> str:
    for field in ("id", "productId", "product_id", "barcode"):
        value = item.get(field)
        if value not in (None, ""):
            return f"{field}:{value}"
    return f"title:{norm(str(item.get('title') or ''))}"


def contains_phrase(title_tokens: tuple[str, ...], phrase: str) -> bool:
    wanted = tuple(norm(phrase).split())
    if not wanted or len(wanted) > len(title_tokens):
        return False
    width = len(wanted)
    return any(title_tokens[i : i + width] == wanted for i in range(len(title_tokens) - width + 1))


def contains_reject_stem(title_tokens: tuple[str, ...], stem: str) -> bool:
    """Reject context may follow Turkish suffixes; commodity matching may not.

    `muz` must not match `muzlu`, while reject contexts such as `püre` should
    still reject `püresi` and `cips` should reject `cipsi`.
    """
    normalized = norm(stem)
    if not normalized:
        return False
    if " " in normalized:
        return contains_phrase(title_tokens, normalized)
    if len(normalized) < 4:
        return normalized in title_tokens
    return any(token.startswith(normalized) for token in title_tokens)


def legacy_score(title: str, spec: dict[str, Any]) -> float:
    normalized = norm(title)
    if not normalized:
        return -1.0
    excludes = [norm(token) for token in spec.get("exclude_tokens") or []]
    if any(token and token in normalized for token in excludes):
        return -1.0
    includes = [norm(token) for token in spec.get("include_tokens") or []]
    if not includes:
        return 1.0
    return sum(token in normalized for token in includes) / len(includes)


def strict_decision(title: str, spec: dict[str, Any]) -> tuple[bool, str, float]:
    title_tokens = tokens(title)
    if not title_tokens:
        return False, "empty-title", -1.0

    for phrase in spec.get("exclude_tokens") or []:
        if contains_reject_stem(title_tokens, phrase):
            return False, f"excluded:{norm(phrase)}", -1.0

    includes = list(spec.get("include_tokens") or [])
    matched = [phrase for phrase in includes if contains_phrase(title_tokens, phrase)]
    score = 1.0 if not includes else len(matched) / len(includes)

    if spec.get("group") in FRESH_GROUPS:
        if includes and len(matched) != len(includes):
            return False, "fresh-missing-required-exact-token", score
        for stem in FRESH_REJECT_STEMS:
            if contains_reject_stem(title_tokens, stem):
                return False, f"fresh-context:{stem}", score
        return True, "fresh-exact-match", score

    if score < 0.5:
        return False, "insufficient-exact-token-score", score
    return True, "exact-token-match", score


def legacy_candidate(title: str, spec: dict[str, Any]) -> bool:
    return legacy_score(title, spec) >= 0.5 and parse_quantity(title, spec["unit"]) is not None


def strict_candidate(title: str, spec: dict[str, Any]) -> tuple[bool, str]:
    accepted, reason, _ = strict_decision(title, spec)
    if not accepted:
        return False, reason
    quantity = parse_quantity(title, spec["unit"])
    if quantity is None:
        return False, "quantity-parse-failed"
    if spec.get("group") in FRESH_GROUPS and quantity.unit == "kg" and quantity.amount < FRESH_MIN_MASS_KG:
        return False, f"fresh-too-small:{quantity.amount:g}kg"
    return True, reason


def expanded_pool(spec: dict[str, Any], base_products: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    output = list(base_products)
    seen = {product_key(item) for item in output}
    queries = EXPANDED_QUERIES.get(spec["id"], [])
    for query in queries:
        for item in search_products(query, page_size=50, max_pages=1):
            key = product_key(item)
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(item)
    return output, queries


def strict_titles(products: list[dict[str, Any]], spec: dict[str, Any]) -> list[str]:
    accepted: list[str] = []
    for item in products:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        ok, _ = strict_candidate(title, spec)
        if ok:
            accepted.append(title)
    return accepted


def audit_type(spec: dict[str, Any]) -> dict[str, Any]:
    base_products = search_products(spec["query"], page_size=50, max_pages=2)
    expanded_products, extra_queries = expanded_pool(spec, base_products)

    legacy: list[str] = []
    strict_single: list[str] = []
    legacy_only: list[dict[str, str]] = []

    for item in base_products:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        old_ok = legacy_candidate(title, spec)
        new_ok, reason = strict_candidate(title, spec)
        if old_ok:
            legacy.append(title)
        if new_ok:
            strict_single.append(title)
        if old_ok and not new_ok:
            legacy_only.append({"title": title, "reason": reason})

    strict_expanded = strict_titles(expanded_products, spec)
    added_by_expansion = [title for title in strict_expanded if title not in set(strict_single)]

    return {
        "type_id": spec["id"],
        "label": spec["label"],
        "base_query": spec["query"],
        "extra_queries": extra_queries,
        "base_raw_candidates": len(base_products),
        "expanded_raw_candidates": len(expanded_products),
        "legacy_accepts": len(legacy),
        "strict_single_accepts": len(strict_single),
        "strict_expanded_accepts": len(strict_expanded),
        "legacy_only_rejected": legacy_only[:20],
        "strict_expanded_examples": strict_expanded[:20],
        "added_by_expansion": added_by_expansion[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare substring matching with strict matching and expanded discovery")
    parser.add_argument(
        "--types",
        nargs="*",
        default=["banana", "carrot", "lemon", "zucchini", "tomato", "pear"],
    )
    args = parser.parse_args()

    specs = {spec["id"]: spec for spec in load_product_types()}
    reports = [audit_type(specs[type_id]) for type_id in args.types]
    print(json.dumps({"matcher": "strict-exact-token-v2", "reports": reports}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
