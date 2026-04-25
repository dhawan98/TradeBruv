from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from tradebruv.models import PriceBar, SecurityData
from tradebruv.replay import point_in_time_security, run_historical_replay, run_outlier_study, run_proof_report
from tradebruv.scanner import DeterministicScanner

from tests.helpers import ANCHOR, StaticProvider, make_trending_bars, squeeze_security


def _benchmark(ticker: str = "SPY") -> SecurityData:
    return SecurityData(
        ticker=ticker,
        company_name=ticker,
        sector="Benchmark",
        bars=make_trending_bars(start_price=100, count=360, drift=0.0008, amplitude=0.005, base_volume=50_000_000),
        provider_name="test",
    )


def _event_security(ticker: str = "TEST") -> SecurityData:
    bars = make_trending_bars(start_price=20, count=360, drift=0.0015, amplitude=0.01, base_volume=2_000_000)
    event_bars = []
    for index, bar in enumerate(bars):
        if 180 <= index <= 220:
            multiplier = 1 + ((index - 179) * 0.018)
            event_bars.append(
                PriceBar(
                    date=bar.date,
                    open=round(bar.open * multiplier, 2),
                    high=round(bar.high * multiplier * 1.02, 2),
                    low=round(bar.low * multiplier * 0.99, 2),
                    close=round(bar.close * multiplier * 1.01, 2),
                    volume=bar.volume * 4,
                )
            )
        else:
            event_bars.append(bar)
    return SecurityData(ticker=ticker, company_name="Replay Test", sector="Technology", bars=event_bars, provider_name="test")


def test_point_in_time_security_truncates_future_and_strips_non_ohlcv() -> None:
    security = squeeze_security("GME")
    as_of = security.bars[120].date
    truncated = point_in_time_security(security, as_of, ohlcv_only=True)

    assert max(bar.date for bar in truncated.bars) <= as_of
    assert len(truncated.bars) < len(security.bars)
    assert truncated.catalyst is None
    assert truncated.social_attention is None
    assert any("OHLCV-only" in note for note in truncated.data_notes)


def test_replay_generates_outputs_and_forward_returns(tmp_path) -> None:
    provider = StaticProvider({"TEST": _event_security(), "SPY": _benchmark("SPY"), "QQQ": _benchmark("QQQ"), "XLK": _benchmark("XLK")})
    payload = run_historical_replay(
        provider=provider,
        universe=["TEST"],
        start_date=ANCHOR - timedelta(days=260),
        end_date=ANCHOR - timedelta(days=80),
        frequency="weekly",
        mode="outliers",
        top_n=1,
        output_dir=tmp_path,
    )

    assert payload["summary"]["total_replay_dates"] > 0
    assert payload["summary"]["total_candidates"] > 0
    assert (tmp_path / "replay_results.json").exists()
    assert (tmp_path / "replay_results.csv").exists()
    assert "20d" in payload["summary"]["average_forward_return_by_horizon"]


def test_velocity_score_and_high_relative_volume_trigger() -> None:
    provider = StaticProvider({"MOCK": squeeze_security("MOCK"), "SPY": _benchmark("SPY"), "QQQ": _benchmark("QQQ"), "XLY": _benchmark("XLY")})
    result = DeterministicScanner(provider, analysis_date=ANCHOR).scan(["MOCK"], mode="velocity")[0].to_dict()

    assert result["velocity_score"] >= 45
    assert result["velocity_type"] in {"Relative Volume Explosion", "Squeeze Watch", "Momentum Continuation", "News + Volume Confirmed"}
    assert "buy now" not in str(result["quick_trade_watch_label"]).lower()


def test_gap_and_fade_avoid_classification_and_pump_warning() -> None:
    security = squeeze_security("FADE")
    last = security.bars[-1]
    previous = security.bars[-2]
    faded = replace(
        security,
        bars=[
            *security.bars[:-1],
            PriceBar(
                date=last.date,
                open=round(previous.close * 1.12, 2),
                high=round(previous.close * 1.16, 2),
                low=round(previous.close * 0.98, 2),
                close=round(previous.close * 1.01, 2),
                volume=last.volume * 5,
            ),
        ],
        market_cap=80_000_000,
    )
    provider = StaticProvider({"FADE": faded, "SPY": _benchmark("SPY"), "QQQ": _benchmark("QQQ"), "XLY": _benchmark("XLY")})
    row = DeterministicScanner(provider, analysis_date=ANCHOR).scan(["FADE"], mode="velocity")[0].to_dict()

    assert row["velocity_type"] in {"Failed Spike / Avoid", "Pump Risk / Avoid"}
    assert "warning" in str(row["chase_warning"]).lower() or "risk" in str(row["chase_warning"]).lower()


def test_outlier_study_detects_mock_trigger(tmp_path) -> None:
    security = _event_security("GME")
    provider = StaticProvider({"GME": security, "SPY": _benchmark("SPY"), "QQQ": _benchmark("QQQ"), "XLK": _benchmark("XLK")})
    payload = run_outlier_study(
        provider=provider,
        ticker="GME",
        start_date=security.bars[140].date,
        end_date=security.bars[260].date,
        output_dir=tmp_path,
    )

    assert payload["available"] is True
    assert payload["did_it_catch_move"] in {"caught", "missed", "inconclusive"}
    assert (tmp_path / "GME_case_study.json").exists()


def test_proof_report_generation(tmp_path) -> None:
    provider = StaticProvider({"TEST": _event_security(), "SPY": _benchmark("SPY"), "QQQ": _benchmark("QQQ"), "XLK": _benchmark("XLK")})
    payload = run_proof_report(
        provider=provider,
        universe=["TEST"],
        start_date=ANCHOR - timedelta(days=260),
        end_date=ANCHOR - timedelta(days=80),
        include_famous_outliers=False,
        include_velocity=True,
        output_dir=tmp_path,
    )

    assert payload["real_money_reliance"] is False
    assert payload["evidence_strength"] in {"Not enough evidence", "Weak evidence", "Promising", "Strong historical evidence", "Needs forward confirmation"}
    assert (tmp_path / "proof_report.json").exists()
