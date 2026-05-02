from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable

from .chart_signals import build_signal_snapshot
from .decision_engine import build_unified_decisions, build_validation_context
from .market_cache import DEFAULT_MARKET_CACHE_DIR, FileCacheMarketDataProvider
from .market_reliability import ResilientMarketDataProvider
from .models import SecurityData
from .providers import BENCHMARK_SYMBOLS, MarketDataProvider
from .scanner import DeterministicScanner
from .ticker_symbols import display_ticker
from .universe_refresh import (
    DEFAULT_LIQUID_STOCKS_UNIVERSE,
    DEFAULT_SYMBOL_MASTER_CSV,
    DEFAULT_THEME_BASKETS_DIR,
    DEFAULT_THEME_ETF_UNIVERSE,
    build_universe_health_report,
    resolve_theme_basket,
)

DEFAULT_COVERAGE_OUTPUT_DIR = Path("outputs/coverage")
DEFAULT_DISCOVERY_OUTPUT_DIR = Path("outputs/discovery")
DEFAULT_HIGHS_OUTPUT_DIR = Path("outputs/highs")
DEFAULT_EARNINGS_OUTPUT_DIR = Path("outputs/earnings")
DEFAULT_THEMES_OUTPUT_DIR = Path("outputs/themes")

DEFAULT_MIN_PRICE = 5.0
DEFAULT_MIN_DOLLAR_VOLUME = 10_000_000.0
DEFAULT_MIN_AVERAGE_VOLUME = 500_000.0

THEME_ETFS = {
    "LIT",
    "HYDR",
    "DRIV",
    "ICLN",
    "XSD",
    "AIQ",
    "SPMO",
    "BAI",
    "EWY",
    "QTUM",
    "IDGT",
    "PBW",
    "FDRV",
    "ROBO",
    "GRID",
    "SMH",
    "SOXX",
    "IGV",
    "SKYY",
    "XLI",
    "XLE",
    "XLF",
    "XLK",
    "XLY",
    "XRT",
    "ARKK",
    "ARKW",
    "BOTZ",
    "CIBR",
    "HACK",
    "FINX",
    "URA",
    "COPX",
    "XME",
    "TAN",
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    *BENCHMARK_SYMBOLS,
}

_VALID_TICKER_RE = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z])?$")


@dataclass(frozen=True)
class DiscoveryResult:
    payload: dict[str, Any]
    json_path: Path
    markdown_path: Path


@dataclass(frozen=True)
class PreparedTicker:
    ticker: str
    security: SecurityData
    row: dict[str, Any]
    decision: dict[str, Any]
    signal: dict[str, Any]
    metrics: dict[str, Any]
    discovery: dict[str, Any]


def read_ticker_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(path)
    return _normalize_tickers(path.read_text(encoding="utf-8").splitlines())


def import_tickers_from_csv(path: Path, *, ticker_column: str | None = None) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        resolved_column = ticker_column or _detect_ticker_column(fieldnames)
        if resolved_column not in fieldnames:
            raise KeyError(f"Ticker column '{resolved_column}' not found in CSV.")
        return _normalize_tickers(str(row.get(resolved_column) or "") for row in reader)


def build_coverage_audit(
    *,
    universe_path: Path,
    tracked_path: Path,
    output_dir: Path = DEFAULT_COVERAGE_OUTPUT_DIR,
) -> DiscoveryResult:
    universe_raw = universe_path.read_text(encoding="utf-8").splitlines()
    tracked_raw = tracked_path.read_text(encoding="utf-8").splitlines()
    universe_report = _file_symbol_report(universe_raw, source=str(universe_path))
    tracked_report = _file_symbol_report(tracked_raw, source=str(tracked_path))

    tracked_included = [ticker for ticker in tracked_report["unique_symbols"] if ticker in universe_report["unique_symbols"]]
    tracked_missing = [ticker for ticker in tracked_report["unique_symbols"] if ticker not in universe_report["unique_symbols"]]
    coverage_label = _coverage_label(universe_report["unique_count"])
    universe_health = build_universe_health_report(
        liquid_universe_path=DEFAULT_LIQUID_STOCKS_UNIVERSE,
        symbol_master_path=DEFAULT_SYMBOL_MASTER_CSV,
        theme_universe_path=DEFAULT_THEME_ETF_UNIVERSE,
        theme_baskets_dir=DEFAULT_THEME_BASKETS_DIR,
    )
    sufficiency = _coverage_sufficiency(
        unique_count=universe_report["unique_count"],
        tracked_count=tracked_report["unique_count"],
        etf_count=universe_report["etf_count"],
        theme_basket_count=int(universe_health.get("theme_basket_count") or 0),
    )
    recommendations = _coverage_recommendations(
        coverage_label=coverage_label,
        sufficiency=sufficiency,
        universe_health=universe_health,
        tracked_missing=tracked_missing,
    )

    payload = {
        "generated_at": _utcnow(),
        "configured_universe_only": True,
        "not_full_us_market": True,
        "may_miss_smaller_liquid_movers_outside_file": True,
        "universe_file": universe_report,
        "tracked_file": tracked_report,
        "tracked_symbols_included": tracked_included,
        "tracked_symbols_missing": tracked_missing,
        "tracked_symbols_included_count": len(tracked_included),
        "tracked_symbols_missing_count": len(tracked_missing),
        "coverage_label": coverage_label,
        "symbol_master_age": universe_health["symbol_master"],
        "liquid_universe_age": universe_health["liquid_universe"],
        "number_of_symbols_in_liquid_universe": universe_health["liquid_universe"]["symbol_count"],
        "theme_etf_universe_exists": universe_health["theme_universe_exists"],
        "theme_baskets_exist": universe_health["theme_baskets_exist"],
        "theme_basket_count": universe_health["theme_basket_count"],
        "theme_basket_files": universe_health["theme_basket_files"],
        "universe_is_stale": universe_health["universe_is_stale"],
        "coverage_notes": [
            "TradeBruv scans the configured universe only.",
            "This is not the full U.S. stock market.",
            "Smaller liquid movers outside the file can be missed.",
        ],
        "sufficiency": sufficiency,
        "coverage_recommendations": recommendations,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "coverage_audit.json"
    markdown_path = output_dir / "coverage_audit.md"
    recommendations_path = output_dir / "coverage_recommendations.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(_build_coverage_markdown(payload), encoding="utf-8")
    recommendations_path.write_text(_build_coverage_recommendations_markdown(payload), encoding="utf-8")
    return DiscoveryResult(payload=payload, json_path=json_path, markdown_path=markdown_path)


def build_why_missed_report(
    *,
    symbol: str,
    provider_name: str,
    universe_path: Path,
    tracked_path: Path,
    latest_daily_path: Path = Path("outputs/daily/decision_today.json"),
    latest_movers_path: Path = Path("outputs/movers/movers.json"),
    analysis_date: date | None = None,
    output_dir: Path = DEFAULT_COVERAGE_OUTPUT_DIR,
    scanner_override: DeterministicScanner | None = None,
    provider_override: MarketDataProvider | None = None,
) -> DiscoveryResult:
    ticker = display_ticker(symbol)
    universe = set(read_ticker_file(universe_path))
    tracked = set(read_ticker_file(tracked_path))
    daily_payload = _load_json_if_exists(latest_daily_path)
    movers_payload = _load_json_if_exists(latest_movers_path)

    latest_daily_decision = _first_by_ticker(daily_payload.get("decisions", []), ticker)
    latest_daily_result = _first_by_ticker(daily_payload.get("results", []), ticker)
    latest_mover = _first_by_ticker(movers_payload.get("results", []), ticker)
    latest_daily_failure = _first_by_ticker(daily_payload.get("scan_failures", []), ticker)
    latest_movers_failure = _first_by_ticker(movers_payload.get("scan_failures", []), ticker)

    evaluation: dict[str, Any] = {
        "available": False,
        "valid_data": False,
        "provider_failure": None,
        "price_validation_status": "not_run",
        "stale_data": False,
        "below_min_price": False,
        "too_illiquid": False,
        "not_enough_signal": False,
        "filtered_by_risk_or_actionability": False,
        "provider_data_status": "not_run",
    }
    if ticker in universe or ticker in tracked:
        try:
            prepared = collect_prepared_tickers(
                tickers=[ticker],
                provider_name=provider_name,
                analysis_date=analysis_date or date.today(),
                preferred_lane="Outlier",
                scanner_override=scanner_override,
                provider_override=provider_override,
            )
            if prepared["prepared"]:
                item = prepared["prepared"][0]
                evaluation = {
                    "available": True,
                    "valid_data": item.decision.get("price_validation_status") == "PASS",
                    "provider_failure": None,
                    "provider_data_status": "ok",
                    "price_validation_status": item.decision.get("price_validation_status"),
                    "stale_data": bool(item.discovery.get("stale_data")),
                    "below_min_price": bool(item.discovery.get("below_min_price")),
                    "too_illiquid": bool(item.discovery.get("too_illiquid")),
                    "not_enough_signal": _label(item.decision) in {
                        "Watch for Better Entry",
                        "Slow Compounder Watch",
                        "High-Volume Mover Watch",
                        "Long-Term Research Candidate",
                        "Data Insufficient",
                    },
                    "filtered_by_risk_or_actionability": _label(item.decision) == "Avoid / Do Not Chase",
                    "decision": item.decision,
                    "discovery": item.discovery,
                    "source_row": item.row,
                }
            elif prepared["failures"]:
                failure = prepared["failures"][0]
                evaluation = {
                    "available": False,
                    "valid_data": False,
                    "provider_failure": failure,
                    "provider_data_status": "provider_failure",
                    "price_validation_status": "provider_failure",
                    "stale_data": False,
                    "below_min_price": False,
                    "too_illiquid": False,
                    "not_enough_signal": False,
                    "filtered_by_risk_or_actionability": False,
                }
        except Exception as exc:
            evaluation = {
                "available": False,
                "valid_data": False,
                "provider_failure": {"ticker": ticker, "reason": str(exc), "category": "provider_failure"},
                "provider_data_status": "provider_failure",
                "price_validation_status": "provider_failure",
                "stale_data": False,
                "below_min_price": False,
                "too_illiquid": False,
                "not_enough_signal": False,
                "filtered_by_risk_or_actionability": False,
            }

    exact_reason = _why_missed_reason(
        ticker=ticker,
        in_universe=ticker in universe,
        in_tracked=ticker in tracked,
        latest_daily_decision=latest_daily_decision,
        latest_mover=latest_mover,
        latest_daily_failure=latest_daily_failure,
        latest_movers_failure=latest_movers_failure,
        evaluation=evaluation,
        daily_payload=daily_payload,
        movers_payload=movers_payload,
    )
    payload = {
        "generated_at": _utcnow(),
        "symbol": ticker,
        "provider": provider_name,
        "universe_file": str(universe_path),
        "tracked_file": str(tracked_path),
        "is_in_broad_universe": ticker in universe,
        "is_in_tracked_tickers": ticker in tracked,
        "was_scanned_in_latest_movers": latest_mover is not None,
        "was_scanned_in_latest_daily_decision": latest_daily_decision is not None,
        "was_present_in_latest_daily_results": latest_daily_result is not None,
        "had_valid_data": evaluation.get("valid_data", False),
        "provider_data_status": evaluation.get("provider_data_status", "not_run"),
        "provider_failure": evaluation.get("provider_failure"),
        "failed_price_validation": evaluation.get("price_validation_status") not in {"PASS", "not_run"} and evaluation.get("price_validation_status") != "provider_failure",
        "stale_data": evaluation.get("stale_data", False),
        "below_min_price": evaluation.get("below_min_price", False),
        "too_illiquid": evaluation.get("too_illiquid", False),
        "filtered_out_by_risk_or_actionability": evaluation.get("filtered_by_risk_or_actionability", False),
        "not_enough_signal": evaluation.get("not_enough_signal", False),
        "latest_daily_failure": latest_daily_failure,
        "latest_movers_failure": latest_movers_failure,
        "exact_reason": exact_reason,
        "what_to_do": _why_missed_actions(
            ticker=ticker,
            exact_reason=exact_reason,
            in_universe=ticker in universe,
            in_tracked=ticker in tracked,
        ),
        "latest_daily_decision": latest_daily_decision,
        "latest_mover_row": latest_mover,
        "evaluation": {
            "price_validation_status": evaluation.get("price_validation_status"),
            "decision": evaluation.get("decision"),
            "discovery": evaluation.get("discovery"),
            "source_row": evaluation.get("source_row"),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    file_stub = f"why_missed_{ticker.replace('.', '_')}"
    json_path = output_dir / f"{file_stub}.json"
    markdown_path = output_dir / f"{file_stub}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(_build_why_missed_markdown(payload), encoding="utf-8")
    return DiscoveryResult(payload=payload, json_path=json_path, markdown_path=markdown_path)


def collect_prepared_tickers(
    *,
    tickers: list[str],
    provider_name: str,
    analysis_date: date,
    history_period: str = "3y",
    data_dir: Path | None = None,
    refresh_cache: bool = False,
    preferred_lane: str = "Outlier",
    scanner_override: DeterministicScanner | None = None,
    provider_override: MarketDataProvider | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if scanner_override is not None:
        scanner = scanner_override
        provider = provider_override or scanner.provider
    else:
        provider, scanner = _build_scan_stack(
            provider_name=provider_name,
            analysis_date=analysis_date,
            history_period=history_period,
            data_dir=data_dir,
            refresh_cache=refresh_cache,
            provider_override=provider_override,
        )
    normalized = _normalize_tickers(tickers)
    failures: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    contexts: list[dict[str, Any]] = []
    prefetch = getattr(provider, "prefetch_many", None)
    if callable(prefetch):
        try:
            prefetch(normalized, batch_size=25)
        except Exception:
            pass
    spy_security = _safe_get_security(scanner, "SPY")
    spy_metrics = _security_metrics(spy_security, build_signal_snapshot(spy_security), analysis_date) if spy_security else {}
    generated_at = _utcnow()
    for index, ticker in enumerate(normalized, start=1):
        try:
            security = scanner._get_data(ticker)
            row = scanner._scan_security(security).to_dict()
            signal = build_signal_snapshot(security)
            metrics = _security_metrics(security, signal, analysis_date, benchmark_metrics=spy_metrics)
            rows.append(row)
            contexts.append({"ticker": ticker, "security": security, "row": row, "signal": signal, "metrics": metrics})
            if progress:
                progress(f"Discovery {index}/{len(normalized)}: {ticker}")
        except Exception as exc:
            failures.append(
                {
                    "ticker": ticker,
                    "reason": str(exc),
                    "category": getattr(exc, "category", getattr(exc, "status", "fetch_error")),
                }
            )
    decisions = build_unified_decisions(
        rows,
        scan_generated_at=generated_at,
        validation_context=build_validation_context(),
        reference_date=analysis_date,
        preferred_lane=preferred_lane,
    )
    decisions_by_ticker = {str(row.get("ticker")): row for row in decisions}
    prepared: list[PreparedTicker] = []
    for context in contexts:
        ticker = str(context["ticker"])
        decision = decisions_by_ticker.get(ticker, {})
        discovery_row = _build_discovery_row(
            ticker=ticker,
            security=context["security"],
            row=context["row"],
            decision=decision,
            signal=context["signal"],
            metrics=context["metrics"],
        )
        prepared.append(
            PreparedTicker(
                ticker=ticker,
                security=context["security"],
                row=context["row"],
                decision=decision,
                signal=context["signal"],
                metrics=context["metrics"],
                discovery=discovery_row,
            )
        )
    return {
        "generated_at": generated_at,
        "provider": provider_name,
        "prepared": prepared,
        "failures": failures,
        "provider_health": getattr(provider, "health_report", lambda: {"provider": provider_name, "status": "healthy"})(),
        "cache": _cache_stats(provider),
        "spy_metrics": spy_metrics,
    }


def run_highs_scan(
    *,
    universe: list[str],
    provider_name: str,
    analysis_date: date,
    history_period: str = "3y",
    data_dir: Path | None = None,
    top_n: int = 50,
    min_price: float = DEFAULT_MIN_PRICE,
    min_dollar_volume: float = DEFAULT_MIN_DOLLAR_VOLUME,
    output_dir: Path = DEFAULT_HIGHS_OUTPUT_DIR,
    refresh_cache: bool = False,
    scanner_override: DeterministicScanner | None = None,
    provider_override: MarketDataProvider | None = None,
) -> DiscoveryResult:
    prepared_payload = collect_prepared_tickers(
        tickers=universe,
        provider_name=provider_name,
        analysis_date=analysis_date,
        history_period=history_period,
        data_dir=data_dir,
        refresh_cache=refresh_cache,
        preferred_lane="Core Investing",
        scanner_override=scanner_override,
        provider_override=provider_override,
    )
    liquid = [
        item.discovery
        for item in prepared_payload["prepared"]
        if not item.discovery["below_min_price"] and not item.discovery["too_illiquid"] and item.discovery["current_price"] >= min_price and item.discovery["dollar_volume"] >= min_dollar_volume
    ]
    results = [
        row
        for row in liquid
        if row["new_52_week_high"] or row["near_52_week_high"]
    ]
    ranked = sorted(
        results,
        key=lambda row: (
            0 if row["new_52_week_high"] else 1,
            -_safe_float(row.get("rs_3m")),
            -_safe_float(row.get("rs_1m")),
            -_safe_float(row.get("relative_volume")),
            row["ticker"],
        ),
    )
    payload = {
        "available": True,
        "generated_at": prepared_payload["generated_at"],
        "provider": provider_name,
        "analysis_date": analysis_date.isoformat(),
        "universe_size": len(_normalize_tickers(universe)),
        "tickers_successfully_scanned": len(prepared_payload["prepared"]),
        "scan_failures": prepared_payload["failures"],
        "provider_health": prepared_payload["provider_health"],
        "cache": prepared_payload["cache"],
        "results": ranked[:top_n],
        "new_52_week_highs": [row for row in ranked if row["new_52_week_high"]][:top_n],
        "near_52_week_highs": [row for row in ranked if row["near_52_week_high"] and not row["new_52_week_high"]][:top_n],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "highs.json"
    markdown_path = output_dir / "highs.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(_build_highs_markdown(payload), encoding="utf-8")
    return DiscoveryResult(payload=payload, json_path=json_path, markdown_path=markdown_path)


def run_earnings_movers_scan(
    *,
    universe: list[str],
    provider_name: str,
    analysis_date: date,
    history_period: str = "3y",
    data_dir: Path | None = None,
    top_n: int = 50,
    min_price: float = DEFAULT_MIN_PRICE,
    min_dollar_volume: float = DEFAULT_MIN_DOLLAR_VOLUME,
    output_dir: Path = DEFAULT_EARNINGS_OUTPUT_DIR,
    refresh_cache: bool = False,
    scanner_override: DeterministicScanner | None = None,
    provider_override: MarketDataProvider | None = None,
) -> DiscoveryResult:
    prepared_payload = collect_prepared_tickers(
        tickers=universe,
        provider_name=provider_name,
        analysis_date=analysis_date,
        history_period=history_period,
        data_dir=data_dir,
        refresh_cache=refresh_cache,
        preferred_lane="Outlier",
        scanner_override=scanner_override,
        provider_override=provider_override,
    )
    results = []
    for item in prepared_payload["prepared"]:
        row = item.discovery
        if row["current_price"] < min_price or row["dollar_volume"] < min_dollar_volume:
            continue
        if row["earnings_like_mover"] or row["event_source"] != "unavailable":
            results.append(row)
    ranked = sorted(
        results,
        key=lambda row: (
            -_safe_float(row.get("earnings_mover_score")),
            -abs(_safe_float(row.get("percent_change"))),
            -_safe_float(row.get("relative_volume")),
            row["ticker"],
        ),
    )[:top_n]
    payload = {
        "available": True,
        "generated_at": prepared_payload["generated_at"],
        "provider": provider_name,
        "analysis_date": analysis_date.isoformat(),
        "universe_size": len(_normalize_tickers(universe)),
        "tickers_successfully_scanned": len(prepared_payload["prepared"]),
        "scan_failures": prepared_payload["failures"],
        "provider_health": prepared_payload["provider_health"],
        "cache": prepared_payload["cache"],
        "results": ranked,
        "earnings_movers": ranked,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "earnings_movers.json"
    markdown_path = output_dir / "earnings_movers.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(_build_earnings_markdown(payload), encoding="utf-8")
    return DiscoveryResult(payload=payload, json_path=json_path, markdown_path=markdown_path)


def run_theme_scan(
    *,
    themes: list[str],
    provider_name: str,
    analysis_date: date,
    history_period: str = "3y",
    data_dir: Path | None = None,
    top_n: int = 25,
    output_dir: Path = DEFAULT_THEMES_OUTPUT_DIR,
    refresh_cache: bool = False,
    scanner_override: DeterministicScanner | None = None,
    provider_override: MarketDataProvider | None = None,
) -> DiscoveryResult:
    prepared_payload = collect_prepared_tickers(
        tickers=themes,
        provider_name=provider_name,
        analysis_date=analysis_date,
        history_period=history_period,
        data_dir=data_dir,
        refresh_cache=refresh_cache,
        preferred_lane="Outlier",
        scanner_override=scanner_override,
        provider_override=provider_override,
    )
    ranked = sorted(
        [item.discovery for item in prepared_payload["prepared"]],
        key=lambda row: (
            -_safe_float(row.get("theme_strength_score")),
            -_safe_float(row.get("rs_3m")),
            -_safe_float(row.get("rs_1m")),
            row["ticker"],
        ),
    )[:top_n]
    payload = {
        "available": True,
        "generated_at": prepared_payload["generated_at"],
        "provider": provider_name,
        "analysis_date": analysis_date.isoformat(),
        "themes_scanned": len(_normalize_tickers(themes)),
        "tickers_successfully_scanned": len(prepared_payload["prepared"]),
        "scan_failures": prepared_payload["failures"],
        "provider_health": prepared_payload["provider_health"],
        "cache": prepared_payload["cache"],
        "strongest_themes": ranked,
        "results": ranked,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "theme_scan.json"
    markdown_path = output_dir / "theme_scan.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(_build_theme_markdown(payload), encoding="utf-8")
    return DiscoveryResult(payload=payload, json_path=json_path, markdown_path=markdown_path)


def run_theme_constituents_scan(
    *,
    theme: str,
    constituents_path: Path,
    provider_name: str,
    analysis_date: date,
    history_period: str = "3y",
    data_dir: Path | None = None,
    top_n: int = 25,
    output_dir: Path = DEFAULT_THEMES_OUTPUT_DIR,
    refresh_cache: bool = False,
    scanner_override: DeterministicScanner | None = None,
    provider_override: MarketDataProvider | None = None,
) -> DiscoveryResult:
    if not constituents_path.exists():
        payload = {
            "available": False,
            "generated_at": _utcnow(),
            "provider": provider_name,
            "theme": theme.upper(),
            "message": f"No constituent file found. Add {constituents_path}.",
            "results": [],
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"{theme.upper()}_constituents.json"
        markdown_path = output_dir / f"{theme.upper()}_constituents.md"
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        markdown_path.write_text(_build_theme_constituents_markdown(payload), encoding="utf-8")
        return DiscoveryResult(payload=payload, json_path=json_path, markdown_path=markdown_path)

    tickers = (
        import_tickers_from_csv(constituents_path)
        if constituents_path.suffix.lower() == ".csv"
        else read_ticker_file(constituents_path)
    )
    prepared_payload = collect_prepared_tickers(
        tickers=tickers,
        provider_name=provider_name,
        analysis_date=analysis_date,
        history_period=history_period,
        data_dir=data_dir,
        refresh_cache=refresh_cache,
        preferred_lane="Outlier",
        scanner_override=scanner_override,
        provider_override=provider_override,
    )
    ranked = sorted(
        [item.discovery for item in prepared_payload["prepared"] if not item.discovery["below_min_price"] and not item.discovery["too_illiquid"]],
        key=lambda row: (
            0 if row["actionability_label"] in {"Momentum Actionable Today", "Breakout Actionable Today", "Pullback Actionable Today"} else 1,
            -_safe_float(row.get("rs_3m")),
            -_safe_float(row.get("relative_volume")),
            row["ticker"],
        ),
    )[:top_n]
    payload = {
        "available": True,
        "generated_at": prepared_payload["generated_at"],
        "provider": provider_name,
        "analysis_date": analysis_date.isoformat(),
        "theme": theme.upper(),
        "constituents_file": str(constituents_path),
        "tickers_successfully_scanned": len(prepared_payload["prepared"]),
        "scan_failures": prepared_payload["failures"],
        "provider_health": prepared_payload["provider_health"],
        "cache": prepared_payload["cache"],
        "results": ranked,
        "theme_constituent_candidates": ranked,
        "actionable_or_research": [row for row in ranked if row["actionability_label"] != "Avoid / Do Not Chase"][:top_n],
        "new_highs": [row for row in ranked if row["new_52_week_high"]][:top_n],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{theme.upper()}_constituents.json"
    markdown_path = output_dir / f"{theme.upper()}_constituents.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(_build_theme_constituents_markdown(payload), encoding="utf-8")
    return DiscoveryResult(payload=payload, json_path=json_path, markdown_path=markdown_path)


def run_theme_basket_scan(
    *,
    basket_path: Path,
    provider_name: str,
    analysis_date: date,
    history_period: str = "3y",
    data_dir: Path | None = None,
    top_n: int = 25,
    output_dir: Path = DEFAULT_THEMES_OUTPUT_DIR,
    refresh_cache: bool = False,
    scanner_override: DeterministicScanner | None = None,
    provider_override: MarketDataProvider | None = None,
) -> DiscoveryResult:
    basket_name = basket_path.stem
    if not basket_path.exists():
        payload = {
            "available": False,
            "generated_at": _utcnow(),
            "provider": provider_name,
            "basket": basket_name,
            "message": f"No basket file found. Add {basket_path}.",
            "results": [],
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"{basket_name}_basket.json"
        markdown_path = output_dir / f"{basket_name}_basket.md"
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        markdown_path.write_text(_build_theme_basket_markdown(payload), encoding="utf-8")
        return DiscoveryResult(payload=payload, json_path=json_path, markdown_path=markdown_path)
    tickers = (
        import_tickers_from_csv(basket_path)
        if basket_path.suffix.lower() == ".csv"
        else read_ticker_file(basket_path)
    )
    prepared_payload = collect_prepared_tickers(
        tickers=tickers,
        provider_name=provider_name,
        analysis_date=analysis_date,
        history_period=history_period,
        data_dir=data_dir,
        refresh_cache=refresh_cache,
        preferred_lane="Outlier",
        scanner_override=scanner_override,
        provider_override=provider_override,
    )
    ranked = sorted(
        [item.discovery for item in prepared_payload["prepared"] if not item.discovery["below_min_price"] and not item.discovery["too_illiquid"]],
        key=lambda row: (
            0 if row["actionability_label"] in {"Momentum Actionable Today", "Breakout Actionable Today", "Pullback Actionable Today"} else 1,
            -_safe_float(row.get("rs_3m")),
            -_safe_float(row.get("relative_volume")),
            row["ticker"],
        ),
    )[:top_n]
    payload = {
        "available": True,
        "generated_at": prepared_payload["generated_at"],
        "provider": provider_name,
        "analysis_date": analysis_date.isoformat(),
        "basket": basket_name,
        "basket_file": str(basket_path),
        "tickers_successfully_scanned": len(prepared_payload["prepared"]),
        "scan_failures": prepared_payload["failures"],
        "provider_health": prepared_payload["provider_health"],
        "cache": prepared_payload["cache"],
        "results": ranked,
        "basket_candidates": ranked,
        "new_highs": [row for row in ranked if row["new_52_week_high"]][:top_n],
        "breakout_or_pullback_setups": [
            row
            for row in ranked
            if row["actionability_label"] in {"Momentum Actionable Today", "Breakout Actionable Today", "Pullback Actionable Today"}
        ][:top_n],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{basket_name}_basket.json"
    markdown_path = output_dir / f"{basket_name}_basket.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(_build_theme_basket_markdown(payload), encoding="utf-8")
    return DiscoveryResult(payload=payload, json_path=json_path, markdown_path=markdown_path)


def run_theme_discovery(
    *,
    themes: list[str],
    baskets_dir: Path,
    provider_name: str,
    analysis_date: date,
    history_period: str = "3y",
    data_dir: Path | None = None,
    top_themes: int = 5,
    top_n: int = 25,
    output_dir: Path = DEFAULT_THEMES_OUTPUT_DIR,
    refresh_cache: bool = False,
    scanner_override: DeterministicScanner | None = None,
    provider_override: MarketDataProvider | None = None,
) -> DiscoveryResult:
    theme_payload = run_theme_scan(
        themes=themes,
        provider_name=provider_name,
        analysis_date=analysis_date,
        history_period=history_period,
        data_dir=data_dir,
        top_n=max(top_themes, top_n),
        output_dir=output_dir,
        refresh_cache=refresh_cache,
        scanner_override=scanner_override,
        provider_override=provider_override,
    ).payload
    strongest = list(theme_payload.get("strongest_themes", []))[:top_themes]
    basket_payloads: list[dict[str, Any]] = []
    missing_baskets: list[str] = []
    for row in strongest:
        theme = str(row.get("ticker") or "").upper()
        if not theme:
            continue
        basket_path = resolve_theme_basket(theme, baskets_dir=baskets_dir)
        if not basket_path.exists():
            missing_baskets.append(f"No basket file found. Add {basket_path}.")
            continue
        basket_payloads.append(
            run_theme_basket_scan(
                basket_path=basket_path,
                provider_name=provider_name,
                analysis_date=analysis_date,
                history_period=history_period,
                data_dir=data_dir,
                top_n=top_n,
                output_dir=output_dir,
                refresh_cache=refresh_cache,
                scanner_override=scanner_override,
                provider_override=provider_override,
            ).payload
        )
    theme_stock_candidates = _merge_theme_constituent_candidates(basket_payloads, limit=top_n)
    payload = {
        "available": True,
        "generated_at": _utcnow(),
        "provider": provider_name,
        "analysis_date": analysis_date.isoformat(),
        "themes_scanned": len(themes),
        "top_themes_requested": top_themes,
        "strongest_themes": strongest,
        "theme_basket_results": basket_payloads,
        "missing_baskets": missing_baskets,
        "theme_stock_candidates": theme_stock_candidates,
        "results": theme_stock_candidates,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "theme_discovery.json"
    markdown_path = output_dir / "theme_discovery.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(_build_theme_discovery_markdown(payload), encoding="utf-8")
    return DiscoveryResult(payload=payload, json_path=json_path, markdown_path=markdown_path)


def _build_scan_stack(
    *,
    provider_name: str,
    analysis_date: date,
    history_period: str,
    data_dir: Path | None,
    refresh_cache: bool,
    provider_override: MarketDataProvider | None = None,
) -> tuple[MarketDataProvider, DeterministicScanner]:
    if provider_override is not None:
        provider = provider_override
    else:
        from .cli import build_provider

        args = SimpleNamespace(provider=provider_name, data_dir=data_dir, history_period=history_period)
        provider = build_provider(args=args, analysis_date=analysis_date)
    if provider_name == "real" and not isinstance(provider, ResilientMarketDataProvider):
        provider = ResilientMarketDataProvider(provider, provider_name=provider_name, history_period=history_period)
    if not isinstance(provider, FileCacheMarketDataProvider):
        provider = FileCacheMarketDataProvider(
            provider,
            provider_name=provider_name,
            history_period=history_period,
            cache_dir=DEFAULT_MARKET_CACHE_DIR,
            refresh_cache=refresh_cache,
        )
    return provider, DeterministicScanner(provider=provider, analysis_date=analysis_date)


def _build_discovery_row(
    *,
    ticker: str,
    security: SecurityData,
    row: dict[str, Any],
    decision: dict[str, Any],
    signal: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    label = _label(decision)
    trigger_needed = bool(decision.get("trigger_needed"))
    entry_or_trigger = decision.get("action_trigger") if trigger_needed else decision.get("entry_zone")
    why_fail = decision.get("why_not") or _first_text(row.get("why_it_could_fail")) or _first_text(row.get("warnings")) or "No clear risk note."
    catalyst_blob = " ".join(
        str(item)
        for item in [
            row.get("catalyst_type"),
            row.get("catalyst_quality"),
            " ".join(row.get("catalyst_tags") or []),
            security.catalyst.description if security.catalyst else "",
        ]
        if item
    ).lower()
    event_source = "unavailable"
    if any(token in catalyst_blob for token in ("earnings", "guidance", "beat", "raise")):
        event_source = "earnings_metadata"
    elif any(token in catalyst_blob for token in ("news", "contract", "product", "upgrade", "policy")):
        event_source = "news_metadata"
    earnings_like = bool(
        abs(metrics["percent_change"]) >= 6.0
        and metrics["relative_volume"] >= 2.0
        and (metrics["gap_up"] or metrics["gap_down"])
    )
    current_price = round(metrics["current_price"], 2)
    dollar_volume = round(metrics["dollar_volume"], 2)
    return {
        "ticker": ticker,
        "company": security.company_name or ticker,
        "current_price": current_price,
        "percent_change": round(metrics["percent_change"], 2),
        "volume": round(metrics["volume"], 2),
        "average_volume_20d": round(metrics["average_volume_20d"], 2),
        "relative_volume": round(metrics["relative_volume"], 2),
        "dollar_volume": dollar_volume,
        "average_dollar_volume_20d": round(metrics["average_dollar_volume_20d"], 2),
        "one_month_return": round(metrics["return_1m"], 2),
        "three_month_return": round(metrics["return_3m"], 2),
        "rs_1m": round(metrics["rs_1m"], 2),
        "rs_3m": round(metrics["rs_3m"], 2),
        "new_52_week_high": metrics["new_52_week_high"],
        "near_52_week_high": metrics["near_52_week_high"],
        "high_52w": round(metrics["high_52w"], 2),
        "distance_from_52w_high_pct": round(metrics["distance_from_52w_high_pct"], 2),
        "gap_up": metrics["gap_up"],
        "gap_down": metrics["gap_down"],
        "breakout_with_volume": metrics["breakout_with_volume"],
        "distribution_or_heavy_selling": metrics["distribution_or_heavy_selling"],
        "gap_and_hold": metrics["gap_and_hold"],
        "volume_confirms": metrics["volume_confirms"],
        "event_source": event_source,
        "earnings_like_mover": earnings_like,
        "new_high_after_earnings": metrics["new_52_week_high"] and (earnings_like or event_source == "earnings_metadata"),
        "guidance_or_news_tags": row.get("catalyst_tags") or [],
        "actionability_label": label,
        "actionability_score": decision.get("actionability_score"),
        "why_it_is_interesting": decision.get("reason") or decision.get("actionability_reason") or row.get("signal_explanation"),
        "why_it_may_fail": why_fail,
        "entry_or_trigger": entry_or_trigger or "unavailable",
        "invalidation": decision.get("invalidation") or decision.get("stop_loss") or row.get("invalidation_level") or "unavailable",
        "is_extended": metrics["is_extended"],
        "too_late": metrics["too_late"],
        "above_ema_21": metrics["above_ema_21"],
        "above_ema_50": metrics["above_ema_50"],
        "above_ema_150": metrics["above_ema_150"],
        "above_ema_200": metrics["above_ema_200"],
        "ema_21": row.get("ema_21"),
        "ema_50": row.get("ema_50"),
        "ema_150": row.get("ema_150"),
        "ema_200": row.get("ema_200"),
        "ema_stack": row.get("ema_stack"),
        "signal_summary": row.get("signal_summary"),
        "signal_explanation": row.get("signal_explanation"),
        "risk_level": decision.get("risk_level"),
        "price_validation_status": decision.get("price_validation_status"),
        "stale_data": decision.get("price_validation_status") != "PASS" and "stale" in str(decision.get("price_validation_reason") or "").lower(),
        "below_min_price": current_price < DEFAULT_MIN_PRICE,
        "too_illiquid": dollar_volume < DEFAULT_MIN_DOLLAR_VOLUME or metrics["average_volume_20d"] < DEFAULT_MIN_AVERAGE_VOLUME,
        "freshness": row.get("last_market_date"),
        "theme_tags": row.get("theme_tags") or [],
        "catalyst_tags": row.get("catalyst_tags") or [],
        "market_cap": security.market_cap,
        "is_etf": _is_etf_symbol(ticker, security=security),
        "benchmark_source": metrics["benchmark_source"],
        "theme_strength_score": metrics["theme_strength_score"],
        "earnings_mover_score": metrics["earnings_mover_score"],
        "source_row": row,
        "decision": decision,
    }


def _security_metrics(
    security: SecurityData,
    signal: dict[str, Any],
    analysis_date: date,
    *,
    benchmark_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bars = list(security.bars)
    closes = [float(bar.close) for bar in bars]
    volumes = [float(bar.volume or 0.0) for bar in bars]
    latest = bars[-1]
    previous = bars[-2] if len(bars) >= 2 else latest
    current_price = float(security.quote_price_if_available or security.latest_available_close or latest.close or 0.0)
    average_volume_20d = _average(volumes[-20:]) if volumes else 0.0
    average_dollar_volume_20d = _average([bar.close * bar.volume for bar in bars[-20:]]) if bars else 0.0
    relative_volume = _safe_float(signal.get("relative_volume_20d"))
    one_day_change = ((current_price / previous.close) - 1.0) * 100 if previous.close else 0.0
    return_1m = _return_pct(closes, 21)
    return_3m = _return_pct(closes, 63)
    benchmark_1m = _safe_float((benchmark_metrics or {}).get("return_1m"))
    benchmark_3m = _safe_float((benchmark_metrics or {}).get("return_3m"))
    high_window = closes[-252:] if len(closes) >= 252 else closes
    high_52w = max(high_window) if high_window else current_price
    distance = ((current_price / high_52w) - 1.0) * 100 if high_52w else 0.0
    gap_up = bool(signal.get("gap_up"))
    gap_down = bool(signal.get("gap_down"))
    close_strength = _safe_float(signal.get("close_strength"))
    return {
        "current_price": current_price,
        "volume": float(latest.volume or 0.0),
        "average_volume_20d": average_volume_20d,
        "average_dollar_volume_20d": average_dollar_volume_20d,
        "relative_volume": relative_volume,
        "percent_change": one_day_change,
        "return_1m": return_1m,
        "return_3m": return_3m,
        "rs_1m": return_1m - benchmark_1m if benchmark_1m is not None else return_1m,
        "rs_3m": return_3m - benchmark_3m if benchmark_3m is not None else return_3m,
        "benchmark_source": "SPY" if benchmark_metrics else "unavailable",
        "dollar_volume": current_price * float(latest.volume or 0.0),
        "high_52w": high_52w,
        "new_52_week_high": bool(current_price >= high_52w * 0.999),
        "near_52_week_high": bool(current_price >= high_52w * 0.97),
        "distance_from_52w_high_pct": distance,
        "gap_up": gap_up,
        "gap_down": gap_down,
        "breakout_with_volume": bool(signal.get("breakout_with_volume")),
        "distribution_or_heavy_selling": bool(signal.get("distribution_warning") or signal.get("high_volume_red_candle_warning")),
        "gap_and_hold": gap_up and current_price > latest.open and close_strength >= 0.6,
        "volume_confirms": relative_volume >= 1.5,
        "above_ema_21": not bool(signal.get("close_below_ema_21")),
        "above_ema_50": not bool(signal.get("close_below_ema_50")),
        "above_ema_150": not bool(signal.get("close_below_ema_150")),
        "above_ema_200": not bool(signal.get("close_below_ema_200")),
        "is_extended": _safe_float(signal.get("price_vs_ema_21_pct")) >= 8.0 or _safe_float(signal.get("price_vs_ema_50_pct")) >= 14.0 or str(signal.get("signal_summary")) in {"Extended Above EMA 21", "Extended Above EMA 50"},
        "too_late": _safe_float(signal.get("price_vs_ema_21_pct")) >= 10.0 or _safe_float(signal.get("price_vs_ema_50_pct")) >= 16.0,
        "theme_strength_score": max(return_3m, 0.0) + max(return_1m, 0.0) + (6.0 if current_price >= high_52w * 0.999 else 0.0) + (3.0 if relative_volume >= 1.2 else 0.0),
        "earnings_mover_score": abs(one_day_change) + (relative_volume * 4.0) + (4.0 if gap_up or gap_down else 0.0) + (4.0 if current_price >= high_52w * 0.999 else 0.0),
    }


def _file_symbol_report(lines: list[str], *, source: str) -> dict[str, Any]:
    symbols_seen: list[str] = []
    duplicates: list[str] = []
    invalid: list[str] = []
    etfs: list[str] = []
    stocks: list[str] = []
    for raw in lines:
        ticker = display_ticker(raw.strip())
        if not ticker or ticker.startswith("#"):
            continue
        if ticker in symbols_seen and ticker not in duplicates:
            duplicates.append(ticker)
        if not _VALID_TICKER_RE.fullmatch(ticker):
            if ticker not in invalid:
                invalid.append(ticker)
            continue
        symbols_seen.append(ticker)
    unique_symbols = sorted(dict.fromkeys(symbols_seen))
    for ticker in unique_symbols:
        if _is_etf_symbol(ticker):
            etfs.append(ticker)
        else:
            stocks.append(ticker)
    return {
        "source": source,
        "total_symbols": len([display_ticker(raw.strip()) for raw in lines if display_ticker(raw.strip()) and not display_ticker(raw.strip()).startswith("#")]),
        "unique_count": len(unique_symbols),
        "unique_symbols": unique_symbols,
        "duplicate_symbols": duplicates,
        "duplicate_count": len(duplicates),
        "invalid_symbols": invalid,
        "invalid_count": len(invalid),
        "etf_symbols": etfs,
        "etf_count": len(etfs),
        "stock_symbols": stocks,
        "stock_count": len(stocks),
    }


def _coverage_label(unique_count: int) -> str:
    if unique_count < 150:
        return "tiny curated list"
    if unique_count < 700:
        return "partial broad universe"
    if unique_count < 2500:
        return "broader liquid universe"
    return "near-full liquid universe"


def _coverage_sufficiency(*, unique_count: int, tracked_count: int, etf_count: int, theme_basket_count: int) -> dict[str, str]:
    def status(ok: bool, limited: bool, ok_text: str, limited_text: str, weak_text: str) -> str:
        if ok:
            return ok_text
        if limited:
            return limited_text
        return weak_text

    return {
        "mega_cap_investing": status(
            unique_count >= 100,
            unique_count >= 40,
            "Yes: enough for mega-cap investing coverage.",
            "Limited: enough for a starter mega-cap workflow, but not robust.",
            "No: too small even for reliable mega-cap coverage.",
        ),
        "swing_trading": status(
            unique_count >= 400,
            unique_count >= 150,
            "Mostly: enough for many liquid swing-trading candidates.",
            "Limited: workable, but many setups will still be missed.",
            "No: universe is too narrow for serious swing-trading discovery.",
        ),
        "outlier_discovery": status(
            unique_count >= 2200,
            unique_count >= 900,
            "Mostly: broad enough for stronger outlier discovery, though still not the full market.",
            "Limited: good for large liquid names, but smaller liquid outliers can be missed.",
            "No: too small for dependable outlier discovery.",
        ),
        "earnings_movers": status(
            unique_count >= 1500,
            unique_count >= 600,
            "Mostly: enough to catch many liquid earnings movers.",
            "Limited: catches bigger liquid earnings movers, but not full breadth.",
            "No: too narrow to trust for earnings breadth.",
        ),
        "theme_rotation_discovery": status(
            (etf_count >= 20 or tracked_count >= 20) and theme_basket_count >= 5,
            etf_count >= 5 or theme_basket_count >= 2,
            "Mostly: enough ETF and basket coverage to support theme rotation discovery.",
            "Limited: some theme rotation discovery is possible, but ETF or basket coverage is incomplete.",
            "No: add dedicated ETF files and manual theme baskets for real theme rotation discovery.",
        ),
    }


def _coverage_recommendations(
    *,
    coverage_label: str,
    sufficiency: dict[str, str],
    universe_health: dict[str, Any],
    tracked_missing: list[str],
) -> list[str]:
    recommendations = [
        f"Current configured coverage is '{coverage_label}', not the full U.S. market.",
    ]
    if universe_health.get("universe_is_stale"):
        recommendations.append("Refresh the symbol master and liquid universe because at least one universe artifact is stale.")
    if not universe_health.get("theme_universe_exists"):
        recommendations.append("Create or refresh config/universe_theme_etfs.txt so theme ETF discovery has a dedicated universe.")
    if not universe_health.get("theme_baskets_exist"):
        recommendations.append("Add manual files under config/theme_baskets so strong themes can map into actionable stock baskets.")
    if tracked_missing:
        recommendations.append("Some tracked tickers are outside the universe. Either add them to the dynamic universe or keep them as tracked-only exceptions.")
    if "Limited" in sufficiency.get("outlier_discovery", "") or "No:" in sufficiency.get("outlier_discovery", ""):
        recommendations.append("Use the dynamic symbol master plus liquid-universe build so smaller liquid movers are less likely to be missed.")
    if "Limited" in sufficiency.get("theme_rotation_discovery", "") or "No:" in sufficiency.get("theme_rotation_discovery", ""):
        recommendations.append("Expand ETF/theme coverage and map strong ETFs to manual stock baskets for better sector-rotation discovery.")
    return recommendations


def _why_missed_reason(
    *,
    ticker: str,
    in_universe: bool,
    in_tracked: bool,
    latest_daily_decision: dict[str, Any] | None,
    latest_mover: dict[str, Any] | None,
    latest_daily_failure: dict[str, Any] | None,
    latest_movers_failure: dict[str, Any] | None,
    evaluation: dict[str, Any],
    daily_payload: dict[str, Any],
    movers_payload: dict[str, Any],
) -> str:
    if not in_universe and not in_tracked:
        return "outside universe"
    if latest_daily_failure or latest_movers_failure or evaluation.get("provider_data_status") == "provider_failure":
        return "provider failure"
    if evaluation.get("stale_data"):
        return "stale data"
    if evaluation.get("price_validation_status") not in {"PASS", "not_run", "provider_failure"}:
        return "failed price validation"
    if evaluation.get("below_min_price"):
        return "below min price"
    if evaluation.get("too_illiquid"):
        return "too illiquid"
    if evaluation.get("filtered_by_risk_or_actionability"):
        return "filtered out by price, volume, risk, or actionability"
    if evaluation.get("not_enough_signal"):
        return "not enough signal"
    if latest_daily_decision or latest_mover:
        label = _label(latest_daily_decision or {})
        if label == "Avoid / Do Not Chase":
            return "filtered out by price, volume, risk, or actionability"
        if label in {"Watch for Better Entry", "Slow Compounder Watch", "High-Volume Mover Watch", "Long-Term Research Candidate"}:
            return "not enough signal"
        return "symbol was scanned"
    if daily_payload or movers_payload:
        return "not in latest scan artifact"
    return "not in latest scan artifact"


def _why_missed_actions(*, ticker: str, exact_reason: str, in_universe: bool, in_tracked: bool) -> list[str]:
    actions: list[str] = []
    if exact_reason == "outside universe":
        if not in_tracked:
            actions.append(f"Add {ticker} to tracked tickers if you want daily explicit monitoring.")
        actions.append("Expand the broad universe or import a larger CSV universe.")
        actions.append("Run movers, highs, earnings-movers, or theme scans on a broader liquid universe.")
    elif exact_reason == "provider failure":
        actions.append("Retry with a healthy provider or rerun after provider rate limits clear.")
    elif exact_reason in {"failed price validation", "stale data"}:
        actions.append("Refresh live data and rerun the scan once price validation passes.")
    elif exact_reason == "too illiquid":
        actions.append("Keep it off the liquid-actionable list unless liquidity improves.")
    elif exact_reason == "below min price":
        actions.append("Treat it as below the minimum quality/price threshold unless you intentionally widen filters.")
    elif exact_reason == "not enough signal":
        actions.append("Keep it on watch or tracked, but wait for a cleaner breakout, pullback, or catalyst confirmation.")
    elif exact_reason == "filtered out by price, volume, risk, or actionability":
        actions.append("Review actionability blockers and only promote it after the deterministic risk filters clear.")
    else:
        actions.append("Check the latest scan artifact and rerun the relevant discovery scans.")
    return actions


def _build_coverage_markdown(payload: dict[str, Any]) -> str:
    universe = payload["universe_file"]
    tracked = payload["tracked_file"]
    lines = [
        "# Coverage Audit",
        "",
        f"- Coverage label: {payload['coverage_label']}",
        "- TradeBruv scans the configured universe only.",
        "- This is not the full U.S. market.",
        "- Smaller liquid movers outside the file can be missed.",
        "",
        "## Refresh Health",
        f"- Symbol master age: {payload['symbol_master_age'].get('age_days')} days",
        f"- Liquid universe age: {payload['liquid_universe_age'].get('age_days')} days",
        f"- Liquid universe symbols: {payload['number_of_symbols_in_liquid_universe']}",
        f"- Theme ETF universe exists: {payload['theme_etf_universe_exists']}",
        f"- Theme baskets exist: {payload['theme_baskets_exist']} ({payload['theme_basket_count']})",
        f"- Universe stale: {payload['universe_is_stale']}",
        "",
        "## Universe File",
        f"- File: {universe['source']}",
        f"- Total symbols: {universe['total_symbols']}",
        f"- Unique symbols after dedupe: {universe['unique_count']}",
        f"- Duplicate symbols: {universe['duplicate_count']}",
        f"- Invalid symbols: {universe['invalid_count']}",
        f"- Detectable ETFs: {universe['etf_count']}",
        f"- Detectable stocks: {universe['stock_count']}",
        "",
        "## Tracked File",
        f"- File: {tracked['source']}",
        f"- Total symbols: {tracked['total_symbols']}",
        f"- Unique symbols after dedupe: {tracked['unique_count']}",
        f"- Tracked symbols included in universe: {payload['tracked_symbols_included_count']}",
        f"- Tracked symbols missing from universe: {payload['tracked_symbols_missing_count']}",
        "",
        "## Sufficiency",
    ]
    for key, value in payload["sufficiency"].items():
        lines.append(f"- {key.replace('_', ' ')}: {value}")
    if universe["duplicate_symbols"]:
        lines.extend(["", "## Duplicate Symbols"])
        for ticker in universe["duplicate_symbols"][:25]:
            lines.append(f"- {ticker}")
    if tracked["duplicate_symbols"]:
        lines.extend(["", "## Tracked Duplicates"])
        for ticker in tracked["duplicate_symbols"][:25]:
            lines.append(f"- {ticker}")
    if universe["invalid_symbols"] or tracked["invalid_symbols"]:
        lines.extend(["", "## Invalid Symbols"])
        for ticker in (universe["invalid_symbols"] + tracked["invalid_symbols"])[:25]:
            lines.append(f"- {ticker}")
    if payload["tracked_symbols_missing"]:
        lines.extend(["", "## Tracked Missing From Universe"])
        for ticker in payload["tracked_symbols_missing"][:25]:
            lines.append(f"- {ticker}")
    return "\n".join(lines)


def _build_coverage_recommendations_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Coverage Recommendations",
        "",
        f"- Coverage label: {payload['coverage_label']}",
        f"- Universe stale: {payload['universe_is_stale']}",
        "",
    ]
    for item in payload.get("coverage_recommendations", []):
        lines.append(f"- {item}")
    return "\n".join(lines)


def _build_why_missed_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Why {payload['symbol']} Was Missed",
        "",
        f"- Exact reason: {payload['exact_reason']}",
        f"- In broad universe: {payload['is_in_broad_universe']}",
        f"- In tracked tickers: {payload['is_in_tracked_tickers']}",
        f"- Scanned in latest movers: {payload['was_scanned_in_latest_movers']}",
        f"- Scanned in latest daily decision: {payload['was_scanned_in_latest_daily_decision']}",
        f"- Valid data: {payload['had_valid_data']}",
        f"- Provider data status: {payload['provider_data_status']}",
        f"- Failed price validation: {payload['failed_price_validation']}",
        f"- Too illiquid: {payload['too_illiquid']}",
        f"- Below min price: {payload['below_min_price']}",
        f"- Stale data: {payload['stale_data']}",
        f"- Not enough signal: {payload['not_enough_signal']}",
        "",
        "## What To Do",
    ]
    for item in payload["what_to_do"]:
        lines.append(f"- {item}")
    decision = ((payload.get("evaluation") or {}).get("decision") or {})
    if decision:
        lines.extend(
            [
                "",
                "## Evaluation Snapshot",
                f"- Actionability label: {_label(decision)}",
                f"- Reason: {decision.get('reason')}",
                f"- Why not: {decision.get('why_not')}",
            ]
        )
    return "\n".join(lines)


def _build_highs_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 52-Week Highs",
        "",
        f"- Provider: {payload['provider']}",
        f"- Coverage: {payload['tickers_successfully_scanned']}/{payload['universe_size']}",
        "",
        "## New 52-Week Highs",
    ]
    _append_discovery_rows(lines, payload.get("new_52_week_highs", []), limit=10)
    lines.extend(["", "## Near 52-Week Highs"])
    _append_discovery_rows(lines, payload.get("near_52_week_highs", []), limit=10)
    return "\n".join(lines)


def _build_earnings_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Earnings / News Movers",
        "",
        f"- Provider: {payload['provider']}",
        f"- Coverage: {payload['tickers_successfully_scanned']}/{payload['universe_size']}",
        "",
        "## Earnings Movers",
    ]
    _append_discovery_rows(lines, payload.get("earnings_movers", []), limit=15)
    return "\n".join(lines)


def _build_theme_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Theme Scan",
        "",
        f"- Provider: {payload['provider']}",
        f"- Themes scanned: {payload['themes_scanned']}",
        "",
        "## Strongest Themes",
    ]
    _append_discovery_rows(lines, payload.get("strongest_themes", []), limit=15)
    return "\n".join(lines)


def _build_theme_constituents_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Theme Constituents: {payload.get('theme', 'Unknown')}",
        "",
    ]
    if not payload.get("available", False):
        lines.append(f"- {payload.get('message')}")
        return "\n".join(lines)
    lines.extend(["## Actionable Or Research", ""])
    _append_discovery_rows(lines, payload.get("actionable_or_research", []), limit=15)
    lines.extend(["", "## New Highs"])
    _append_discovery_rows(lines, payload.get("new_highs", []), limit=10)
    return "\n".join(lines)


def _build_theme_basket_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# Theme Basket: {payload.get('basket', 'Unknown')}", ""]
    if not payload.get("available", False):
        lines.append(f"- {payload.get('message')}")
        return "\n".join(lines)
    lines.extend(["## Basket Candidates", ""])
    _append_discovery_rows(lines, payload.get("basket_candidates", []), limit=15)
    lines.extend(["", "## Breakout / Pullback Setups"])
    _append_discovery_rows(lines, payload.get("breakout_or_pullback_setups", []), limit=10)
    return "\n".join(lines)


def _build_theme_discovery_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Theme Discovery",
        "",
        f"- Provider: {payload.get('provider')}",
        f"- Themes scanned: {payload.get('themes_scanned')}",
        "",
        "## Strongest Themes",
    ]
    _append_discovery_rows(lines, payload.get("strongest_themes", []), limit=10)
    lines.extend(["", "## Theme Stock Candidates"])
    _append_discovery_rows(lines, payload.get("theme_stock_candidates", []), limit=15)
    if payload.get("missing_baskets"):
        lines.extend(["", "## Missing Baskets"])
        for item in payload["missing_baskets"]:
            lines.append(f"- {item}")
    return "\n".join(lines)


def _append_discovery_rows(lines: list[str], rows: list[dict[str, Any]], *, limit: int) -> None:
    if not rows:
        lines.append("- None.")
        return
    for row in rows[:limit]:
        lines.append(
            f"- {row['ticker']}: {row['actionability_label']} | {row['why_it_is_interesting']} | RV {row['relative_volume']} | 1M RS {row['rs_1m']} | 3M RS {row['rs_3m']}"
        )


def _merge_theme_constituent_candidates(payloads: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        if not payload.get("available", False):
            continue
        rows.extend(payload.get("theme_constituent_candidates", []))
        rows.extend(payload.get("basket_candidates", []))
    rows.sort(
        key=lambda row: (
            0 if str(row.get("actionability_label")) in {"Momentum Actionable Today", "Breakout Actionable Today", "Pullback Actionable Today"} else 1,
            -float(row.get("rs_3m") or 0),
            -float(row.get("relative_volume") or 0),
            str(row.get("ticker") or ""),
        )
    )
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            deduped.append(row)
    return deduped[:limit]


def _first_by_ticker(rows: list[dict[str, Any]] | Any, ticker: str) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    for row in rows:
        if str(row.get("ticker") or "").upper() == ticker:
            return row
    return None


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _safe_get_security(scanner: DeterministicScanner, ticker: str) -> SecurityData | None:
    try:
        return scanner._get_data(ticker)
    except Exception:
        return None


def _normalize_tickers(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    for raw in values:
        ticker = display_ticker(str(raw or "").strip())
        if not ticker or ticker.startswith("#") or ticker in output:
            continue
        output.append(ticker)
    return output


def _detect_ticker_column(fieldnames: list[str]) -> str:
    normalized = {name.lower(): name for name in fieldnames}
    for candidate in ("symbol", "ticker", "symbols", "tickers"):
        if candidate in normalized:
            return normalized[candidate]
    if fieldnames:
        return fieldnames[0]
    raise KeyError("No columns found in CSV.")


def _average(values: list[float]) -> float:
    clean = [float(value) for value in values if value not in (None, "unavailable")]
    return sum(clean) / len(clean) if clean else 0.0


def _return_pct(closes: list[float], periods: int) -> float:
    if len(closes) <= periods or closes[-periods - 1] == 0:
        return 0.0
    return ((closes[-1] / closes[-periods - 1]) - 1.0) * 100


def _safe_float(value: Any) -> float:
    if value in (None, "", "unavailable", "None"):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_etf_symbol(ticker: str, *, security: SecurityData | None = None) -> bool:
    if ticker.upper() in THEME_ETFS:
        return True
    if security and any("etf" in str(value).lower() for value in (security.company_name, security.industry or "", security.sector or "")):
        return True
    return False


def _label(decision: dict[str, Any]) -> str:
    return str(decision.get("ai_adjusted_actionability_label") or decision.get("actionability_label") or "Data Insufficient")


def _first_text(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    for item in values:
        text = str(item or "").strip()
        if text:
            return text
    return ""


def _cache_stats(provider: Any) -> dict[str, Any]:
    if hasattr(provider, "cache_stats"):
        try:
            return provider.cache_stats()
        except Exception:
            return {"hits": 0, "misses": 0, "ttl_minutes": "unavailable"}
    return {"hits": 0, "misses": 0, "ttl_minutes": "unavailable"}


def _utcnow() -> str:
    return datetime.utcnow().isoformat() + "Z"
