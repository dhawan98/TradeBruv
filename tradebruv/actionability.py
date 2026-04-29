from __future__ import annotations

from typing import Any


def build_actionability_profile(
    row: dict[str, Any],
    *,
    price_sanity: dict[str, Any],
    risk_level: str,
    portfolio_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_price = _to_float(price_sanity.get("validated_price")) or _to_float(row.get("current_price"))
    entry_zone = str(row.get("entry_zone") or "unavailable")
    entry_low, entry_high = _parse_entry_zone(entry_zone)
    invalidation = _to_float(row.get("stop_loss_reference")) or _to_float(row.get("invalidation_level"))
    tp1 = _to_float(row.get("tp1"))
    tp2 = _to_float(row.get("tp2"))
    reward_risk = _to_float(row.get("reward_risk"))
    primary_score = max(
        _to_float(row.get("regular_investing_score"), default=0) or 0,
        _to_float(row.get("outlier_score"), default=0) or 0,
        _to_float(row.get("velocity_score"), default=0) or 0,
    )
    setup_quality = _to_float(row.get("setup_quality_score"), default=0) or 0
    price_validation_status = str(price_sanity.get("price_validation_status") or "FAIL")
    warnings_text = " ".join(
        str(value or "").lower()
        for value in (
            row.get("chase_risk_warning"),
            row.get("chase_warning"),
            row.get("investing_bear_case"),
            row.get("value_trap_warning"),
            row.get("outlier_reason"),
            *(row.get("warnings") or []),
            *(row.get("why_it_could_fail") or []),
            *(price_sanity.get("price_warnings") or []),
        )
    )

    hard_avoid = any(
        (
            str(row.get("status_label") or "") == "Avoid",
            str(row.get("investing_action_label") or "") == "Avoid",
            "avoid" in str(row.get("outlier_type") or "").lower(),
            "value trap" in str(row.get("value_trap_warning") or "").lower(),
            bool(row.get("pump_risk")),
        )
    )
    overextended = any(keyword in warnings_text for keyword in ("extended", "chase risk", "chasing", "overextension"))
    severe_overextension = any(
        keyword in warnings_text
        for keyword in (
            "extremely extended",
            "far extended",
            "severe overextension",
            "do not chase",
            "pump-like",
        )
    )
    catalyst_confirmed = bool(
        row.get("price_volume_confirms_catalyst")
        or str(row.get("catalyst_quality") or "") in {"Official Confirmed", "Price Confirmed", "Narrative Supported"}
        or int(_to_float(row.get("catalyst_source_count"), default=0) or 0) > 0
    )
    missing_core_levels = entry_low is None or entry_high is None or invalidation is None
    broken_setup = bool(
        current_price is not None
        and invalidation is not None
        and current_price <= invalidation
    ) or any(keyword in warnings_text for keyword in ("falling knife", "failed breakout", "broken thesis", "broken trend"))

    current_setup_state = _current_setup_state(
        current_price=current_price,
        entry_low=entry_low,
        entry_high=entry_high,
        invalidation=invalidation,
        overextended=overextended or severe_overextension,
        broken=broken_setup,
        row=row,
    )

    actionability_blockers: list[str] = []
    if price_validation_status != "PASS":
        actionability_blockers.append(str(price_sanity.get("price_validation_reason") or "No validated live price."))
    if hard_avoid:
        actionability_blockers.append("Avoid conditions are active.")
    if broken_setup:
        actionability_blockers.append("The setup is broken.")
    if missing_core_levels:
        actionability_blockers.append("Entry or invalidation is unavailable.")
    if reward_risk is None:
        actionability_blockers.append("Reward/risk could not be computed.")
    elif reward_risk < 1.75:
        actionability_blockers.append("Reward/risk is below threshold.")
    if severe_overextension:
        actionability_blockers.append("The setup is too extended to chase.")
    if bool(row.get("pump_risk")):
        actionability_blockers.append("Pump-risk behavior is active.")

    if price_validation_status != "PASS":
        return _profile(
            score=0,
            label="Data Insufficient",
            reason="Critical live-price validation failed, so this cannot become a daily pick.",
            blockers=actionability_blockers,
            trigger="Wait for data refresh.",
            current_setup_state="Data Insufficient",
            level_status="Hidden",
            entry_label="Hidden",
            levels_explanation="Levels hidden until live price validation passes.",
            trigger_needed=True,
        )

    if missing_core_levels:
        return _profile(
            score=0,
            label="Data Insufficient",
            reason="Price is valid, but critical levels are missing.",
            blockers=actionability_blockers,
            trigger="Wait for a refreshed scan with entry and invalidation levels.",
            current_setup_state="Data Insufficient",
            level_status="Hidden",
            entry_label="Hidden",
            levels_explanation="Levels hidden because entry or invalidation is unavailable.",
            trigger_needed=True,
        )

    if hard_avoid or broken_setup or bool(row.get("pump_risk")):
        return _profile(
            score=min(_base_actionability_score(
                primary_score=primary_score,
                setup_quality=setup_quality,
                reward_risk=reward_risk,
                current_setup_state=current_setup_state,
                overextended=True,
                catalyst_confirmed=catalyst_confirmed,
                row=row,
                portfolio_decision=portfolio_decision,
            ), 25),
            label="Avoid / Do Not Chase",
            reason="Risk/reward or avoid conditions make this a poor chase today.",
            blockers=actionability_blockers,
            trigger="Stand aside unless the setup fully resets with better risk/reward.",
            current_setup_state="Broken" if broken_setup else current_setup_state,
            level_status="Hidden",
            entry_label="Hidden",
            levels_explanation="Levels are hidden for avoid names.",
            trigger_needed=True,
        )

    score = _base_actionability_score(
        primary_score=primary_score,
        setup_quality=setup_quality,
        reward_risk=reward_risk,
        current_setup_state=current_setup_state,
        overextended=overextended or severe_overextension,
        catalyst_confirmed=catalyst_confirmed,
        row=row,
        portfolio_decision=portfolio_decision,
    )

    if severe_overextension or current_setup_state in {"Above Entry / Extended", "Pullback Needed"}:
        return _profile(
            score=min(score, 69),
            label="Wait for Better Entry",
            reason=f"Current price is valid, but the setup is extended. Wait for consolidation or pullback near {entry_zone}.",
            blockers=actionability_blockers,
            trigger=f"Pullback to {entry_zone}, or a fresh breakout with volume and catalyst confirmation.",
            current_setup_state="Above Entry / Extended" if current_setup_state != "Broken" else current_setup_state,
            level_status="Conditional",
            entry_label="Pullback Zone",
            levels_explanation="Conditional levels only. Wait for a better entry before treating this as actionable.",
            trigger_needed=True,
        )

    if current_setup_state in {"Below Trigger", "Breakout Needed"}:
        breakout_level = entry_high if entry_high is not None else entry_low
        return _profile(
            score=min(score, 64),
            label="Watch for Trigger",
            reason="Interesting setup, but it still needs a trigger before it becomes actionable today.",
            blockers=actionability_blockers,
            trigger=f"Wait for a clean close above {breakout_level:.2f} with volume confirmation." if breakout_level is not None else "Wait for the trigger level to form.",
            current_setup_state=current_setup_state,
            level_status="Conditional",
            entry_label="Breakout Trigger",
            levels_explanation="Conditional levels only. Treat the entry as a trigger, not as a live buy zone.",
            trigger_needed=True,
        )

    if score >= 78 and reward_risk is not None and reward_risk >= 1.75 and risk_level not in {"High", "Extreme", "Very High"}:
        return _profile(
            score=score,
            label="Actionable Today",
            reason="Validated price, acceptable risk/reward, and current setup all line up for a same-day actionable idea.",
            blockers=actionability_blockers,
            trigger=f"Already in range near {entry_zone}.",
            current_setup_state="In Entry Zone",
            level_status="Actionable",
            entry_label="Entry",
            levels_explanation="These levels are actionable today.",
            trigger_needed=False,
        )

    if score >= 58:
        return _profile(
            score=score,
            label="Research First",
            reason="Price is valid and the thesis is interesting, but confirmation is not clean enough for a same-day entry.",
            blockers=actionability_blockers,
            trigger=f"Research around {entry_zone}, then reassess catalyst, risk, and execution discipline.",
            current_setup_state=current_setup_state if current_setup_state != "In Entry Zone" else "In Entry Zone",
            level_status="Preliminary",
            entry_label="Research Zone",
            levels_explanation="Levels are preliminary. Use them for research framing, not as an immediate trade plan.",
            trigger_needed=True,
        )

    return _profile(
        score=min(score, 49),
        label="Watch for Trigger",
        reason="The setup is interesting enough to monitor, but it is not actionable today.",
        blockers=actionability_blockers,
        trigger=f"Wait for cleaner structure near {entry_zone}." if entry_zone != "unavailable" else "Wait for a refreshed setup.",
        current_setup_state=current_setup_state,
        level_status="Conditional",
        entry_label="Better Entry",
        levels_explanation="Conditional levels only. A better trigger or pullback is needed.",
        trigger_needed=True,
    )


def evidence_pill(validation_context: dict[str, Any] | None) -> str:
    context = validation_context or {}
    strength = str(context.get("evidence_strength") or "Not enough evidence").lower()
    if context.get("real_money_reliance") is False:
        if "promising" in strength:
            return "Promising"
        if "mixed" in strength:
            return "Mixed"
        return "Paper-track only"
    if "promising" in strength:
        return "Promising"
    if "mixed" in strength:
        return "Mixed"
    if "weak" in strength:
        return "Weak"
    return "Not enough evidence"


def _profile(
    *,
    score: int,
    label: str,
    reason: str,
    blockers: list[str],
    trigger: str,
    current_setup_state: str,
    level_status: str,
    entry_label: str,
    levels_explanation: str,
    trigger_needed: bool,
) -> dict[str, Any]:
    return {
        "actionability_score": int(max(0, min(100, score))),
        "actionability_label": label,
        "actionability_reason": reason,
        "actionability_blockers": list(dict.fromkeys(blockers)),
        "action_trigger": trigger,
        "current_setup_state": current_setup_state,
        "level_status": level_status,
        "entry_label": entry_label,
        "levels_explanation": levels_explanation,
        "trigger_needed": trigger_needed,
    }


def _base_actionability_score(
    *,
    primary_score: float,
    setup_quality: float,
    reward_risk: float | None,
    current_setup_state: str,
    overextended: bool,
    catalyst_confirmed: bool,
    row: dict[str, Any],
    portfolio_decision: dict[str, Any] | None,
) -> int:
    score = 0
    score += int(round(_scale(primary_score, 35, 90, 0, 20)))
    score += int(round(_scale(setup_quality, 35, 90, 0, 20)))
    score += _reward_risk_points(reward_risk)
    score += {
        "In Entry Zone": 15,
        "Above Entry / Extended": 3,
        "Below Trigger": 6,
        "Pullback Needed": 4,
        "Breakout Needed": 6,
        "Broken": 0,
        "Data Insufficient": 0,
    }.get(current_setup_state, 4)
    score += 0 if overextended else 15
    score += 5 if catalyst_confirmed else 2
    score += _fit_points(row, portfolio_decision)
    score += _data_points(row)
    return int(max(0, min(100, score)))


def _fit_points(row: dict[str, Any], portfolio_decision: dict[str, Any] | None) -> int:
    if portfolio_decision:
        recommendation = str(portfolio_decision.get("recommendation_label") or "")
        if recommendation in {"Add on Strength", "Add on Better Entry", "Strong Hold", "Hold"}:
            return 5
        return 3
    if (_to_float(row.get("regular_investing_score"), default=0) or 0) >= 60:
        return 5
    if str(row.get("investing_style") or "") not in {"Data Insufficient", "Watchlist Only"}:
        return 4
    return 2


def _data_points(row: dict[str, Any]) -> int:
    quality = str(row.get("investing_data_quality") or "Medium")
    if quality == "Strong":
        return 5
    if quality == "Medium":
        return 3
    notes = row.get("data_availability_notes") or []
    return 2 if notes else 1


def _reward_risk_points(reward_risk: float | None) -> int:
    if reward_risk is None:
        return 0
    if reward_risk >= 2.75:
        return 15
    if reward_risk >= 2.2:
        return 12
    if reward_risk >= 1.75:
        return 9
    if reward_risk >= 1.4:
        return 5
    return 0


def _current_setup_state(
    *,
    current_price: float | None,
    entry_low: float | None,
    entry_high: float | None,
    invalidation: float | None,
    overextended: bool,
    broken: bool,
    row: dict[str, Any],
) -> str:
    if current_price is None or entry_low is None or entry_high is None or invalidation is None:
        return "Data Insufficient"
    if broken or current_price <= invalidation:
        return "Broken"
    if overextended:
        return "Above Entry / Extended"
    if entry_low <= current_price <= entry_high * 1.02:
        return "In Entry Zone"
    if current_price > entry_high * 1.02:
        return "Pullback Needed"
    if current_price < entry_low * 0.98:
        breakout_bias = any(
            keyword in " ".join(
                str(row.get(field) or "").lower()
                for field in ("strategy_label", "outlier_type", "trigger_reason")
            )
            for keyword in ("breakout", "momentum", "repricing")
        )
        return "Breakout Needed" if breakout_bias else "Below Trigger"
    return "Below Trigger"


def _parse_entry_zone(value: str | None) -> tuple[float | None, float | None]:
    if not value or value == "unavailable":
        return None, None
    parts = [part.strip() for part in str(value).split("-")]
    if len(parts) != 2:
        return None, None
    low = _to_float(parts[0])
    high = _to_float(parts[1])
    if low is None or high is None:
        return None, None
    return (low, high) if low <= high else (high, low)


def _scale(value: float, start: float, end: float, out_low: float, out_high: float) -> float:
    if value <= start:
        return out_low
    if value >= end:
        return out_high
    ratio = (value - start) / (end - start)
    return out_low + (ratio * (out_high - out_low))


def _to_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, "", "unavailable", "None"):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
