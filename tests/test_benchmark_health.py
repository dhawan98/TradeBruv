from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from tradebruv.benchmarking import BENCHMARK_DEGRADED_WARNING
from tradebruv.broad_scan import run_broad_scan
from tradebruv.daily_decision import run_daily_decision
from tradebruv.market_cache import FileCacheMarketDataProvider
from tradebruv.models import PriceBar, SecurityData
from tradebruv.scanner import DeterministicScanner


def _security(ticker: str, closes: list[float], *, sector: str | None = "Technology") -> SecurityData:
    start = date(2025, 1, 1)
    bars = [
        PriceBar(
            date=start + timedelta(days=index),
            open=closes[index - 1] if index else close * 0.99,
            high=close * 1.01,
            low=close * 0.99,
            close=close,
            volume=1_000_000.0,
        )
        for index, close in enumerate(closes)
    ]
    return SecurityData(
        ticker=ticker,
        company_name=ticker,
        sector=sector,
        industry="Software",
        bars=bars,
        provider_name="sample",
        latest_available_close=bars[-1].close,
        last_market_date=bars[-1].date,
        quote_price_if_available=bars[-1].close,
    )


def _decision_rows(rows: list[dict[str, object]], **_: object) -> list[dict[str, object]]:
    decisions = []
    for row in rows:
        source_group = str(row.get("scan_source_group") or "Broad")
        score = int(row.get("regular_investing_score") or row.get("outlier_score") or row.get("velocity_score") or 80)
        decisions.append(
            {
                "ticker": str(row.get("ticker")),
                "company": str(row.get("company_name") or row.get("ticker")),
                "primary_action": "Research / Buy Candidate",
                "action_lane": str(row.get("decision_source_lane") or "Outlier"),
                "source_group": source_group,
                "source_groups": [source_group],
                "score": score,
                "regular_investing_score": score,
                "actionability_score": 85,
                "actionability_label": "Breakout Actionable Today",
                "actionability_reason": "Benchmark degradation should not fail the stock.",
                "reason": "Benchmark degradation should not fail the stock.",
                "why_not": "None.",
                "level_status": "Actionable",
                "entry_label": "Entry",
                "entry_zone": "100 - 101",
                "stop_loss": 95.0,
                "tp1": 110.0,
                "tp2": 120.0,
                "risk_level": "Low",
                "latest_market_date": str(row.get("last_market_date") or "2025-09-17"),
                "trigger_needed": False,
                "source_row": row,
                "price_validation_status": "PASS",
                "data_freshness": "Fresh enough",
            }
        )
    return decisions


def test_xly_fetched_once_for_multiple_consumer_cyclical_stocks() -> None:
    counts: dict[str, int] = {}

    class Provider:
        def get_security_data(self, ticker: str) -> SecurityData:
            counts[ticker] = counts.get(ticker, 0) + 1
            if ticker in {"SPY", "QQQ"}:
                return _security(ticker, list(range(100, 360)), sector=None)
            if ticker == "XLY":
                return _security(ticker, list(range(90, 350)), sector=None)
            return _security(ticker, list(range(120, 380)), sector="Consumer Cyclical")

    scanner = DeterministicScanner(provider=Provider(), analysis_date=date(2026, 5, 1))
    diagnostics = scanner.scan_with_diagnostics(["AMZN", "HD"], mode="outliers", include_failures_in_results=False)

    assert diagnostics.failures == []
    assert counts["XLY"] == 1
    assert counts["SPY"] == 1
    assert counts["QQQ"] == 1


def test_benchmark_cache_reused_across_broad_scan(monkeypatch, tmp_path: Path) -> None:
    counts: dict[str, int] = {}
    cache_dir = tmp_path / "cache"
    tracked_path = tmp_path / "tracked.txt"
    tracked_path.write_text("", encoding="utf-8")

    class Provider:
        def get_security_data(self, ticker: str) -> SecurityData:
            counts[ticker] = counts.get(ticker, 0) + 1
            if ticker in {"SPY", "QQQ"}:
                return _security(ticker, list(range(100, 360)), sector=None)
            if ticker == "XLY":
                return _security(ticker, list(range(90, 350)), sector=None)
            return _security(ticker, list(range(120, 380)), sector="Consumer Cyclical")

    monkeypatch.setattr("tradebruv.broad_scan.build_provider", lambda **_: Provider())
    monkeypatch.setattr("tradebruv.broad_scan.DEFAULT_MARKET_CACHE_DIR", cache_dir)

    run_broad_scan(
        universe=["AMZN"],
        provider_name="sample",
        analysis_date=date(2026, 5, 1),
        tracked_path=tracked_path,
        output_dir=tmp_path / "outputs" / "first",
    )
    run_broad_scan(
        universe=["HD"],
        provider_name="sample",
        analysis_date=date(2026, 5, 1),
        tracked_path=tracked_path,
        output_dir=tmp_path / "outputs" / "second",
    )

    assert counts["XLY"] == 1
    assert counts["SPY"] == 1
    assert counts["QQQ"] == 1


def test_xly_rate_limit_does_not_fail_stock_scan() -> None:
    class Provider:
        def get_security_data(self, ticker: str) -> SecurityData:
            if ticker == "XLY":
                raise RuntimeError("Too Many Requests. Rate limited. Try after a while.")
            if ticker in {"SPY", "QQQ"}:
                return _security(ticker, list(range(100, 360)), sector=None)
            return _security(ticker, list(range(120, 380)), sector="Consumer Cyclical")

    scanner = DeterministicScanner(provider=Provider(), analysis_date=date(2026, 5, 1))
    diagnostics = scanner.scan_with_diagnostics(["AMZN"], mode="outliers", include_failures_in_results=False)

    assert diagnostics.failures == []
    assert diagnostics.results[0].ticker == "AMZN"
    assert diagnostics.results[0].data_used["sector_benchmark_available"] is False
    assert diagnostics.results[0].data_used["sector_relative_strength"] == "unavailable"
    assert diagnostics.benchmark_health["benchmark_health"] == "rate_limited"


def test_benchmark_unavailable_downgrades_relative_strength_gracefully() -> None:
    class Provider:
        def get_security_data(self, ticker: str) -> SecurityData:
            if ticker == "XLY":
                raise RuntimeError("No history returned for XLY from yfinance.")
            if ticker in {"SPY", "QQQ"}:
                return _security(ticker, list(range(100, 360)), sector=None)
            return _security(ticker, list(range(120, 380)), sector="Consumer Cyclical")

    scanner = DeterministicScanner(provider=Provider(), analysis_date=date(2026, 5, 1))
    diagnostics = scanner.scan_with_diagnostics(["AMZN"], mode="outliers", include_failures_in_results=False)
    row = diagnostics.results[0]

    assert row.status_label != "Avoid"
    assert row.data_used["benchmark_degraded"] is True
    assert row.data_used["sector_benchmark_available"] is False
    assert row.data_used["sector_relative_strength"] == "unavailable"


def test_repeated_benchmark_failures_produce_one_warning_not_spam(monkeypatch, tmp_path: Path) -> None:
    tracked_path = tmp_path / "tracked.txt"
    tracked_path.write_text("", encoding="utf-8")

    class Provider:
        def get_security_data(self, ticker: str) -> SecurityData:
            if ticker == "XLY":
                raise RuntimeError("Too Many Requests. Rate limited. Try after a while.")
            if ticker in {"SPY", "QQQ"}:
                return _security(ticker, list(range(100, 360)), sector=None)
            return _security(ticker, list(range(120, 380)), sector="Consumer Cyclical")

    monkeypatch.setattr("tradebruv.broad_scan.build_provider", lambda **_: Provider())
    monkeypatch.setattr("tradebruv.broad_scan.DEFAULT_MARKET_CACHE_DIR", tmp_path / "cache")

    result = run_broad_scan(
        universe=["AMZN", "HD"],
        provider_name="sample",
        analysis_date=date(2026, 5, 1),
        tracked_path=tracked_path,
        output_dir=tmp_path / "outputs" / "broad",
    )

    assert result.payload["benchmark_warnings"] == [BENCHMARK_DEGRADED_WARNING]
    assert result.payload["scan_failures"] == []


def test_decision_today_completes_when_benchmark_etf_fetch_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    for name in ("core.txt", "outlier.txt", "velocity.txt", "broad.txt", "tracked.txt"):
        (config_dir / name).write_text("AMZN\nHD\n", encoding="utf-8")

    class Provider:
        def get_security_data(self, ticker: str) -> SecurityData:
            if ticker == "XLY":
                raise RuntimeError("Too Many Requests. Rate limited. Try after a while.")
            if ticker in {"SPY", "QQQ"}:
                return _security(ticker, list(range(100, 360)), sector=None)
            return _security(ticker, list(range(120, 380)), sector="Consumer Cyclical")

    monkeypatch.setattr("tradebruv.daily_decision.build_provider", lambda **_: Provider())
    monkeypatch.setattr("tradebruv.daily_decision.build_unified_decisions", _decision_rows)
    monkeypatch.setattr("tradebruv.daily_decision.build_daily_summary", lambda rows: {"count": len(rows)})
    monkeypatch.setattr("tradebruv.daily_decision.load_dashboard_portfolio", lambda: [])

    payload = run_daily_decision(
        provider_name="sample",
        core_universe=config_dir / "core.txt",
        outlier_universe=config_dir / "outlier.txt",
        velocity_universe=config_dir / "velocity.txt",
        broad_universe=config_dir / "broad.txt",
        tracked=config_dir / "tracked.txt",
        include_movers=False,
        analysis_date=date(2026, 5, 1),
        output_dir=tmp_path / "outputs" / "daily",
    )

    assert payload["available"] is True
    assert payload["benchmark_warnings"] == [BENCHMARK_DEGRADED_WARNING]
    assert payload["scan_failures"] == []
    assert payload["decisions"]
    markdown = (tmp_path / "outputs" / "daily" / "decision_today.md").read_text(encoding="utf-8")
    assert markdown.count(BENCHMARK_DEGRADED_WARNING) == 1


def test_benchmark_health_report_marks_cache_and_rate_limit(tmp_path: Path) -> None:
    counts: dict[str, int] = {}

    class Provider:
        def get_security_data(self, ticker: str) -> SecurityData:
            counts[ticker] = counts.get(ticker, 0) + 1
            if ticker == "XLY":
                raise RuntimeError("Too Many Requests. Rate limited. Try after a while.")
            return _security(ticker, list(range(100, 360)), sector=None)

    cache_provider = FileCacheMarketDataProvider(Provider(), provider_name="sample", cache_dir=tmp_path / "cache", ttl_minutes=60)
    cache_provider.store_security(_security("SPY", list(range(100, 360)), sector=None), ticker="SPY")

    from tradebruv.benchmarking import build_benchmark_health_report

    report = build_benchmark_health_report(cache_provider, symbols=("SPY", "XLY"))

    assert report["benchmarks"][0]["status"] == "cache_hit"
    assert report["benchmarks"][1]["status"] == "rate_limited"
    assert report["benchmark_health"] == "rate_limited"
