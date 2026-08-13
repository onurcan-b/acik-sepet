from __future__ import annotations

from typing import Any


def keep_same_sources(rows: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep observations tied to the same source IDs across collection dates."""
    saved = set(state.get("source_ids") or [])
    if saved:
        return [row for row in rows if row.get("depot_id") in saved]
    found = sorted({row["depot_id"] for row in rows if row.get("depot_id")})
    if found:
        state["source_ids"] = found
    return rows
