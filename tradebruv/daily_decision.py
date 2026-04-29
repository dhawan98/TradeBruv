from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .dashboard_data import (
    build_daily_summary,
    load_dashboard_portfolio,
    run_dashboard_scan,
)
from .decision_engine import build_unified_decisions, build_validation_context
from .price_sanity import build_price_sanity_from_row

DEFAULT_DAILY_DECISION_OUTPUT_DIR = Path("outputs/daily")
DEFAULT_DAILY_DECISION_JSON_PATH = DEFAULT_DAILY_DECISION_OUTPUT_DIR / "decision_today.json"
DEFAULT_DAILY_DECISION_MD_PATH = DEFAULT_DAILY_DECISION_OUTPUT_DIR / "decision_today.md"


def run_daily_decision(
    *,
    provider_name: str,
    core_universe: Path,
    outlier_universe: Path,
    velocity_universe: Path,
    analysis_date: date | None = None,
    output_dir: Path = DEFAULT_DAILY_DECISION_OUTPUT_DIR,
) -> dict[str, Any]:
    as_of = analysis_date or date.today()
    validation_context = build_validation_context()
    portfolio_rows = load_dashboard_portfolio()
    scans = [
        ("Core Investing", run_dashboard_scan(provider_name=provider_name, mode="investing", universe_path=core_universe, analysis_date=as_of)),
        ("Outlier", run_dashboard_scan(provider_name=provider_name, mode="outliers", universe_path=outlier_universe, analysis_date=as_of)),
        ("Velocity", run_dashboard_scan(provider_name=provider_name, mode="velocity", universe_path=velocity_universe, analysis_date=as_of)),
    ]

    combined_rows: list[dict[str, Any]] = []
    combined_decisions: list[dict[str, Any]] = []
    scan_summaries: list[dict[str, Any]] = []
    for lane, scan in scans:
        rows = [
            _enrich_row(
                row,
                generated_at=scan.generated_at,
                reference_date=as_of,
                extra={
                    "data_mode": "live_daily_decision",
                    "selected_provider": provider_name,
                    "provider_is_live_capable": provider_name == "real",
                    "decision_source_lane": lane,
                    "report_snapshot_selected": False,
                    "is_report_only": False,
                },
            )
            for row in scan.results
        ]
        decisions = build_unified_decisions(
            rows,
            portfolio_rows=portfolio_rows,
            scan_generated_at=scan.generated_at,
            validation_context=validation_context,
            reference_date=as_of,
            preferred_lane=lane,
        )
        combined_rows.extend(rows)
        combined_decisions.extend(decisions)
        scan_summaries.append(
            {
                "lane": lane,
                "generated_at": scan.generated_at,
                "provider": scan.provider,
                "source": scan.source,
                "universe": _universe_for_lane(lane, core_universe=core_universe, outlier_universe=outlier_universe, velocity_universe=velocity_universe),
                "result_count": len(rows),
                "market_regime": scan.market_regime,
            }
        )

    merged_rows = _dedupe_rows(combined_rows)
    merged_decisions = _dedupe_decisions(combined_decisions)
    data_issues = [decision for decision in merged_decisions if decision.get("price_validation_status") != "PASS"]
    picker_view = _build_picker_view(merged_decisions, data_issues=data_issues)
    payload = {
        "available": True,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "analysis_date": as_of.isoformat(),
        "provider": provider_name,
        "mode": "daily-decision",
        "data_mode": "live_daily_decision",
        "results": merged_rows,
        "summary": build_daily_summary(merged_rows),
        "decisions": merged_decisions,
        "data_issues": data_issues,
        "top_candidate": picker_view["top_candidate"],
        "research_candidates": picker_view["research_candidates"],
        "watch_candidates": picker_view["watch_candidates"],
        "avoid_candidates": picker_view["avoid_candidates"],
        "portfolio_actions": picker_view["portfolio_actions"],
        "compact_board": picker_view["compact_board"],
        "no_clean_candidate_reason": picker_view["no_clean_candidate_reason"],
        "validation_context": validation_context,
        "market_regime": _pick_market_regime(scan_summaries),
        "scans": scan_summaries,
        "demo_mode": provider_name == "sample",
        "report_snapshot": False,
        "stale_data": any(bool(decision.get("price_sanity", {}).get("is_stale")) for decision in merged_decisions),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "decision_today.json"
    markdown_path = output_dir / "decision_today.md"
    quality_review_path = output_dir / "decision_quality_review.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(_build_daily_decision_markdown(payload), encoding="utf-8")
    quality_review_path.write_text(_build_decision_quality_review(payload), encoding="utf-8")
    payload["json_path"] = str(json_path)
    payload["markdown_path"] = str(markdown_path)
    payload["quality_review_path"] = str(quality_review_path)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_daily_decision(path: Path = DEFAULT_DAILY_DECISION_JSON_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "available": False,
            "generated_at": "unavailable",
            "provider": "unavailable",
            "mode": "daily-decision",
            "data_mode": "live_daily_decision",
            "results": [],
            "summary": {},
            "decisions": [],
            "data_issues": [],
            "top_candidate": None,
            "research_candidates": [],
            "watch_candidates": [],
            "avoid_candidates": [],
            "portfolio_actions": [],
            "compact_board": [],
            "no_clean_candidate_reason": "No live daily decision has been built yet.",
            "validation_context": build_validation_context(),
            "market_regime": {},
            "demo_mode": False,
            "report_snapshot": False,
            "stale_data": False,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _enrich_row(
    row: dict[str, Any],
    *,
    generated_at: str,
    reference_date: date,
    extra: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(row) | extra
    enriched.update(
        build_price_sanity_from_row(
            enriched,
            reference_date=reference_date,
            scan_generated_at=generated_at,
        )
    )
    return enriched


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        existing = best.get(ticker)
        if existing is None or _row_rank(row) < _row_rank(existing):
            best[ticker] = row
    return sorted(best.values(), key=lambda row: (_row_rank(row), str(row.get("ticker"))))


def _dedupe_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        ticker = str(decision.get("ticker") or "").upper()
        if not ticker:
            continue
        existing = best.get(ticker)
        if existing is None or _decision_rank(decision) < _decision_rank(existing):
            best[ticker] = decision
    return sorted(best.values(), key=lambda row: (_decision_rank(row), str(row.get("ticker"))))


def _row_rank(row: dict[str, Any]) -> tuple[int, int, float]:
    status = _validation_order(str(row.get("price_validation_status") or row.get("price_sanity", {}).get("price_validation_status") or "FAIL"))
    lane = _lane_order(str(row.get("decision_source_lane") or ""))
    score = -float(row.get("regular_investing_score") or row.get("outlier_score") or row.get("velocity_score") or 0)
    return (status, lane, score)


def _decision_rank(decision: dict[str, Any]) -> tuple[int, int, int, float]:
    status = _validation_order(str(decision.get("price_validation_status") or "FAIL"))
    action = _action_order(str(decision.get("primary_action") or "Data Insufficient"))
    lane = _lane_order(str(decision.get("action_lane") or ""))
    score = -float(decision.get("score") or 0)
    return (status, action, lane, score)


def _validation_order(status: str) -> int:
    return {"PASS": 0, "WARN": 1, "FAIL": 2}.get(status, 3)


def _lane_order(lane: str) -> int:
    return {"Core Investing": 0, "Outlier": 1, "Velocity": 2}.get(lane, 3)


def _action_order(action: str) -> int:
    return {
        "Research / Buy Candidate": 0,
        "Add": 1,
        "Hold": 2,
        "Trim": 3,
        "Sell / Exit Candidate": 4,
        "Watch": 5,
        "Watch Closely": 6,
        "Avoid": 7,
        "Data Insufficient": 8,
    }.get(action, 9)


def _pick_market_regime(scan_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    for item in scan_summaries:
        regime = item.get("market_regime") or {}
        if regime:
            return regime
    return {}


def _universe_for_lane(
    lane: str,
    *,
    core_universe: Path,
    outlier_universe: Path,
    velocity_universe: Path,
) -> str:
    if lane == "Core Investing":
        return str(core_universe)
    if lane == "Outlier":
        return str(outlier_universe)
    return str(velocity_universe)


def _build_daily_decision_markdown(payload: dict[str, Any]) -> str:
    top_candidate = payload.get("top_candidate")
    research_candidates = payload.get("research_candidates", [])
    watch_candidates = payload.get("watch_candidates", [])
    avoid_candidates = payload.get("avoid_candidates", [])
    data_issues = payload.get("data_issues", [])
    lines = [
        "# TradeBruv Daily Pick",
        "",
        f"- Generated: {payload.get('generated_at', 'unavailable')}",
        f"- Analysis date: {payload.get('analysis_date', 'unavailable')}",
        f"- Provider: {payload.get('provider', 'unavailable')}",
        f"- Demo mode: {payload.get('demo_mode', False)}",
        "",
    ]
    if top_candidate:
        lines.extend(
            [
                "## Top Candidate",
                f"Ticker: {top_candidate.get('ticker')}",
                f"Action: {top_candidate.get('primary_action')}",
                f"Actionability: {top_candidate.get('actionability_label')} ({top_candidate.get('actionability_score')})",
                f"Why now: {top_candidate.get('actionability_reason') or top_candidate.get('reason')}",
                f"Why not: {top_candidate.get('why_not')}",
                f"{top_candidate.get('entry_label', 'Entry')}: {top_candidate.get('entry_zone')}",
                f"Stop: {top_candidate.get('stop_loss')}",
                f"TP1: {top_candidate.get('tp1')}",
                f"TP2: {top_candidate.get('tp2')}",
                f"Data freshness: {top_candidate.get('data_freshness')}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "# No Clean Candidate Today",
                f"Reason: {payload.get('no_clean_candidate_reason') or 'No validated setup passed the actionability gate.'}",
                "",
                "Best Watch Names:",
            ]
        )
        if watch_candidates:
            for row in watch_candidates[:5]:
                lines.append(f"- {row.get('ticker')}: {row.get('action_trigger')}")
        else:
            lines.append("- None.")
    lines.extend(["", "## Next 3 Research Candidates"])
    if not research_candidates:
        lines.append("- None.")
    else:
        for row in research_candidates[:3]:
            lines.append(
                f"- {row.get('ticker')}: {row.get('actionability_label')} | {row.get('reason')} | {row.get('entry_label')}: {row.get('entry_zone')}"
            )
    lines.extend(["", "## Watch / Wait"])
    if not watch_candidates:
        lines.append("- None.")
    else:
        for row in watch_candidates[:5]:
            lines.append(f"- {row.get('ticker')}: {row.get('actionability_label')} | trigger {row.get('action_trigger')}")
    lines.extend(["", "## Avoid / Do Not Chase"])
    if not avoid_candidates:
        lines.append("- None.")
    else:
        for row in avoid_candidates[:5]:
            lines.append(f"- {row.get('ticker')}: {row.get('why_not') or row.get('reason')}")
    if data_issues:
        lines.extend(["", "## Data Issues"])
        for row in data_issues[:10]:
            lines.append(f"- {row.get('ticker')}: {row.get('price_validation_reason') or row.get('reason')}")
    return "\n".join(lines)


def _build_decision_quality_review(payload: dict[str, Any]) -> str:
    top_candidate = payload.get("top_candidate")
    research_candidates = payload.get("research_candidates", [])
    watch_candidates = payload.get("watch_candidates", [])
    decisions = payload.get("decisions", [])
    excluded = [row for row in decisions if row.get("actionability_label") in {"Avoid / Do Not Chase", "Data Insufficient"}]
    tracked = {str(row.get("ticker")): row for row in decisions}
    excluded_summary = ", ".join(
        f"{row.get('ticker')} ({row.get('actionability_label')})"
        for row in excluded[:10]
    ) or "None"
    ticker_summary = "; ".join(
        f"{ticker}: {tracked.get(ticker, {}).get('actionability_label', 'missing')}"
        for ticker in ("NVDA", "PLTR", "MU")
    )
    watch_trigger_summary = (
        "N/A (no watch names)"
        if not watch_candidates
        else "Yes" if all(row.get("action_trigger") for row in watch_candidates) else "No"
    )
    lines = [
        "# Decision Quality Review",
        "",
        f"- Did the system produce a top candidate? {'Yes' if top_candidate else 'No'}",
        f"- If not, why not? {payload.get('no_clean_candidate_reason') or 'A top candidate was available.'}",
        f"- What are the top 3 research candidates? {', '.join(str(row.get('ticker')) for row in research_candidates[:3]) or 'None'}",
        f"- What are the best watch names? {', '.join(str(row.get('ticker')) for row in watch_candidates[:5]) or 'None'}",
        f"- Which names were excluded and why? {excluded_summary}",
        f"- Are NVDA/PLTR/MU classified clearly? {ticker_summary}",
        f"- Are 'Watch' names given triggers? {watch_trigger_summary}",
        f"- Are TP/SL levels hidden/conditional/actionable correctly? {'Yes' if all(row.get('level_status') in {'Actionable', 'Preliminary', 'Conditional', 'Hidden'} for row in decisions) else 'No'}",
        f"- Is the output readable in under 60 seconds? {'Yes' if len(research_candidates) <= 3 and len(watch_candidates) <= 5 else 'No'}",
        "",
    ]
    return "\n".join(lines)


def _build_picker_view(decisions: list[dict[str, Any]], *, data_issues: list[dict[str, Any]]) -> dict[str, Any]:
    actionable = [row for row in decisions if row.get("actionability_label") == "Actionable Today" and row.get("primary_action") == "Research / Buy Candidate"]
    research = [row for row in decisions if row.get("actionability_label") == "Research First" and row.get("primary_action") == "Research / Buy Candidate"]
    watch = [row for row in decisions if row.get("actionability_label") in {"Wait for Better Entry", "Watch for Trigger"}]
    avoid = [row for row in decisions if row.get("actionability_label") == "Avoid / Do Not Chase"]
    portfolio_actions = [row for row in decisions if row.get("action_lane") == "Portfolio" and row.get("primary_action") not in {"Data Insufficient", "Avoid"}][:5]
    top_candidate = actionable[0] if actionable else None
    research_candidates = [row for row in actionable[1:]] + research
    compact_board = [
        row
        for row in decisions
        if row.get("level_status") in {"Actionable", "Preliminary", "Conditional"}
    ][:8]
    no_clean_candidate_reason = ""
    if not top_candidate:
        if data_issues and len(data_issues) == len(decisions):
            no_clean_candidate_reason = "Every candidate failed the live price or freshness gate."
        elif watch:
            no_clean_candidate_reason = "The best names are valid, but they still need a trigger or a better entry."
        elif research:
            no_clean_candidate_reason = "There are research names, but none are clean enough to call actionable today."
        else:
            no_clean_candidate_reason = "No validated setup passed the actionability threshold."
    return {
        "top_candidate": top_candidate,
        "research_candidates": research_candidates[:3],
        "watch_candidates": watch[:5],
        "avoid_candidates": avoid[:5],
        "portfolio_actions": portfolio_actions,
        "compact_board": compact_board,
        "no_clean_candidate_reason": no_clean_candidate_reason,
    }
