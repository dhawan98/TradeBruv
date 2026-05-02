from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import tradebruv.cli as cli
from tradebruv.discovery import build_coverage_audit, run_theme_discovery
from tradebruv.models import PriceBar, SecurityData
from tradebruv.universe_refresh import build_liquid_universe, parse_nasdaqtrader_listing_text, refresh_symbol_master, resolve_discovery_universe


ANCHOR = date(2026, 5, 1)


def _security(
    ticker: str,
    *,
    last_price: float,
    start_price: float | None = None,
    avg_volume: float,
    last_volume: float | None = None,
    industry: str = "Software",
) -> SecurityData:
    last_volume = last_volume if last_volume is not None else avg_volume
    start_price = start_price if start_price is not None else last_price
    bars: list[PriceBar] = []
    periods = 70
    start = ANCHOR - timedelta(days=periods)
    for index in range(periods - 1):
        close = start_price + ((last_price - start_price) * (index / (periods - 1)))
        bars.append(
            PriceBar(
                date=start + timedelta(days=index),
                open=close * 0.99,
                high=close * 1.01,
                low=close * 0.98,
                close=close,
                volume=avg_volume,
            )
        )
    bars.append(
        PriceBar(
            date=ANCHOR,
            open=last_price * 0.99,
            high=last_price * 1.01,
            low=last_price * 0.98,
            close=last_price,
            volume=last_volume,
        )
    )
    return SecurityData(
        ticker=ticker,
        company_name=ticker,
        sector="Technology",
        industry=industry,
        bars=bars,
        provider_name="test",
        quote_price_if_available=last_price,
        latest_available_close=last_price,
        last_market_date=ANCHOR,
    )


class StaticProvider:
    def __init__(self, mapping: dict[str, SecurityData]) -> None:
        self.mapping = mapping
        self.prefetched: list[list[str]] = []

    def prefetch_many(self, tickers: list[str], *, batch_size: int = 25) -> None:
        self.prefetched.append(list(tickers))

    def get_security_data(self, ticker: str) -> SecurityData:
        return self.mapping[ticker]

    def health_report(self) -> dict[str, object]:
        return {"provider": "test", "status": "healthy"}

    def should_stop_scan(self) -> bool:
        return False


def _write_symbol_master(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "symbol",
                "display_symbol",
                "provider_symbol",
                "name",
                "exchange",
                "is_etf",
                "is_test_issue",
                "raw_type",
                "source",
                "active",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_parse_nasdaqtrader_formats_and_symbol_mapping() -> None:
    nasdaq_text = "\n".join(
        [
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares",
            "BRK.B|Berkshire Hathaway Inc. Class B|Q|N|N|100|N|N",
            "TST1|Test Issue Corp|Q|Y|N|100|N|N",
            "File Creation Time: 05012026",
        ]
    )
    other_text = "\n".join(
        [
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol",
            "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY",
            "AAPL|Apple Inc.|N|AAPL|N|100|N|AAPL",
            "File Creation Time: 05012026",
        ]
    )

    nasdaq_rows = parse_nasdaqtrader_listing_text(nasdaq_text, listing_type="nasdaqlisted")
    other_rows = parse_nasdaqtrader_listing_text(other_text, listing_type="otherlisted")

    brk = next(row for row in nasdaq_rows if row["symbol"] == "BRK.B")
    test_issue = next(row for row in nasdaq_rows if row["symbol"] == "TST1")
    spy = next(row for row in other_rows if row["symbol"] == "SPY")

    assert brk["display_symbol"] == "BRK.B"
    assert brk["provider_symbol"] == "BRK-B"
    assert test_issue["is_test_issue"] is True
    assert spy["is_etf"] is True
    assert spy["exchange"] == "NYSE Arca"


def test_refresh_symbol_master_excludes_test_issues(monkeypatch, tmp_path: Path) -> None:
    rows = [
        {
            "symbol": "BRK.B",
            "display_symbol": "BRK.B",
            "provider_symbol": "BRK-B",
            "name": "Berkshire Hathaway Inc. Class B",
            "exchange": "NASDAQ",
            "is_etf": False,
            "is_test_issue": False,
            "raw_type": "stock",
            "source": "nasdaqtrader:nasdaqlisted",
            "active": True,
        },
        {
            "symbol": "TST1",
            "display_symbol": "TST1",
            "provider_symbol": "TST1",
            "name": "Test Issue Corp",
            "exchange": "NASDAQ",
            "is_etf": False,
            "is_test_issue": True,
            "raw_type": "stock",
            "source": "nasdaqtrader:nasdaqlisted",
            "active": True,
        },
    ]
    monkeypatch.setattr("tradebruv.universe_refresh._load_symbol_master_from_source", lambda *_, **__: rows)

    payload = refresh_symbol_master(source="nasdaqtrader", output_path=tmp_path / "symbol_master.csv")

    assert payload["refresh_succeeded"] is True
    assert payload["row_count"] == 1
    assert payload["sample_symbols"] == ["BRK.B"]


def test_build_liquid_universe_filters_etfs_and_special_instruments(monkeypatch, tmp_path: Path) -> None:
    symbol_master = tmp_path / "symbol_master.csv"
    _write_symbol_master(
        symbol_master,
        [
            {"symbol": "AAPL", "display_symbol": "AAPL", "provider_symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "is_etf": False, "is_test_issue": False, "raw_type": "stock", "source": "test", "active": True},
            {"symbol": "SPY", "display_symbol": "SPY", "provider_symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "exchange": "NYSE Arca", "is_etf": True, "is_test_issue": False, "raw_type": "ETF", "source": "test", "active": True},
            {"symbol": "ABCD-W", "display_symbol": "ABCD-W", "provider_symbol": "ABCD-W", "name": "ABCD Warrant", "exchange": "NASDAQ", "is_etf": False, "is_test_issue": False, "raw_type": "stock", "source": "test", "active": True},
            {"symbol": "EFGH-R", "display_symbol": "EFGH-R", "provider_symbol": "EFGH-R", "name": "EFGH Rights", "exchange": "NASDAQ", "is_etf": False, "is_test_issue": False, "raw_type": "stock", "source": "test", "active": True},
            {"symbol": "IJKL-U", "display_symbol": "IJKL-U", "provider_symbol": "IJKL-U", "name": "IJKL Units", "exchange": "NASDAQ", "is_etf": False, "is_test_issue": False, "raw_type": "stock", "source": "test", "active": True},
            {"symbol": "MNOP-P", "display_symbol": "MNOP-P", "provider_symbol": "MNOP-P", "name": "MNOP Preferred", "exchange": "NASDAQ", "is_etf": False, "is_test_issue": False, "raw_type": "preferred", "source": "test", "active": True},
            {"symbol": "QRST$A", "display_symbol": "QRST$A", "provider_symbol": "QRST$A", "name": "QRST Preferred A", "exchange": "NYSE", "is_etf": False, "is_test_issue": False, "raw_type": "stock", "source": "test", "active": True},
        ],
    )
    provider = StaticProvider({"AAPL": _security("AAPL", last_price=190.0, avg_volume=2_000_000.0)})
    monkeypatch.setattr("tradebruv.universe_refresh._build_market_provider", lambda **_: provider)

    payload = build_liquid_universe(
        symbol_master_path=symbol_master,
        provider_name="sample",
        output_path=tmp_path / "universe_us_liquid_stocks.txt",
        snapshot_path=tmp_path / "liquidity_snapshot.csv",
    )

    assert payload["counts"]["excluded_etfs"] == 1
    assert payload["counts"]["excluded_warrants"] == 1
    assert payload["counts"]["excluded_rights"] == 1
    assert payload["counts"]["excluded_units"] == 1
    assert payload["counts"]["excluded_preferreds"] == 2
    assert (tmp_path / "universe_us_liquid_stocks.txt").read_text(encoding="utf-8").splitlines() == ["AAPL"]


def test_build_liquid_universe_from_mocked_quotes(monkeypatch, tmp_path: Path) -> None:
    symbol_master = tmp_path / "symbol_master.csv"
    _write_symbol_master(
        symbol_master,
        [
            {"symbol": "AAPL", "display_symbol": "AAPL", "provider_symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "is_etf": False, "is_test_issue": False, "raw_type": "stock", "source": "test", "active": True},
            {"symbol": "THIN", "display_symbol": "THIN", "provider_symbol": "THIN", "name": "Thin Liquidity Inc.", "exchange": "NASDAQ", "is_etf": False, "is_test_issue": False, "raw_type": "stock", "source": "test", "active": True},
        ],
    )
    provider = StaticProvider(
        {
            "AAPL": _security("AAPL", last_price=190.0, avg_volume=2_000_000.0),
            "THIN": _security("THIN", last_price=8.0, avg_volume=40_000.0, last_volume=50_000.0),
        }
    )
    monkeypatch.setattr("tradebruv.universe_refresh._build_market_provider", lambda **_: provider)

    payload = build_liquid_universe(
        symbol_master_path=symbol_master,
        provider_name="sample",
        output_path=tmp_path / "universe_us_liquid_stocks.txt",
        snapshot_path=tmp_path / "liquidity_snapshot.csv",
    )

    assert payload["counts"]["passed_liquidity_filters"] == 1
    assert (tmp_path / "universe_us_liquid_stocks.txt").read_text(encoding="utf-8").splitlines() == ["AAPL"]
    snapshot_rows = (tmp_path / "liquidity_snapshot.csv").read_text(encoding="utf-8")
    assert "AAPL" in snapshot_rows
    assert "THIN" in snapshot_rows
    assert "too_illiquid" in snapshot_rows


def test_build_liquid_universe_resumes_partial_snapshot(monkeypatch, tmp_path: Path) -> None:
    symbol_master = tmp_path / "symbol_master.csv"
    snapshot = tmp_path / "liquidity_snapshot.csv"
    output_path = tmp_path / "universe_us_liquid_stocks.txt"
    _write_symbol_master(
        symbol_master,
        [
            {"symbol": "AAPL", "display_symbol": "AAPL", "provider_symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "is_etf": False, "is_test_issue": False, "raw_type": "stock", "source": "test", "active": True},
            {"symbol": "MSFT", "display_symbol": "MSFT", "provider_symbol": "MSFT", "name": "Microsoft Corp.", "exchange": "NASDAQ", "is_etf": False, "is_test_issue": False, "raw_type": "stock", "source": "test", "active": True},
        ],
    )
    snapshot.write_text(
        "\n".join(
            [
                "symbol,display_symbol,provider_symbol,name,exchange,is_etf,raw_type,snapshot_date,last_price,last_volume,avg_volume_20d,dollar_volume,avg_dollar_volume_20d,last_market_date,status,reason,category,provider_name,refreshed_at",
                f"AAPL,AAPL,AAPL,Apple Inc.,NASDAQ,False,stock,{ANCHOR.isoformat()},190,2000000,2000000,380000000,380000000,{ANCHOR.isoformat()},passed,,,test,{ANCHOR.isoformat()}T00:00:00Z",
            ]
        ),
        encoding="utf-8",
    )

    class ResumeProvider(StaticProvider):
        def get_security_data(self, ticker: str) -> SecurityData:
            if ticker == "AAPL":
                raise AssertionError("AAPL should have been resumed from the existing snapshot.")
            return super().get_security_data(ticker)

    provider = ResumeProvider({"MSFT": _security("MSFT", last_price=420.0, avg_volume=1_500_000.0)})
    monkeypatch.setattr("tradebruv.universe_refresh._build_market_provider", lambda **_: provider)
    monkeypatch.setattr("tradebruv.universe_refresh.date", SimpleNamespace(today=lambda: ANCHOR))

    payload = build_liquid_universe(
        symbol_master_path=symbol_master,
        provider_name="sample",
        output_path=output_path,
        snapshot_path=snapshot,
    )

    assert payload["counts"]["cache_hits"] == 1
    assert output_path.read_text(encoding="utf-8").splitlines() == ["AAPL", "MSFT"]


def test_build_liquid_universe_handles_rate_limit(monkeypatch, tmp_path: Path) -> None:
    symbol_master = tmp_path / "symbol_master.csv"
    _write_symbol_master(
        symbol_master,
        [
            {"symbol": "AAPL", "display_symbol": "AAPL", "provider_symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "is_etf": False, "is_test_issue": False, "raw_type": "stock", "source": "test", "active": True},
            {"symbol": "MSFT", "display_symbol": "MSFT", "provider_symbol": "MSFT", "name": "Microsoft Corp.", "exchange": "NASDAQ", "is_etf": False, "is_test_issue": False, "raw_type": "stock", "source": "test", "active": True},
        ],
    )

    class RateLimitProvider(StaticProvider):
        def __init__(self) -> None:
            super().__init__({"AAPL": _security("AAPL", last_price=190.0, avg_volume=2_000_000.0)})
            self.stopped = False

        def get_security_data(self, ticker: str) -> SecurityData:
            if ticker == "MSFT":
                self.stopped = True
                raise RuntimeError("429 rate limit")
            return super().get_security_data(ticker)

        def should_stop_scan(self) -> bool:
            return self.stopped

        def health_report(self) -> dict[str, object]:
            return {"provider": "test", "status": "rate_limited", "stop_scan": self.stopped}

    monkeypatch.setattr("tradebruv.universe_refresh._build_market_provider", lambda **_: RateLimitProvider())

    payload = build_liquid_universe(
        symbol_master_path=symbol_master,
        provider_name="sample",
        output_path=tmp_path / "universe_us_liquid_stocks.txt",
        snapshot_path=tmp_path / "liquidity_snapshot.csv",
    )

    assert payload["partial"] is True
    assert payload["provider_health"]["status"] == "rate_limited"
    assert "AAPL" in (tmp_path / "universe_us_liquid_stocks.txt").read_text(encoding="utf-8")


def test_resolve_discovery_universe_prefers_liquid_stocks(tmp_path: Path, monkeypatch) -> None:
    liquid = tmp_path / "universe_us_liquid_stocks.txt"
    expanded = tmp_path / "universe_us_liquid_expanded.txt"
    broad = tmp_path / "universe_us_broad_1000.txt"
    liquid.write_text("AAPL\n", encoding="utf-8")
    expanded.write_text("MSFT\n", encoding="utf-8")
    broad.write_text("NVDA\n", encoding="utf-8")
    monkeypatch.setattr("tradebruv.universe_refresh.DISCOVERY_UNIVERSE_PRIORITY", (liquid, expanded, broad))

    resolved = resolve_discovery_universe(None)

    assert resolved["path"] == liquid


def test_cli_movers_uses_default_liquid_universe(monkeypatch, tmp_path: Path) -> None:
    liquid = tmp_path / "universe_us_liquid_stocks.txt"
    liquid.write_text("AAPL\n", encoding="utf-8")
    monkeypatch.setattr("tradebruv.universe_refresh.DISCOVERY_UNIVERSE_PRIORITY", (liquid,))
    captured: dict[str, object] = {}

    def fake_run_movers_scan(*, universe: list[str], **_: object):
        captured["universe"] = universe
        return SimpleNamespace(json_path=tmp_path / "movers.json", csv_path=tmp_path / "movers.csv", markdown_path=tmp_path / "movers.md")

    monkeypatch.setattr("tradebruv.movers.run_movers_scan", fake_run_movers_scan)

    exit_code = cli.main(["movers", "--provider", "sample"])

    assert exit_code == 0
    assert captured["universe"] == ["AAPL"]


def test_theme_discovery_scans_basket_for_strong_theme(tmp_path: Path) -> None:
    basket_dir = tmp_path / "theme_baskets"
    basket_dir.mkdir(parents=True)
    (basket_dir / "semiconductors.txt").write_text("NVDA\nAMD\n", encoding="utf-8")
    provider = StaticProvider(
        {
            "SPY": _security("SPY", last_price=550.0, start_price=500.0, avg_volume=10_000_000.0, industry="ETF"),
            "XSD": _security("XSD", last_price=220.0, start_price=150.0, avg_volume=1_500_000.0, industry="ETF"),
            "AIQ": _security("AIQ", last_price=38.0, start_price=36.0, avg_volume=300_000.0, industry="ETF"),
            "NVDA": _security("NVDA", last_price=920.0, start_price=700.0, avg_volume=4_000_000.0),
            "AMD": _security("AMD", last_price=170.0, start_price=130.0, avg_volume=3_000_000.0),
        }
    )

    payload = run_theme_discovery(
        themes=["XSD", "AIQ"],
        baskets_dir=basket_dir,
        provider_name="sample",
        analysis_date=ANCHOR,
        top_themes=1,
        top_n=5,
        output_dir=tmp_path / "themes",
        provider_override=provider,
        refresh_cache=True,
    ).payload

    assert payload["strongest_themes"][0]["ticker"] == "XSD"
    assert payload["theme_stock_candidates"][0]["ticker"] == "NVDA"


def test_coverage_audit_reports_stale_and_missing_universe(monkeypatch, tmp_path: Path) -> None:
    universe_path = tmp_path / "universe.txt"
    tracked_path = tmp_path / "tracked.txt"
    universe_path.write_text("AAPL\nMSFT\nSPY\n", encoding="utf-8")
    tracked_path.write_text("AAPL\n", encoding="utf-8")
    monkeypatch.setattr(
        "tradebruv.discovery.build_universe_health_report",
        lambda **_: {
            "symbol_master": {"path": "data/universes/symbol_master.csv", "exists": False, "updated_at": None, "age_days": None},
            "liquid_universe": {"path": "config/universe_us_liquid_stocks.txt", "exists": True, "updated_at": "2026-04-20T00:00:00Z", "age_days": 11.0, "symbol_count": 3},
            "theme_universe_exists": False,
            "theme_baskets_exist": False,
            "theme_basket_count": 0,
            "theme_basket_files": [],
            "universe_is_stale": True,
            "stale_after_days": 3,
        },
    )

    result = build_coverage_audit(universe_path=universe_path, tracked_path=tracked_path, output_dir=tmp_path / "outputs")

    assert result.payload["universe_is_stale"] is True
    assert result.payload["theme_etf_universe_exists"] is False
    assert result.payload["coverage_recommendations"]
    assert (tmp_path / "outputs" / "coverage_recommendations.md").exists()
