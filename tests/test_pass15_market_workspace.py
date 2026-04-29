from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from tradebruv.broad_scan import run_broad_scan
from tradebruv.chart_signals import build_signal_snapshot
from tradebruv.daily_decision import run_daily_decision
from tradebruv.models import PriceBar, SecurityData
from tradebruv.tracked import add_tracked_ticker, list_tracked_tickers, remove_tracked_ticker


def _security_from_closes(closes: list[float], *, volumes: list[float] | None = None) -> SecurityData:
    series = volumes or [1_000_000.0 for _ in closes]
    start = date(2025, 1, 1)
    bars: list[PriceBar] = []
    for index, close in enumerate(closes):
        previous = closes[index - 1] if index else close * 0.99
        bars.append(
            PriceBar(
                date=start + timedelta(days=index),
                open=previous,
                high=max(previous, close) * 1.01,
                low=min(previous, close) * 0.99,
                close=close,
                volume=series[index],
            )
        )
    return SecurityData(
        ticker="TEST",
        company_name="Test Corp",
        sector="Technology",
        industry="Software",
        bars=bars,
        provider_name="sample",
        latest_available_close=closes[-1],
        last_market_date=bars[-1].date,
    )


def _decision_row(ticker: str, source_group: str, score: int, *, label: str = "Actionable Today", action: str = "Research / Buy Candidate") -> dict[str, object]:
    return {
        "ticker": ticker,
        "company_name": ticker,
        "current_price": 100.0,
        "regular_investing_score": score,
        "outlier_score": score,
        "velocity_score": 25,
        "price_validation_status": "PASS",
        "price_validation_reason": "Validated live price.",
        "actionability_score": score,
        "actionability_label": label,
        "actionability_reason": f"{ticker} looks actionable.",
        "primary_action": action,
        "reason": f"{ticker} reason.",
        "why_not": f"{ticker} why not.",
        "level_status": "Actionable" if label == "Actionable Today" else "Conditional",
        "entry_label": "Entry",
        "entry_zone": "99 - 101",
        "stop_loss": 94.0,
        "tp1": 110.0,
        "tp2": 118.0,
        "reward_risk": 2.0,
        "risk_level": "Low",
        "latest_market_date": "2026-04-24",
        "action_trigger": f"Wait for {ticker}",
        "trigger_needed": label != "Actionable Today",
        "source_group": source_group,
        "source_row": {
            "ticker": ticker,
            "current_price": 100.0,
            "price_change_1d_pct": 2.5,
            "relative_volume_20d": 1.5,
            "ema_stack": "Bullish Stack",
            "signal_summary": "Breakout with Volume",
        },
    }


def test_ema_and_volume_signals_cover_bullish_breakout_and_distribution() -> None:
    bullish = build_signal_snapshot(_security_from_closes(list(range(100, 360))))
    breakout = build_signal_snapshot(
        _security_from_closes([100.0] * 40 + [101, 102, 103, 104, 105, 106, 107, 108, 109, 112], volumes=[1_000_000.0] * 49 + [2_500_000.0])
    )
    pullback = build_signal_snapshot(_security_from_closes(list(range(100, 160)) + [155, 154, 153, 152, 151]))
    bearish = build_signal_snapshot(_security_from_closes(list(range(360, 100, -1))))
    distribution = build_signal_snapshot(
        _security_from_closes(
            list(range(100, 150)) + [149, 147, 146, 145, 144, 143],
            volumes=[1_000_000.0] * 50 + [1_800_000.0, 1_700_000.0, 1_600_000.0, 1_500_000.0, 1_400_000.0, 1_300_000.0],
        )
    )

    assert bullish["ema_21"] != "unavailable"
    assert bullish["ema_stack"] == "Bullish Stack"
    assert bearish["ema_stack"] == "Bearish Stack"
    assert breakout["signal_summary"] == "Breakout with Volume"
    assert breakout["relative_volume_20d"] == 2.33
    assert pullback["signal_summary"] == "Pullback to EMA 21"
    assert distribution["distribution_signal"] == "Distribution Warning"


def test_tracked_watchlist_add_remove_and_list(tmp_path) -> None:
    path = tmp_path / "tracked_tickers.txt"
    path.write_text("", encoding="utf-8")

    added = add_tracked_ticker("NVDA", path)
    add_tracked_ticker("PLTR", path)
    removed = remove_tracked_ticker("NVDA", path)

    assert added == ["NVDA"]
    assert list_tracked_tickers(path) == ["PLTR"]
    assert removed == ["PLTR"]


def test_broad_scan_handles_failures_and_limits_top_n(tmp_path) -> None:
    result = run_broad_scan(
        universe=["NVDA", "MISSING", "PLTR"],
        provider_name="sample",
        analysis_date=date(2026, 4, 24),
        top_n=1,
        output_dir=tmp_path / "outputs" / "broad_scan",
    )

    assert result.json_path.exists()
    assert result.csv_path.exists()
    assert result.markdown_path.exists()
    assert len(result.payload["decisions"]) <= 1
    assert any(item["ticker"] == "MISSING" for item in result.payload["failed_tickers"])


def test_decision_today_prefers_best_tracked_setup(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    broad_path = config_dir / "universe_sp500.txt"
    tracked_path = config_dir / "tracked_tickers.txt"
    core_path = config_dir / "core.txt"
    outlier_path = config_dir / "outlier.txt"
    velocity_path = config_dir / "velocity.txt"
    broad_path.write_text("BROAD\n", encoding="utf-8")
    tracked_path.write_text("TRACK\n", encoding="utf-8")
    core_path.write_text("", encoding="utf-8")
    outlier_path.write_text("", encoding="utf-8")
    velocity_path.write_text("", encoding="utf-8")

    empty_scan = SimpleNamespace(generated_at="2026-04-24T12:00:00Z", provider="real", source="baseline", market_regime={}, results=[], cache_stats={"hits": 0, "misses": 0, "ttl_minutes": 60})

    def fake_run_dashboard_scan(**_: object):
        return empty_scan

    def fake_run_custom_scan(*, tickers: list[str], **_: object):
        row = {
            "ticker": tickers[0],
            "company_name": tickers[0],
            "current_price": 100.0,
            "regular_investing_score": 90 if tickers[0] == "TRACK" else 75,
            "outlier_score": 90 if tickers[0] == "TRACK" else 75,
            "velocity_score": 25,
            "last_market_date": "2026-04-24",
            "relative_volume_20d": 1.5,
            "ema_stack": "Bullish Stack",
            "signal_summary": "Breakout with Volume",
            "price_change_1d_pct": 2.5,
        }
        return SimpleNamespace(generated_at="2026-04-24T12:00:00Z", provider="real", source="custom", market_regime={}, results=[row], cache_stats={"hits": 2, "misses": 1, "ttl_minutes": 60})

    def fake_build_unified_decisions(rows: list[dict[str, object]], **_: object):
        decisions = []
        for row in rows:
            ticker = str(row["ticker"])
            source_group = str(row["scan_source_group"])
            decisions.append(_decision_row(ticker, source_group, 95 if ticker == "TRACK" else 80))
        return decisions

    monkeypatch.setattr("tradebruv.daily_decision.run_dashboard_scan", fake_run_dashboard_scan)
    monkeypatch.setattr("tradebruv.daily_decision._run_custom_scan", fake_run_custom_scan)
    monkeypatch.setattr("tradebruv.daily_decision.build_unified_decisions", fake_build_unified_decisions)
    monkeypatch.setattr("tradebruv.daily_decision.load_dashboard_portfolio", lambda: [])
    monkeypatch.setattr("tradebruv.daily_decision.build_daily_summary", lambda rows: {"count": len(rows)})

    payload = run_daily_decision(
        provider_name="real",
        core_universe=core_path,
        outlier_universe=outlier_path,
        velocity_universe=velocity_path,
        broad_universe=broad_path,
        tracked=tracked_path,
        analysis_date=date(2026, 4, 24),
        output_dir=tmp_path / "outputs" / "daily",
    )

    assert payload["overall_top_candidate"]["ticker"] == "TRACK"
    assert payload["best_tracked_setup"]["ticker"] == "TRACK"
    assert payload["best_broad_setup"]["ticker"] == "BROAD"
    assert payload["data_coverage_status"]["cache_hits"] == 4
    assert payload["data_coverage_status"]["scan_groups"]


def test_decision_today_can_select_broad_candidate_over_tracked_watch(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    broad_path = config_dir / "universe_sp500.txt"
    tracked_path = config_dir / "tracked_tickers.txt"
    core_path = config_dir / "core.txt"
    outlier_path = config_dir / "outlier.txt"
    velocity_path = config_dir / "velocity.txt"
    broad_path.write_text("BROAD\n", encoding="utf-8")
    tracked_path.write_text("TRACK\n", encoding="utf-8")
    core_path.write_text("", encoding="utf-8")
    outlier_path.write_text("", encoding="utf-8")
    velocity_path.write_text("", encoding="utf-8")

    empty_scan = SimpleNamespace(generated_at="2026-04-24T12:00:00Z", provider="real", source="baseline", market_regime={}, results=[], cache_stats={"hits": 0, "misses": 0, "ttl_minutes": 60})
    monkeypatch.setattr("tradebruv.daily_decision.run_dashboard_scan", lambda **_: empty_scan)

    def fake_run_custom_scan(*, tickers: list[str], **_: object):
        row = {
            "ticker": tickers[0],
            "company_name": tickers[0],
            "current_price": 100.0,
            "regular_investing_score": 88 if tickers[0] == "BROAD" else 65,
            "outlier_score": 88 if tickers[0] == "BROAD" else 65,
            "velocity_score": 25,
            "last_market_date": "2026-04-24",
            "relative_volume_20d": 1.4,
            "ema_stack": "Bullish Stack",
            "signal_summary": "Breakout with Volume",
            "price_change_1d_pct": 2.1,
        }
        return SimpleNamespace(generated_at="2026-04-24T12:00:00Z", provider="real", source="custom", market_regime={}, results=[row], cache_stats={"hits": 1, "misses": 1, "ttl_minutes": 60})

    def fake_build_unified_decisions(rows: list[dict[str, object]], **_: object):
        decisions = []
        for row in rows:
            ticker = str(row["ticker"])
            if ticker == "TRACK":
                decisions.append(_decision_row("TRACK", "Tracked", 70, label="Watch for Trigger", action="Watch"))
            else:
                decisions.append(_decision_row("BROAD", "Broad", 92))
        return decisions

    monkeypatch.setattr("tradebruv.daily_decision._run_custom_scan", fake_run_custom_scan)
    monkeypatch.setattr("tradebruv.daily_decision.build_unified_decisions", fake_build_unified_decisions)
    monkeypatch.setattr("tradebruv.daily_decision.load_dashboard_portfolio", lambda: [])
    monkeypatch.setattr("tradebruv.daily_decision.build_daily_summary", lambda rows: {"count": len(rows)})

    payload = run_daily_decision(
        provider_name="real",
        core_universe=core_path,
        outlier_universe=outlier_path,
        velocity_universe=velocity_path,
        broad_universe=broad_path,
        tracked=tracked_path,
        analysis_date=date(2026, 4, 24),
        output_dir=tmp_path / "outputs" / "daily",
    )

    assert payload["overall_top_candidate"]["ticker"] == "BROAD"
    assert payload["best_tracked_setup"]["ticker"] == "TRACK"
    assert payload["best_broad_setup"]["ticker"] == "BROAD"
    assert payload["signal_table"]
    review = json.loads((tmp_path / "outputs" / "daily" / "decision_today.json").read_text(encoding="utf-8"))
    assert review["data_coverage_status"]["provider"] == "real"
