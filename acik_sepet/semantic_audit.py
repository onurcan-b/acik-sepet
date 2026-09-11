from __future__ import annotations

import argparse
import csv
import json
import unicodedata
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .collect import _title_matches
from .product_types import load_product_types

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "data" / "v0.4" / "snapshots"
RULES_PATH = ROOT / "config" / "semantic_audit.json"
OUTPUT_JSON = ROOT / "data" / "v0.4" / "semantic-audit.json"
OUTPUT_MD = ROOT / "data" / "v0.4" / "semantic-audit.md"


def _norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower().replace("ı", "i")).strip()


def _contains_pattern(title: str, pattern: str) -> bool:
    wanted = _norm(pattern)
    actual = _norm(title)
    return bool(wanted and wanted in actual)


def _latest_snapshot() -> Path:
    paths = sorted(SNAPSHOT_DIR.glob("*.csv"))
    if not paths:
        raise SystemExit("v0.4 snapshot bulunamadı")
    return paths[-1]


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_rules() -> dict[str, Any]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def audit_rows(
    rows: list[dict[str, str]],
    specs: list[dict[str, Any]] | None = None,
    rule_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    specs = specs or load_product_types()
    rule_config = rule_config or _load_rules()
    spec_by_id = {spec["id"]: spec for spec in specs}
    rules_by_type: dict[str, list[dict[str, Any]]] = {}
    for rule in rule_config.get("rules", []):
        rules_by_type.setdefault(str(rule["type_id"]), []).append(rule)

    group_specs: dict[str, list[dict[str, Any]]] = {}
    for spec in specs:
        group_specs.setdefault(str(spec["group"]), []).append(spec)

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add(finding: dict[str, Any], discriminator: str) -> None:
        key = (
            str(finding.get("kind") or ""),
            str(finding.get("type_id") or ""),
            str(finding.get("product_key") or ""),
            discriminator,
        )
        if key not in seen:
            seen.add(key)
            findings.append(finding)

    for row in rows:
        type_id = str(row.get("type_id") or "")
        title = str(row.get("title") or "")
        product_key = str(row.get("product_key") or "")
        slot_id = str(row.get("slot_id") or product_key)
        current_spec = spec_by_id.get(type_id)

        for rule in rules_by_type.get(type_id, []):
            matched = [p for p in rule.get("patterns", []) if _contains_pattern(title, str(p))]
            if not matched:
                continue
            add(
                {
                    "kind": "curated_rule",
                    "severity": str(rule.get("severity") or "review"),
                    "rule_id": str(rule.get("id") or ""),
                    "type_id": type_id,
                    "type_label": row.get("type_label", ""),
                    "product_key": product_key,
                    "slot_id": slot_id,
                    "title": title,
                    "matched_patterns": matched,
                    "reason": str(rule.get("reason") or ""),
                    "suggestion": str(rule.get("suggestion") or ""),
                },
                str(rule.get("id") or ""),
            )

        if current_spec is not None:
            overlaps = [
                spec["id"]
                for spec in group_specs.get(str(current_spec["group"]), [])
                if spec["id"] != type_id and _title_matches(title, spec)
            ]
            if overlaps:
                add(
                    {
                        "kind": "same_group_title_overlap",
                        "severity": "review",
                        "type_id": type_id,
                        "type_label": row.get("type_label", ""),
                        "product_key": product_key,
                        "slot_id": slot_id,
                        "title": title,
                        "overlaps_with": sorted(overlaps),
                        "reason": "The title satisfies the hard title rules of another product type in the same group. API categories may still disambiguate it, so this is review-only.",
                    },
                    ",".join(sorted(overlaps)),
                )

        try:
            generation = int(row.get("generation") or 0)
        except (TypeError, ValueError):
            generation = 0
        if generation > 0:
            add(
                {
                    "kind": "bridged_replacement",
                    "severity": "review",
                    "type_id": type_id,
                    "type_label": row.get("type_label", ""),
                    "product_key": product_key,
                    "slot_id": slot_id,
                    "title": title,
                    "generation": generation,
                    "reason": "This slot has been bridged to a replacement SKU. The price link is mathematically continuous, but semantic equivalence deserves manual review.",
                },
                str(generation),
            )

    severity_order = {"high": 0, "medium": 1, "review": 2}
    findings.sort(
        key=lambda item: (
            severity_order.get(str(item.get("severity")), 9),
            str(item.get("type_id")),
            str(item.get("kind")),
            str(item.get("title")),
        )
    )
    return findings


def _summary(snapshot: Path, rows: list[dict[str, str]], findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_severity = Counter(str(item.get("severity") or "review") for item in findings)
    by_kind = Counter(str(item.get("kind") or "unknown") for item in findings)
    by_type = Counter(str(item.get("type_id") or "unknown") for item in findings)
    affected_products = {str(item.get("product_key") or "") for item in findings if item.get("product_key")}
    return {
        "version": "v0.4",
        "mode": "review-only",
        "snapshot": snapshot.name,
        "rows": len(rows),
        "findings": len(findings),
        "affected_products": len(affected_products),
        "by_severity": dict(sorted(by_severity.items())),
        "by_kind": dict(sorted(by_kind.items())),
        "by_type": dict(sorted(by_type.items(), key=lambda item: (-item[1], item[0]))),
        "items": findings,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Semantic audit — {report['snapshot'].removesuffix('.csv')}",
        "",
        "> Review-only: this audit does **not** change matching, panel membership, indices, charts, or the README diagram.",
        "",
        f"- Snapshot rows: **{report['rows']}**",
        f"- Findings: **{report['findings']}** across **{report['affected_products']}** products",
        f"- Severity: `{report['by_severity']}`",
        f"- Kinds: `{report['by_kind']}`",
        "",
        "## Findings",
        "",
        "| Severity | Type | Kind | Product | Why |",
        "|---|---|---|---|---|",
    ]
    for item in report["items"]:
        why = str(item.get("reason") or "").replace("|", "/")
        title = str(item.get("title") or "").replace("|", "/")
        lines.append(
            f"| {item.get('severity', '')} | {item.get('type_id', '')} | {item.get('kind', '')} | {title} | {why} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "A finding is not automatically a bad row. `high` means the current semantic scope is likely inconsistent; `review` means the row is economically heterogeneous, overlaps a sibling title rule, or came through a bridged replacement and should be inspected before tightening production matching.",
            "",
        ]
    )
    return "\n".join(lines)


def run(snapshot: Path | None = None, fail_on_high: bool = False) -> dict[str, Any]:
    snapshot = snapshot or _latest_snapshot()
    rows = _load_rows(snapshot)
    findings = audit_rows(rows)
    report = _summary(snapshot, rows, findings)
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(_markdown(report), encoding="utf-8")
    print(
        f"semantic_audit snapshot={snapshot.name} rows={len(rows)} findings={report['findings']} "
        f"affected_products={report['affected_products']} severity={report['by_severity']}"
    )
    if fail_on_high and int(report["by_severity"].get("high", 0)) > 0:
        raise SystemExit("High-severity semantic audit findings exist")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--fail-on-high", action="store_true")
    args = parser.parse_args()
    run(args.snapshot, args.fail_on_high)


if __name__ == "__main__":
    main()
