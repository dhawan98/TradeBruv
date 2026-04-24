from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .review import load_scan_report, normalize_scan_row


DEFAULT_JOURNAL_PATH = Path("outputs/journal.csv")

DECISIONS = {
    "Research",
    "Watch",
    "Paper Trade",
    "Took Trade",
    "Skipped",
    "Avoided",
}
MISTAKE_CATEGORIES = {
    "Chased extended move",
    "Ignored invalidation",
    "Entered before confirmation",
    "Sold winner too early",
    "Held loser too long",
    "Position too large",
    "Ignored market regime",
    "Ignored catalyst risk",
    "Ignored earnings risk",
    "Good process / bad outcome",
    "Bad process / good outcome",
    "Other",
}

JOURNAL_FIELDS = [
    "id",
    "created_at",
    "ticker",
    "company_name",
    "strategy_label",
    "outlier_type",
    "status_label",
    "winner_score",
    "outlier_score",
    "setup_quality_score",
    "risk_score",
    "confidence_label",
    "entry_zone",
    "invalidation_level",
    "stop_reference",
    "tp1",
    "tp2",
    "reward_risk",
    "catalyst_quality",
    "theme_tags",
    "warnings",
    "decision",
    "actual_entry_price",
    "actual_exit_price",
    "entry_date",
    "exit_date",
    "position_type",
    "planned_holding_period",
    "actual_holding_period",
    "result_pct",
    "result_r",
    "followed_rules",
    "mistake_category",
    "notes",
]


def add_journal_entry(
    *,
    journal_path: str | Path = DEFAULT_JOURNAL_PATH,
    from_report: str | Path | None = None,
    ticker: str | None = None,
    updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updates = updates or {}
    if from_report:
        if not ticker:
            raise ValueError("--ticker is required with --from-report.")
        row = _row_from_report(from_report, ticker)
        entry = _entry_from_scan_row(row)
    else:
        if not ticker:
            raise ValueError("--ticker is required when adding a manual journal entry.")
        entry = _blank_entry(ticker)
    entry.update(_clean_updates(updates))
    _validate_entry(entry)
    rows = read_journal(journal_path)
    rows.append(entry)
    write_journal(rows, journal_path)
    return entry


def read_journal(path: str | Path = DEFAULT_JOURNAL_PATH) -> list[dict[str, Any]]:
    journal_path = Path(path)
    if not journal_path.exists():
        return []
    with journal_path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_journal(rows: list[dict[str, Any]], path: str | Path = DEFAULT_JOURNAL_PATH) -> Path:
    journal_path = Path(path)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    with journal_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=JOURNAL_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in JOURNAL_FIELDS})
    return journal_path


def update_journal_entry(
    *,
    entry_id: str,
    updates: dict[str, Any],
    journal_path: str | Path = DEFAULT_JOURNAL_PATH,
) -> dict[str, Any]:
    rows = read_journal(journal_path)
    for row in rows:
        if row.get("id") == entry_id:
            row.update(_clean_updates(updates))
            _validate_entry(row)
            write_journal(rows, journal_path)
            return row
    raise ValueError(f"Journal entry not found: {entry_id}")


def export_journal(
    *,
    output_path: str | Path,
    journal_path: str | Path = DEFAULT_JOURNAL_PATH,
) -> Path:
    rows = read_journal(journal_path)
    return write_journal(rows, output_path)


def journal_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    closed = [row for row in rows if row.get("exit_date") or row.get("actual_exit_price")]
    open_rows = [row for row in rows if row not in closed]
    followed = [row for row in rows if _truthy(row.get("followed_rules"))]
    not_followed = [row for row in rows if _falsey(row.get("followed_rules"))]
    avoided = [row for row in rows if row.get("decision") == "Avoided"]
    mistake_counts: dict[str, int] = {}
    for row in rows:
        mistake = row.get("mistake_category") or ""
        if mistake:
            mistake_counts[mistake] = mistake_counts.get(mistake, 0) + 1
    return {
        "total_entries": total,
        "open_entries": len(open_rows),
        "closed_entries": len(closed),
        "decision_counts": _counts(rows, "decision"),
        "rules_followed_pct": _rate(len(followed), total),
        "average_result_pct": _average_result(rows),
        "average_result_pct_rules_followed": _average_result(followed),
        "average_result_pct_rules_not_followed": _average_result(not_followed),
        "most_common_mistakes": sorted(mistake_counts.items(), key=lambda item: (-item[1], item[0])),
        "chasing_frequency": mistake_counts.get("Chased extended move", 0),
        "stop_invalidation_violations": mistake_counts.get("Ignored invalidation", 0),
        "early_winner_exits": mistake_counts.get("Sold winner too early", 0),
        "avoided_setups": len(avoided),
    }


def _row_from_report(path: str | Path, ticker: str) -> dict[str, Any]:
    report = load_scan_report(path)
    ticker = ticker.upper()
    for row in report.rows:
        if row["ticker"] == ticker:
            return normalize_scan_row(row)
    raise ValueError(f"Ticker {ticker} was not found in {path}.")


def _entry_from_scan_row(row: dict[str, Any]) -> dict[str, Any]:
    entry = _blank_entry(row["ticker"])
    entry.update(
        {
            "company_name": row.get("company_name", ""),
            "strategy_label": row.get("strategy_label", ""),
            "outlier_type": row.get("outlier_type", ""),
            "status_label": row.get("status_label", ""),
            "winner_score": row.get("winner_score", ""),
            "outlier_score": row.get("outlier_score", ""),
            "setup_quality_score": row.get("setup_quality_score", ""),
            "risk_score": row.get("risk_score", ""),
            "confidence_label": row.get("confidence_label", ""),
            "entry_zone": row.get("entry_zone", ""),
            "invalidation_level": row.get("invalidation_level", ""),
            "stop_reference": row.get("stop_loss_reference", ""),
            "tp1": row.get("tp1", ""),
            "tp2": row.get("tp2", ""),
            "reward_risk": row.get("reward_risk", ""),
            "catalyst_quality": row.get("catalyst_quality", ""),
            "theme_tags": row.get("theme_tags", []),
            "warnings": row.get("warnings", []),
            "planned_holding_period": row.get("holding_period", ""),
        }
    )
    return entry


def _blank_entry(ticker: str) -> dict[str, Any]:
    entry = {field: "" for field in JOURNAL_FIELDS}
    entry.update(
        {
            "id": uuid.uuid4().hex[:12],
            "created_at": datetime.utcnow().isoformat() + "Z",
            "ticker": ticker.upper(),
            "decision": "Research",
            "position_type": "stock",
        }
    )
    return entry


def _clean_updates(updates: dict[str, Any]) -> dict[str, Any]:
    cleaned = {}
    for key, value in updates.items():
        if key not in JOURNAL_FIELDS:
            continue
        cleaned[key] = value
    return cleaned


def _validate_entry(entry: dict[str, Any]) -> None:
    decision = entry.get("decision")
    if decision and decision not in DECISIONS:
        raise ValueError(f"Unknown decision '{decision}'. Valid values: {', '.join(sorted(DECISIONS))}")
    mistake = entry.get("mistake_category")
    if mistake and mistake not in MISTAKE_CATEGORIES:
        raise ValueError(
            f"Unknown mistake category '{mistake}'. Valid values: {', '.join(sorted(MISTAKE_CATEGORIES))}"
        )
    position_type = entry.get("position_type")
    if position_type and position_type not in {"stock", "options_placeholder_only"}:
        raise ValueError("position_type must be stock or options_placeholder_only.")


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return " | ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return value


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key) or "unavailable"
        counts[value] = counts.get(value, 0) + 1
    return counts


def _average_result(rows: list[dict[str, Any]]) -> float | str:
    values = []
    for row in rows:
        try:
            if row.get("result_pct") not in (None, ""):
                values.append(float(row["result_pct"]))
        except (TypeError, ValueError):
            continue
    if not values:
        return "unavailable"
    return round(sum(values) / len(values), 4)


def _rate(count: int, total: int) -> float:
    if not total:
        return 0.0
    return round((count / total) * 100, 4)


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "yes", "y", "1"}


def _falsey(value: Any) -> bool:
    return str(value).strip().lower() in {"false", "no", "n", "0"}
