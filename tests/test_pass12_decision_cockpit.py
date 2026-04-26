from __future__ import annotations

from datetime import date

from tradebruv.decision_engine import build_unified_decision, build_unified_decisions, build_validation_context
from tradebruv.price_sanity import build_price_sanity_from_row

from tests.helpers import ANCHOR, sample_results


def test_sample_provider_price_warning_is_explicit() -> None:
    row = sample_results()["NVDA"].to_dict()
    sanity = build_price_sanity_from_row(row, reference_date=ANCHOR, scan_generated_at="2026-04-24T12:00:00Z")

    assert sanity["is_sample_data"] is True
    assert "Sample data" in sanity["price_warning"]
    assert sanity["price_confidence"] == "Low"


def test_stale_scan_and_price_warnings_surface() -> None:
    row = sample_results()["MSFT"].to_dict() | {
        "provider": "real",
        "provider_name": "real",
        "is_sample_data": False,
        "last_market_date": "2026-04-21",
        "latest_available_close": 100.0,
        "quote_price_if_available": None,
    }
    sanity = build_price_sanity_from_row(row, reference_date=date(2026, 4, 25), scan_generated_at="2026-04-21T12:00:00Z")

    assert sanity["is_stale_price"] is True
    assert sanity["scan_is_stale"] is True
    assert "Stale price data." in sanity["price_warning"]
    assert "Latest close, not live quote." in sanity["price_warning"]


def test_quote_close_mismatch_warning_surfaces() -> None:
    row = sample_results()["PLTR"].to_dict() | {
        "provider": "real",
        "provider_name": "real",
        "is_sample_data": False,
        "last_market_date": "2026-04-24",
        "latest_available_close": 100.0,
        "quote_price_if_available": 112.0,
    }
    sanity = build_price_sanity_from_row(row, reference_date=ANCHOR, scan_generated_at="2026-04-24T12:00:00Z")

    assert "materially" in sanity["price_warning"]
    assert sanity["price_confidence"] == "Medium"


def test_missing_price_becomes_data_insufficient() -> None:
    row = sample_results()["RIVN"].to_dict() | {
        "current_price": "unavailable",
        "latest_available_close": "unavailable",
        "quote_price_if_available": "unavailable",
        "provider": "real",
        "provider_name": "real",
        "is_sample_data": False,
    }
    decision = build_unified_decision(
        row,
        portfolio_row=None,
        scan_generated_at="2026-04-24T12:00:00Z",
        validation_context=build_validation_context(),
        reference_date=ANCHOR,
    )

    assert decision["primary_action"] == "Data Insufficient"
    assert "price unavailable" in decision["price_sanity"]["price_warning"].lower()


def test_validation_context_plain_english_message() -> None:
    context = build_validation_context(
        investing_proof_report={
            "evidence_strength": "Mixed evidence",
            "real_money_reliance": False,
            "answers": {
                "does_regular_investing_score_beat_SPY": "Yes in this replay window.",
                "does_regular_investing_score_beat_QQQ": "Yes in this replay window.",
                "does_it_beat_random_baseline": "No in this replay window.",
            },
        },
        signal_quality_report={"conclusion": "This bucket has high false-positive risk."},
    )

    assert "This strategy beat SPY/QQQ but did not beat random baseline." in context["messages"]
    assert "This bucket has high false-positive risk." in context["messages"]
    assert "This label is paper-track only." in context["messages"]


def test_preferred_lane_keeps_outlier_scan_out_of_core_lane() -> None:
    row = sample_results()["NVDA"].to_dict()

    decisions = build_unified_decisions(
        [row],
        scan_generated_at="2026-04-24T12:00:00Z",
        validation_context=build_validation_context(),
        reference_date=ANCHOR,
        preferred_lane="Outlier",
    )

    assert decisions[0]["action_lane"] == "Outlier"
