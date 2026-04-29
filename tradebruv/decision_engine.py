from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from .actionability import build_actionability_profile, evidence_pill
from .analysis import build_portfolio_recommendation
from .portfolio import _as_position
from .price_sanity import build_price_sanity_from_row


def build_unified_decisions(
    rows: Iterable[dict[str, Any]],
    *,
    portfolio_rows: Iterable[dict[str, Any]] | None = None,
    scan_generated_at: str | None = None,
    validation_context: dict[str, Any] | None = None,
    reference_date: date | None = None,
    preferred_lane: str | None = None,
) -> list[dict[str, Any]]:
    portfolio_map = {str(row.get("ticker", "")).upper(): row for row in (portfolio_rows or []) if row.get("ticker")}
    decisions = [
        build_unified_decision(
            row,
            portfolio_row=portfolio_map.get(str(row.get("ticker", "")).upper()),
            scan_generated_at=scan_generated_at,
            validation_context=validation_context,
            reference_date=reference_date,
            preferred_lane=preferred_lane,
        )
        for row in rows
    ]
    return sorted(
        decisions,
        key=lambda row: (
            _actionability_priority(str(row.get("actionability_label") or "Data Insufficient")),
            -_to_float(row.get("actionability_score"), default=0),
            _priority(row["primary_action"]),
            -_to_float(row.get("score"), default=0),
            row["ticker"],
        ),
    )


def build_unified_decision(
    row: dict[str, Any],
    *,
    portfolio_row: dict[str, Any] | None = None,
    scan_generated_at: str | None = None,
    validation_context: dict[str, Any] | None = None,
    reference_date: date | None = None,
    preferred_lane: str | None = None,
) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "UNKNOWN").upper()
    price_sanity = build_price_sanity_from_row(row, reference_date=reference_date, scan_generated_at=scan_generated_at)
    owned = portfolio_row is not None
    portfolio_decision = build_portfolio_recommendation(position=portfolio_row, scanner_row=row) if owned else None
    action_lane = _action_lane(row, portfolio_decision, preferred_lane=preferred_lane)
    risk_level = _risk_level(row, portfolio_decision)
    actionability = build_actionability_profile(
        row,
        price_sanity=price_sanity,
        risk_level=risk_level,
        portfolio_decision=portfolio_decision,
    )
    levels_visible = actionability["level_status"] != "Hidden"
    primary_action = _primary_action(row, portfolio_decision, price_sanity, actionability, owned=owned)
    confidence_label = _confidence_label(row, price_sanity, validation_context)
    evidence_strength = str((validation_context or {}).get("evidence_strength") or "Not enough evidence yet")
    base_entry_zone = str(row.get("entry_zone") or "unavailable")
    base_stop_loss = row.get("stop_loss_reference") or row.get("invalidation_level") or "unavailable"
    base_invalidation = portfolio_decision.get("invalidation_level") if portfolio_decision else row.get("invalidation_level", "unavailable")
    entry_zone = base_entry_zone if levels_visible else "unavailable"
    stop_loss = base_stop_loss if levels_visible else "unavailable"
    invalidation = base_invalidation if levels_visible else "unavailable"
    next_review_date = _next_review_date(primary_action, price_sanity)
    reason = _reason(row, portfolio_decision, primary_action, validation_context, actionability)
    why_not = _why_not(row, portfolio_decision, price_sanity, actionability)

    return {
        "ticker": ticker,
        "company": row.get("company_name", "unavailable"),
        "primary_action": primary_action,
        "action_lane": action_lane,
        "score": max(
            _to_float(row.get("regular_investing_score"), default=0),
            _to_float(row.get("outlier_score"), default=0),
            _to_float(row.get("velocity_score"), default=0),
        ),
        "confidence_label": confidence_label,
        "evidence_strength": evidence_strength,
        "risk_level": risk_level,
        "entry_zone": entry_zone,
        "stop_loss": stop_loss,
        "invalidation": invalidation,
        "tp1": row.get("tp1", "unavailable") if levels_visible else "unavailable",
        "tp2": row.get("tp2", "unavailable") if levels_visible else "unavailable",
        "reward_risk": row.get("reward_risk", "unavailable") if levels_visible else "unavailable",
        "holding_horizon": row.get("investing_time_horizon") or row.get("expected_horizon") or row.get("holding_period") or "unavailable",
        "reason": reason,
        "why_not": why_not,
        "events_to_watch": list(row.get("investing_events_to_watch") or row.get("why_it_could_fail") or row.get("warnings") or []),
        "data_quality": row.get("investing_data_quality") or row.get("data_availability_notes", []),
        "data_freshness": "Stale scan" if price_sanity["scan_is_stale"] else "Fresh enough",
        "price_source": price_sanity.get("validated_price_source") or price_sanity.get("price_source"),
        "latest_market_date": price_sanity.get("last_market_date"),
        "price_validation_status": price_sanity.get("price_validation_status"),
        "price_validation_reason": price_sanity.get("price_validation_reason"),
        "is_actionable": actionability["actionability_label"] == "Actionable Today",
        "is_conditional": actionability["level_status"] == "Conditional",
        "is_preliminary": actionability["level_status"] == "Preliminary",
        "actionability_score": actionability["actionability_score"],
        "actionability_label": actionability["actionability_label"],
        "actionability_reason": actionability["actionability_reason"],
        "actionability_blockers": actionability["actionability_blockers"],
        "action_trigger": actionability["action_trigger"],
        "trigger_needed": actionability["trigger_needed"],
        "current_setup_state": actionability["current_setup_state"],
        "level_status": actionability["level_status"],
        "entry_label": actionability["entry_label"],
        "levels_explanation": actionability["levels_explanation"],
        "evidence_pill": evidence_pill(validation_context),
        "price_sanity": price_sanity,
        "next_review_date": next_review_date,
        "source_group": row.get("scan_source_group") or action_lane,
        "portfolio_context": portfolio_decision,
        "validation_context": validation_context or {},
        "source_row": row,
    }


def build_validation_context(
    *,
    investing_proof_report: dict[str, Any] | None = None,
    proof_report: dict[str, Any] | None = None,
    signal_quality_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = investing_proof_report or proof_report or {}
    answers = source.get("answers", {}) if isinstance(source.get("answers"), dict) else {}
    messages: list[str] = []

    beat_spy = str(answers.get("does_regular_investing_score_beat_SPY") or "")
    beat_qqq = str(answers.get("does_regular_investing_score_beat_QQQ") or "")
    beat_random = str(answers.get("does_it_beat_random_baseline") or "")
    signal_conclusion = str((signal_quality_report or {}).get("conclusion") or "")

    if beat_spy.startswith("Yes") and beat_qqq.startswith("Yes") and beat_random.startswith("No"):
        messages.append("This strategy beat SPY/QQQ but did not beat random baseline.")
    elif beat_spy.startswith("Yes") or beat_qqq.startswith("Yes"):
        messages.append("This strategy beat SPY/QQQ in the latest replay window.")

    if "false-positive" in signal_conclusion.lower():
        messages.append("This bucket has high false-positive risk.")
    elif signal_conclusion:
        messages.append(signal_conclusion)

    if source.get("real_money_reliance") is False:
        messages.append("This label is paper-track only.")
    if not messages:
        messages.append("Not enough evidence yet.")

    return {
        "evidence_strength": source.get("evidence_strength", "Not enough evidence yet"),
        "real_money_reliance": bool(source.get("real_money_reliance", False)),
        "language_note": source.get("language_note") or "Historical evidence only.",
        "messages": list(dict.fromkeys(messages)),
        "proof_report_path": _guess_report_path("outputs/investing/investing_proof_report.json"),
        "signal_quality_path": _guess_report_path("outputs/signal_quality_report.json"),
    }


def _primary_action(
    row: dict[str, Any],
    portfolio_decision: dict[str, Any] | None,
    price_sanity: dict[str, Any],
    actionability: dict[str, Any],
    *,
    owned: bool,
) -> str:
    if price_sanity.get("price_validation_status") != "PASS":
        return "Data Insufficient"
    if portfolio_decision:
        mapping = {
            "Strong Hold": "Hold",
            "Hold": "Hold",
            "Add on Strength": "Add",
            "Add on Better Entry": "Add",
            "Trim": "Trim",
            "Exit / Sell Candidate": "Sell / Exit Candidate",
            "Watch Closely": "Watch Closely",
            "Avoid Adding": "Avoid",
            "Data Insufficient": "Data Insufficient",
        }
        return mapping.get(str(portfolio_decision.get("recommendation_label")), "Hold")
    label = str(actionability.get("actionability_label") or "Data Insufficient")
    if label == "Data Insufficient":
        return "Data Insufficient"
    if label == "Avoid / Do Not Chase" or str(row.get("status_label")) == "Avoid":
        return "Avoid"
    if label in {"Actionable Today", "Research First"}:
        return "Research / Buy Candidate"
    if label in {"Wait for Better Entry", "Watch for Trigger"}:
        return "Watch" if not owned else "Hold"
    if str(row.get("investing_action_label")) == "Hold":
        return "Hold" if owned else "Watch"
    if _to_float(row.get("velocity_score"), default=0) >= 45:
        return "Watch"
    if _to_float(row.get("outlier_score"), default=0) >= 50:
        return "Research / Buy Candidate"
    return "Watch"


def _action_lane(row: dict[str, Any], portfolio_decision: dict[str, Any] | None, *, preferred_lane: str | None = None) -> str:
    if portfolio_decision:
        return "Portfolio"
    if preferred_lane in {"Core Investing", "Outlier", "Velocity", "Mixed"}:
        return preferred_lane
    regular_score = _to_float(row.get("regular_investing_score"), default=0)
    outlier_score = _to_float(row.get("outlier_score"), default=0)
    velocity_score = _to_float(row.get("velocity_score"), default=0)
    if regular_score >= outlier_score and regular_score >= velocity_score:
        return "Core Investing"
    if velocity_score > regular_score and velocity_score > outlier_score:
        return "Velocity"
    if outlier_score > 0 and velocity_score > 0:
        return "Mixed"
    return "Outlier"


def _risk_level(row: dict[str, Any], portfolio_decision: dict[str, Any] | None) -> str:
    if portfolio_decision and portfolio_decision.get("concentration_risk"):
        return str(portfolio_decision["concentration_risk"])
    return str(row.get("investing_risk") or row.get("outlier_risk") or row.get("velocity_risk") or "Unknown")


def _confidence_label(row: dict[str, Any], price_sanity: dict[str, Any], validation_context: dict[str, Any] | None) -> str:
    confidence = str(row.get("confidence_label") or "Low")
    if price_sanity.get("price_validation_status") != "PASS" or price_sanity["scan_is_stale"]:
        return "Low"
    if "Not enough evidence" in str((validation_context or {}).get("evidence_strength", "")) and confidence in {"Very High", "High"}:
        return "Medium"
    if price_sanity["price_confidence"] == "Medium" and confidence == "Very High":
        return "High"
    return confidence


def _reason(
    row: dict[str, Any],
    portfolio_decision: dict[str, Any] | None,
    primary_action: str,
    validation_context: dict[str, Any] | None,
    actionability: dict[str, Any],
) -> str:
    if primary_action == "Data Insufficient" and row.get("ticker"):
        return "No validated live price. Levels hidden."
    if portfolio_decision:
        for key in ("reason_to_add", "reason_to_hold", "reason_to_trim", "reason_to_exit"):
            value = str(portfolio_decision.get(key) or "")
            if value and "not confirmed" not in value.lower() and "no " not in value.lower():
                return value
    label = str(actionability.get("actionability_label") or "")
    if label == "Actionable Today":
        return str(row.get("investing_reason") or row.get("outlier_reason") or "Validated price and current setup make this actionable today.")
    if label == "Research First":
        return str(actionability.get("actionability_reason") or "Worth researching first, but not clean enough for an immediate entry.")
    if label == "Wait for Better Entry":
        return str(actionability.get("actionability_reason") or "Valid price, but the setup is extended and needs a better entry.")
    if label == "Watch for Trigger":
        return str(actionability.get("actionability_reason") or "Interesting setup, but it needs a trigger before it becomes actionable.")
    if primary_action == "Avoid":
        return str(row.get("investing_bear_case") or row.get("outlier_reason") or "Risk/reward is not clean enough.")
    if primary_action == "Research / Buy Candidate":
        return str(row.get("investing_reason") or row.get("outlier_reason") or "Deterministic setup is worth deeper research.")
    return str(actionability.get("action_trigger") or row.get("trigger_reason") or row.get("outlier_reason") or "Wait for clearer confirmation.")


def _why_not(
    row: dict[str, Any],
    portfolio_decision: dict[str, Any] | None,
    price_sanity: dict[str, Any],
    actionability: dict[str, Any],
) -> str:
    warnings = list(row.get("warnings") or []) + list(row.get("why_it_could_fail") or [])
    if portfolio_decision:
        warnings.extend(
            str(portfolio_decision.get(key))
            for key in ("concentration_warning", "valuation_or_overextension_warning", "broken_trend_warning")
            if portfolio_decision.get(key)
        )
    warnings.extend(
        warning
        for warning in (price_sanity.get("price_warnings") or [])
        if "Sample data" not in str(warning)
    )
    validation_reason = str(price_sanity.get("price_validation_reason") or "")
    if validation_reason and validation_reason != "Validated live price." and actionability.get("actionability_label") == "Data Insufficient":
        warnings.append(validation_reason)
    warnings.extend(actionability.get("actionability_blockers") or [])
    warnings = [
        warning
        for warning in warnings
        if warning
        and "No " not in str(warning)
        and "strategy beat" not in str(warning).lower()
    ]
    if not warnings:
        return "No major counter-thesis beyond routine review discipline."
    return " | ".join(dict.fromkeys(str(warning) for warning in warnings[:2]))


def _next_review_date(primary_action: str, price_sanity: dict[str, Any]) -> str:
    today = date.today()
    if price_sanity["scan_is_stale"]:
        return today.isoformat()
    days = 1 if primary_action in {"Sell / Exit Candidate", "Avoid", "Watch Closely"} else 3 if primary_action in {"Add", "Trim"} else 7
    return (today + timedelta(days=days)).isoformat()


def _priority(action: str) -> int:
    order = {
        "Research / Buy Candidate": 0,
        "Add": 1,
        "Hold": 2,
        "Trim": 3,
        "Sell / Exit Candidate": 4,
        "Watch": 5,
        "Watch Closely": 6,
        "Avoid": 7,
        "Data Insufficient": 8,
    }
    return order.get(action, 9)


def _actionability_priority(label: str) -> int:
    order = {
        "Actionable Today": 0,
        "Research First": 1,
        "Wait for Better Entry": 2,
        "Watch for Trigger": 3,
        "Avoid / Do Not Chase": 4,
        "Data Insufficient": 5,
    }
    return order.get(label, 6)


def _to_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, "", "unavailable", "None"):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _guess_report_path(path_str: str) -> str | None:
    path = Path(path_str)
    return str(path) if path.exists() else None
