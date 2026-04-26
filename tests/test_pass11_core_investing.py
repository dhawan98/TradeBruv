from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from tradebruv.analysis import build_portfolio_recommendation
from tradebruv.models import FundamentalsSnapshot, SecurityData
from tradebruv.portfolio import PortfolioPosition
from tradebruv.replay import run_investing_proof_report, run_investing_replay, run_portfolio_replay
from tradebruv.scanner import DeterministicScanner

from tests.helpers import ANCHOR, StaticProvider, make_trending_bars, sample_results


def _benchmark(ticker: str = "SPY") -> SecurityData:
    return SecurityData(
        ticker=ticker,
        company_name=ticker,
        sector="Benchmark",
        bars=make_trending_bars(start_price=100, count=420, drift=0.0005, amplitude=0.004, base_volume=50_000_000),
        provider_name="test",
    )


def _quality_security(ticker: str = "QGRO") -> SecurityData:
    return SecurityData(
        ticker=ticker,
        company_name="Quality Growth Inc.",
        sector="Technology",
        industry="Software",
        bars=make_trending_bars(start_price=30, count=420, drift=0.0018, amplitude=0.006, base_volume=4_000_000),
        market_cap=90_000_000_000,
        fundamentals=FundamentalsSnapshot(
            revenue_growth=0.22,
            eps_growth=0.25,
            margin_change=0.03,
            free_cash_flow_growth=0.18,
            analyst_revision_score=0.5,
            profitability_positive=True,
            recent_dilution=False,
            estimate_revision_trend=0.5,
        ),
        provider_name="test",
    )


def _broken_value_trap(ticker: str = "TRAP") -> SecurityData:
    return SecurityData(
        ticker=ticker,
        company_name="Broken Value Co.",
        sector="Technology",
        industry="Hardware",
        bars=make_trending_bars(start_price=80, count=420, drift=-0.0018, amplitude=0.008, base_volume=3_000_000),
        market_cap=4_000_000_000,
        fundamentals=FundamentalsSnapshot(
            revenue_growth=-0.14,
            eps_growth=-0.25,
            free_cash_flow_growth=-0.2,
            profitability_positive=False,
            recent_dilution=True,
        ),
        provider_name="test",
    )


def _provider(*securities: SecurityData) -> StaticProvider:
    payload = {security.ticker: security for security in securities}
    payload.update({"SPY": _benchmark("SPY"), "QQQ": _benchmark("QQQ"), "XLK": _benchmark("XLK")})
    return StaticProvider(payload)


def test_regular_investing_score_and_quality_growth_classification() -> None:
    row = DeterministicScanner(_provider(_quality_security()), analysis_date=ANCHOR).scan(["QGRO"], mode="investing")[0].to_dict()

    assert row["regular_investing_score"] >= 70
    assert row["investing_style"] in {"Long-Term Compounder", "Quality Growth Leader", "Profitable Growth"}
    assert row["investing_action_label"] in {"High Priority Research", "Buy Candidate", "Add on Strength"}
    assert "research candidate" not in row["investing_reason"].lower() or "order" not in row["investing_reason"].lower()


def test_value_trap_and_broken_thesis_exit_candidate() -> None:
    row = DeterministicScanner(_provider(_broken_value_trap()), analysis_date=ANCHOR).scan(["TRAP"], mode="investing")[0].to_dict()

    assert row["investing_style"] in {"Avoid / Value Trap", "Exit / Broken Thesis"}
    assert row["investing_action_label"] in {"Avoid", "Exit / Sell Candidate"}
    assert "value trap" in row["value_trap_warning"].lower() or "broken" in row["investing_bear_case"].lower()


def test_portfolio_aware_add_trim_hold_labels() -> None:
    scanner_row = sample_results()["NVDA"].to_dict()
    add_position = PortfolioPosition(ticker="NVDA", quantity=1, current_price=100, market_value=100, average_cost=80, position_weight_pct=5)
    trim_position = PortfolioPosition(ticker="NVDA", quantity=1, current_price=100, market_value=100, average_cost=80, position_weight_pct=25)

    add_decision = build_portfolio_recommendation(position=add_position, scanner_row=scanner_row)
    trim_decision = build_portfolio_recommendation(position=trim_position, scanner_row=scanner_row)

    assert add_decision["core_investing_decision"] in {"Strong Hold", "Add on Strength", "Add on Better Entry", "Hold"}
    assert trim_decision["core_investing_decision"] in {"Trim", "Strong Hold", "Hold"}
    assert "concentration_warning" in trim_decision
    assert "reason_to_exit" in add_decision


def test_investing_replay_outputs_and_no_lookahead_limitations(tmp_path) -> None:
    quality = _quality_security()
    future_boosted = replace(
        quality,
        bars=[
            *quality.bars[:-20],
            *[
                replace(bar, close=round(bar.close * 1.5, 2), high=round(bar.high * 1.55, 2), volume=bar.volume * 3)
                for bar in quality.bars[-20:]
            ],
        ],
    )
    payload = run_investing_replay(
        provider=_provider(future_boosted),
        universe=["QGRO"],
        start_date=ANCHOR - timedelta(days=260),
        end_date=ANCHOR - timedelta(days=80),
        frequency="monthly",
        output_dir=tmp_path,
        random_baseline=True,
    )

    assert payload["summary"]["total_replay_dates"] > 0
    assert "Replay truncates OHLCV" in payload["point_in_time_limitations"]
    assert (tmp_path / "investing_replay_results.json").exists()
    assert (tmp_path / "investing_replay_results.csv").exists()
    assert (tmp_path / "investing_replay_summary.md").exists()


def test_investing_proof_and_portfolio_replay_generation(tmp_path) -> None:
    provider = _provider(_quality_security(), _broken_value_trap())
    proof = run_investing_proof_report(
        provider=provider,
        universe=["QGRO", "TRAP"],
        start_date=ANCHOR - timedelta(days=260),
        end_date=ANCHOR - timedelta(days=80),
        output_dir=tmp_path,
    )
    portfolio = run_portfolio_replay(
        provider=provider,
        universe=["QGRO", "TRAP"],
        start_date=ANCHOR - timedelta(days=260),
        end_date=ANCHOR - timedelta(days=80),
        output_dir=tmp_path,
    )

    assert proof["real_money_reliance"] is False
    assert "does_regular_investing_score_beat_SPY" in proof["answers"]
    assert (tmp_path / "investing_proof_report.json").exists()
    assert portfolio["summary"]["total_decisions"] > 0
    assert (tmp_path / "portfolio_replay_report.json").exists()
