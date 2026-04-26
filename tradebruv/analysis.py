from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any, Iterable

from .journal import read_journal
from .portfolio import PortfolioPosition, _as_position, portfolio_summary
from .providers import MarketDataProvider
from .scanner import DeterministicScanner


PORTFOLIO_RECOMMENDATION_LABELS = (
    "Strong Hold",
    "Hold",
    "Add on Strength",
    "Add on Better Entry",
    "Trim",
    "Exit / Sell Candidate",
    "Watch Closely",
    "Avoid Adding",
    "Data Insufficient",
)

DEEP_RESEARCH_LABELS = (
    "Strong Buy Candidate",
    "Buy Candidate",
    "Hold / Watch",
    "Wait for Better Entry",
    "Avoid",
    "Sell / Exit Candidate",
    "Data Insufficient",
)


def analyze_portfolio(
    *,
    positions: Iterable[PortfolioPosition | dict[str, Any]],
    provider: MarketDataProvider,
    analysis_date: date | None = None,
) -> dict[str, Any]:
    rows = [_as_position(row) for row in positions]
    scanner = DeterministicScanner(provider=provider, analysis_date=analysis_date)
    results_by_ticker = {result.ticker: result.to_dict() for result in scanner.scan([row.ticker for row in rows], mode="outliers")}
    analyses = [
        build_portfolio_recommendation(position=row, scanner_row=results_by_ticker.get(row.ticker, {}))
        for row in rows
    ]
    return {
        "generated_at": _iso_now(),
        "positions": analyses,
        "summary": build_portfolio_analyst_summary(analyses),
        "portfolio_summary": portfolio_summary(rows),
        "safety": "Research support only. No broker execution or order placement exists.",
    }


def build_portfolio_recommendation(
    *,
    position: PortfolioPosition | dict[str, Any],
    scanner_row: dict[str, Any],
) -> dict[str, Any]:
    position_obj = _as_position(position)
    scanner = _normalize_scanner_row(scanner_row, position_obj.ticker)
    weight = position_obj.position_weight_pct
    risk_score = _to_float(scanner.get("risk_score"))
    winner_score = _to_float(scanner.get("winner_score"))
    outlier_score = _to_float(scanner.get("outlier_score"))
    regular_score = _to_float(scanner.get("regular_investing_score"))
    setup_quality = _to_float(scanner.get("setup_quality_score"))
    current_price = _to_float(scanner.get("current_price")) or position_obj.current_price
    if current_price:
        position_obj.current_price = current_price
        position_obj.market_value = 0
        position_obj.recalculate()
        weight = position_obj.position_weight_pct
    avg_cost = position_obj.average_cost
    invalidation = _first_number(position_obj.stop_or_invalidation) or _to_float(scanner.get("invalidation_level"), default=0)
    target = _first_number(position_obj.target_price) or _to_float(scanner.get("tp1"), default=0)
    near_invalidation = bool(invalidation and current_price and current_price <= invalidation * 1.04)
    near_target = bool(target and current_price and current_price >= target * 0.97)
    concentration = weight >= 20
    broken_setup = scanner.get("investing_action_label") == "Exit / Sell Candidate" or scanner.get("status_label") == "Avoid" or risk_score >= 75 or near_invalidation
    strong_setup = regular_score >= 70 or (scanner.get("status_label") in {"Strong Research Candidate", "Active Setup"} and setup_quality >= 70)
    overextended = "extended" in str(scanner.get("investing_bear_case", "")).lower() or any("extended" in str(warning).lower() for warning in scanner.get("warnings", []))
    weak_regular = regular_score < 45 or scanner.get("investing_action_label") in {"Avoid", "Data Insufficient"}
    profitable = bool(avg_cost and current_price and current_price > avg_cost)

    if not scanner_row or current_price <= 0:
        label = "Data Insufficient"
    elif broken_setup and near_invalidation:
        label = "Exit / Sell Candidate"
    elif broken_setup:
        label = "Avoid Adding" if not position_obj.quantity else "Watch Closely"
    elif weak_regular and position_obj.quantity:
        label = "Watch Closely"
    elif weak_regular:
        label = "Avoid Adding"
    elif concentration and (near_target or risk_score >= 55 or regular_score < 65):
        label = "Trim"
    elif strong_setup and overextended and not concentration:
        label = "Add on Better Entry"
    elif strong_setup and regular_score >= 75 and risk_score <= 40 and not concentration:
        label = "Add on Strength"
    elif strong_setup and not near_target and risk_score <= 45:
        label = "Strong Hold" if position_obj.quantity else "Add on Better Entry"
    elif regular_score >= 55 and risk_score <= 60:
        label = "Hold"
    else:
        label = "Watch Closely"

    core_decision = label
    concentration_warning = "Position concentration is high; adding may be inappropriate." if concentration else "No concentration warning."
    overextension_warning = "Good long-term candidate but overextended; consider better entry discipline." if overextended else "No valuation or overextension warning."
    broken_trend_warning = "Trend or thesis appears broken; review exit risk before adding." if broken_setup else "No broken-trend warning."
    reason_to_exit = _reason_to_exit(scanner, near_invalidation, broken_setup)
    confidence = _confidence_label(scanner, label)
    conviction = _conviction_score(winner_score, outlier_score, setup_quality, risk_score, weight)
    action_urgency = _action_urgency(label, near_invalidation, near_target, concentration)
    data_quality = _data_quality(scanner)
    next_review = date.today() + timedelta(days=3 if action_urgency == "High" else 7 if action_urgency == "Medium" else 14)
    reason_to_hold = _reason_to_hold(scanner, position_obj, profitable)
    reason_to_add = _reason_to_add(scanner, concentration, near_target)
    reason_to_trim = _reason_to_trim(scanner, concentration, near_target, near_invalidation)

    return {
        "ticker": position_obj.ticker,
        "company_name": position_obj.company_name or scanner.get("company_name", "unavailable"),
        "account_name": position_obj.account_name,
        "quantity": position_obj.quantity,
        "current_price": _round(current_price),
        "average_cost": _round(avg_cost),
        "market_value": _round(position_obj.market_value),
        "position_weight_pct": _round(weight),
        "scanner_status": scanner.get("status_label"),
        "winner_score": scanner.get("winner_score"),
        "regular_investing_score": scanner.get("regular_investing_score"),
        "investing_style": scanner.get("investing_style"),
        "investing_action_label": scanner.get("investing_action_label"),
        "investing_risk": scanner.get("investing_risk"),
        "outlier_score": scanner.get("outlier_score"),
        "risk_score": scanner.get("risk_score"),
        "setup_quality": scanner.get("setup_quality_score"),
        "trend_status": _trend_status(scanner),
        "relative_strength": _note_contains(scanner, "relative strength"),
        "momentum_status": _note_contains(scanner, "momentum", "trend", "breakout"),
        "fundamental_support": scanner.get("component_scores", {}).get("fundamental_support", "unavailable"),
        "news_catalyst_status": scanner.get("catalyst_quality", "Unavailable"),
        "current_vs_average_cost_pct": _round(((current_price - avg_cost) / avg_cost) * 100) if avg_cost and current_price else 0,
        "current_vs_invalidation_pct": _round(((current_price - invalidation) / invalidation) * 100) if invalidation and current_price else "unavailable",
        "current_vs_target_pct": _round(((target - current_price) / current_price) * 100) if target and current_price else "unavailable",
        "concentration_risk": "High" if concentration else ("Medium" if weight >= 10 else "Low"),
        "theme_overlap": position_obj.theme_tags or "unavailable",
        "thesis_match": _thesis_match(position_obj, scanner),
        "recommendation_label": label,
        "core_investing_decision": core_decision,
        "confidence_label": confidence,
        "conviction_score": conviction,
        "action_urgency": action_urgency,
        "reason_to_hold": reason_to_hold,
        "reason_to_add": reason_to_add,
        "reason_to_trim": reason_to_trim,
        "reason_to_exit": reason_to_exit,
        "reason_to_trim_or_sell": reason_to_trim if label != "Exit / Sell Candidate" else reason_to_exit,
        "thesis_status": _thesis_status(scanner, broken_setup),
        "concentration_warning": concentration_warning,
        "valuation_or_overextension_warning": overextension_warning,
        "broken_trend_warning": broken_trend_warning,
        "review_priority": _review_priority(label, near_invalidation, concentration, broken_setup),
        "next_review_trigger": _next_review_trigger(scanner, position_obj),
        "events_to_watch": _events_to_watch(scanner),
        "invalidation_level": invalidation or scanner.get("invalidation_level", "unavailable"),
        "risk_to_portfolio": _risk_to_portfolio(weight, risk_score, scanner),
        "suggested_review_date": next_review.isoformat(),
        "data_quality": data_quality,
        "warnings": scanner.get("warnings", []),
        "scanner_row": scanner,
    }


def build_portfolio_analyst_summary(analyses: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(analyses)
    return {
        "review_today": [row for row in rows if row["action_urgency"] == "High" or row["recommendation_label"] in {"Watch Closely", "Exit / Sell Candidate"}],
        "consider_adding": [row for row in rows if row["recommendation_label"] in {"Add on Strength", "Add on Better Entry"}],
        "consider_trimming": [row for row in rows if row["recommendation_label"] == "Trim"],
        "broken_setup": [row for row in rows if row["recommendation_label"] in {"Exit / Sell Candidate", "Avoid Adding"}],
        "catalyst_risk": [row for row in rows if "hype" in str(row.get("news_catalyst_status", "")).lower()],
        "high_concentration": [row for row in rows if row["concentration_risk"] == "High"],
        "thesis_changed": [row for row in rows if row["thesis_match"] == "Needs review"],
        "near_invalidation": [row for row in rows if row["current_vs_invalidation_pct"] != "unavailable" and _to_float(row["current_vs_invalidation_pct"]) <= 5],
        "near_target": [row for row in rows if row["current_vs_target_pct"] != "unavailable" and _to_float(row["current_vs_target_pct"]) <= 5],
    }


def deep_research(
    *,
    ticker: str,
    provider: MarketDataProvider,
    portfolio_positions: Iterable[PortfolioPosition | dict[str, Any]] | None = None,
    journal_rows: Iterable[dict[str, Any]] | None = None,
    analysis_date: date | None = None,
) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    scanner = DeterministicScanner(provider=provider, analysis_date=analysis_date)
    result = scanner.scan([ticker], mode="outliers")[0].to_dict()
    owned_position = next((_as_position(row) for row in (portfolio_positions or []) if _as_position(row).ticker == ticker), None)
    portfolio_advice = (
        build_portfolio_recommendation(position=owned_position, scanner_row=result)
        if owned_position
        else None
    )
    journal_matches = [row for row in (journal_rows or []) if str(row.get("ticker", "")).upper() == ticker]
    label = _deep_research_label(result, owned=owned_position is not None)
    data_quality = _data_quality(result)
    return {
        "ticker": ticker,
        "company_name": result.get("company_name", "unavailable"),
        "current_price": result.get("current_price", "unavailable"),
        "market_cap": result.get("data_used", {}).get("market_cap", "unavailable"),
        "sector": result.get("data_used", {}).get("sector", "unavailable"),
        "industry": result.get("data_used", {}).get("industry", "unavailable"),
        "price_chart_summary": _price_chart_summary(result),
        "trend_score": result.get("component_scores", {}).get("price_leadership", "unavailable"),
        "relative_strength": _note_contains(result, "relative strength"),
        "momentum_score": result.get("component_scores", {}).get("price_leadership", "unavailable"),
        "winner_score": result.get("winner_score"),
        "outlier_score": result.get("outlier_score"),
        "risk_score": result.get("risk_score"),
        "setup_quality": result.get("setup_quality_score"),
        "catalyst_news_social_summary": _catalyst_summary(result),
        "earnings_date": result.get("data_used", {}).get("next_earnings_date", "unavailable"),
        "earnings_guidance_notes": _available_note(result, "earnings", "guidance"),
        "analyst_revision_info": result.get("component_scores", {}).get("fundamental_support", "unavailable"),
        "institutional_insider_short_interest": result.get("squeeze_watch", {}),
        "key_risks": result.get("why_it_could_fail", []) + result.get("warnings", []),
        "bull_case": result.get("why_it_passed", []) + result.get("why_it_could_be_a_big_winner", []),
        "bear_case": result.get("why_it_could_fail", []),
        "events_to_watch": _events_to_watch(result),
        "entry_zone": result.get("entry_zone", "unavailable"),
        "invalidation": result.get("invalidation_level", "unavailable"),
        "tp1": result.get("tp1", "unavailable"),
        "tp2": result.get("tp2", "unavailable"),
        "reward_risk": result.get("reward_risk", "unavailable"),
        "current_status": result.get("status_label", "unavailable"),
        "portfolio_context": portfolio_advice or "Not owned in local portfolio.",
        "journal_history": journal_matches,
        "historical_review": "Use Validation Lab / Historical Review for saved signals.",
        "decision_card": {
            "research_recommendation": label,
            "confidence_label": result.get("confidence_label", "Low") if data_quality != "Weak" else "Low",
            "why_this_recommendation": _why_deep_label(label, result, owned_position),
            "what_would_change_the_recommendation": _what_would_change(result),
            "events_to_watch": _events_to_watch(result),
            "next_review_trigger": _next_review_trigger(result, owned_position),
            "data_quality": data_quality,
            "safety": "Research/action candidate inside your personal system, not a guarantee or order.",
        },
        "regular_investing_view": {
            "regular_investing_score": result.get("regular_investing_score"),
            "investing_action_label": result.get("investing_action_label"),
            "investing_style": result.get("investing_style"),
            "investing_risk": result.get("investing_risk"),
            "investing_time_horizon": result.get("investing_time_horizon"),
            "bull_case": result.get("investing_reason"),
            "bear_case": result.get("investing_bear_case"),
            "invalidation": result.get("investing_invalidation"),
            "events_to_watch": result.get("investing_events_to_watch"),
            "value_trap_warning": result.get("value_trap_warning"),
            "thesis_quality": result.get("thesis_quality"),
            "data_quality": result.get("investing_data_quality"),
            "safety": "Buy Candidate means research candidate, not an order.",
        },
        "scanner_row": result,
    }


def _deep_research_label(row: dict[str, Any], *, owned: bool) -> str:
    if _to_float(row.get("current_price")) <= 0:
        return "Data Insufficient"
    if row.get("investing_action_label") == "Data Insufficient":
        return "Data Insufficient"
    if owned and (row.get("status_label") == "Avoid" or _to_float(row.get("risk_score")) >= 75):
        return "Sell / Exit Candidate"
    if row.get("investing_action_label") in {"Buy Candidate", "High Priority Research"}:
        return "Buy Candidate"
    if row.get("investing_action_label") == "Hold":
        return "Hold / Watch"
    if row.get("status_label") == "Avoid":
        return "Avoid"
    if _to_float(row.get("winner_score")) >= 80 and _to_float(row.get("risk_score")) <= 35 and _to_float(row.get("setup_quality_score")) >= 70:
        return "Strong Buy Candidate"
    if _to_float(row.get("winner_score")) >= 65 and _to_float(row.get("risk_score")) <= 50:
        return "Buy Candidate"
    if _to_float(row.get("risk_score")) >= 60:
        return "Wait for Better Entry"
    return "Hold / Watch"


def _normalize_scanner_row(row: dict[str, Any], ticker: str) -> dict[str, Any]:
    if not row:
        return {
            "ticker": ticker,
            "status_label": "Data Insufficient",
            "winner_score": 0,
            "outlier_score": 0,
            "risk_score": 100,
            "setup_quality_score": 0,
            "warnings": ["Scanner data unavailable."],
            "why_it_passed": [],
            "why_it_could_fail": ["Scanner data unavailable."],
            "data_availability_notes": ["Missing scanner row."],
        }
    return row


def _confidence_label(row: dict[str, Any], label: str) -> str:
    if label == "Data Insufficient" or _data_quality(row) == "Weak":
        return "Low"
    if _to_float(row.get("setup_quality_score")) >= 75 and _to_float(row.get("risk_score")) <= 35:
        return "High"
    if _to_float(row.get("setup_quality_score")) >= 55:
        return "Medium"
    return "Low"


def _conviction_score(winner: float, outlier: float, setup: float, risk: float, weight: float) -> int:
    penalty = 10 if weight >= 20 else 5 if weight >= 10 else 0
    return int(max(0, min(100, (winner * 0.35) + (outlier * 0.25) + (setup * 0.25) + ((100 - risk) * 0.15) - penalty)))


def _action_urgency(label: str, near_invalidation: bool, near_target: bool, concentration: bool) -> str:
    if label == "Exit / Sell Candidate" or near_invalidation:
        return "High"
    if label in {"Trim", "Watch Closely", "Avoid Adding"} or near_target or concentration:
        return "Medium"
    return "Low"


def _data_quality(row: dict[str, Any]) -> str:
    notes = row.get("data_availability_notes", []) or []
    if _to_float(row.get("current_price")) <= 0:
        return "Weak"
    if "data fetch failed" in " ".join(map(str, notes)).lower():
        return "Weak"
    if "unavailable" in " ".join(map(str, notes)).lower():
        return "Partial"
    if notes:
        return "Partial"
    return "Good"


def _reason_to_hold(row: dict[str, Any], position: PortfolioPosition, profitable: bool) -> str:
    reasons = list(row.get("why_it_passed", [])[:2])
    if profitable:
        reasons.append("Position is above average cost.")
    if position.thesis:
        reasons.append(f"User thesis: {position.thesis}")
    return " | ".join(reasons) or "No strong hold reason available."


def _reason_to_add(row: dict[str, Any], concentration: bool, near_target: bool) -> str:
    if concentration:
        return "Do not add automatically: position is already concentrated."
    if near_target:
        return "Do not add automatically: price is near the entered/scanner target."
    regular_reason = row.get("investing_reason")
    return str(regular_reason) if regular_reason else " | ".join(row.get("why_it_passed", [])[:3]) or "Add case requires more evidence."


def _reason_to_trim(row: dict[str, Any], concentration: bool, near_target: bool, near_invalidation: bool) -> str:
    reasons = []
    if concentration:
        reasons.append("High position weight.")
    if near_target:
        reasons.append("Price is near target.")
    if near_invalidation:
        reasons.append("Price is near invalidation.")
    reasons.extend(row.get("why_it_could_fail", [])[:2])
    return " | ".join(reasons) or "No trim/sell reason confirmed."


def _reason_to_exit(row: dict[str, Any], near_invalidation: bool, broken_setup: bool) -> str:
    reasons = []
    if near_invalidation:
        reasons.append("Price is near or below invalidation.")
    if broken_setup:
        reasons.append("Core investing or scanner trend is broken enough to require review.")
    if row.get("value_trap_warning") and row.get("value_trap_warning") != "No value-trap warning.":
        reasons.append(str(row.get("value_trap_warning")))
    reasons.extend(row.get("why_it_could_fail", [])[:2])
    return " | ".join(reasons) or "Exit case is not confirmed; review manually."


def _thesis_status(row: dict[str, Any], broken_setup: bool) -> str:
    if broken_setup:
        return "Broken / needs review"
    if row.get("thesis_quality") in {"High", "Medium"}:
        return str(row.get("thesis_quality"))
    if row.get("investing_data_quality") == "Weak":
        return "Data Insufficient"
    return "Mixed"


def _review_priority(label: str, near_invalidation: bool, concentration: bool, broken_setup: bool) -> str:
    if near_invalidation or broken_setup or label == "Exit / Sell Candidate":
        return "High"
    if concentration or label in {"Trim", "Watch Closely", "Avoid Adding"}:
        return "Medium"
    return "Normal"


def _events_to_watch(row: dict[str, Any]) -> list[str]:
    events = []
    events.extend(str(item) for item in row.get("investing_events_to_watch", [])[:3])
    if row.get("catalyst_quality") and row.get("catalyst_quality") != "Unavailable":
        events.append(f"Catalyst: {row.get('catalyst_quality')} / {row.get('catalyst_type')}")
    for warning in row.get("warnings", [])[:3]:
        events.append(str(warning))
    if row.get("tp1") != "unavailable":
        events.append(f"TP1: {row.get('tp1')}")
    if row.get("invalidation_level") != "unavailable":
        events.append(f"Invalidation: {row.get('invalidation_level')}")
    return events or ["No specific event available; refresh scanner data before acting."]


def _risk_to_portfolio(weight: float, risk_score: float, row: dict[str, Any]) -> str:
    if weight >= 20 and risk_score >= 50:
        return "High: concentrated and scanner risk is elevated."
    if weight >= 20:
        return "High: concentration risk even if scanner setup is acceptable."
    if risk_score >= 65:
        return "High: scanner risk flags are elevated."
    if weight >= 10 or risk_score >= 45:
        return "Medium: monitor weight and setup."
    return "Low: no major portfolio-level risk flag."


def _thesis_match(position: PortfolioPosition, row: dict[str, Any]) -> str:
    if not position.thesis:
        return "No thesis recorded"
    failure_text = " ".join(row.get("why_it_could_fail", []) + row.get("warnings", [])).lower()
    return "Needs review" if any(word in failure_text for word in ("broken", "failed", "avoid", "hype")) else "Still plausible"


def _trend_status(row: dict[str, Any]) -> str:
    if row.get("status_label") in {"Strong Research Candidate", "Active Setup"}:
        return "Constructive"
    if row.get("status_label") == "Avoid":
        return "Broken/risky"
    return "Mixed/watch"


def _note_contains(row: dict[str, Any], *needles: str) -> str:
    text = " | ".join(row.get("why_it_passed", []) + row.get("signals_used", []) + row.get("warnings", []))
    matches = [item for item in text.split(" | ") if any(needle in item.lower() for needle in needles)]
    return " | ".join(matches[:3]) or "unavailable"


def _available_note(row: dict[str, Any], *needles: str) -> str:
    return _note_contains(row, *needles)


def _price_chart_summary(row: dict[str, Any]) -> str:
    return (
        f"Status {row.get('status_label', 'unavailable')}; strategy {row.get('strategy_label', 'unavailable')}; "
        f"entry {row.get('entry_zone', 'unavailable')}; invalidation {row.get('invalidation_level', 'unavailable')}."
    )


def _catalyst_summary(row: dict[str, Any]) -> str:
    return (
        f"{row.get('catalyst_quality', 'Unavailable')} catalyst quality; "
        f"{row.get('catalyst_source_count', 0)} source(s); social score {row.get('social_attention_score', 0)}."
    )


def _why_deep_label(label: str, row: dict[str, Any], owned: PortfolioPosition | None) -> str:
    reasons = []
    if owned:
        reasons.append("You own this in the local portfolio, so position cost, weight, and invalidation are included.")
    reasons.extend(row.get("why_it_passed", [])[:2])
    reasons.extend(row.get("why_it_could_fail", [])[:1])
    return f"{label}: " + (" | ".join(reasons) or "insufficient evidence for a stronger label.")


def _what_would_change(row: dict[str, Any]) -> list[str]:
    return [
        f"Break or reclaim scanner invalidation near {row.get('invalidation_level', 'unavailable')}.",
        "Fresh verified catalyst/news source changes the catalyst quality.",
        "Risk score or setup quality materially changes on a refreshed scan.",
    ]


def _next_review_trigger(row: dict[str, Any], owned: PortfolioPosition | None) -> str:
    if owned and owned.stop_or_invalidation:
        return f"Review if price approaches your invalidation: {owned.stop_or_invalidation}."
    return f"Review on invalidation {row.get('invalidation_level', 'unavailable')}, TP1 {row.get('tp1', 'unavailable')}, or new catalyst data."


def _to_float(value: Any, default: float = 0) -> float:
    try:
        if value in (None, "", "unavailable"):
            raise ValueError
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_number(value: Any) -> float:
    if value in (None, ""):
        return 0
    for token in str(value).replace("$", "").replace(",", " ").replace("-", " ").split():
        try:
            return float(token)
        except ValueError:
            continue
    return 0


def _round(value: float) -> float:
    return round(float(value or 0), 4)


def _iso_now() -> str:
    return date.today().isoformat()
