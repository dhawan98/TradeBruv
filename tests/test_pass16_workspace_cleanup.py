from __future__ import annotations

from pathlib import Path

from tradebruv.daily_decision import _build_workspace_payload
from tradebruv.decision_merge import merge_canonical_rows
from tradebruv.ticker_symbols import display_ticker, provider_ticker
from tradebruv.universe_registry import validate_universe_file


def _decision(
    ticker: str,
    *,
    source_group: str,
    status: str,
    actionability_score: int,
    regular_score: int,
    winner_score: int,
    setup_quality: int,
    current_price: float,
    timestamp: str = "2026-04-29T15:00:00Z",
) -> dict:
    return {
        "ticker": ticker,
        "source_group": source_group,
        "primary_action": "Research / Buy Candidate" if status == "PASS" else "Data Insufficient",
        "actionability_label": "Breakout Actionable Today" if status == "PASS" else "Data Insufficient",
        "actionability_score": actionability_score,
        "price_validation_status": status,
        "price_sanity": {
            "price_validation_status": status,
            "price_timestamp": timestamp,
        },
        "source_row": {
            "ticker": ticker,
            "scan_source_group": source_group,
            "current_price": current_price,
            "regular_investing_score": regular_score,
            "winner_score": winner_score,
            "setup_quality_score": setup_quality,
            "price_validation_status": status,
            "price_sanity": {
                "price_validation_status": status,
                "price_timestamp": timestamp,
            },
        },
    }


def test_canonical_merge_prefers_valid_broad_row_over_failed_tracked_row() -> None:
    failed_tracked = _decision(
        "AAPL",
        source_group="Tracked",
        status="FAIL",
        actionability_score=0,
        regular_score=10,
        winner_score=5,
        setup_quality=5,
        current_price=0.0,
        timestamp="2026-04-29T10:00:00Z",
    )
    valid_broad = _decision(
        "AAPL",
        source_group="Broad",
        status="PASS",
        actionability_score=82,
        regular_score=75,
        winner_score=66,
        setup_quality=71,
        current_price=212.45,
        timestamp="2026-04-29T15:30:00Z",
    )

    merged = merge_canonical_rows(
        rows=[failed_tracked["source_row"], valid_broad["source_row"]],
        decisions=[failed_tracked, valid_broad],
    )

    assert len(merged["canonical_decisions"]) == 1
    row = merged["canonical_decisions"][0]
    assert row["ticker"] == "AAPL"
    assert row["price_validation_status"] == "PASS"
    assert row["best_source_group"] == "Broad"
    assert row["source_groups"] == ["Tracked", "Broad"]
    assert row["failed_source_groups"] == ["Tracked"]
    assert row["valid_source_groups"] == ["Broad"]
    assert row["source_row"]["current_price"] == 212.45
    assert row["has_conflicting_source_rows"] is True


def test_workspace_payload_uses_canonical_selected_ticker() -> None:
    nvda = _decision(
        "NVDA",
        source_group="Tracked",
        status="PASS",
        actionability_score=88,
        regular_score=84,
        winner_score=76,
        setup_quality=80,
        current_price=201.1,
    )
    watch = _decision(
        "SBUX",
        source_group="Broad",
        status="PASS",
        actionability_score=64,
        regular_score=59,
        winner_score=55,
        setup_quality=58,
        current_price=105.2,
    )
    watch["actionability_label"] = "Long-Term Research Candidate"

    workspace = _build_workspace_payload(
        [nvda, watch],
        coverage_status={"universe_label": "Large Cap Starter"},
        data_issues=[],
        top_n=25,
    )

    assert workspace["selected_ticker"] == "NVDA"
    assert workspace["selected_ticker_consistency_status"] == "PASS"
    assert workspace["decision_by_ticker"]["NVDA"]["ticker"] == "NVDA"
    assert workspace["source_aware_top"]["overall_top_setup"]["ticker"] == "NVDA"


def test_universe_validate_flags_partial_sp500_file(tmp_path: Path) -> None:
    path = tmp_path / "universe_sp500.txt"
    path.write_text("AAPL\nMSFT\nNVDA\n", encoding="utf-8")

    payload = validate_universe_file(path)

    assert payload["universe_label"] == "Large Cap Starter"
    assert payload["expected_universe_size"] == 500
    assert payload["is_partial_universe"] is True
    assert "not a full live S&P 500 membership list" in payload["universe_warning"]


def test_class_ticker_mapping_uses_display_and_provider_symbols() -> None:
    assert display_ticker("BRK-B") == "BRK.B"
    assert display_ticker("brk.b") == "BRK.B"
    assert provider_ticker("BRK.B") == "BRK-B"
    assert provider_ticker("BF.B") == "BF-B"
