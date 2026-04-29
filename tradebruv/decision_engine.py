from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

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
    levels_visible = bool(price_sanity.get("levels_allowed"))
    owned = portfolio_row is not None
    portfolio_decision = build_portfolio_recommendation(position=portfolio_row, scanner_row=row) if owned else None
    action_lane = _action_lane(row, portfolio_decision, preferred_lane=preferred_lane)
    primary_action = _primary_action(row, portfolio_decision, price_sanity, owned=owned)
    risk_level = _risk_level(row, portfolio_decision)
    confidence_label = _confidence_label(row, price_sanity, validation_context)
    evidence_strength = str((validation_context or {}).get("evidence_strength") or "Not enough evidence yet")
    entry_zone = str(row.get("entry_zone") or "unavailable") if levels_visible else "unavailable"
    stop_loss = (row.get("stop_loss_reference") or row.get("invalidation_level") or "unavailable") if levels_visible else "unavailable"
    invalidation = (portfolio_decision.get("invalidation_level") if portfolio_decision else row.get("invalidation_level", "unavailable")) if levels_visible else "unavailable"
    next_review_date = _next_review_date(primary_action, price_sanity)
    reason = _reason(row, portfolio_decision, primary_action, validation_context)
    why_not = _why_not(row, portfolio_decision, price_sanity)
    if not levels_visible:
        reason = "No validated live price. Levels hidden."

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
        "is_actionable": levels_visible and primary_action != "Data Insufficient",
        "price_sanity": price_sanity,
        "next_review_date": next_review_date,
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
    if str(row.get("status_label")) == "Avoid":
        return "Avoid"
    if str(row.get("investing_action_label")) in {"High Priority Research", "Buy Candidate"}:
        return "Research / Buy Candidate"
    if str(row.get("investing_action_label")) == "Hold":
        return "Watch" if not owned else "Hold"
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
) -> str:
    if primary_action == "Data Insufficient" and row.get("ticker"):
        return "No validated live price. Levels hidden."
    if portfolio_decision:
        for key in ("reason_to_add", "reason_to_hold", "reason_to_trim", "reason_to_exit"):
            value = str(portfolio_decision.get(key) or "")
            if value and "not confirmed" not in value.lower() and "no " not in value.lower():
                return value
    if primary_action == "Avoid":
        return str(row.get("investing_bear_case") or row.get("outlier_reason") or "Risk/reward is not clean enough.")
    if primary_action == "Research / Buy Candidate":
        return str(row.get("investing_reason") or row.get("outlier_reason") or "Deterministic setup is worth deeper research.")
    validation_messages = (validation_context or {}).get("messages") or []
    if validation_messages:
        return str(validation_messages[0])
    return str(row.get("trigger_reason") or row.get("outlier_reason") or "Wait for clearer confirmation.")


def _why_not(row: dict[str, Any], portfolio_decision: dict[str, Any] | None, price_sanity: dict[str, Any]) -> str:
    warnings = list(row.get("warnings") or []) + list(row.get("why_it_could_fail") or [])
    if portfolio_decision:
        warnings.extend(
            str(portfolio_decision.get(key))
            for key in ("concentration_warning", "valuation_or_overextension_warning", "broken_trend_warning")
            if portfolio_decision.get(key)
        )
    warnings.extend(price_sanity.get("price_warnings") or [])
    validation_reason = str(price_sanity.get("price_validation_reason") or "")
    if validation_reason and validation_reason != "Validated live price.":
        warnings.append(validation_reason)
    warnings = [warning for warning in warnings if warning and "No " not in str(warning)]
    if not warnings:
        return "No major counter-thesis beyond routine review discipline."
    return " | ".join(dict.fromkeys(str(warning) for warning in warnings[:4]))


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
