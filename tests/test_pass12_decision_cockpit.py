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
    assert decision["entry_zone"] == "unavailable"
    assert decision["tp1"] == "unavailable"


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


def test_sample_provider_cannot_create_actionable_tp_sl_board() -> None:
    row = sample_results()["NVDA"].to_dict()

    decision = build_unified_decision(
        row,
        portfolio_row=None,
        scan_generated_at="2026-04-24T12:00:00Z",
        validation_context=build_validation_context(),
        reference_date=ANCHOR,
    )

    assert decision["primary_action"] == "Data Insufficient"
    assert decision["price_validation_status"] == "FAIL"
    assert decision["is_actionable"] is False
    assert "Demo sample data" in decision["price_validation_reason"]
    assert decision["entry_zone"] == "unavailable"
    assert decision["stop_loss"] == "unavailable"
    assert decision["tp1"] == "unavailable"
    assert decision["tp2"] == "unavailable"


def test_report_snapshot_row_is_marked_historical_and_hidden() -> None:
    row = sample_results()["PLTR"].to_dict() | {
        "provider": "real",
        "provider_name": "real",
        "is_sample_data": False,
        "current_price": 120.0,
        "latest_available_close": 120.0,
        "quote_price_if_available": 120.0,
        "last_market_date": "2026-04-24",
        "data_mode": "report_snapshot",
        "is_report_only": True,
        "report_snapshot_selected": False,
    }

    decision = build_unified_decision(
        row,
        portfolio_row=None,
        scan_generated_at="2026-04-24T12:00:00Z",
        validation_context=build_validation_context(),
        reference_date=ANCHOR,
    )

    assert decision["primary_action"] == "Data Insufficient"
    assert decision["price_validation_status"] == "FAIL"
    assert "historical snapshot" in decision["price_validation_reason"]
    assert decision["entry_zone"] == "unavailable"


def test_price_mismatch_above_ten_percent_fails_validation_and_flags_split() -> None:
    row = sample_results()["NVDA"].to_dict() | {
        "provider": "real",
        "provider_name": "real",
        "is_sample_data": False,
        "current_price": 1050.82,
        "latest_available_close": 131.35,
        "quote_price_if_available": 132.0,
        "last_market_date": "2026-04-24",
    }

    sanity = build_price_sanity_from_row(row, reference_date=ANCHOR, scan_generated_at="2026-04-24T12:00:00Z")

    assert sanity["price_validation_status"] == "FAIL"
    assert sanity["price_mismatch_pct"] != "unavailable"
    assert float(sanity["price_mismatch_pct"]) > 10
    assert sanity["possible_split_adjustment_mismatch"] is True
    assert "Possible split/adjustment mismatch." in sanity["price_validation_reason"]


def test_valid_quote_latest_close_passes_price_validation() -> None:
    row = sample_results()["MSFT"].to_dict() | {
        "provider": "real",
        "provider_name": "real",
        "is_sample_data": False,
        "price_source": "latest quote",
        "current_price": 422.15,
        "latest_available_close": 421.7,
        "quote_price_if_available": 422.15,
        "last_market_date": "2026-04-24",
    }

    sanity = build_price_sanity_from_row(row, reference_date=ANCHOR, scan_generated_at="2026-04-24T12:00:00Z")

    assert sanity["price_validation_status"] == "PASS"
    assert sanity["validated_price"] == 422.15
    assert sanity["validated_price_source"] == "live quote"
    assert sanity["levels_allowed"] is True


def test_decision_engine_sorts_failed_price_rows_out_of_top_candidate_lane() -> None:
    good = sample_results()["MSFT"].to_dict() | {
        "provider": "real",
        "provider_name": "real",
        "is_sample_data": False,
        "price_source": "latest quote",
        "current_price": 422.15,
        "latest_available_close": 421.7,
        "quote_price_if_available": 422.15,
        "last_market_date": "2026-04-24",
    }
    bad = sample_results()["NVDA"].to_dict() | {
        "provider": "real",
        "provider_name": "real",
        "is_sample_data": False,
        "price_source": "latest quote",
        "current_price": 1050.82,
        "latest_available_close": 131.35,
        "quote_price_if_available": 132.0,
        "last_market_date": "2026-04-24",
    }

    decisions = build_unified_decisions(
        [bad, good],
        scan_generated_at="2026-04-24T12:00:00Z",
        validation_context=build_validation_context(),
        reference_date=ANCHOR,
        preferred_lane="Outlier",
    )

    assert decisions[0]["ticker"] == "MSFT"
    assert decisions[0]["price_validation_status"] == "PASS"
    assert decisions[-1]["ticker"] == "NVDA"
    assert decisions[-1]["primary_action"] == "Data Insufficient"
