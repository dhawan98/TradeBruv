from __future__ import annotations

import csv
import json
import re
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .indicators import pct_change, sma
from .models import ScannerResult
from .reporting import write_csv_report


DEFAULT_SCAN_ARCHIVE_ROOT = Path("reports/scans")
DEFAULT_WATCHLIST_STATE_PATH = Path("reports/watchlist_state.json")
DEFAULT_DAILY_OUTPUT_DIR = Path("outputs/daily")
OPPORTUNITY_TYPES = {
    "New Strong Research Candidate",
    "New Active Setup",
    "Watch Only upgraded to Trade Setup Forming",
    "Trade Setup Forming upgraded to Active Setup",
    "Outlier Score crossed threshold",
    "Winner Score crossed threshold",
    "Setup Quality improved significantly",
    "Relative strength improved",
    "Breakout confirmed",
    "Price entered entry zone",
    "Price reclaimed key level",
    "Catalyst became price-confirmed",
}
RISK_TYPES = {
    "Status downgraded to Avoid",
    "Setup invalidated",
    "Stop/invalidation hit",
    "Breakout failed",
    "Price fell below key level",
    "Risk score increased significantly",
    "Heavy selling warning appeared",
    "Earnings risk approaching",
    "Hype/pump warning appeared",
    "Social-only hype without price confirmation",
    "Catalyst became stale",
    "Price became overextended",
}
TARGET_TYPES = {
    "TP1 reached",
    "TP2 reached",
    "Reward/risk changed materially",
    "Price moved far above entry zone",
    "Setup no longer offers good reward/risk",
    "Consider moving from Research to Journal review",
}
DATA_TYPES = {
    "Ticker missing data",
    "Ticker no longer scanned",
    "Data provider failed for ticker",
    "Catalyst data missing",
    "AI explanation unavailable if enabled",
}


def archive_scan_report(
    *,
    results: list[ScannerResult],
    provider: str,
    mode: str,
    universe_file: Path,
    catalyst_file: Path | None,
    ai_enabled: bool,
    command_used: str,
    archive_root: Path = DEFAULT_SCAN_ARCHIVE_ROOT,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    created = created_at or datetime.utcnow()
    scan_id = _scan_id(provider=provider, mode=mode, created_at=created)
    day_dir = archive_root / created.date().isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    stem = f"scan_{mode}_{provider}_{created.strftime('%H%M%S')}"
    json_path = day_dir / f"{stem}.json"
    csv_path = day_dir / f"{stem}.csv"
    metadata = build_scan_metadata(
        scan_id=scan_id,
        created_at=created,
        provider=provider,
        mode=mode,
        universe_file=universe_file,
        catalyst_file=catalyst_file,
        ai_enabled=ai_enabled,
        result_count=len(results),
        command_used=command_used,
    )
    payload = {
        "generated_at": created.isoformat() + "Z",
        "scanner": "TradeBruv deterministic scanner",
        "mode": mode,
        "provider": provider,
        "metadata": metadata,
        "results": [result.to_dict() for result in results],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_csv_report(results, csv_path)
    return {"scan_id": scan_id, "json_path": json_path, "csv_path": csv_path, "metadata": metadata}


def build_scan_metadata(
    *,
    scan_id: str,
    created_at: datetime,
    provider: str,
    mode: str,
    universe_file: Path,
    catalyst_file: Path | None,
    ai_enabled: bool,
    result_count: int,
    command_used: str,
) -> dict[str, Any]:
    return {
        "scan_id": scan_id,
        "created_at": created_at.isoformat() + "Z",
        "provider": provider,
        "mode": mode,
        "universe_file": str(universe_file),
        "catalyst_file": str(catalyst_file) if catalyst_file else "unavailable",
        "ai_enabled": ai_enabled,
        "result_count": result_count,
        "command_used": command_used,
        "git_commit": _git_commit(),
    }


def load_watchlist_state(path: Path = DEFAULT_WATCHLIST_STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "tickers": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("version", 1)
    payload.setdefault("tickers", {})
    return payload


def update_watchlist_state(
    *,
    previous_state: dict[str, Any],
    rows: list[dict[str, Any]],
    scan_id: str,
    timestamp: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    previous_tickers = previous_state.get("tickers", {})
    current_tickers: dict[str, dict[str, Any]] = {}
    changes: dict[str, dict[str, Any]] = {}
    for row in rows:
        snapshot = _snapshot_from_row(row, timestamp=timestamp)
        ticker = snapshot["ticker"]
        previous = previous_tickers.get(ticker)
        if previous:
            _carry_previous_values(snapshot, previous)
        changes[ticker] = {"previous": previous, "current": snapshot}
        current_tickers[ticker] = snapshot

    for ticker, previous in previous_tickers.items():
        if ticker not in current_tickers:
            changes[ticker] = {"previous": previous, "current": None}
            current_tickers[ticker] = {**previous, "previous_status": previous.get("current_status"), "last_seen_at": previous.get("last_seen_at")}

    return {
        "version": 1,
        "updated_at": timestamp,
        "source_scan_id": scan_id,
        "tickers": current_tickers,
    }, changes


def save_watchlist_state(state: dict[str, Any], path: Path = DEFAULT_WATCHLIST_STATE_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


def generate_alerts(
    *,
    changes: dict[str, dict[str, Any]],
    source_scan_id: str,
    timestamp: str,
    ai_enabled: bool = False,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for ticker, change in sorted(changes.items()):
        previous = change.get("previous")
        current = change.get("current")
        if current is None and previous is not None:
            alerts.append(
                _alert(
                    timestamp=timestamp,
                    ticker=ticker,
                    alert_type="Ticker no longer scanned",
                    severity="Watch",
                    old_value=previous.get("current_status"),
                    new_value="missing",
                    explanation=f"{ticker} was present in the previous watchlist state but not in this scan.",
                    row=previous,
                    recommended_action_label="Watch",
                    deterministic_reason="ticker_absent_from_current_scan",
                    source_scan_id=source_scan_id,
                )
            )
            continue
        if current is None:
            continue
        alerts.extend(_status_alerts(previous, current, timestamp, source_scan_id))
        alerts.extend(_score_alerts(previous, current, timestamp, source_scan_id))
        alerts.extend(_level_alerts(previous, current, timestamp, source_scan_id))
        alerts.extend(_warning_alerts(previous, current, timestamp, source_scan_id, ai_enabled=ai_enabled))
        alerts.extend(_catalyst_alerts(previous, current, timestamp, source_scan_id))
    return alerts


def write_alerts_json(alerts: list[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"generated_at": datetime.utcnow().isoformat() + "Z", "alerts": alerts}, indent=2), encoding="utf-8")
    return path


def write_alerts_csv(alerts: list[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "alert_id",
        "timestamp",
        "ticker",
        "alert_type",
        "category",
        "severity",
        "old_value",
        "new_value",
        "explanation",
        "related_strategy",
        "related_outlier_type",
        "related_score",
        "recommended_action_label",
        "deterministic_reason",
        "source_scan_id",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(alerts)
    return path


def build_daily_summary_payload(
    *,
    rows: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    scan_metadata: dict[str, Any],
    market_regime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sorted_outliers = _sort(rows, "outlier_score")
    sorted_winners = _sort(rows, "winner_score")
    avoid_rows = [row for row in rows if row.get("status_label") == "Avoid"]
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "scan_metadata": scan_metadata,
        "market_regime": market_regime or {"regime": "Unavailable", "summary": "Market regime unavailable."},
        "top_outlier_candidates": _compact(sorted_outliers[:5]),
        "top_momentum_breakout_candidates": _compact(
            [row for row in sorted_winners if _contains_any(row, ("breakout", "momentum"))][:5] or sorted_winners[:5]
        ),
        "top_long_term_monster_candidates": _compact([row for row in sorted_outliers if row.get("outlier_type") == "Long-Term Monster"][:5]),
        "top_high_risk_squeeze_watch_names": _compact(
            [row for row in sorted_outliers if row.get("outlier_type") == "Short Squeeze Watch" or row.get("outlier_risk") in {"High", "Extreme"}][:5]
        ),
        "top_avoid_names": _compact(_sort(avoid_rows, "risk_score")[:5]),
        "new_upgrades": _alerts(alerts, OPPORTUNITY_TYPES),
        "new_downgrades": _alerts(alerts, {"Status downgraded to Avoid"}),
        "new_active_setups": _alerts(alerts, {"New Active Setup", "Trade Setup Forming upgraded to Active Setup"}),
        "new_invalidations": _alerts(alerts, {"Setup invalidated", "Stop/invalidation hit"}),
        "target_hits": _alerts(alerts, {"TP1 reached", "TP2 reached"}),
        "biggest_score_improvements": _score_change_alerts(alerts, reverse=True),
        "biggest_score_deteriorations": _score_change_alerts(alerts, reverse=False),
        "catalyst_confirmed_names": _compact([row for row in rows if row.get("catalyst_quality") in {"Official Confirmed", "Price Confirmed"}][:5]),
        "hype_risk_names": _compact([row for row in rows if row.get("hype_risk") or row.get("pump_risk") or _warnings_contain(row, ("hype", "pump"))][:5]),
        "watchlist_names_needing_review": _alerts(alerts, {"Consider moving from Research to Journal review", "Price became overextended", "Setup no longer offers good reward/risk"}),
        "data_quality_issues": _alerts(alerts, DATA_TYPES),
        "top_alerts": sorted(alerts, key=lambda alert: _severity_rank(alert["severity"]), reverse=True)[:10],
        "alert_counts": dict(Counter(alert["category"] for alert in alerts)),
        "disclaimer": "Daily alerts are deterministic research prompts, not buy/sell instructions or financial advice.",
    }


def build_simple_market_regime(provider: Any) -> dict[str, Any]:
    spy = _benchmark(provider, "SPY")
    qqq = _benchmark(provider, "QQQ")
    bullish = sum(1 for item in (spy, qqq) if item["trend_state"] in {"Strong Uptrend", "Uptrend"})
    risk_off = sum(1 for item in (spy, qqq) if item["trend_state"] in {"Below 200-DMA", "Downtrend"})
    if bullish == 2:
        regime = "Bullish"
    elif risk_off:
        regime = "Risk-Off"
    else:
        regime = "Mixed"
    return {
        "regime": regime,
        "spy": spy,
        "qqq": qqq,
        "summary": f"SPY {spy['trend_state']}; QQQ {qqq['trend_state']}; overall {regime}.",
    }


def write_daily_summary_json(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def build_daily_summary_markdown(payload: dict[str, Any]) -> str:
    metadata = payload.get("scan_metadata", {})
    lines = [
        "# TradeBruv Daily Summary",
        "",
        f"Generated: {payload.get('generated_at', 'unavailable')}",
        f"Scan: {metadata.get('scan_id', 'unavailable')} | Provider: {metadata.get('provider', 'unavailable')} | Mode: {metadata.get('mode', 'unavailable')}",
        "",
        "> Deterministic research prompts only. No alert is a buy/sell instruction or financial advice.",
        "",
        "## Market Regime",
        _market_regime_text(payload.get("market_regime", {})),
        "",
    ]
    sections = [
        ("Top Outlier Candidates", "top_outlier_candidates"),
        ("Top Momentum/Breakout Candidates", "top_momentum_breakout_candidates"),
        ("Top Long-Term Monster Candidates", "top_long_term_monster_candidates"),
        ("Top High-Risk Squeeze/Watch Names", "top_high_risk_squeeze_watch_names"),
        ("Top Avoid Names", "top_avoid_names"),
        ("New Upgrades", "new_upgrades"),
        ("New Downgrades", "new_downgrades"),
        ("New Active Setups", "new_active_setups"),
        ("New Invalidations", "new_invalidations"),
        ("TP1/TP2 Hits", "target_hits"),
        ("Biggest Score Improvements", "biggest_score_improvements"),
        ("Biggest Score Deteriorations", "biggest_score_deteriorations"),
        ("Catalyst-Confirmed Names", "catalyst_confirmed_names"),
        ("Hype-Risk Names", "hype_risk_names"),
        ("Watchlist Names Needing Review", "watchlist_names_needing_review"),
        ("Data Quality Issues", "data_quality_issues"),
    ]
    for title, key in sections:
        lines.extend([f"## {title}", *_markdown_items(payload.get(key, [])), ""])
    return "\n".join(lines).strip() + "\n"


def write_daily_summary_markdown(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_daily_summary_markdown(payload), encoding="utf-8")
    return path


def write_daily_outputs(
    *,
    alerts: list[dict[str, Any]],
    summary_payload: dict[str, Any],
    output_dir: Path = DEFAULT_DAILY_OUTPUT_DIR,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "alerts_json": write_alerts_json(alerts, output_dir / "alerts.json"),
        "alerts_csv": write_alerts_csv(alerts, output_dir / "alerts.csv"),
        "summary_json": write_daily_summary_json(summary_payload, output_dir / "daily_summary.json"),
        "summary_markdown": write_daily_summary_markdown(summary_payload, output_dir / "daily_summary.md"),
    }


def filter_alerts(alerts: Iterable[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    severity = set(filters.get("severity") or [])
    alert_type = set(filters.get("alert_type") or [])
    ticker = set(filters.get("ticker") or [])
    category = set(filters.get("category") or [])
    search = str(filters.get("search") or "").lower()
    filtered = []
    for alert in alerts:
        if severity and alert.get("severity") not in severity:
            continue
        if alert_type and alert.get("alert_type") not in alert_type:
            continue
        if ticker and alert.get("ticker") not in ticker:
            continue
        if category and alert.get("category") not in category:
            continue
        if search and search not in json.dumps(alert).lower():
            continue
        filtered.append(alert)
    return filtered


def summarize_watchlist_changes(alerts: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    rows = list(alerts)
    return {
        "score_changes": [alert for alert in rows if "Score" in alert.get("alert_type", "") or "score" in alert.get("deterministic_reason", "")],
        "status_changes": [alert for alert in rows if "Status" in alert.get("alert_type", "") or "Setup" in alert.get("alert_type", "")],
        "risk_changes": [alert for alert in rows if alert.get("category") == "Risk"],
        "setup_changes": [alert for alert in rows if alert.get("category") in {"Opportunity", "Target/Management"}],
        "level_changes": [alert for alert in rows if alert.get("alert_type") in {"Price entered entry zone", "TP1 reached", "TP2 reached", "Setup invalidated", "Stop/invalidation hit"}],
        "catalyst_changes": [alert for alert in rows if "Catalyst" in alert.get("alert_type", "")],
    }


def _status_alerts(previous: dict[str, Any] | None, current: dict[str, Any], timestamp: str, scan_id: str) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    old_status = previous.get("current_status") if previous else None
    new_status = current.get("current_status")
    if old_status != "Strong Research Candidate" and new_status == "Strong Research Candidate":
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="New Strong Research Candidate", severity="Important", old_value=old_status, new_value=new_status, explanation=f"{current['ticker']} is now a Strong Research Candidate.", row=current, recommended_action_label="Research", deterministic_reason="status_entered_strong_research", source_scan_id=scan_id))
    if old_status != "Active Setup" and new_status == "Active Setup":
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="New Active Setup", severity="Important", old_value=old_status, new_value=new_status, explanation=f"{current['ticker']} is now an Active Setup.", row=current, recommended_action_label="Research", deterministic_reason="status_entered_active_setup", source_scan_id=scan_id))
    if old_status == "Watch Only" and new_status == "Trade Setup Forming":
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Watch Only upgraded to Trade Setup Forming", severity="Watch", old_value=old_status, new_value=new_status, explanation=f"{current['ticker']} improved from Watch Only to Trade Setup Forming.", row=current, recommended_action_label="Watch", deterministic_reason="status_watch_to_forming", source_scan_id=scan_id))
    if old_status == "Trade Setup Forming" and new_status == "Active Setup":
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Trade Setup Forming upgraded to Active Setup", severity="Important", old_value=old_status, new_value=new_status, explanation=f"{current['ticker']} moved from forming to active.", row=current, recommended_action_label="Research", deterministic_reason="status_forming_to_active", source_scan_id=scan_id))
    if old_status != "Avoid" and new_status == "Avoid":
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Status downgraded to Avoid", severity="Critical", old_value=old_status, new_value=new_status, explanation=f"{current['ticker']} is now flagged Avoid.", row=current, recommended_action_label="Avoid", deterministic_reason="status_downgraded_to_avoid", source_scan_id=scan_id))
    if old_status in {"Active Setup", "Trade Setup Forming"} and new_status in {"Watch Only", "Avoid"}:
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Breakout failed", severity="Critical" if new_status == "Avoid" else "Important", old_value=old_status, new_value=new_status, explanation=f"{current['ticker']} lost setup status after previously being {old_status}.", row=current, recommended_action_label="Avoid" if new_status == "Avoid" else "Watch", deterministic_reason="setup_status_deteriorated", source_scan_id=scan_id))
    return alerts


def _score_alerts(previous: dict[str, Any] | None, current: dict[str, Any], timestamp: str, scan_id: str) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    old_outlier = _num(previous.get("current_outlier_score")) if previous else None
    new_outlier = _num(current.get("current_outlier_score"))
    old_winner = _num(previous.get("current_winner_score")) if previous else None
    new_winner = _num(current.get("current_winner_score"))
    old_setup = _num(previous.get("current_setup_quality")) if previous else None
    new_setup = _num(current.get("current_setup_quality"))
    old_risk = _num(previous.get("current_risk_score")) if previous else None
    new_risk = _num(current.get("current_risk_score"))
    if _crossed(old_outlier, new_outlier, 80):
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Outlier Score crossed threshold", severity="Important", old_value=old_outlier, new_value=new_outlier, explanation=f"{current['ticker']} crossed the outlier score threshold.", row=current, recommended_action_label="Research", deterministic_reason="outlier_score_crossed_80", source_scan_id=scan_id))
    if _crossed(old_winner, new_winner, 80):
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Winner Score crossed threshold", severity="Important", old_value=old_winner, new_value=new_winner, explanation=f"{current['ticker']} crossed the winner score threshold.", row=current, recommended_action_label="Research", deterministic_reason="winner_score_crossed_80", source_scan_id=scan_id))
    if old_setup is not None and new_setup is not None and new_setup - old_setup >= 15:
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Setup Quality improved significantly", severity="Watch", old_value=old_setup, new_value=new_setup, explanation=f"{current['ticker']} setup quality improved by at least 15 points.", row=current, recommended_action_label="Watch", deterministic_reason="setup_quality_improved_15", source_scan_id=scan_id))
    if old_winner is not None and new_winner is not None and new_winner - old_winner >= 15:
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Relative strength improved", severity="Watch", old_value=old_winner, new_value=new_winner, explanation=f"{current['ticker']} winner score improved materially.", row=current, recommended_action_label="Watch", deterministic_reason="winner_score_improved_15", source_scan_id=scan_id))
    if old_risk is not None and new_risk is not None and new_risk - old_risk >= 15:
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Risk score increased significantly", severity="Important", old_value=old_risk, new_value=new_risk, explanation=f"{current['ticker']} risk score increased by at least 15 points.", row=current, recommended_action_label="Watch", deterministic_reason="risk_score_increased_15", source_scan_id=scan_id))
    if old_outlier is not None and new_outlier is not None and old_outlier - new_outlier >= 20:
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Setup no longer offers good reward/risk", severity="Watch", old_value=old_outlier, new_value=new_outlier, explanation=f"{current['ticker']} outlier score deteriorated materially.", row=current, recommended_action_label="Review Journal", deterministic_reason="outlier_score_deteriorated_20", source_scan_id=scan_id))
    return alerts


def _level_alerts(previous: dict[str, Any] | None, current: dict[str, Any], timestamp: str, scan_id: str) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    price = _num(current.get("current_price"))
    prev_price = _num(previous.get("current_price")) if previous else None
    entry_low, entry_high = _entry_bounds(current.get("current_entry_zone"))
    invalidation = _num(current.get("current_invalidation_level"))
    tp1 = _num(current.get("current_tp1"))
    tp2 = _num(current.get("current_tp2"))
    if price is not None and entry_low is not None and entry_high is not None:
        previously_inside = prev_price is not None and entry_low <= prev_price <= entry_high
        if not previously_inside and entry_low <= price <= entry_high:
            alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Price entered entry zone", severity="Important", old_value=prev_price, new_value=price, explanation=f"{current['ticker']} moved into the saved entry zone.", row=current, recommended_action_label="Research", deterministic_reason="price_inside_entry_zone", source_scan_id=scan_id))
        if price > entry_high * 1.08:
            alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Price moved far above entry zone", severity="Watch", old_value=entry_high, new_value=price, explanation=f"{current['ticker']} is more than 8% above the entry zone high.", row=current, recommended_action_label="Review Journal", deterministic_reason="price_extended_above_entry_zone", source_scan_id=scan_id))
            alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Price became overextended", severity="Watch", old_value=entry_high, new_value=price, explanation=f"{current['ticker']} may be extended relative to its planned entry zone.", row=current, recommended_action_label="Watch", deterministic_reason="price_extended_above_entry_zone", source_scan_id=scan_id))
    if price is not None and invalidation is not None and price <= invalidation:
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Setup invalidated", severity="Critical", old_value=invalidation, new_value=price, explanation=f"{current['ticker']} is at or below invalidation.", row=current, recommended_action_label="Avoid", deterministic_reason="price_below_invalidation", source_scan_id=scan_id))
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Stop/invalidation hit", severity="Critical", old_value=invalidation, new_value=price, explanation=f"{current['ticker']} hit the stop or invalidation reference.", row=current, recommended_action_label="Avoid", deterministic_reason="price_below_invalidation", source_scan_id=scan_id))
    if price is not None and tp1 is not None and price >= tp1 and not (prev_price is not None and prev_price >= tp1):
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="TP1 reached", severity="Important", old_value=prev_price, new_value=price, explanation=f"{current['ticker']} reached TP1.", row=current, recommended_action_label="Review Journal", deterministic_reason="price_reached_tp1", source_scan_id=scan_id))
    if price is not None and tp2 is not None and price >= tp2 and not (prev_price is not None and prev_price >= tp2):
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="TP2 reached", severity="Important", old_value=prev_price, new_value=price, explanation=f"{current['ticker']} reached TP2.", row=current, recommended_action_label="Review Journal", deterministic_reason="price_reached_tp2", source_scan_id=scan_id))
    if previous and current.get("current_entry_zone") != previous.get("current_entry_zone"):
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Reward/risk changed materially", severity="Watch", old_value=previous.get("current_entry_zone"), new_value=current.get("current_entry_zone"), explanation=f"{current['ticker']} entry zone changed since the last scan.", row=current, recommended_action_label="Review Journal", deterministic_reason="entry_zone_changed", source_scan_id=scan_id))
    return alerts


def _warning_alerts(previous: dict[str, Any] | None, current: dict[str, Any], timestamp: str, scan_id: str, *, ai_enabled: bool) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    old = set(previous.get("current_warnings", [])) if previous else set()
    new = set(current.get("current_warnings", []))
    appeared = new - old
    for warning in sorted(appeared):
        lower = warning.lower()
        if any(needle in lower for needle in ("selling", "distribution", "heavy")):
            alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Heavy selling warning appeared", severity="Important", old_value="", new_value=warning, explanation=warning, row=current, recommended_action_label="Watch", deterministic_reason="new_heavy_selling_warning", source_scan_id=scan_id))
        if "earnings" in lower:
            alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Earnings risk approaching", severity="Watch", old_value="", new_value=warning, explanation=warning, row=current, recommended_action_label="Watch", deterministic_reason="new_earnings_warning", source_scan_id=scan_id))
        if "hype" in lower or "pump" in lower:
            alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Hype/pump warning appeared", severity="Critical", old_value="", new_value=warning, explanation=warning, row=current, recommended_action_label="Avoid", deterministic_reason="new_hype_or_pump_warning", source_scan_id=scan_id))
        if "catalyst unavailable" in lower or "catalyst data" in lower:
            alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Catalyst data missing", severity="Info", old_value="", new_value=warning, explanation=warning, row=current, recommended_action_label="No Action", deterministic_reason="catalyst_missing_warning", source_scan_id=scan_id))
        if "data fetch failed" in lower or "unavailable in the" in lower:
            alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Data provider failed for ticker", severity="Watch", old_value="", new_value=warning, explanation=warning, row=current, recommended_action_label="Watch", deterministic_reason="provider_failed_warning", source_scan_id=scan_id))
    if current.get("current_status") == "Avoid" and _warnings_contain(current, ("data fetch failed", "unavailable in the")):
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Ticker missing data", severity="Watch", old_value="", new_value=current.get("current_status"), explanation=f"{current['ticker']} has missing provider data.", row=current, recommended_action_label="Watch", deterministic_reason="ticker_missing_data", source_scan_id=scan_id))
    if current.get("hype_risk") or current.get("pump_risk"):
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Social-only hype without price confirmation", severity="Critical", old_value="", new_value="hype/pump risk", explanation=f"{current['ticker']} has hype or pump risk flags.", row=current, recommended_action_label="Avoid", deterministic_reason="hype_or_pump_flag_true", source_scan_id=scan_id))
    if ai_enabled and not current.get("ai_explanation_available"):
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="AI explanation unavailable if enabled", severity="Info", old_value="", new_value="unavailable", explanation=f"{current['ticker']} has no AI explanation payload even though AI was enabled.", row=current, recommended_action_label="No Action", deterministic_reason="ai_enabled_but_unavailable", source_scan_id=scan_id))
    return alerts


def _catalyst_alerts(previous: dict[str, Any] | None, current: dict[str, Any], timestamp: str, scan_id: str) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    old_quality = previous.get("current_catalyst_quality") if previous else None
    new_quality = current.get("current_catalyst_quality")
    if old_quality not in {"Official Confirmed", "Price Confirmed"} and new_quality in {"Official Confirmed", "Price Confirmed"}:
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Catalyst became price-confirmed", severity="Important", old_value=old_quality, new_value=new_quality, explanation=f"{current['ticker']} catalyst quality is now {new_quality}.", row=current, recommended_action_label="Research", deterministic_reason="catalyst_quality_now_confirmed", source_scan_id=scan_id))
    if old_quality in {"Official Confirmed", "Price Confirmed", "Narrative Supported"} and new_quality in {"Unconfirmed", "Unavailable"}:
        alerts.append(_alert(timestamp=timestamp, ticker=current["ticker"], alert_type="Catalyst became stale", severity="Watch", old_value=old_quality, new_value=new_quality, explanation=f"{current['ticker']} catalyst quality weakened.", row=current, recommended_action_label="Watch", deterministic_reason="catalyst_quality_weakened", source_scan_id=scan_id))
    return alerts


def _snapshot_from_row(row: dict[str, Any], *, timestamp: str) -> dict[str, Any]:
    return {
        "ticker": str(row.get("ticker", "UNKNOWN")).upper(),
        "last_seen_at": timestamp,
        "previous_status": row.get("previous_status", ""),
        "current_status": row.get("status_label", "Watch Only"),
        "previous_winner_score": row.get("previous_winner_score", ""),
        "current_winner_score": row.get("winner_score", 0),
        "previous_outlier_score": row.get("previous_outlier_score", ""),
        "current_outlier_score": row.get("outlier_score", 0),
        "previous_risk_score": row.get("previous_risk_score", ""),
        "current_risk_score": row.get("risk_score", 0),
        "previous_setup_quality": row.get("previous_setup_quality", ""),
        "current_setup_quality": row.get("setup_quality_score", 0),
        "previous_outlier_type": row.get("previous_outlier_type", ""),
        "current_outlier_type": row.get("outlier_type", "Watch Only"),
        "previous_price": row.get("previous_price", ""),
        "current_price": row.get("current_price", "unavailable"),
        "previous_entry_zone": row.get("previous_entry_zone", ""),
        "current_entry_zone": row.get("entry_zone", "unavailable"),
        "previous_invalidation_level": row.get("previous_invalidation_level", ""),
        "current_invalidation_level": row.get("invalidation_level", "unavailable"),
        "previous_tp1": row.get("previous_tp1", ""),
        "current_tp1": row.get("tp1", "unavailable"),
        "previous_tp2": row.get("previous_tp2", ""),
        "current_tp2": row.get("tp2", "unavailable"),
        "previous_warnings": row.get("previous_warnings", []),
        "current_warnings": _listify(row.get("warnings")),
        "previous_catalyst_quality": row.get("previous_catalyst_quality", ""),
        "current_catalyst_quality": row.get("catalyst_quality", "Unavailable"),
        "previous_theme_tags": row.get("previous_theme_tags", []),
        "current_theme_tags": _listify(row.get("theme_tags")),
        "related_strategy": row.get("strategy_label", "unavailable"),
        "related_outlier_type": row.get("outlier_type", "unavailable"),
        "hype_risk": bool(row.get("hype_risk")),
        "pump_risk": bool(row.get("pump_risk")),
        "ai_explanation_available": bool(row.get("ai_explanation_available")),
    }


def _carry_previous_values(snapshot: dict[str, Any], previous: dict[str, Any]) -> None:
    pairs = {
        "previous_status": "current_status",
        "previous_winner_score": "current_winner_score",
        "previous_outlier_score": "current_outlier_score",
        "previous_risk_score": "current_risk_score",
        "previous_setup_quality": "current_setup_quality",
        "previous_outlier_type": "current_outlier_type",
        "previous_price": "current_price",
        "previous_entry_zone": "current_entry_zone",
        "previous_invalidation_level": "current_invalidation_level",
        "previous_tp1": "current_tp1",
        "previous_tp2": "current_tp2",
        "previous_warnings": "current_warnings",
        "previous_catalyst_quality": "current_catalyst_quality",
        "previous_theme_tags": "current_theme_tags",
    }
    for target, source in pairs.items():
        snapshot[target] = previous.get(source, "")


def _alert(
    *,
    timestamp: str,
    ticker: str,
    alert_type: str,
    severity: str,
    old_value: Any,
    new_value: Any,
    explanation: str,
    row: dict[str, Any],
    recommended_action_label: str,
    deterministic_reason: str,
    source_scan_id: str,
) -> dict[str, Any]:
    return {
        "alert_id": f"{source_scan_id}_{ticker}_{_slug(alert_type)}",
        "timestamp": timestamp,
        "ticker": ticker,
        "alert_type": alert_type,
        "category": _alert_category(alert_type),
        "severity": severity,
        "old_value": _sanitize_alert_text(_csv_value(old_value)),
        "new_value": _sanitize_alert_text(_csv_value(new_value)),
        "explanation": _sanitize_alert_text(explanation),
        "related_strategy": row.get("related_strategy") or row.get("strategy_label") or "unavailable",
        "related_outlier_type": row.get("related_outlier_type") or row.get("outlier_type") or "unavailable",
        "related_score": row.get("current_outlier_score", row.get("outlier_score", "unavailable")),
        "recommended_action_label": recommended_action_label,
        "deterministic_reason": deterministic_reason,
        "source_scan_id": source_scan_id,
    }


def _alert_category(alert_type: str) -> str:
    if alert_type in OPPORTUNITY_TYPES:
        return "Opportunity"
    if alert_type in RISK_TYPES:
        return "Risk"
    if alert_type in TARGET_TYPES:
        return "Target/Management"
    if alert_type in DATA_TYPES:
        return "Data Quality"
    return "Watchlist Maintenance"


def _scan_id(*, provider: str, mode: str, created_at: datetime) -> str:
    return f"{created_at.strftime('%Y%m%dT%H%M%SZ')}_{mode}_{provider}"


def _git_commit() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], check=False, capture_output=True, text=True, timeout=2)
    except Exception:
        return "unavailable"
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def _num(value: Any) -> float | None:
    if value in (None, "", "unavailable"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _crossed(old: float | None, new: float | None, threshold: float) -> bool:
    return new is not None and new >= threshold and (old is None or old < threshold)


def _entry_bounds(value: Any) -> tuple[float | None, float | None]:
    if not value or value == "unavailable":
        return None, None
    text = str(value).replace("–", "-")
    parts = [part.strip() for part in text.split("-")]
    if len(parts) < 2:
        number = _num(parts[0])
        return number, number
    return _num(parts[0]), _num(parts[1])


def _listify(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        if value == "unavailable":
            return []
        if " | " in value:
            return [item.strip() for item in value.split("|") if item.strip()]
        return [value]
    return [str(value)]


def _csv_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return " | ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return "" if value is None else str(value)


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")


def _sanitize_alert_text(value: str) -> str:
    text = re.sub(r"\bbuy\b", "research", value, flags=re.IGNORECASE)
    return re.sub(r"\bguaranteed?\b", "not guaranteed", text, flags=re.IGNORECASE)


def _sort(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: _num(row.get(key)) or 0, reverse=True)


def _compact(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "ticker": row.get("ticker"),
            "status_label": row.get("status_label"),
            "strategy_label": row.get("strategy_label"),
            "outlier_type": row.get("outlier_type"),
            "winner_score": row.get("winner_score"),
            "outlier_score": row.get("outlier_score"),
            "risk_score": row.get("risk_score"),
            "current_price": row.get("current_price"),
            "catalyst_quality": row.get("catalyst_quality"),
        }
        for row in rows
    ]


def _contains_any(row: dict[str, Any], needles: tuple[str, ...]) -> bool:
    text = json.dumps(row).lower()
    return any(needle in text for needle in needles)


def _warnings_contain(row: dict[str, Any], needles: tuple[str, ...]) -> bool:
    text = " ".join(_listify(row.get("warnings") or row.get("current_warnings"))).lower()
    return any(needle in text for needle in needles)


def _alerts(alerts: list[dict[str, Any]], alert_types: set[str]) -> list[dict[str, Any]]:
    return [alert for alert in alerts if alert["alert_type"] in alert_types][:10]


def _score_change_alerts(alerts: list[dict[str, Any]], *, reverse: bool) -> list[dict[str, Any]]:
    candidates = [alert for alert in alerts if "score" in alert.get("deterministic_reason", "")]
    if reverse:
        candidates = [
            alert
            for alert in candidates
            if (_num(alert.get("new_value")) or 0) >= (_num(alert.get("old_value")) or 0)
        ]
    else:
        candidates = [
            alert
            for alert in candidates
            if (_num(alert.get("new_value")) or 0) < (_num(alert.get("old_value")) or 0)
        ]
    return sorted(
        candidates,
        key=lambda alert: abs((_num(alert.get("new_value")) or 0) - (_num(alert.get("old_value")) or 0)),
        reverse=True,
    )[:10]


def _severity_rank(severity: str) -> int:
    return {"Info": 1, "Watch": 2, "Important": 3, "Critical": 4}.get(severity, 0)


def _market_regime_text(regime: dict[str, Any]) -> str:
    if "summary" in regime:
        return str(regime["summary"])
    return str(regime.get("regime", "Unavailable"))


def _benchmark(provider: Any, ticker: str) -> dict[str, Any]:
    try:
        security = provider.get_security_data(ticker)
        closes = [bar.close for bar in security.bars]
    except Exception as exc:
        return {"ticker": ticker, "trend_state": "Unavailable", "warning": str(exc)}
    latest = closes[-1] if closes else None
    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200)
    one_month = pct_change(closes, 21)
    three_month = pct_change(closes, 63)
    above50 = latest is not None and sma50 is not None and latest >= sma50
    above200 = latest is not None and sma200 is not None and latest >= sma200
    if above50 and above200 and (one_month or 0) > 0 and (three_month or 0) > 0:
        trend = "Strong Uptrend"
    elif above200:
        trend = "Uptrend"
    elif latest is not None and sma200 is not None:
        trend = "Below 200-DMA"
    else:
        trend = "Unavailable"
    return {
        "ticker": ticker,
        "trend_state": trend,
        "latest_close": round(latest, 2) if latest is not None else "unavailable",
        "sma50": round(sma50, 2) if sma50 is not None else "unavailable",
        "sma200": round(sma200, 2) if sma200 is not None else "unavailable",
        "return_1m": round((one_month or 0) * 100, 2) if one_month is not None else "unavailable",
        "return_3m": round((three_month or 0) * 100, 2) if three_month is not None else "unavailable",
        "warning": "" if trend != "Unavailable" else f"{ticker} benchmark unavailable.",
    }


def _markdown_items(items: Any) -> list[str]:
    if not items:
        return ["- None"]
    output = []
    for item in items[:10]:
        if isinstance(item, dict):
            ticker = item.get("ticker", "unavailable")
            label = item.get("alert_type") or item.get("status_label") or item.get("strategy_label") or "review"
            score = item.get("outlier_score") or item.get("related_score") or ""
            output.append(f"- {ticker}: {label}" + (f" ({score})" if score != "" else ""))
        else:
            output.append(f"- {item}")
    return output
