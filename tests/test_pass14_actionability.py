from __future__ import annotations

from tradebruv.actionability import build_actionability_profile
from tradebruv.daily_decision import _build_daily_decision_markdown
from tradebruv.decision_engine import build_unified_decision, build_validation_context

from tests.helpers import ANCHOR


def _live_row(**overrides):
    row = {
        "ticker": "MSFT",
        "company_name": "Microsoft",
        "provider": "real",
        "provider_name": "real",
        "selected_provider": "real",
        "provider_is_live_capable": True,
        "is_sample_data": False,
        "is_report_only": False,
        "report_snapshot_selected": False,
        "current_price": 100.0,
        "price_source": "latest quote",
        "latest_available_close": 100.0,
        "quote_price_if_available": 100.0,
        "last_market_date": "2026-04-24",
        "regular_investing_score": 82,
        "outlier_score": 74,
        "velocity_score": 38,
        "setup_quality_score": 84,
        "entry_zone": "99 - 101",
        "invalidation_level": 94.0,
        "stop_loss_reference": 94.0,
        "tp1": 110.0,
        "tp2": 118.0,
        "reward_risk": 2.5,
        "investing_risk": "Low",
        "investing_style": "Quality Compounder",
        "investing_reason": "Strong quality setup with acceptable risk/reward.",
        "investing_bear_case": "Valuation can still reset if momentum fades.",
        "investing_data_quality": "Strong",
        "status_label": "Trade Setup Forming",
        "catalyst_quality": "Official Confirmed",
        "catalyst_source_count": 2,
        "price_volume_confirms_catalyst": True,
        "relative_volume_20d": 1.5,
        "relative_volume_50d": 1.1,
        "signal_summary": "Breakout with Volume",
        "signal_explanation": "Strong breakout with broad participation.",
        "ema_stack": "Bullish Stack",
        "sector_relative_strength": 0.04,
        "warnings": [],
        "why_it_could_fail": [],
        "data_availability_notes": [],
        "pump_risk": False,
    }
    row.update(overrides)
    return row


def test_actionability_score_marks_clean_breakout_actionable() -> None:
    profile = build_actionability_profile(
        _live_row(),
        price_sanity={
            "price_validation_status": "PASS",
            "validated_price": 100.0,
        },
        risk_level="Low",
    )

    assert 78 <= profile["actionability_score"] <= 100
    assert profile["actionability_label"] == "Breakout Actionable Today"
    assert profile["level_status"] == "Actionable"
    assert profile["trigger_needed"] is False
    assert profile["breakout_actionability_score"] >= profile["pullback_actionability_score"]


def test_buy_candidate_requires_actionability_gates() -> None:
    decision = build_unified_decision(
        _live_row(reward_risk=1.2, current_price=108.0, quote_price_if_available=108.0, latest_available_close=108.0, relative_volume_20d=0.2, signal_summary="Quiet drift"),
        portfolio_row=None,
        scan_generated_at="2026-04-24T12:00:00Z",
        validation_context=build_validation_context(),
        reference_date=ANCHOR,
    )

    assert decision["primary_action"] != "Research / Buy Candidate"
    assert decision["actionability_label"] in {"Watch for Better Entry", "Slow Compounder Watch", "Avoid / Do Not Chase"}


def test_overextended_setup_becomes_wait_for_better_entry_with_trigger() -> None:
    decision = build_unified_decision(
        _live_row(
            current_price=100.5,
            quote_price_if_available=100.5,
            latest_available_close=100.5,
            chase_risk_warning="Extended setup. Chase risk is elevated.",
        ),
        portfolio_row=None,
        scan_generated_at="2026-04-24T12:00:00Z",
        validation_context=build_validation_context(),
        reference_date=ANCHOR,
    )

    assert decision["actionability_label"] in {"Wait for Better Entry", "Slow Compounder Watch"}
    assert decision["primary_action"] == "Watch"
    assert decision["trigger_needed"] is True
    assert decision["level_status"] == "Conditional"
    assert decision["entry_label"] == "Pullback Zone"
    assert "Pullback" in decision["action_trigger"]


def test_missing_catalyst_does_not_become_data_insufficient() -> None:
    decision = build_unified_decision(
        _live_row(
            catalyst_quality="Not Confirmed",
            catalyst_source_count=0,
            price_volume_confirms_catalyst=False,
        ),
        portfolio_row=None,
        scan_generated_at="2026-04-24T12:00:00Z",
        validation_context=build_validation_context(),
        reference_date=ANCHOR,
    )

    assert decision["price_validation_status"] == "PASS"
    assert decision["actionability_label"] != "Data Insufficient"
    assert decision["primary_action"] in {"Research / Buy Candidate", "Watch"}


def test_rost_like_low_relative_volume_becomes_research_not_fast_actionable() -> None:
    decision = build_unified_decision(
        _live_row(
            ticker="ROST",
            company_name="Ross Stores",
            relative_volume_20d=0.03,
            relative_volume_50d=0.08,
            signal_summary="Steady trend",
            signal_explanation="Strong trend but very quiet tape.",
            catalyst_quality="Not Confirmed",
            catalyst_source_count=0,
            price_volume_confirms_catalyst=False,
            price_change_1d_pct=0.2,
            price_change_5d_pct=1.1,
        ),
        portfolio_row=None,
        scan_generated_at="2026-04-24T12:00:00Z",
        validation_context=build_validation_context(),
        reference_date=ANCHOR,
    )

    assert decision["actionability_label"] in {"Long-Term Research Candidate", "Slow Compounder Watch"}
    assert decision["actionability_label"] not in {
        "Momentum Actionable Today",
        "Breakout Actionable Today",
        "Pullback Actionable Today",
    }
    assert decision["momentum_actionability_score"] < decision["long_term_research_score"]


def test_high_relative_volume_breakout_can_be_actionable_today() -> None:
    decision = build_unified_decision(
        _live_row(
            ticker="QCOM",
            signal_summary="Breakout with Volume",
            signal_explanation="High-volume breakout from a tight base.",
            relative_volume_20d=2.3,
            relative_volume_50d=1.8,
            price_change_1d_pct=4.8,
            price_change_5d_pct=8.2,
        ),
        portfolio_row=None,
        scan_generated_at="2026-04-24T12:00:00Z",
        validation_context=build_validation_context(),
        reference_date=ANCHOR,
    )

    assert decision["actionability_label"] == "Breakout Actionable Today"
    assert decision["primary_action"] == "Research / Buy Candidate"


def test_data_insufficient_only_for_critical_missing_data() -> None:
    decision = build_unified_decision(
        _live_row(entry_zone="unavailable", invalidation_level="unavailable", stop_loss_reference="unavailable"),
        portfolio_row=None,
        scan_generated_at="2026-04-24T12:00:00Z",
        validation_context=build_validation_context(),
        reference_date=ANCHOR,
    )

    assert decision["actionability_label"] == "Data Insufficient"
    assert decision["primary_action"] == "Data Insufficient"
    assert decision["level_status"] == "Hidden"


def test_daily_decision_markdown_stays_short_and_bucketed() -> None:
    def decision(ticker: str, label: str, *, why_not: str = "Needs review.", trigger: str = "Wait for setup.") -> dict[str, object]:
        return {
            "ticker": ticker,
            "primary_action": "Research / Buy Candidate" if label in {"Breakout Actionable Today", "Long-Term Research Candidate"} else "Watch",
            "actionability_label": label,
            "actionability_score": 80,
            "actionability_reason": f"{ticker} setup summary.",
            "why_not": why_not,
            "entry_label": "Entry",
            "entry_zone": "99 - 101",
            "stop_loss": 94,
            "tp1": 110,
            "tp2": 118,
            "data_freshness": "Fresh enough",
            "action_trigger": trigger,
            "price_validation_reason": "No validated live price.",
            "level_status": "Actionable",
        }

    payload = {
        "generated_at": "2026-04-24T12:00:00Z",
        "analysis_date": "2026-04-24",
        "provider": "real",
        "ai_rerank": "off",
        "demo_mode": False,
        "top_candidate": decision("TOP", "Breakout Actionable Today"),
        "fast_actionable_setups": [decision("TOP", "Breakout Actionable Today")],
        "long_term_research_candidates": [decision(f"R{i}", "Long-Term Research Candidate") for i in range(5)],
        "high_volume_mover_watch": [decision(f"M{i}", "High-Volume Mover Watch", trigger=f"Wait for M{i}") for i in range(6)],
        "tracked_watchlist_setups": [decision(f"T{i}", "Slow Compounder Watch", trigger=f"Wait for T{i}") for i in range(6)],
        "watch_candidates": [decision(f"W{i}", "Watch for Better Entry", trigger=f"Wait for W{i}") for i in range(6)],
        "avoid_candidates": [decision(f"A{i}", "Avoid / Do Not Chase", why_not=f"Avoid {i}") for i in range(6)],
        "data_issues": [decision(f"D{i}", "Data Insufficient") for i in range(12)],
        "no_clean_candidate_reason": "",
    }

    markdown = _build_daily_decision_markdown(payload)

    assert "# TradeBruv Daily Pick" in markdown
    assert "## Fast Actionable Setups" in markdown
    assert "## Long-Term Research Candidates" in markdown
    assert "## High-Volume Movers" in markdown
    assert "## Tracked Watchlist Setups" in markdown
    assert "## Watch for Better Entry" in markdown
    assert "## Avoid / Do Not Chase" in markdown
    assert "R0" in markdown and "R4" in markdown
    assert "M0" in markdown and "M4" in markdown and "M5" not in markdown
    assert "W0" in markdown and "W4" in markdown and "W5" not in markdown
    assert "A0" in markdown and "A4" in markdown and "A5" not in markdown
    assert "D0" in markdown and "D9" in markdown and "D10" not in markdown
