from __future__ import annotations

from pathlib import Path

from tradebruv.ai_rerank import apply_ai_rerank
from tradebruv.daily_decision import _build_picker_view
from tradebruv.universe_registry import expand_universe


def _decision(
    ticker: str,
    label: str,
    *,
    source_group: str = "Broad",
    primary_action: str | None = None,
    status_label: str = "Trade Setup Forming",
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "primary_action": primary_action or ("Research / Buy Candidate" if "Candidate" in label or "Actionable" in label else "Watch"),
        "actionability_label": label,
        "actionability_score": 82,
        "actionability_reason": f"{ticker} summary",
        "reason": f"{ticker} reason",
        "why_not": f"{ticker} why not",
        "source_group": source_group,
        "level_status": "Actionable" if "Actionable" in label else "Conditional",
        "entry_label": "Entry",
        "entry_zone": "99 - 101",
        "action_trigger": f"Wait for {ticker}",
        "price_validation_status": "PASS",
        "source_row": {
            "ticker": ticker,
            "status_label": status_label,
            "current_price": 100.0,
            "relative_volume_20d": 1.8,
            "relative_volume_50d": 1.2,
            "signal_summary": "Breakout with Volume",
            "warnings": [],
            "why_it_could_fail": [],
            "data_availability_notes": [],
        },
    }


class _MockRerankProvider:
    name = "mock-rerank"

    def __init__(self, response: dict[str, object]) -> None:
        self.response = response

    def review(self, prompt_payload: dict[str, object]) -> dict[str, object]:
        return dict(self.response)


def test_picker_view_separates_movers_from_long_term_candidates() -> None:
    decisions = [
        _decision("ROST", "Long-Term Research Candidate"),
        _decision("QCOM", "High-Volume Mover Watch", source_group="Movers", primary_action="Watch"),
        _decision("PWR", "Breakout Actionable Today"),
        _decision("IRM", "Slow Compounder Watch", source_group="Tracked", primary_action="Watch"),
    ]

    picker = _build_picker_view(decisions, data_issues=[])

    assert [row["ticker"] for row in picker["fast_actionable_setups"]] == ["PWR"]
    assert [row["ticker"] for row in picker["long_term_research_candidates"]] == ["ROST"]
    assert [row["ticker"] for row in picker["high_volume_mover_watch"]] == ["QCOM"]
    assert [row["ticker"] for row in picker["tracked_watchlist_setups"]] == ["IRM"]


def test_ai_reranker_cannot_invent_data() -> None:
    provider = _MockRerankProvider(
        {
            "available": True,
            "provider": "mock-rerank",
            "bullish_case": ["Strong quality trend."],
            "bearish_case": ["Review https://invented.example.com before buying."],
            "what_would_make_me_buy": "Wait for support to hold.",
            "what_would_make_me_avoid": "Avoid if support breaks.",
            "deterministic_label_too_aggressive": True,
            "suggested_label": "Long-Term Research Candidate",
            "final_ai_caution": "medium",
            "rerank_score": 65,
            "disagreement_reason": "The deterministic label is too aggressive without better tape.",
            "missing_data": ["fresh catalyst"],
        }
    )

    [reviewed] = apply_ai_rerank([_decision("ROST", "Breakout Actionable Today")], mode="openai", provider=provider, limit=5)

    assert reviewed["ai_review"]["unsupported_claims_detected"] is True
    assert "ai_adjusted_actionability_label" not in reviewed


def test_ai_reranker_can_downgrade_but_not_override_hard_risk_flags() -> None:
    downgrade_provider = _MockRerankProvider(
        {
            "available": True,
            "provider": "mock-rerank",
            "bullish_case": ["Quality trend is intact."],
            "bearish_case": ["Volume is too weak for a fast setup."],
            "what_would_make_me_buy": "A real volume pickup or fresh catalyst.",
            "what_would_make_me_avoid": "Keep avoiding fast entries while relative volume stays weak.",
            "deterministic_label_too_aggressive": True,
            "suggested_label": "Long-Term Research Candidate",
            "final_ai_caution": "high",
            "rerank_score": 58,
            "disagreement_reason": "The setup looks investable, but not tactically actionable.",
            "missing_data": ["fresh catalyst"],
        }
    )
    [downgraded] = apply_ai_rerank([_decision("ROST", "Breakout Actionable Today")], mode="openai", provider=downgrade_provider, limit=5)
    assert downgraded["ai_adjusted_actionability_label"] == "Long-Term Research Candidate"

    upgrade_provider = _MockRerankProvider(
        {
            "available": True,
            "provider": "mock-rerank",
            "bullish_case": ["Looks better."],
            "bearish_case": ["Still risky."],
            "what_would_make_me_buy": "Not applicable.",
            "what_would_make_me_avoid": "Stay away.",
            "deterministic_label_too_aggressive": False,
            "suggested_label": "Breakout Actionable Today",
            "final_ai_caution": "high",
            "rerank_score": 30,
            "disagreement_reason": "No change.",
            "missing_data": [],
        }
    )
    [avoided] = apply_ai_rerank([_decision("RISK", "Avoid / Do Not Chase", primary_action="Avoid", status_label="Avoid")], mode="openai", provider=upgrade_provider, limit=5)
    assert avoided["actionability_label"] == "Avoid / Do Not Chase"
    assert "ai_adjusted_actionability_label" not in avoided


def test_universe_expand_creates_larger_deduped_universe(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "universe_us_broad_1000.txt").write_text("AAPL\nMSFT\nNVDA\n", encoding="utf-8")
    (config_dir / "universe_sp500.txt").write_text("AAPL\nAMZN\nMETA\n", encoding="utf-8")
    (config_dir / "tracked_tickers.txt").write_text("PLTR\nNVDA\n", encoding="utf-8")
    csv_path = tmp_path / "custom.csv"
    csv_path.write_text("symbol\nTSM\nPLTR\nAVGO\n", encoding="utf-8")

    payload = expand_universe(
        output_path=config_dir / "universe_us_liquid_expanded.txt",
        target_size=12,
        csv_inputs=[(csv_path, "symbol")],
    )

    rows = (config_dir / "universe_us_liquid_expanded.txt").read_text(encoding="utf-8").splitlines()
    assert payload["actual_size"] == 12
    assert len(rows) == len(set(rows))
    assert {"AAPL", "MSFT", "NVDA", "TSM", "AVGO", "PLTR"}.issubset(set(rows))
