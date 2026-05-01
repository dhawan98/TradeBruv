from __future__ import annotations

from typing import Any

FAST_ACTIONABLE_LABELS = {
    "Momentum Actionable Today",
    "Breakout Actionable Today",
    "Pullback Actionable Today",
}
RESEARCH_LABELS = {"Long-Term Research Candidate"}
WATCH_LABELS = {
    "Slow Compounder Watch",
    "Watch for Better Entry",
    "High-Volume Mover Watch",
}
AVOID_LABELS = {"Avoid / Do Not Chase"}
DATA_LABELS = {"Data Insufficient"}
ACTIONABILITY_LABELS = FAST_ACTIONABLE_LABELS | RESEARCH_LABELS | WATCH_LABELS | AVOID_LABELS | DATA_LABELS


def actionability_priority(label: str) -> int:
    order = {
        "Breakout Actionable Today": 0,
        "Momentum Actionable Today": 1,
        "Pullback Actionable Today": 2,
        "Long-Term Research Candidate": 3,
        "High-Volume Mover Watch": 4,
        "Slow Compounder Watch": 5,
        "Watch for Better Entry": 6,
        "Avoid / Do Not Chase": 7,
        "Data Insufficient": 8,
    }
    return order.get(label, 9)


def label_primary_action(label: str, *, owned: bool = False) -> str:
    if label in DATA_LABELS:
        return "Data Insufficient"
    if label in AVOID_LABELS:
        return "Avoid"
    if label in FAST_ACTIONABLE_LABELS | RESEARCH_LABELS:
        return "Research / Buy Candidate"
    if label in WATCH_LABELS:
        return "Hold" if owned else "Watch"
    return "Hold" if owned else "Watch"


def is_fast_actionable_label(label: str) -> bool:
    return label in FAST_ACTIONABLE_LABELS


def label_bucket(label: str) -> str:
    if label in FAST_ACTIONABLE_LABELS:
        return "fast_actionable"
    if label in RESEARCH_LABELS:
        return "long_term_research"
    if label == "High-Volume Mover Watch":
        return "movers"
    if label in WATCH_LABELS:
        return "watch"
    if label in AVOID_LABELS:
        return "avoid"
    return "data_issues"


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
    regular_investing_score = _to_float(row.get("regular_investing_score"), default=0) or 0
    investing_action_label = str(row.get("investing_action_label") or "")
    outlier_type = str(row.get("outlier_type") or "").lower()
    positive_long_term_thesis = (
        regular_investing_score >= 70
        and investing_action_label not in {"Avoid", "Watchlist Only", "Data Insufficient"}
        and str(row.get("investing_style") or "") not in {"", "Data Insufficient"}
    )

    hard_avoid = any(
        (
            str(row.get("status_label") or "") == "Avoid",
            str(row.get("investing_action_label") or "") == "Avoid",
            ("avoid" in outlier_type and not positive_long_term_thesis),
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
    relative_volume_20d = _to_float(row.get("relative_volume_20d"), default=0) or 0
    relative_volume_50d = _to_float(row.get("relative_volume_50d"), default=0) or 0
    best_relative_volume = max(relative_volume_20d, relative_volume_50d)
    acceptable_relative_volume = best_relative_volume >= 0.8
    strong_relative_volume = best_relative_volume >= 1.2
    high_relative_volume = best_relative_volume >= 1.6
    extremely_low_relative_volume = best_relative_volume < 0.25
    sector_relative_strength = _to_float(row.get("sector_relative_strength"))
    strong_sector_relative_strength = sector_relative_strength is not None and sector_relative_strength >= 0.02
    signal_text = " ".join(
        str(row.get(field) or "").lower()
        for field in (
            "signal_summary",
            "signal_explanation",
            "breakout_signal",
            "pullback_signal",
            "volume_signal",
            "trend_signal",
            "strategy_label",
            "outlier_type",
            "trigger_reason",
        )
    )
    breakout_signal = any(token in signal_text for token in ("breakout", "range expansion", "new high"))
    pullback_signal = any(token in signal_text for token in ("pullback", "reclaim", "ema 21", "ema21", "ema 50", "ema50", "support hold"))
    mover_signal = any(token in signal_text for token in ("mover", "gap", "unusual volume", "momentum", "repricing"))
    recent_price_change = max(
        abs(_to_float(row.get("price_change_1d_pct"), default=0) or 0),
        abs(_to_float(row.get("price_change_5d_pct"), default=0) or 0),
    )
    bullish_stack = "bullish" in str(row.get("ema_stack") or "").lower()
    long_term_style = any(
        token in str(row.get("investing_style") or "").lower()
        for token in ("compound", "quality", "leader", "long")
    )
    breakout_with_volume = breakout_signal and strong_relative_volume
    pullback_with_volume = pullback_signal and best_relative_volume >= 0.6
    momentum_with_confirmation = acceptable_relative_volume and (catalyst_confirmed or strong_sector_relative_strength or recent_price_change >= 4)
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
    if extremely_low_relative_volume:
        actionability_blockers.append("Relative volume is too low for a fast actionable setup.")
    if not catalyst_confirmed:
        actionability_blockers.append("No fresh catalyst is confirmed.")

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
            lane_scores=_empty_lane_scores(),
            best_lane="data_insufficient",
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
            lane_scores=_empty_lane_scores(),
            best_lane="data_insufficient",
        )

    lane_scores = _lane_scores(
        row=row,
        primary_score=primary_score,
        setup_quality=setup_quality,
        reward_risk=reward_risk,
        current_setup_state=current_setup_state,
        catalyst_confirmed=catalyst_confirmed,
        best_relative_volume=best_relative_volume,
        sector_relative_strength=sector_relative_strength,
        breakout_signal=breakout_signal,
        pullback_signal=pullback_signal,
        mover_signal=mover_signal,
        bullish_stack=bullish_stack,
        long_term_style=long_term_style,
        recent_price_change=recent_price_change,
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
            lane_scores=lane_scores,
            best_lane="avoid",
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

    fast_actionable_allowed = (
        not extremely_low_relative_volume
        and reward_risk is not None
        and reward_risk >= 1.75
        and risk_level not in {"High", "Extreme", "Very High"}
        and (
            acceptable_relative_volume
            or breakout_with_volume
            or (strong_sector_relative_strength and catalyst_confirmed)
            or pullback_with_volume
            or momentum_with_confirmation
        )
    )
    best_lane = max(lane_scores, key=lane_scores.get)

    if severe_overextension or current_setup_state in {"Above Entry / Extended", "Pullback Needed"}:
        mover_watch_score = max(lane_scores["mover_score"], lane_scores["breakout_actionability_score"])
        if mover_watch_score >= 68 and high_relative_volume:
            return _profile(
                score=min(mover_watch_score, 74),
                label="High-Volume Mover Watch",
                reason="This has real velocity, but the current entry is too extended to call actionable today.",
                blockers=actionability_blockers,
                trigger=f"Wait for the move to tighten or pull back toward {entry_zone}.",
                current_setup_state="Above Entry / Extended" if current_setup_state != "Broken" else current_setup_state,
                level_status="Conditional",
                entry_label="Pullback Zone",
                levels_explanation="High-volume momentum is present, but the current entry is still conditional.",
                trigger_needed=True,
                lane_scores=lane_scores,
                best_lane="mover",
            )
        return _profile(
            score=min(max(score, lane_scores["slow_compounder_score"]), 69),
            label="Slow Compounder Watch" if lane_scores["slow_compounder_score"] >= 64 else "Watch for Better Entry",
            reason=f"Current price is valid, but the setup is extended. Wait for consolidation or pullback near {entry_zone}.",
            blockers=actionability_blockers,
            trigger=f"Pullback to {entry_zone}, or a fresh breakout with volume and catalyst confirmation.",
            current_setup_state="Above Entry / Extended" if current_setup_state != "Broken" else current_setup_state,
            level_status="Conditional",
            entry_label="Pullback Zone",
            levels_explanation="Conditional levels only. Wait for a better entry before treating this as actionable.",
            trigger_needed=True,
            lane_scores=lane_scores,
            best_lane="slow_compounder" if lane_scores["slow_compounder_score"] >= 64 else best_lane,
        )

    if current_setup_state in {"Below Trigger", "Breakout Needed"}:
        breakout_level = entry_high if entry_high is not None else entry_low
        label = "High-Volume Mover Watch" if lane_scores["mover_score"] >= 68 and strong_relative_volume else "Watch for Better Entry"
        return _profile(
            score=min(max(score, lane_scores["breakout_actionability_score"], lane_scores["mover_score"]), 72 if label == "High-Volume Mover Watch" else 64),
            label=label,
            reason="Interesting setup, but it still needs a trigger before it becomes actionable today.",
            blockers=actionability_blockers,
            trigger=f"Wait for a clean close above {breakout_level:.2f} with volume confirmation." if breakout_level is not None else "Wait for the trigger level to form.",
            current_setup_state=current_setup_state,
            level_status="Conditional",
            entry_label="Breakout Trigger",
            levels_explanation="Conditional levels only. Treat the entry as a trigger, not as a live buy zone.",
            trigger_needed=True,
            lane_scores=lane_scores,
            best_lane="mover" if label == "High-Volume Mover Watch" else "breakout",
        )

    if fast_actionable_allowed:
        if breakout_with_volume and lane_scores["breakout_actionability_score"] >= 78:
            return _profile(
                score=lane_scores["breakout_actionability_score"],
                label="Breakout Actionable Today",
                reason="Breakout structure, volume confirmation, and risk/reward all line up for a same-day setup.",
                blockers=actionability_blockers,
                trigger=f"Already in range near {entry_zone}.",
                current_setup_state="In Entry Zone",
                level_status="Actionable",
                entry_label="Entry",
                levels_explanation="These breakout levels are actionable today.",
                trigger_needed=False,
                lane_scores=lane_scores,
                best_lane="breakout",
            )
        if pullback_with_volume and lane_scores["pullback_actionability_score"] >= 76:
            return _profile(
                score=lane_scores["pullback_actionability_score"],
                label="Pullback Actionable Today",
                reason="Constructive pullback/reclaim conditions are in place with enough volume to support a near-term entry.",
                blockers=actionability_blockers,
                trigger=f"Already in range near {entry_zone}.",
                current_setup_state="In Entry Zone",
                level_status="Actionable",
                entry_label="Entry",
                levels_explanation="These pullback levels are actionable today.",
                trigger_needed=False,
                lane_scores=lane_scores,
                best_lane="pullback",
            )
        if momentum_with_confirmation and lane_scores["momentum_actionability_score"] >= 78:
            return _profile(
                score=lane_scores["momentum_actionability_score"],
                label="Momentum Actionable Today",
                reason="Momentum, confirmation, and execution quality line up for a same-day actionable idea.",
                blockers=actionability_blockers,
                trigger=f"Already in range near {entry_zone}.",
                current_setup_state="In Entry Zone",
                level_status="Actionable",
                entry_label="Entry",
                levels_explanation="These momentum levels are actionable today.",
                trigger_needed=False,
                lane_scores=lane_scores,
                best_lane="momentum",
            )

    if lane_scores["long_term_research_score"] >= 72 and (extremely_low_relative_volume or not catalyst_confirmed or long_term_style):
        return _profile(
            score=lane_scores["long_term_research_score"],
            label="Long-Term Research Candidate",
            reason="Trend and business quality look constructive, but this is better framed as a research/accumulation idea than a fast trade today.",
            blockers=actionability_blockers,
            trigger=f"Use pullbacks near {entry_zone} to build a better long-term plan." if entry_zone != "unavailable" else "Wait for a cleaner research entry zone.",
            current_setup_state=current_setup_state if current_setup_state != "Broken" else "In Entry Zone",
            level_status="Preliminary",
            entry_label="Research Zone",
            levels_explanation="Levels are research framing only. This is not a same-day momentum call.",
            trigger_needed=True,
            lane_scores=lane_scores,
            best_lane="long_term_research",
        )

    if lane_scores["mover_score"] >= 68 and strong_relative_volume:
        return _profile(
            score=min(lane_scores["mover_score"], 74),
            label="High-Volume Mover Watch",
            reason="This has real participation and tape speed, but the entry/risk profile is not clean enough for a same-day green light.",
            blockers=actionability_blockers,
            trigger=f"Look for a tighter trigger or lower-risk reclaim around {entry_zone}.",
            current_setup_state=current_setup_state,
            level_status="Conditional",
            entry_label="Trigger Zone",
            levels_explanation="Participation is strong, but the setup still needs a better tactical entry.",
            trigger_needed=True,
            lane_scores=lane_scores,
            best_lane="mover",
        )

    if lane_scores["slow_compounder_score"] >= 62:
        return _profile(
            score=lane_scores["slow_compounder_score"],
            label="Slow Compounder Watch",
            reason="The trend quality is decent, but the tape is too quiet right now to treat it as a fast actionable setup.",
            blockers=actionability_blockers,
            trigger=f"Wait for stronger participation or a cleaner pullback near {entry_zone}.",
            current_setup_state=current_setup_state,
            level_status="Conditional",
            entry_label="Watch Zone",
            levels_explanation="This is a slower-grind watch name, not a fast setup.",
            trigger_needed=True,
            lane_scores=lane_scores,
            best_lane="slow_compounder",
        )

    return _profile(
        score=min(max(score, lane_scores["pullback_actionability_score"]), 59),
        label="Watch for Better Entry",
        reason="The setup is interesting enough to monitor, but it is not actionable today.",
        blockers=actionability_blockers,
        trigger=f"Wait for cleaner structure near {entry_zone}." if entry_zone != "unavailable" else "Wait for a refreshed setup.",
        current_setup_state=current_setup_state,
        level_status="Conditional",
        entry_label="Better Entry",
        levels_explanation="Conditional levels only. A better trigger or pullback is needed.",
        trigger_needed=True,
        lane_scores=lane_scores,
        best_lane=best_lane,
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
    lane_scores: dict[str, int],
    best_lane: str,
) -> dict[str, Any]:
    return {
        "actionability_score": int(max(0, min(100, score))),
        "actionability_label": label,
        "best_actionability_lane": best_lane,
        "actionability_reason": reason,
        "actionability_blockers": list(dict.fromkeys(blockers)),
        "action_trigger": trigger,
        "current_setup_state": current_setup_state,
        "level_status": level_status,
        "entry_label": entry_label,
        "levels_explanation": levels_explanation,
        "trigger_needed": trigger_needed,
        **lane_scores,
    }


def _empty_lane_scores() -> dict[str, int]:
    return {
        "momentum_actionability_score": 0,
        "breakout_actionability_score": 0,
        "pullback_actionability_score": 0,
        "long_term_research_score": 0,
        "mover_score": 0,
        "slow_compounder_score": 0,
    }


def _lane_scores(
    *,
    row: dict[str, Any],
    primary_score: float,
    setup_quality: float,
    reward_risk: float | None,
    current_setup_state: str,
    catalyst_confirmed: bool,
    best_relative_volume: float,
    sector_relative_strength: float | None,
    breakout_signal: bool,
    pullback_signal: bool,
    mover_signal: bool,
    bullish_stack: bool,
    long_term_style: bool,
    recent_price_change: float,
) -> dict[str, int]:
    momentum = 0
    momentum += int(round(_scale(primary_score, 40, 90, 0, 24)))
    momentum += int(round(_scale(setup_quality, 40, 90, 0, 18)))
    momentum += int(round(_scale(best_relative_volume, 0.25, 2.0, 0, 22)))
    momentum += int(round(_scale(recent_price_change, 0.5, 8.0, 0, 10)))
    momentum += 8 if catalyst_confirmed else 0
    momentum += 6 if (sector_relative_strength or 0) > 0 else 0
    momentum += 6 if bullish_stack else 0
    momentum += _reward_risk_points(reward_risk) // 2
    if best_relative_volume < 0.25:
        momentum = min(momentum, 34)

    breakout = 0
    breakout += int(round(_scale(primary_score, 40, 90, 0, 18)))
    breakout += int(round(_scale(setup_quality, 40, 90, 0, 20)))
    breakout += 18 if breakout_signal else 0
    breakout += int(round(_scale(best_relative_volume, 0.3, 2.2, 0, 24)))
    breakout += {
        "In Entry Zone": 10,
        "Below Trigger": 10,
        "Breakout Needed": 12,
        "Above Entry / Extended": 3,
        "Pullback Needed": 3,
    }.get(current_setup_state, 0)
    breakout += 6 if catalyst_confirmed else 0
    breakout += _reward_risk_points(reward_risk) // 2
    if best_relative_volume < 0.25:
        breakout = min(breakout, 30)

    pullback = 0
    pullback += int(round(_scale(primary_score, 40, 90, 0, 18)))
    pullback += int(round(_scale(setup_quality, 40, 90, 0, 18)))
    pullback += 18 if pullback_signal else 0
    pullback += int(round(_scale(best_relative_volume, 0.2, 1.6, 0, 16)))
    pullback += {
        "In Entry Zone": 16,
        "Above Entry / Extended": 4,
        "Pullback Needed": 2,
        "Below Trigger": 5,
    }.get(current_setup_state, 0)
    pullback += 5 if catalyst_confirmed else 0
    pullback += _reward_risk_points(reward_risk) // 2

    long_term = 0
    long_term += int(round(_scale(_to_float(row.get("regular_investing_score"), default=0) or 0, 45, 95, 0, 34)))
    long_term += int(round(_scale(setup_quality, 40, 90, 0, 18)))
    long_term += 12 if bullish_stack else 0
    long_term += 8 if long_term_style else 0
    long_term += 8 if (sector_relative_strength or 0) > 0 else 0
    long_term += _data_points(row) * 2
    long_term += _reward_risk_points(reward_risk) // 2

    mover = 0
    mover += int(round(_scale(_to_float(row.get("velocity_score"), default=0) or 0, 20, 90, 0, 22)))
    mover += int(round(_scale(best_relative_volume, 0.3, 3.0, 0, 24)))
    mover += int(round(_scale(recent_price_change, 1.0, 12.0, 0, 20)))
    mover += 12 if mover_signal else 0
    mover += 10 if breakout_signal else 0
    mover += 6 if catalyst_confirmed else 0
    mover += 6 if bullish_stack else 0

    slow = 0
    slow += int(round(_scale(_to_float(row.get("regular_investing_score"), default=0) or 0, 45, 95, 0, 28)))
    slow += int(round(_scale(setup_quality, 40, 90, 0, 16)))
    slow += 16 if bullish_stack else 0
    slow += 15 if best_relative_volume < 0.8 else 4
    slow += 8 if long_term_style else 0
    slow += 6 if not catalyst_confirmed else 2
    slow += _reward_risk_points(reward_risk) // 2

    return {
        "momentum_actionability_score": int(max(0, min(100, momentum))),
        "breakout_actionability_score": int(max(0, min(100, breakout))),
        "pullback_actionability_score": int(max(0, min(100, pullback))),
        "long_term_research_score": int(max(0, min(100, long_term))),
        "mover_score": int(max(0, min(100, mover))),
        "slow_compounder_score": int(max(0, min(100, slow))),
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
