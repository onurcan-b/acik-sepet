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
FRESH_REJECT_STEMS = {
    "baby",
    "bebek",
    "cips",
    "corba",
    "deterjan",
    "dondurulmus",
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
    "puding",
    "pure",
    "recel",
    "sabun",
    "salca",
    "sampuan",
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


def contains_phrase(title_tokens: tuple[str, ...], phrase: str) -> bool:
    wanted = tuple(norm(phrase).split())
    if not wanted or len(wanted) > len(title_tokens):
        return False
    width = len(wanted)
    return any(title_tokens[i : i + width] == wanted for i in range(len(title_tokens) - width + 1))


def contains_reject_stem(title_tokens: tuple[str, ...], stem: str) -> bool:
    """Reject-context matching may follow Turkish suffixes; commodity matching may not.

    This asymmetry is intentional: `muz` must not match `muzlu`, while reject
    contexts such as `püre` should still reject `püresi` and `cips` should
    reject `cipsi`.
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
    if parse_quantity(title, spec["unit"]) is None:
        return False, "quantity-parse-failed"
    return True, reason


def audit_type(spec: dict[str, Any]) -> dict[str, Any]:
    products = search_products(spec["query"], page_size=50, max_pages=2)
    legacy: list[str] = []
    strict: list[str] = []
    legacy_only: list[dict[str, str]] = []

    for item in products:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        old_ok = legacy_candidate(title, spec)
        new_ok, reason = strict_candidate(title, spec)
        if old_ok:
            legacy.append(title)
        if new_ok:
            strict.append(title)
        if old_ok and not new_ok:
            legacy_only.append({"title": title, "reason": reason})

    return {
        "type_id": spec["id"],
        "label": spec["label"],
        "query": spec["query"],
        "raw_candidates": len(products),
        "legacy_accepts": len(legacy),
        "strict_accepts": len(strict),
        "legacy_only_rejected": legacy_only[:20],
        "strict_examples": strict[:12],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare current substring matching with strict exact-token matching")
    parser.add_argument(
        "--types",
        nargs="*",
        default=["banana", "carrot", "lemon", "zucchini", "tomato", "pear"],
    )
    args = parser.parse_args()

    specs = {spec["id"]: spec for spec in load_product_types()}
    reports = [audit_type(specs[type_id]) for type_id in args.types]
    print(json.dumps({"matcher": "strict-exact-token-v0", "reports": reports}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
