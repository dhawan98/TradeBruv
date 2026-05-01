from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from tradebruv.daily_decision import run_daily_decision
from tradebruv.discovery import PreparedTicker, build_coverage_audit, build_why_missed_report, run_earnings_movers_scan, run_highs_scan, run_theme_constituents_scan, run_theme_scan
from tradebruv.models import PriceBar, SecurityData
from tradebruv.movers import run_movers_scan
from tradebruv.universe_registry import clean_universe_file, import_universe_csv


ANCHOR = date(2026, 4, 24)


class Provider:
    def __init__(self, mapping: dict[str, SecurityData]) -> None:
        self.mapping = mapping

    def get_security_data(self, ticker: str) -> SecurityData:
        return self.mapping[ticker]


def _ticker(index: int) -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    chars: list[str] = []
    value = index
    for _ in range(4):
        chars.append(letters[value % 26])
        value //= 26
    return "".join(reversed(chars))


def _security(
    ticker: str,
    closes: list[float],
    *,
    volumes: list[float] | None = None,
    sector: str = "Technology",
    industry: str = "Software",
    company_name: str | None = None,
) -> SecurityData:
    volume_series = volumes or [1_000_000.0 for _ in closes]
    start = ANCHOR - timedelta(days=len(closes) + 120)
    bars: list[PriceBar] = []
    for index, close in enumerate(closes):
        previous = closes[index - 1] if index else close * 0.99
        current_date = start + timedelta(days=index)
        bars.append(
            PriceBar(
                date=current_date,
                open=previous,
                high=max(previous, close) * 1.01,
                low=min(previous, close) * 0.99,
                close=close,
                volume=volume_series[index],
            )
        )
    return SecurityData(
        ticker=ticker,
        company_name=company_name or ticker,
        sector=sector,
        industry=industry,
        bars=bars,
        provider_name="test",
        latest_available_close=bars[-1].close,
        last_market_date=bars[-1].date,
        quote_price_if_available=bars[-1].close,
    )


def _gapped_security(ticker: str) -> SecurityData:
    closes = [50.0 + (index * 0.1) for index in range(70)] + [63.0]
    volumes = [900_000.0 for _ in range(70)] + [4_200_000.0]
    security = _security(ticker, closes, volumes=volumes)
    previous = security.bars[-2]
    latest = security.bars[-1]
    security.bars[-1] = PriceBar(
        date=latest.date,
        open=previous.high * 1.04,
        high=latest.close * 1.03,
        low=latest.close * 0.97,
        close=latest.close,
        volume=latest.volume,
    )
    security.quote_price_if_available = security.bars[-1].close
    security.latest_available_close = security.bars[-1].close
    security.last_market_date = security.bars[-1].date
    return security


def _prepared(symbol: str, label: str) -> PreparedTicker:
    security = _security(symbol, [20.0 + (index * 0.1) for index in range(260)])
    row = {
        "ticker": symbol,
        "company_name": symbol,
        "current_price": 46.0,
        "signal_summary": "No Clean Signal",
        "signal_explanation": f"{symbol} explanation",
        "why_it_could_fail": [f"{symbol} risk"],
        "catalyst_tags": [],
        "theme_tags": [],
        "ema_21": 44.0,
        "ema_50": 40.0,
        "ema_150": 32.0,
        "ema_200": 28.0,
        "ema_stack": "Bullish Stack",
        "last_market_date": ANCHOR.isoformat(),
    }
    decision = {
        "ticker": symbol,
        "actionability_label": label,
        "actionability_score": 42,
        "trigger_needed": True,
        "action_trigger": f"Wait for {symbol}",
        "entry_zone": "44 - 45",
        "invalidation": 41.0,
        "stop_loss": 41.0,
        "risk_level": "High",
        "reason": f"{symbol} reason",
        "why_not": f"{symbol} why not",
        "price_validation_status": "PASS",
    }
    signal = {
        "relative_volume_20d": 1.1,
        "gap_up": False,
        "gap_down": False,
        "breakout_with_volume": False,
        "distribution_warning": False,
        "high_volume_red_candle_warning": False,
        "close_strength": 0.5,
        "close_below_ema_21": False,
        "close_below_ema_50": False,
        "close_below_ema_150": False,
        "close_below_ema_200": False,
        "price_vs_ema_21_pct": 3.0,
        "price_vs_ema_50_pct": 6.0,
        "signal_summary": "No Clean Signal",
    }
    metrics = {
        "current_price": 46.0,
        "volume": 1_200_000.0,
        "average_volume_20d": 1_100_000.0,
        "average_dollar_volume_20d": 50_000_000.0,
        "relative_volume": 1.1,
        "percent_change": 1.2,
        "return_1m": 8.0,
        "return_3m": 15.0,
        "rs_1m": 5.0,
        "rs_3m": 9.0,
        "benchmark_source": "SPY",
        "dollar_volume": 55_200_000.0,
        "high_52w": 48.0,
        "new_52_week_high": False,
        "near_52_week_high": True,
        "distance_from_52w_high_pct": -4.17,
        "gap_up": False,
        "gap_down": False,
        "breakout_with_volume": False,
        "distribution_or_heavy_selling": False,
        "gap_and_hold": False,
        "volume_confirms": False,
        "above_ema_21": True,
        "above_ema_50": True,
        "above_ema_150": True,
        "above_ema_200": True,
        "is_extended": False,
        "too_late": False,
        "theme_strength_score": 20.0,
        "earnings_mover_score": 6.0,
    }
    discovery = {
        "ticker": symbol,
        "actionability_label": label,
        "why_it_is_interesting": f"{symbol} reason",
        "why_it_may_fail": f"{symbol} why not",
        "entry_or_trigger": f"Wait for {symbol}",
        "current_price": 46.0,
        "percent_change": 1.2,
        "relative_volume": 1.1,
        "dollar_volume": 55_200_000.0,
        "average_volume_20d": 1_100_000.0,
        "market_cap": None,
        "signal_summary": "No Clean Signal",
        "risk_level": "High",
        "freshness": ANCHOR.isoformat(),
        "decision": decision,
    }
    return PreparedTicker(ticker=symbol, security=security, row=row, decision=decision, signal=signal, metrics=metrics, discovery=discovery)


def _decision_row(ticker: str, source_group: str, label: str = "Breakout Actionable Today") -> dict[str, object]:
    return {
        "ticker": ticker,
        "company": ticker,
        "primary_action": "Research / Buy Candidate" if label != "Avoid / Do Not Chase" else "Avoid",
        "actionability_label": label,
        "actionability_score": 84,
        "actionability_reason": f"{ticker} summary",
        "reason": f"{ticker} reason",
        "why_not": f"{ticker} why not",
        "source_group": source_group,
        "level_status": "Actionable" if "Actionable" in label else "Conditional",
        "entry_label": "Entry",
        "entry_zone": "99 - 101",
        "action_trigger": f"Wait for {ticker}",
        "price_validation_status": "PASS",
        "risk_level": "Medium",
        "source_row": {
            "ticker": ticker,
            "status_label": "Trade Setup Forming",
            "current_price": 100.0,
            "relative_volume_20d": 1.8,
            "relative_volume_50d": 1.2,
            "signal_summary": "Breakout with Volume",
            "warnings": [],
            "why_it_could_fail": [],
            "data_availability_notes": [],
        },
    }


def test_coverage_audit_detects_partial_universe(tmp_path: Path) -> None:
    universe_path = tmp_path / "universe.txt"
    tracked_path = tmp_path / "tracked.txt"
    universe_rows = [_ticker(index) for index in range(500)] + ["BAND", "BAND", "BAD1", "SPY"]
    tracked_rows = ["BAND", "XSD", "MISS"]
    universe_path.write_text("\n".join(universe_rows) + "\n", encoding="utf-8")
    tracked_path.write_text("\n".join(tracked_rows) + "\n", encoding="utf-8")

    result = build_coverage_audit(universe_path=universe_path, tracked_path=tracked_path, output_dir=tmp_path / "outputs")

    assert result.payload["coverage_label"] == "partial broad universe"
    assert "BAND" in result.payload["universe_file"]["duplicate_symbols"]
    assert "BAD1" in result.payload["universe_file"]["invalid_symbols"]
    assert result.payload["tracked_symbols_missing"] == ["MISS", "XSD"]


def test_why_missed_reports_outside_universe_for_any_symbol(tmp_path: Path) -> None:
    universe_path = tmp_path / "universe.txt"
    tracked_path = tmp_path / "tracked.txt"
    universe_path.write_text("AAPL\nMSFT\n", encoding="utf-8")
    tracked_path.write_text("", encoding="utf-8")

    band = build_why_missed_report(symbol="BAND", provider_name="sample", universe_path=universe_path, tracked_path=tracked_path, output_dir=tmp_path / "outputs")
    custom = build_why_missed_report(symbol="ZZZZ", provider_name="sample", universe_path=universe_path, tracked_path=tracked_path, output_dir=tmp_path / "outputs")

    assert band.payload["exact_reason"] == "outside universe"
    assert custom.payload["exact_reason"] == "outside universe"


def test_why_missed_reports_scanned_but_filtered(monkeypatch, tmp_path: Path) -> None:
    universe_path = tmp_path / "universe.txt"
    tracked_path = tmp_path / "tracked.txt"
    universe_path.write_text("MISS\n", encoding="utf-8")
    tracked_path.write_text("", encoding="utf-8")

    monkeypatch.setattr("tradebruv.discovery.collect_prepared_tickers", lambda **_: {"prepared": [_prepared("MISS", "Avoid / Do Not Chase")], "failures": [], "generated_at": "2026-04-24T12:00:00Z"})

    result = build_why_missed_report(symbol="MISS", provider_name="sample", universe_path=universe_path, tracked_path=tracked_path, output_dir=tmp_path / "outputs")

    assert result.payload["exact_reason"] == "filtered out by price, volume, risk, or actionability"


def test_import_and_clean_universe_dedupes_symbols(tmp_path: Path) -> None:
    csv_path = tmp_path / "symbols.csv"
    imported = tmp_path / "imported.txt"
    cleaned = tmp_path / "cleaned.txt"
    csv_path.write_text("Symbol\nband\nBAND\npltr\n\nPLTR\n", encoding="utf-8")

    import_result = import_universe_csv(csv_path, ticker_column="Symbol", output_path=imported)
    clean_result = clean_universe_file(imported, cleaned, min_price=5.0, min_dollar_volume=10_000_000.0)

    assert import_result["row_count"] == 2
    assert cleaned.read_text(encoding="utf-8").splitlines() == ["BAND", "PLTR"]
    assert clean_result["liquidity_filters_applied"] is False


def test_movers_scanner_finds_top_gainer_and_unusual_volume(tmp_path: Path) -> None:
    provider = Provider(
        {
            "SPY": _security("SPY", [100.0 + (index * 0.2) for index in range(300)], sector="Financial", industry="ETF"),
            "QQQ": _security("QQQ", [100.0 + (index * 0.25) for index in range(300)], sector="Financial", industry="ETF"),
            "GAIN": _security("GAIN", [40.0 + (index * 0.15) for index in range(299)] + [95.0], volumes=[900_000.0] * 299 + [4_500_000.0]),
            "DROP": _security("DROP", [90.0 - (index * 0.18) for index in range(300)]),
            "VOLUME": _security("VOLUME", [30.0 + (index * 0.05) for index in range(300)], volumes=[700_000.0] * 299 + [3_000_000.0]),
        }
    )

    result = run_movers_scan(universe=["GAIN", "DROP", "VOLUME"], provider_name="sample", analysis_date=ANCHOR, output_dir=tmp_path / "movers", provider_override=provider, refresh_cache=True)

    assert result.payload["top_gainers"][0]["ticker"] == "GAIN"
    assert any(row["ticker"] == "VOLUME" for row in result.payload["unusual_volume"])


def test_highs_scanner_finds_new_52_week_high(tmp_path: Path) -> None:
    provider = Provider(
        {
            "SPY": _security("SPY", [100.0 + (index * 0.2) for index in range(300)], sector="Financial", industry="ETF"),
            "QQQ": _security("QQQ", [100.0 + (index * 0.22) for index in range(300)], sector="Financial", industry="ETF"),
            "LEAD": _security("LEAD", [50.0 + (index * 0.4) for index in range(300)], volumes=[1_200_000.0] * 299 + [3_200_000.0]),
            "LAG": _security("LAG", [60.0 + ((index % 10) * 0.1) for index in range(300)]),
        }
    )

    result = run_highs_scan(universe=["LEAD", "LAG"], provider_name="sample", analysis_date=ANCHOR, output_dir=tmp_path / "highs", provider_override=provider, refresh_cache=True)

    assert result.payload["new_52_week_highs"][0]["ticker"] == "LEAD"


def test_earnings_movers_detects_earnings_like_gapper_without_metadata(tmp_path: Path) -> None:
    provider = Provider(
        {
            "SPY": _security("SPY", [100.0 + (index * 0.2) for index in range(300)], sector="Financial", industry="ETF"),
            "QQQ": _security("QQQ", [100.0 + (index * 0.22) for index in range(300)], sector="Financial", industry="ETF"),
            "GAPR": _gapped_security("GAPR"),
        }
    )

    result = run_earnings_movers_scan(universe=["GAPR"], provider_name="sample", analysis_date=ANCHOR, output_dir=tmp_path / "earnings", provider_override=provider, refresh_cache=True)

    assert result.payload["earnings_movers"][0]["ticker"] == "GAPR"
    assert result.payload["earnings_movers"][0]["earnings_like_mover"] is True
    assert result.payload["earnings_movers"][0]["event_source"] == "unavailable"


def test_theme_scan_ranks_strong_etfs(tmp_path: Path) -> None:
    provider = Provider(
        {
            "SPY": _security("SPY", [100.0 + (index * 0.2) for index in range(300)], sector="Financial", industry="ETF"),
            "QQQ": _security("QQQ", [100.0 + (index * 0.22) for index in range(300)], sector="Financial", industry="ETF"),
            "XSD": _security("XSD", [40.0 + (index * 0.3) for index in range(300)], sector="Financial", industry="ETF"),
            "AIQ": _security("AIQ", [35.0 + (index * 0.12) for index in range(300)], sector="Financial", industry="ETF"),
        }
    )

    result = run_theme_scan(themes=["XSD", "AIQ"], provider_name="sample", analysis_date=ANCHOR, output_dir=tmp_path / "themes", provider_override=provider, refresh_cache=True)

    assert result.payload["strongest_themes"][0]["ticker"] == "XSD"


def test_theme_constituents_scan_uses_manual_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "XSD.csv"
    csv_path.write_text("Symbol\nWIN\nLATE\n", encoding="utf-8")
    provider = Provider(
        {
            "SPY": _security("SPY", [100.0 + (index * 0.2) for index in range(300)], sector="Financial", industry="ETF"),
            "QQQ": _security("QQQ", [100.0 + (index * 0.22) for index in range(300)], sector="Financial", industry="ETF"),
            "WIN": _security("WIN", [25.0 + (index * 0.25) for index in range(300)], volumes=[800_000.0] * 299 + [2_400_000.0]),
            "LATE": _security("LATE", [20.0 + (index * 0.06) for index in range(300)]),
        }
    )

    result = run_theme_constituents_scan(theme="XSD", constituents_path=csv_path, provider_name="sample", analysis_date=ANCHOR, output_dir=tmp_path / "themes", provider_override=provider, refresh_cache=True)

    assert result.payload["available"] is True
    assert result.payload["results"][0]["ticker"] == "WIN"


def test_decision_today_includes_discovery_sections_and_warning(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "config"
    (config_dir / "theme_constituents").mkdir(parents=True)
    broad_path = config_dir / "broad.txt"
    tracked_path = config_dir / "tracked.txt"
    core_path = config_dir / "core.txt"
    outlier_path = config_dir / "outlier.txt"
    velocity_path = config_dir / "velocity.txt"
    theme_path = config_dir / "theme_etfs.txt"
    broad_path.write_text("BROAD\n", encoding="utf-8")
    tracked_path.write_text("TRACK\n", encoding="utf-8")
    core_path.write_text("", encoding="utf-8")
    outlier_path.write_text("", encoding="utf-8")
    velocity_path.write_text("", encoding="utf-8")
    theme_path.write_text("XSD\n", encoding="utf-8")
    (config_dir / "theme_constituents" / "XSD.csv").write_text("Symbol\nCHIP\n", encoding="utf-8")

    empty_scan = SimpleNamespace(generated_at="2026-04-24T12:00:00Z", provider="real", source="baseline", market_regime={}, results=[], cache_stats={"hits": 0, "misses": 0, "ttl_minutes": 60})
    monkeypatch.setattr("tradebruv.daily_decision.run_dashboard_scan", lambda **_: empty_scan)

    def fake_run_custom_scan(*, tickers: list[str], **_: object):
        ticker = tickers[0]
        row = {
            "ticker": ticker,
            "company_name": ticker,
            "current_price": 100.0,
            "regular_investing_score": 90,
            "outlier_score": 88,
            "velocity_score": 24,
            "last_market_date": "2026-04-24",
            "relative_volume_20d": 1.6,
            "ema_stack": "Bullish Stack",
            "signal_summary": "Breakout with Volume",
            "price_change_1d_pct": 3.1,
        }
        return SimpleNamespace(generated_at="2026-04-24T12:00:00Z", provider="real", source="custom", market_regime={}, results=[row], cache_stats={"hits": 1, "misses": 0, "ttl_minutes": 60})

    def fake_build_unified_decisions(rows: list[dict[str, object]], **_: object):
        return [_decision_row(str(row["ticker"]), str(row.get("scan_source_group") or "Broad")) for row in rows]

    monkeypatch.setattr("tradebruv.daily_decision._run_custom_scan", fake_run_custom_scan)
    monkeypatch.setattr("tradebruv.daily_decision.build_unified_decisions", fake_build_unified_decisions)
    monkeypatch.setattr("tradebruv.daily_decision.load_dashboard_portfolio", lambda: [])
    monkeypatch.setattr("tradebruv.daily_decision.build_daily_summary", lambda rows: {"count": len(rows)})
    monkeypatch.setattr(
        "tradebruv.daily_decision.run_movers_scan",
        lambda **_: SimpleNamespace(
            payload={
                "generated_at": "2026-04-24T12:00:00Z",
                "provider_health": {"status": "healthy"},
                "cache": {"hits": 1, "misses": 0, "ttl_minutes": 60},
                "tickers_attempted": 1,
                "tickers_successfully_scanned": 1,
                "scan_failures": [],
                "results": [{"ticker": "MOVE", "signal_summary": "Breakout with Volume", "source_row": {"ticker": "MOVE", "company_name": "MOVE", "current_price": 55.0, "regular_investing_score": 80, "outlier_score": 84, "velocity_score": 40, "last_market_date": "2026-04-24", "relative_volume_20d": 2.8, "ema_stack": "Bullish Stack", "signal_summary": "Breakout with Volume", "price_change_1d_pct": 8.5}}],
                "unusual_volume": [{"ticker": "MOVE", "actionability_label": "High-Volume Mover Watch", "why_it_is_interesting": "RV surge", "entry_or_trigger": "Wait for MOVE", "why_it_may_fail": "Could fade"}],
                "top_gainers": [],
                "top_losers": [],
                "breakout_volume": [],
            }
        ),
    )
    monkeypatch.setattr(
        "tradebruv.daily_decision.run_highs_scan",
        lambda **_: SimpleNamespace(payload={"new_52_week_highs": [{"ticker": "HIGH", "actionability_label": "Breakout Actionable Today", "why_it_is_interesting": "New high", "entry_or_trigger": "99 - 101", "why_it_may_fail": "Extended"}], "tickers_successfully_scanned": 1, "scan_failures": [], "provider_health": {"status": "healthy"}}),
    )
    monkeypatch.setattr(
        "tradebruv.daily_decision.run_earnings_movers_scan",
        lambda **_: SimpleNamespace(payload={"earnings_movers": [{"ticker": "EARN", "actionability_label": "Momentum Actionable Today", "why_it_is_interesting": "Gap and hold", "entry_or_trigger": "Wait for pullback", "why_it_may_fail": "Fading risk"}], "tickers_successfully_scanned": 1, "scan_failures": [], "provider_health": {"status": "healthy"}}),
    )
    monkeypatch.setattr(
        "tradebruv.daily_decision.run_theme_scan",
        lambda **_: SimpleNamespace(payload={"strongest_themes": [{"ticker": "XSD", "actionability_label": "Theme Leader", "why_it_is_interesting": "Strong 3M RS", "entry_or_trigger": "Monitor ETF", "why_it_may_fail": "Theme reversal"}], "themes_scanned": 1, "tickers_successfully_scanned": 1, "scan_failures": [], "provider_health": {"status": "healthy"}}),
    )
    monkeypatch.setattr(
        "tradebruv.daily_decision.run_theme_constituents_scan",
        lambda **_: SimpleNamespace(payload={"available": True, "theme_constituent_candidates": [{"ticker": "CHIP", "actionability_label": "Breakout Actionable Today", "why_it_is_interesting": "Theme leader", "entry_or_trigger": "44 - 45", "why_it_may_fail": "Could shake out"}], "tickers_successfully_scanned": 1, "scan_failures": [], "provider_health": {"status": "healthy"}}),
    )

    payload = run_daily_decision(
        provider_name="real",
        core_universe=core_path,
        outlier_universe=outlier_path,
        velocity_universe=velocity_path,
        broad_universe=broad_path,
        tracked=tracked_path,
        include_movers=True,
        include_highs=True,
        include_earnings_movers=True,
        include_themes=True,
        theme_etfs=theme_path,
        analysis_date=ANCHOR,
        output_dir=tmp_path / "outputs" / "daily",
    )

    assert payload["earnings_news_movers"][0]["ticker"] == "EARN"
    assert payload["new_52_week_highs"][0]["ticker"] == "HIGH"
    assert payload["high_volume_movers"][0]["ticker"] == "MOVE"
    assert payload["strong_themes"][0]["ticker"] == "XSD"
    assert payload["theme_constituent_candidates"][0]["ticker"] == "CHIP"
    assert "Coverage limitation:" in payload["coverage_limitation"]
