from __future__ import annotations

from copy import deepcopy
from typing import Any

from .ticker_symbols import canonical_ticker_key, display_ticker


def merge_canonical_rows(
    rows: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    decision_groups: dict[str, list[dict[str, Any]]] = {}
    row_groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = canonical_ticker_key(str(row.get("ticker") or ""))
        if key:
            row_groups.setdefault(key, []).append(row)
    for decision in decisions:
        key = canonical_ticker_key(str(decision.get("ticker") or ""))
        if key:
            decision_groups.setdefault(key, []).append(decision)

    canonical_rows: list[dict[str, Any]] = []
    canonical_decisions: list[dict[str, Any]] = []
    decision_by_ticker: dict[str, dict[str, Any]] = {}
    row_by_ticker: dict[str, dict[str, Any]] = {}

    all_keys = sorted(set(row_groups) | set(decision_groups))
    for key in all_keys:
        grouped_decisions = decision_groups.get(key, [])
        grouped_rows = row_groups.get(key, [])
        canonical_decision = _merge_decision_group(key, grouped_decisions, grouped_rows)
        canonical_row = canonical_decision.get("source_row") if canonical_decision.get("source_row") else _merge_row_group(key, grouped_rows)
        canonical_row = _decorate_row(canonical_row, canonical_decision)
        canonical_rows.append(canonical_row)
        canonical_decisions.append(canonical_decision)
        decision_by_ticker[key] = canonical_decision
        row_by_ticker[key] = canonical_row

    canonical_decisions.sort(key=_canonical_decision_sort_key)
    canonical_rows.sort(key=lambda row: (_validation_priority(row.get("price_validation_status") or row.get("price_sanity", {}).get("price_validation_status")), str(row.get("ticker") or "")))
    return {
        "canonical_rows": canonical_rows,
        "canonical_decisions": canonical_decisions,
        "decision_by_ticker": decision_by_ticker,
        "row_by_ticker": row_by_ticker,
    }


def _merge_decision_group(
    canonical_key: str,
    grouped_decisions: list[dict[str, Any]],
    grouped_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    best_candidate = grouped_decisions[0] if grouped_decisions else {}
    if grouped_decisions:
        best_candidate = sorted(grouped_decisions, key=_decision_candidate_sort_key)[0]
    elif grouped_rows:
        best_candidate = {"ticker": canonical_key, "source_row": grouped_rows[0]}
    merged = deepcopy(best_candidate)
    merged["ticker"] = display_ticker(canonical_key)
    merged["source_row"] = deepcopy(merged.get("source_row") or _best_row_candidate(grouped_rows))

    source_groups = _unique_nonempty(str(item.get("source_group") or item.get("scan_source_group") or item.get("decision_source_lane") or "" ) for item in grouped_decisions + grouped_rows)
    valid_source_groups = _unique_nonempty(
        str(item.get("source_group") or item.get("scan_source_group") or item.get("decision_source_lane") or "")
        for item in grouped_decisions + grouped_rows
        if _row_validation_status(item) == "PASS"
    )
    failed_source_groups = _unique_nonempty(
        str(item.get("source_group") or item.get("scan_source_group") or item.get("decision_source_lane") or "")
        for item in grouped_decisions + grouped_rows
        if _row_validation_status(item) != "PASS"
    )
    merge_sources = []
    for item in grouped_decisions or [{"source_row": row} for row in grouped_rows]:
        source_row = item.get("source_row") or {}
        merge_sources.append(
            {
                "ticker": display_ticker(str(item.get("ticker") or source_row.get("ticker") or canonical_key)),
                "source_group": item.get("source_group") or source_row.get("scan_source_group") or source_row.get("decision_source_lane"),
                "action_lane": item.get("action_lane"),
                "price_validation_status": _row_validation_status(item),
                "current_price": source_row.get("current_price", item.get("current_price")),
                "actionability_score": item.get("actionability_score"),
                "price_timestamp": _price_timestamp(item),
            }
        )

    merge_warnings = _merge_warnings(grouped_decisions, grouped_rows, merged_source_group=str(merged.get("source_group") or ""))
    merged["merged_from_sources"] = merge_sources
    merged["source_groups"] = source_groups
    merged["best_source_group"] = merged.get("source_group") or (source_groups[0] if source_groups else "Unknown")
    merged["valid_source_groups"] = valid_source_groups
    merged["failed_source_groups"] = failed_source_groups
    merged["merge_warnings"] = merge_warnings
    merged["has_conflicting_source_rows"] = bool(merge_warnings or len(source_groups) > 1)
    return merged


def _merge_row_group(canonical_key: str, grouped_rows: list[dict[str, Any]]) -> dict[str, Any]:
    row = deepcopy(_best_row_candidate(grouped_rows))
    row["ticker"] = display_ticker(canonical_key)
    return row


def _decorate_row(row: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    decorated = deepcopy(row or {})
    decorated["ticker"] = display_ticker(str(decision.get("ticker") or decorated.get("ticker") or ""))
    for field in (
        "merged_from_sources",
        "source_groups",
        "best_source_group",
        "valid_source_groups",
        "failed_source_groups",
        "merge_warnings",
        "has_conflicting_source_rows",
    ):
        decorated[field] = deepcopy(decision.get(field))
    decorated["scan_source_group"] = decision.get("best_source_group") or decorated.get("scan_source_group")
    return decorated


def _best_row_candidate(grouped_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not grouped_rows:
        return {}
    return sorted(grouped_rows, key=_row_candidate_sort_key)[0]


def _decision_candidate_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    source_row = item.get("source_row") or {}
    return (
        _validation_priority(_row_validation_status(item)),
        -_to_float(item.get("actionability_score")),
        -_to_float(source_row.get("regular_investing_score")),
        -_to_float(source_row.get("winner_score")),
        -_to_float(source_row.get("setup_quality_score")),
        -_timestamp_sort_value(_price_timestamp(item)),
        _source_preference(str(item.get("source_group") or source_row.get("scan_source_group") or "")),
        str(item.get("ticker") or ""),
    )


def _row_candidate_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _validation_priority(_row_validation_status(item)),
        -_to_float(item.get("regular_investing_score")),
        -_to_float(item.get("winner_score")),
        -_to_float(item.get("setup_quality_score")),
        -_timestamp_sort_value(_price_timestamp(item)),
        _source_preference(str(item.get("scan_source_group") or item.get("decision_source_lane") or "")),
        str(item.get("ticker") or ""),
    )


def _canonical_decision_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _validation_priority(_row_validation_status(item)),
        _actionability_priority(str(item.get("actionability_label") or "Data Insufficient")),
        -_to_float(item.get("actionability_score")),
        -_to_float(item.get("score")),
        str(item.get("ticker") or ""),
    )


def _row_validation_status(item: dict[str, Any]) -> str:
    source_row = item.get("source_row") or {}
    return str(
        item.get("price_validation_status")
        or item.get("price_sanity", {}).get("price_validation_status")
        or source_row.get("price_validation_status")
        or source_row.get("price_sanity", {}).get("price_validation_status")
        or "FAIL"
    )


def _price_timestamp(item: dict[str, Any]) -> str:
    source_row = item.get("source_row") or {}
    return str(
        item.get("price_sanity", {}).get("price_timestamp")
        or source_row.get("price_sanity", {}).get("price_timestamp")
        or item.get("price_timestamp")
        or source_row.get("price_timestamp")
        or ""
    )


def _timestamp_sort_value(value: str) -> float:
    if not value or value == "unavailable":
        return 0.0
    digits = "".join(ch for ch in value if ch.isdigit())
    return float(digits or 0)


def _validation_priority(status: Any) -> int:
    return {"PASS": 0, "WARN": 1, "FAIL": 2}.get(str(status or "FAIL"), 3)


def _source_preference(source_group: str) -> int:
    return {
        "Tracked": 0,
        "Portfolio": 1,
        "Broad": 2,
        "Core Investing": 3,
        "Outlier": 4,
        "Velocity": 5,
    }.get(source_group, 6)


def _actionability_priority(label: str) -> int:
    return {
        "Actionable Today": 0,
        "Research First": 1,
        "Wait for Better Entry": 2,
        "Watch for Trigger": 3,
        "Avoid / Do Not Chase": 4,
        "Data Insufficient": 5,
    }.get(label, 6)


def _merge_warnings(grouped_decisions: list[dict[str, Any]], grouped_rows: list[dict[str, Any]], *, merged_source_group: str) -> list[str]:
    warnings: list[str] = []
    source_groups = _unique_nonempty(
        str(item.get("source_group") or item.get("scan_source_group") or item.get("decision_source_lane") or "")
        for item in grouped_decisions + grouped_rows
    )
    if len(source_groups) > 1:
        warnings.append(f"Merged duplicate source rows from {', '.join(source_groups)}.")
    failed_sources = _unique_nonempty(
        str(item.get("source_group") or item.get("scan_source_group") or item.get("decision_source_lane") or "")
        for item in grouped_decisions + grouped_rows
        if _row_validation_status(item) != "PASS"
    )
    if failed_sources:
        warnings.append(f"Ignored failed source rows from {', '.join(failed_sources)} in favor of the best canonical row.")
    if merged_source_group and failed_sources and merged_source_group not in failed_sources:
        warnings.append(f"{merged_source_group} supplied the canonical row after lower-quality duplicates were removed.")
    return list(dict.fromkeys(warnings))


def _unique_nonempty(values: Any) -> list[str]:
    ordered: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in ordered:
            ordered.append(clean)
    return ordered


def _to_float(value: Any) -> float:
    if value in (None, "", "unavailable", "None"):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
