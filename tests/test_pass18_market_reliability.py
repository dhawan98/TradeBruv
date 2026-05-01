from __future__ import annotations

import importlib.util
import json
import math
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from tradebruv.broad_scan import run_broad_scan
from tradebruv.daily_decision import run_daily_decision
from tradebruv.market_cache import FileCacheMarketDataProvider
from tradebruv.market_reliability import ProviderStopError, ResilientMarketDataProvider, build_provider_check_report, classify_provider_error
from tradebruv.models import PriceBar, SecurityData
from tradebruv.movers import run_movers_scan
from tradebruv.providers import ProviderFetchError
from tradebruv.scanner import ScanDiagnostics


def _security(ticker: str, closes: list[float], *, volumes: list[float] | None = None) -> SecurityData:
    volume_series = volumes or [1_000_000.0 for _ in closes]
    start = date(2025, 1, 1)
    bars = [
        PriceBar(
            date=start + timedelta(days=index),
            open=closes[index - 1] if index else closes[index] * 0.99,
            high=close * 1.01,
            low=close * 0.99,
            close=close,
            volume=volume_series[index],
        )
        for index, close in enumerate(closes)
    ]
    return SecurityData(
        ticker=ticker,
        company_name=ticker,
        sector="Technology" if ticker not in {"SPY", "QQQ"} else None,
        industry="Software",
        bars=bars,
        provider_name="sample",
        latest_available_close=bars[-1].close,
        last_market_date=bars[-1].date,
        quote_price_if_available=bars[-1].close,
    )


def test_rate_limit_classification_and_resilient_provider_stop() -> None:
    class FailingProvider:
        def get_security_data(self, ticker: str) -> SecurityData:
            raise RuntimeError(f"Too Many Requests for {ticker}")

    resilient = ResilientMarketDataProvider(FailingProvider(), provider_name="yfinance", history_period="6mo")
    assert classify_provider_error(RuntimeError("429 Too Many Requests"))["status"] == "rate_limited"
    with pytest.raises(Exception):
        resilient.get_security_data("NVDA")
    with pytest.raises(Exception):
        resilient.get_security_data("MSFT")
    with pytest.raises(ProviderStopError):
        resilient.get_security_data("AAPL")
    assert resilient.health_report()["status"] == "rate_limited"
    assert resilient.should_stop_scan() is True


def test_ticker_failure_does_not_mark_provider_degraded() -> None:
    class MixedProvider:
        def get_security_data(self, ticker: str) -> SecurityData:
            if ticker == "BAD":
                raise ProviderFetchError("possibly delisted; no price data found")
            return _security(ticker, list(range(100, 360)))

    resilient = ResilientMarketDataProvider(MixedProvider(), provider_name="yfinance", history_period="6mo")
    with pytest.raises(ProviderFetchError) as exc_info:
        resilient.get_security_data("BAD")
    good = resilient.get_security_data("GOOD")

    assert getattr(exc_info.value, "category", "") == "delisted_or_invalid"
    assert good.ticker == "GOOD"
    health = resilient.health_report()
    assert health["ticker_failures_count"] == 1
    assert health["provider_failures_count"] == 0
    assert health["status"] == "healthy"
    assert resilient.should_stop_scan() is False


def test_repeated_rate_limits_trigger_provider_stop() -> None:
    class RateLimitedProvider:
        def get_security_data(self, ticker: str) -> SecurityData:
            raise RuntimeError("429 Too Many Requests")

    resilient = ResilientMarketDataProvider(RateLimitedProvider(), provider_name="yfinance", history_period="6mo")
    for ticker in ("A", "B"):
        with pytest.raises(Exception):
            resilient.get_security_data(ticker)
    assert resilient.should_stop_scan() is False
    with pytest.raises(ProviderStopError):
        resilient.get_security_data("C")
    health = resilient.health_report()
    assert health["rate_limit_failures"] == 3
    assert health["status"] == "rate_limited"
    assert health["stop_scan"] is True


def test_broad_scan_keeps_failures_out_of_ranked_rows(monkeypatch, tmp_path: Path) -> None:
    class FakeResult:
        def __init__(self, ticker: str, score: int) -> None:
            self.ticker = ticker
            self.score = score

        def to_dict(self) -> dict[str, object]:
            return {
                "ticker": self.ticker,
                "company_name": self.ticker,
                "current_price": 100.0,
                "regular_investing_score": self.score,
                "outlier_score": self.score,
                "velocity_score": 25,
                "last_market_date": "2026-04-29",
                "price_change_1d_pct": 3.4,
                "relative_volume_20d": 1.8,
                "ema_stack": "Bullish Stack",
                "signal_summary": "Breakout with Volume",
                "signal_grade": "A",
            }

    def fake_scan(self, tickers, **_: object):
        return ScanDiagnostics(
            results=[FakeResult("NVDA", 92)],
            failures=[{"ticker": "FAIL", "reason": "Too Many Requests", "category": "rate_limited"}],
            attempted=2,
            aborted_tickers=["AAPL"],
            provider_health={"provider": "real", "status": "rate_limited", "stop_scan": True, "stop_reason": "Provider rate-limited after 1 symbols"},
            benchmark_health={},
        )

    monkeypatch.setattr("tradebruv.broad_scan.DeterministicScanner.scan_with_diagnostics", fake_scan)
    result = run_broad_scan(
        universe=["NVDA", "FAIL", "AAPL"],
        provider_name="sample",
        analysis_date=date(2026, 4, 29),
        output_dir=tmp_path / "outputs" / "broad_scan",
    )

    assert [row["ticker"] for row in result.payload["decisions"]] == ["NVDA"]
    assert result.payload["scan_incomplete"] is True
    assert {row["ticker"] for row in result.payload["scan_failures"]} == {"FAIL", "AAPL"}
    assert result.payload["top_avoid_names"] == []


def test_movers_scan_finds_gainers_losers_and_unusual_volume(monkeypatch, tmp_path: Path) -> None:
    provider_map = {
        "SPY": _security("SPY", list(range(100, 360))),
        "QQQ": _security("QQQ", list(range(100, 360))),
        "GAIN": _security("GAIN", [100.0] * 40 + [101, 102, 103, 104, 105, 106, 107, 108, 109, 115], volumes=[1_000_000.0] * 49 + [3_200_000.0]),
        "DROP": _security("DROP", list(range(180, 120, -1))),
        "VOLUME": _security("VOLUME", [80.0 + (index * 0.2) for index in range(60)], volumes=[600_000.0] * 59 + [2_400_000.0]),
    }

    class Provider:
        def get_security_data(self, ticker: str) -> SecurityData:
            return provider_map[ticker]

    monkeypatch.setattr("tradebruv.movers.build_provider", lambda **_: Provider())
    result = run_movers_scan(
        universe=["GAIN", "DROP", "VOLUME"],
        provider_name="sample",
        analysis_date=date(2026, 4, 29),
        output_dir=tmp_path / "outputs" / "movers",
    )

    assert result.payload["top_gainers"][0]["ticker"] == "GAIN"
    assert result.payload["top_losers"][0]["ticker"] == "DROP"
    assert any(row["ticker"] == "VOLUME" for row in result.payload["unusual_volume"])


def test_movers_continue_after_one_invalid_ticker(monkeypatch, tmp_path: Path) -> None:
    provider_map = {
        "SPY": _security("SPY", list(range(100, 360))),
        "QQQ": _security("QQQ", list(range(100, 360))),
        "GAIN": _security("GAIN", [100.0] * 40 + [101, 102, 103, 104, 105, 106, 107, 108, 109, 115], volumes=[1_000_000.0] * 49 + [3_200_000.0]),
        "VOLUME": _security("VOLUME", [80.0 + (index * 0.2) for index in range(60)], volumes=[600_000.0] * 59 + [2_400_000.0]),
    }

    class Provider:
        def get_security_data(self, ticker: str) -> SecurityData:
            if ticker == "BAD":
                raise ProviderFetchError("possibly delisted; no price data found")
            return provider_map[ticker]

    monkeypatch.setattr("tradebruv.movers.build_provider", lambda **_: Provider())
    result = run_movers_scan(
        universe=["GAIN", "BAD", "VOLUME"],
        provider_name="sample",
        analysis_date=date(2026, 4, 29),
        output_dir=tmp_path / "outputs" / "movers",
    )

    assert result.payload["tickers_attempted"] == 3
    assert result.payload["tickers_successfully_scanned"] == 2
    assert len(result.payload["scan_failures"]) == 1
    assert result.payload["scan_failures"][0]["ticker"] == "BAD"
    assert {row["ticker"] for row in result.payload["results"]} == {"GAIN", "VOLUME"}


def test_market_cache_falls_back_to_cached_security(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TRADEBRUV_ALLOW_CACHE_ON_PROVIDER_FAILURE", "true")
    monkeypatch.setenv("TRADEBRUV_MAX_CACHE_AGE_HOURS", "24")

    class Provider:
        def __init__(self, security: SecurityData | None) -> None:
            self.security = security

        def get_security_data(self, ticker: str) -> SecurityData:
            if self.security is None:
                raise RuntimeError("Too Many Requests")
            return self.security

    security = _security("NVDA", list(range(100, 360)))
    cache_dir = tmp_path / "cache"
    writer = FileCacheMarketDataProvider(Provider(security), provider_name="real", cache_dir=cache_dir, ttl_minutes=1)
    writer.get_security_data("NVDA")
    cache_file = next(cache_dir.glob("*.json"))
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    payload["cached_at"] = (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z"
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    reader = FileCacheMarketDataProvider(Provider(None), provider_name="real", cache_dir=cache_dir, ttl_minutes=1)
    cached = reader.get_security_data("NVDA")

    assert cached.ticker == "NVDA"
    assert reader.cache_stats()["fallback_hits"] == 1


def test_invalid_nan_cached_bars_are_ignored_and_refetched(tmp_path: Path) -> None:
    calls: dict[str, int] = {}

    class Provider:
        def get_security_data(self, ticker: str) -> SecurityData:
            calls[ticker] = calls.get(ticker, 0) + 1
            return _security(ticker, list(range(100, 360)))

    cache_dir = tmp_path / "cache"
    reader = FileCacheMarketDataProvider(Provider(), provider_name="real", cache_dir=cache_dir, ttl_minutes=60)
    cache_path = reader._cache_path("MMC")
    bad_payload = {
        "cached_at": datetime.utcnow().isoformat() + "Z",
        "ticker": "MMC",
        "provider": "real",
        "history_period": "3y",
        "interval": "1d",
        "security": {
            "ticker": "MMC",
            "company_name": "MMC",
            "sector": "Financials",
            "industry": "Insurance",
            "bars": [
                {
                    "date": (date(2026, 4, 1) + timedelta(days=index)).isoformat(),
                    "open": math.nan,
                    "high": math.nan,
                    "low": math.nan,
                    "close": math.nan,
                    "volume": math.nan,
                }
                for index in range(5)
            ],
            "provider_name": "real",
            "source_notes": [],
            "data_notes": [],
            "quote_price_if_available": math.nan,
            "quote_timestamp": None,
            "latest_available_close": math.nan,
            "last_market_date": None,
            "is_adjusted_price": True,
        },
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(bad_payload), encoding="utf-8")

    security = reader.get_security_data("MMC")

    assert calls["MMC"] == 1
    assert len(security.bars) > 200
    assert all(math.isfinite(bar.close) for bar in security.bars)


def test_invalid_json_cached_file_is_ignored_and_refetched(tmp_path: Path) -> None:
    calls: dict[str, int] = {}

    class Provider:
        def get_security_data(self, ticker: str) -> SecurityData:
            calls[ticker] = calls.get(ticker, 0) + 1
            return _security(ticker, list(range(100, 360)))

    cache_dir = tmp_path / "cache"
    reader = FileCacheMarketDataProvider(Provider(), provider_name="real", cache_dir=cache_dir, ttl_minutes=60)
    cache_path = reader._cache_path("FDX")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text('{"cached_at":"2026-04-24T00:00:00Z"}{"broken":true}', encoding="utf-8")

    security = reader.get_security_data("FDX")

    assert calls["FDX"] == 1
    assert security.ticker == "FDX"
    assert not cache_path.exists() or json.loads(cache_path.read_text(encoding="utf-8"))["ticker"] == "FDX"


def test_json_decode_errors_are_sanitized_as_malformed_responses() -> None:
    classification = classify_provider_error(json.JSONDecodeError("Extra data", "{}", 1))

    assert classification["category"] == "malformed_response"
    assert classification["scope"] == "ticker"
    assert classification["reason"] == "Provider or cache returned malformed market data for this ticker."


def test_nan_cached_bars_do_not_surface_numerator_failures(monkeypatch, tmp_path: Path) -> None:
    class Provider:
        def get_security_data(self, ticker: str) -> SecurityData:
            if ticker in {"SPY", "QQQ"}:
                return _security(ticker, list(range(100, 360)))
            return _security(ticker, [100.0 + index for index in range(260)])

    cache_dir = tmp_path / "cache"
    reader = FileCacheMarketDataProvider(Provider(), provider_name="sample", cache_dir=cache_dir, ttl_minutes=60)
    cache_path = reader._cache_path("MMC")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({
        "cached_at": datetime.utcnow().isoformat() + "Z",
        "ticker": "MMC",
        "provider": "sample",
        "history_period": "3y",
        "interval": "1d",
        "security": {
            "ticker": "MMC",
            "company_name": "MMC",
            "sector": "Financials",
            "industry": "Insurance",
            "bars": [{
                "date": (date(2026, 4, 1) + timedelta(days=index)).isoformat(),
                "open": math.nan,
                "high": math.nan,
                "low": math.nan,
                "close": math.nan,
                "volume": math.nan,
            } for index in range(10)],
            "provider_name": "sample",
            "source_notes": [],
            "data_notes": [],
            "quote_price_if_available": math.nan,
            "quote_timestamp": None,
            "latest_available_close": math.nan,
            "last_market_date": None,
            "is_adjusted_price": False,
        },
    }), encoding="utf-8")

    monkeypatch.setattr("tradebruv.movers.build_provider", lambda **_: Provider())
    monkeypatch.setattr("tradebruv.movers.DEFAULT_MARKET_CACHE_DIR", cache_dir)

    result = run_movers_scan(
        universe=["MMC", "GOOD"],
        provider_name="sample",
        analysis_date=date(2026, 4, 29),
        output_dir=tmp_path / "outputs" / "movers",
    )

    assert {row["ticker"] for row in result.payload["results"]} == {"MMC", "GOOD"}
    assert all("numerator" not in str(row.get("reason", "")).lower() for row in result.payload["scan_failures"])


def test_daily_decision_dedupes_failures_and_uses_movers_sections(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    broad_path = config_dir / "broad.txt"
    tracked_path = config_dir / "tracked.txt"
    core_path = config_dir / "core.txt"
    outlier_path = config_dir / "outlier.txt"
    velocity_path = config_dir / "velocity.txt"
    broad_path.write_text("NVDA\nFAIL\n", encoding="utf-8")
    tracked_path.write_text("NVDA\nFAIL\n", encoding="utf-8")
    core_path.write_text("", encoding="utf-8")
    outlier_path.write_text("", encoding="utf-8")
    velocity_path.write_text("", encoding="utf-8")

    empty_scan = SimpleNamespace(
        generated_at="2026-04-29T12:00:00Z",
        provider="real",
        source="baseline",
        market_regime={},
        results=[],
        scan_failures=[],
        cache_stats={"hits": 0, "misses": 0, "ttl_minutes": 60},
    )

    def fake_run_custom_scan(*, tickers: list[str], **_: object):
        return SimpleNamespace(
            generated_at="2026-04-29T12:00:00Z",
            provider="real",
            source="custom",
            market_regime={},
            results=[{
                "ticker": "NVDA",
                "company_name": "NVIDIA",
                "current_price": 210.0,
                "regular_investing_score": 88,
                "outlier_score": 88,
                "velocity_score": 35,
                "last_market_date": "2026-04-29",
                "relative_volume_20d": 2.4,
                "ema_stack": "Bullish Stack",
                "signal_summary": "Breakout with Volume",
                "price_change_1d_pct": 6.2,
            }],
            scan_failures=[{"ticker": "FAIL", "reason": "Too Many Requests", "category": "rate_limited"}],
            provider_health={"provider": "real", "status": "rate_limited", "stop_scan": True, "stop_reason": "Provider rate-limited after 1 symbols"},
            cache_stats={"hits": 1, "misses": 1, "ttl_minutes": 60},
        )

    def fake_run_movers_scan(**_: object):
        return SimpleNamespace(
            payload={
                "generated_at": "2026-04-29T12:00:00Z",
                "results": [{
                    "ticker": "NVDA",
                    "company_name": "NVIDIA",
                    "company": "NVIDIA",
                    "current_price": 210.0,
                    "regular_investing_score": 88,
                    "outlier_score": 88,
                    "velocity_score": 35,
                    "last_market_date": "2026-04-29",
                    "relative_volume_20d": 2.4,
                    "relative_volume": 2.4,
                    "ema_stack": "Bullish Stack",
                    "signal_summary": "Breakout with Volume",
                    "signal": "Breakout with Volume",
                    "price_change_1d_pct": 6.2,
                    "percent_change": 6.2,
                    "freshness": "2026-04-29",
                    "dollar_volume": 50000000.0,
                    "mover_type": "Top Gainers",
                }],
                "scan_failures": [{"ticker": "FAIL", "reason": "Too Many Requests", "category": "rate_limited"}],
                "provider_health": {"provider": "real", "status": "rate_limited", "stop_scan": True, "stop_reason": "Provider rate-limited after 1 symbols"},
                "cache": {"hits": 1, "misses": 1, "ttl_minutes": 60},
                "tickers_attempted": 12,
                "tickers_successfully_scanned": 11,
                "top_gainers": [{
                    "ticker": "NVDA",
                    "company": "NVIDIA",
                    "price": 210.0,
                    "percent_change": 6.2,
                    "relative_volume": 2.4,
                    "dollar_volume": 50000000.0,
                    "mover_type": "Top Gainers",
                    "signal": "Breakout with Volume",
                    "freshness": "2026-04-29",
                }],
                "top_losers": [],
                "unusual_volume": [{
                    "ticker": "NVDA",
                    "company": "NVIDIA",
                    "price": 210.0,
                    "percent_change": 6.2,
                    "relative_volume": 2.4,
                    "dollar_volume": 50000000.0,
                    "mover_type": "Unusual Volume",
                    "signal": "Breakout with Volume",
                    "freshness": "2026-04-29",
                }],
                "breakout_volume": [{
                    "ticker": "NVDA",
                    "company": "NVIDIA",
                    "price": 210.0,
                    "percent_change": 6.2,
                    "relative_volume": 2.4,
                    "dollar_volume": 50000000.0,
                    "mover_type": "Breakout with Volume",
                    "signal": "Breakout with Volume",
                    "freshness": "2026-04-29",
                }],
            }
        )

    def fake_build_unified_decisions(rows: list[dict[str, object]], **_: object):
        decisions = []
        for row in rows:
            source_group = str(row.get("scan_source_group"))
            decisions.append(
                {
                    "ticker": "NVDA",
                    "company": "NVIDIA",
                    "primary_action": "Research / Buy Candidate",
                    "action_lane": "Outlier",
                    "source_group": source_group,
                    "source_groups": [source_group],
                    "score": 88,
                    "regular_investing_score": 88,
                    "actionability_score": 91,
                    "actionability_label": "Breakout Actionable Today",
                    "actionability_reason": "Breakout with volume.",
                    "reason": "Breakout with volume.",
                    "why_not": "Needs trend to hold.",
                    "level_status": "Actionable",
                    "entry_label": "Entry",
                    "entry_zone": "205 - 210",
                    "stop_loss": 198.0,
                    "tp1": 225.0,
                    "tp2": 240.0,
                    "risk_level": "Low",
                    "latest_market_date": "2026-04-29",
                    "trigger_needed": False,
                    "source_row": row,
                    "price_validation_status": "PASS",
                    "data_freshness": "Fresh enough",
                }
            )
        return decisions

    monkeypatch.setattr("tradebruv.daily_decision.run_dashboard_scan", lambda **_: empty_scan)
    monkeypatch.setattr("tradebruv.daily_decision._run_custom_scan", fake_run_custom_scan)
    monkeypatch.setattr("tradebruv.daily_decision.run_movers_scan", fake_run_movers_scan)
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
        include_movers=True,
        analysis_date=date(2026, 4, 29),
        output_dir=tmp_path / "outputs" / "daily",
    )

    assert payload["scan_failures"] == [{
        "ticker": "FAIL",
        "reason": "Too Many Requests",
        "category": "rate_limited",
        "source_groups": ["Broad", "Movers", "Tracked"],
        "lanes": ["Outlier"],
    }]
    assert payload["data_coverage_status"]["tickers_failed"] == 1
    assert payload["best_mover_setup"]["ticker"] == "NVDA"
    assert payload["top_gainers"][0]["ticker"] == "NVDA"
    assert payload["top_gainers"][0]["percent_change"] == 6.2
    assert payload["unusual_volume"][0]["relative_volume"] == 2.4
    assert payload["breakout_volume"][0]["ticker"] == "NVDA"
    assert "## Best Mover Setup" in (tmp_path / "outputs" / "daily" / "decision_today.md").read_text(encoding="utf-8")
    assert "## Breakout with Volume" in (tmp_path / "outputs" / "daily" / "decision_today.md").read_text(encoding="utf-8")
    review_text = (tmp_path / "outputs" / "daily" / "decision_quality_review.md").read_text(encoding="utf-8")
    assert "Did movers scan complete?" in review_text
    assert "What were the best mover setups?" in review_text


def test_provider_check_uses_fallback_when_primary_fails(monkeypatch) -> None:
    class PrimaryProvider:
        def __init__(self, history_period: str = "6mo") -> None:
            self.history_period = history_period

        def get_security_data(self, ticker: str) -> SecurityData:
            raise RuntimeError("timeout")

    class FallbackProvider:
        def __init__(self, history_period: str = "6mo") -> None:
            self.history_period = history_period

        def get_security_data(self, ticker: str) -> SecurityData:
            return _security(ticker, list(range(100, 360)))

    monkeypatch.setattr("tradebruv.providers.YFinanceMarketDataProvider", PrimaryProvider)
    monkeypatch.setattr("tradebruv.market_reliability._build_fallback_providers", lambda **_: [("finnhub", FallbackProvider())])

    report = build_provider_check_report("NVDA", provider_name="real", include_fallbacks=True)

    assert report["success"] is True
    assert report["final_selected_source"] == "sample"
    assert report["fallback_used"] is True
    assert any(check["provider"] == "finnhub" and check["success"] for check in report["checks"])


def test_daily_decision_reuses_unique_fetches_once_per_run(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "core.txt").write_text("NVDA\nAAPL\n", encoding="utf-8")
    (config_dir / "outlier.txt").write_text("NVDA\n", encoding="utf-8")
    (config_dir / "velocity.txt").write_text("AAPL\n", encoding="utf-8")
    (config_dir / "broad.txt").write_text("NVDA\nAAPL\n", encoding="utf-8")
    (config_dir / "tracked.txt").write_text("NVDA\n", encoding="utf-8")

    counts: dict[str, int] = {}

    class CountingProvider:
        def get_security_data(self, ticker: str) -> SecurityData:
            counts[ticker] = counts.get(ticker, 0) + 1
            return _security(ticker, list(range(100, 360)))

    def fake_build_unified_decisions(rows: list[dict[str, object]], **_: object):
        return [
            {
                "ticker": str(row["ticker"]),
                "company": str(row["ticker"]),
                "primary_action": "Research / Buy Candidate",
                "action_lane": "Outlier",
                "source_group": str(row.get("scan_source_group") or "Broad"),
                "source_groups": [str(row.get("scan_source_group") or "Broad")],
                "score": 80,
                "regular_investing_score": 80,
                "actionability_score": 80,
                "actionability_label": "Breakout Actionable Today",
                "actionability_reason": "Shared cache test.",
                "reason": "Shared cache test.",
                "why_not": "Watch risk.",
                "level_status": "Actionable",
                "entry_label": "Entry",
                "entry_zone": "99 - 101",
                "stop_loss": 94.0,
                "tp1": 110.0,
                "tp2": 118.0,
                "risk_level": "Low",
                "latest_market_date": "2026-04-29",
                "trigger_needed": False,
                "source_row": row,
                "price_validation_status": "PASS",
                "data_freshness": "Fresh enough",
            }
            for row in rows
        ]

    monkeypatch.setattr("tradebruv.daily_decision.build_provider", lambda **_: CountingProvider())
    monkeypatch.setattr("tradebruv.daily_decision.load_dashboard_portfolio", lambda: [])
    monkeypatch.setattr("tradebruv.daily_decision.build_unified_decisions", fake_build_unified_decisions)
    monkeypatch.setattr("tradebruv.daily_decision.build_daily_summary", lambda rows: {"count": len(rows)})

    payload = run_daily_decision(
        provider_name="sample",
        core_universe=config_dir / "core.txt",
        outlier_universe=config_dir / "outlier.txt",
        velocity_universe=config_dir / "velocity.txt",
        broad_universe=config_dir / "broad.txt",
        tracked=config_dir / "tracked.txt",
        include_movers=True,
        analysis_date=date(2026, 4, 29),
        output_dir=tmp_path / "outputs" / "daily",
    )

    assert counts["NVDA"] == 1
    assert counts["AAPL"] == 1
    assert payload["data_coverage_status"]["unique_candidate_tickers_requested"] == 2


pytestmark_api = pytest.mark.skipif(importlib.util.find_spec("fastapi") is None, reason="FastAPI is not installed")


@pytestmark_api
def test_async_scan_endpoints_return_job_progress(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "outputs").mkdir()
    source_template = Path(__file__).resolve().parents[1] / ".env.example"
    (tmp_path / ".env.example").write_text(source_template.read_text(encoding="utf-8"), encoding="utf-8")

    def fake_run_scan(payload: dict[str, object]) -> dict[str, object]:
        callback = payload.get("progress_callback")
        if callable(callback):
            callback({"attempted": 3, "scanned": 2, "failed": 1, "ticker": "NVDA", "latest_result": {"ticker": "NVDA", "current_price": 100.0, "price_change_1d_pct": 2.0, "relative_volume_20d": 1.5, "signal_summary": "Breakout with Volume", "outlier_score": 82}})
        return {
            "generated_at": "2026-04-29T12:00:00Z",
            "provider": "sample",
            "mode": "outliers",
            "results": [],
            "summary": {},
            "market_regime": {},
            "decisions": [],
            "data_issues": [],
            "scan_health": {"attempted": 3, "scanned": 2, "failed": 1, "provider_health": {"status": "degraded"}},
            "provider_health": {"status": "degraded"},
            "scan_failures": [{"ticker": "FAIL", "reason": "Provider timed out"}],
        }

    monkeypatch.setattr("tradebruv.api_services.run_scan", fake_run_scan)

    from fastapi.testclient import TestClient
    from tradebruv.api import create_app

    client = TestClient(create_app())
    started = client.post("/api/scan/start", json={"provider": "sample", "mode": "outliers", "universe_path": "config/sample_universe.txt"}).json()
    time.sleep(0.1)
    status = client.get(f"/api/scan/status/{started['job_id']}").json()
    result = client.get(f"/api/scan/result/{started['job_id']}").json()

    assert status["status"] == "completed"
    assert status["attempted"] == 3
    assert status["preview_rows"][0]["ticker"] == "NVDA"
    assert result["scan_failures"][0]["ticker"] == "FAIL"
