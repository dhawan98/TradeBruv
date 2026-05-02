from __future__ import annotations

import csv
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .market_cache import DEFAULT_MARKET_CACHE_DIR, FileCacheMarketDataProvider
from .market_reliability import ResilientMarketDataProvider, classify_provider_error
from .ticker_symbols import display_ticker, provider_ticker

DEFAULT_SYMBOL_MASTER_CSV = Path("data/universes/symbol_master.csv")
DEFAULT_SYMBOL_MASTER_JSON = Path("data/universes/symbol_master.json")
DEFAULT_LIQUIDITY_SNAPSHOT_CSV = Path("data/universes/liquidity_snapshot.csv")
DEFAULT_LIQUID_STOCKS_UNIVERSE = Path("config/universe_us_liquid_stocks.txt")
DEFAULT_THEME_ETFS_SOURCE = Path("config/theme_etfs.txt")
DEFAULT_THEME_ETF_UNIVERSE = Path("config/universe_theme_etfs.txt")
DEFAULT_LIQUID_ETF_UNIVERSE = Path("config/universe_etfs_liquid.txt")
DEFAULT_THEME_BASKETS_DIR = Path("config/theme_baskets")
DEFAULT_THEME_CONSTITUENTS_DIR = Path("config/theme_constituents")
DEFAULT_COVERAGE_OUTPUT_DIR = Path("outputs/coverage")

DISCOVERY_UNIVERSE_PRIORITY = (
    DEFAULT_LIQUID_STOCKS_UNIVERSE,
    Path("config/universe_us_liquid_expanded.txt"),
    Path("config/universe_us_broad_1000.txt"),
)

THEME_BASKET_MAP = {
    "SMH": "semiconductors.txt",
    "SOXX": "semiconductors.txt",
    "XSD": "semiconductors.txt",
    "AIQ": "ai_software.txt",
    "SKYY": "data_centers.txt",
    "IGV": "ai_software.txt",
    "LIT": "lithium_batteries.txt",
    "HYDR": "hydrogen_fuel_cells.txt",
    "ICLN": "clean_energy.txt",
    "PBW": "clean_energy.txt",
    "TAN": "clean_energy.txt",
    "ROBO": "robotics_automation.txt",
    "GRID": "grid_infrastructure.txt",
    "QTUM": "quantum.txt",
    "DRIV": "ev_autonomous.txt",
    "FDRV": "ev_autonomous.txt",
    "CIBR": "cybersecurity.txt",
    "HACK": "cybersecurity.txt",
    "BOTZ": "robotics_automation.txt",
}

NASDAQTRADER_URLS = {
    "nasdaqlisted": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "otherlisted": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
}


def refresh_symbol_master(
    *,
    source: str,
    output_path: Path = DEFAULT_SYMBOL_MASTER_CSV,
    coverage_output_dir: Path = DEFAULT_COVERAGE_OUTPUT_DIR,
    exclude_test_issues: bool = True,
) -> dict[str, Any]:
    requested_source = source.strip().lower()
    attempts: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    effective_source = requested_source
    refresh_succeeded = False
    fallback_used = False
    message = ""

    for candidate in _symbol_master_source_candidates(requested_source):
        try:
            rows = _dedupe_symbol_master_rows(
                _load_symbol_master_from_source(candidate, exclude_test_issues=exclude_test_issues),
                exclude_test_issues=exclude_test_issues,
            )
            effective_source = candidate
            refresh_succeeded = True
            fallback_used = candidate != requested_source
            if fallback_used:
                message = f"Requested source '{requested_source}' was unavailable. Refreshed from '{candidate}' instead."
            break
        except Exception as exc:
            attempts.append({"source": candidate, "status": "failed", "reason": str(exc)})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_path.with_suffix(".json")
    refresh_markdown_path = coverage_output_dir / "symbol_master_refresh.md"
    coverage_output_dir.mkdir(parents=True, exist_ok=True)

    cached_rows: list[dict[str, Any]] = []
    used_cached_master = False
    if not refresh_succeeded:
        cached_rows = load_symbol_master(output_path) if output_path.exists() else []
        if cached_rows:
            rows = cached_rows
            effective_source = "cached"
            used_cached_master = True
            message = (
                f"Refresh failed for requested source '{requested_source}'. "
                "Reused the previous cached symbol master instead."
            )
        else:
            message = (
                f"Refresh failed for requested source '{requested_source}', "
                "and no previous symbol master was available."
            )

    if rows:
        _write_symbol_master_csv(output_path, rows)
        json_payload = {
            "generated_at": _utcnow(),
            "requested_source": requested_source,
            "effective_source": effective_source,
            "refresh_succeeded": refresh_succeeded,
            "fallback_used": fallback_used,
            "used_cached_master": used_cached_master,
            "row_count": len(rows),
            "symbols": rows,
        }
        json_path.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

    payload = {
        "generated_at": _utcnow(),
        "requested_source": requested_source,
        "effective_source": effective_source,
        "refresh_succeeded": refresh_succeeded,
        "fallback_used": fallback_used,
        "used_cached_master": used_cached_master,
        "status": (
            "refreshed"
            if refresh_succeeded and not fallback_used
            else "refreshed_with_fallback"
            if refresh_succeeded
            else "cached_fallback"
            if used_cached_master
            else "failed"
        ),
        "message": message,
        "attempts": attempts,
        "row_count": len(rows),
        "output_csv": str(output_path),
        "output_json": str(json_path),
        "excluded_test_issues": exclude_test_issues,
        "counts": _symbol_master_counts(rows),
        "sample_symbols": [row["symbol"] for row in rows[:10]],
    }
    refresh_markdown_path.write_text(_build_symbol_master_refresh_markdown(payload), encoding="utf-8")
    payload["output_markdown"] = str(refresh_markdown_path)
    return payload


def build_liquid_universe(
    *,
    symbol_master_path: Path,
    provider_name: str,
    output_path: Path = DEFAULT_LIQUID_STOCKS_UNIVERSE,
    snapshot_path: Path = DEFAULT_LIQUIDITY_SNAPSHOT_CSV,
    min_price: float = 5.0,
    min_dollar_volume: float = 10_000_000.0,
    min_avg_volume: float = 300_000.0,
    exclude_etfs: bool = True,
    exclude_funds: bool = True,
    exclude_warrants: bool = True,
    exclude_rights: bool = True,
    exclude_units: bool = True,
    exclude_preferred: bool = True,
    history_period: str = "6mo",
    data_dir: Path | None = None,
    refresh_cache: bool = False,
    coverage_output_dir: Path = DEFAULT_COVERAGE_OUTPUT_DIR,
    etf_output_path: Path = DEFAULT_LIQUID_ETF_UNIVERSE,
) -> dict[str, Any]:
    symbol_master = load_symbol_master(symbol_master_path)
    if not symbol_master:
        raise FileNotFoundError(f"Symbol master is missing or empty: {symbol_master_path}")

    snapshot_by_symbol = _load_liquidity_snapshot(snapshot_path)
    today_text = date.today().isoformat()
    stock_candidates: list[dict[str, Any]] = []
    etf_candidates: list[str] = []
    counts = {
        "raw_symbols": len(symbol_master),
        "eligible_candidates": 0,
        "excluded_etfs": 0,
        "excluded_funds": 0,
        "excluded_warrants": 0,
        "excluded_rights": 0,
        "excluded_units": 0,
        "excluded_preferreds": 0,
        "inactive_or_test_issues": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "provider_failures": 0,
        "failed_symbols": 0,
        "passed_liquidity_filters": 0,
    }
    exclusions_requested = {
        "exclude_etfs": exclude_etfs,
        "exclude_funds": exclude_funds,
        "exclude_warrants": exclude_warrants,
        "exclude_rights": exclude_rights,
        "exclude_units": exclude_units,
        "exclude_preferred": exclude_preferred,
    }

    for row in symbol_master:
        if not _truthy(row.get("active"), default=True) or _truthy(row.get("is_test_issue"), default=False):
            counts["inactive_or_test_issues"] += 1
            continue
        flags = classify_symbol_master_row(row)
        if flags["is_etf"]:
            etf_candidates.append(str(row.get("symbol") or ""))
        excluded = False
        if exclude_etfs and flags["is_etf"]:
            counts["excluded_etfs"] += 1
            excluded = True
        if exclude_funds and flags["is_fund"]:
            counts["excluded_funds"] += 1
            excluded = True
        if exclude_warrants and flags["is_warrant"]:
            counts["excluded_warrants"] += 1
            excluded = True
        if exclude_rights and flags["is_right"]:
            counts["excluded_rights"] += 1
            excluded = True
        if exclude_units and flags["is_unit"]:
            counts["excluded_units"] += 1
            excluded = True
        if exclude_preferred and flags["is_preferred"]:
            counts["excluded_preferreds"] += 1
            excluded = True
        if excluded:
            continue
        counts["eligible_candidates"] += 1
        stock_candidates.append(dict(row) | flags)

    provider = _build_market_provider(
        provider_name=provider_name,
        analysis_date=date.today(),
        history_period=history_period,
        data_dir=data_dir,
        refresh_cache=refresh_cache,
    )
    health = getattr(provider, "health_report", lambda: {"provider": provider_name, "status": "healthy"})()

    pending: list[dict[str, Any]] = []
    output_snapshot: dict[str, dict[str, Any]] = dict(snapshot_by_symbol)
    for row in stock_candidates:
        symbol = str(row.get("symbol") or "").upper()
        cached = output_snapshot.get(symbol)
        if cached and str(cached.get("snapshot_date") or "") == today_text and str(cached.get("status") or "") != "pending":
            counts["cache_hits"] += 1
            continue
        counts["cache_misses"] += 1
        pending.append(row)

    for start in range(0, len(pending), 25):
        batch = pending[start : start + 25]
        batch_symbols = [str(row.get("symbol") or "") for row in batch if row.get("symbol")]
        prefetch = getattr(provider, "prefetch_many", None)
        if callable(prefetch) and batch_symbols:
            try:
                prefetch(batch_symbols, batch_size=25)
            except Exception:
                pass
        for row in batch:
            symbol = str(row.get("symbol") or "").upper()
            try:
                security = provider.get_security_data(symbol)
                snapshot_row = _build_liquidity_snapshot_row(
                    row=row,
                    security=security,
                    snapshot_date=today_text,
                    min_price=min_price,
                    min_dollar_volume=min_dollar_volume,
                    min_avg_volume=min_avg_volume,
                )
                if snapshot_row["status"] == "passed":
                    counts["passed_liquidity_filters"] += 1
                output_snapshot[symbol] = snapshot_row
            except Exception as exc:
                classification = classify_provider_error(exc)
                counts["provider_failures"] += 1 if classification["scope"] == "provider" else 0
                counts["failed_symbols"] += 1
                output_snapshot[symbol] = _failed_liquidity_snapshot_row(
                    row=row,
                    snapshot_date=today_text,
                    status=str(classification["status"]),
                    reason=str(classification["reason"]),
                    category=str(classification["category"]),
                )
                if bool(classification["stop_scan"]) or getattr(provider, "should_stop_scan", lambda: False)():
                    _write_liquidity_snapshot(snapshot_path, output_snapshot)
                    _write_universe_from_snapshot(output_path, output_snapshot, status="passed")
                    _write_universe_from_symbols(etf_output_path, etf_candidates)
                    final_health = getattr(provider, "health_report", lambda: health)()
                    payload = _liquid_universe_payload(
                        symbol_master_path=symbol_master_path,
                        output_path=output_path,
                        snapshot_path=snapshot_path,
                        provider_name=provider_name,
                        counts=counts,
                        output_snapshot=output_snapshot,
                        provider_health=final_health,
                        partial=True,
                        message="Provider rate-limited or degraded. Partial liquidity snapshot saved for resume.",
                        exclusions_requested=exclusions_requested,
                    )
                    coverage_output_dir.mkdir(parents=True, exist_ok=True)
                    (coverage_output_dir / "liquid_universe_build.md").write_text(
                        _build_liquid_universe_markdown(payload),
                        encoding="utf-8",
                    )
                    return payload
        _write_liquidity_snapshot(snapshot_path, output_snapshot)
        _write_universe_from_snapshot(output_path, output_snapshot, status="passed")
        _write_universe_from_symbols(etf_output_path, etf_candidates)

    _write_liquidity_snapshot(snapshot_path, output_snapshot)
    _write_universe_from_snapshot(output_path, output_snapshot, status="passed")
    _write_universe_from_symbols(etf_output_path, etf_candidates)
    final_health = getattr(provider, "health_report", lambda: health)()
    payload = _liquid_universe_payload(
        symbol_master_path=symbol_master_path,
        output_path=output_path,
        snapshot_path=snapshot_path,
        provider_name=provider_name,
        counts=counts,
        output_snapshot=output_snapshot,
        provider_health=final_health,
        partial=False,
        message="Liquidity universe refresh completed.",
        exclusions_requested=exclusions_requested,
    )
    coverage_output_dir.mkdir(parents=True, exist_ok=True)
    (coverage_output_dir / "liquid_universe_build.md").write_text(_build_liquid_universe_markdown(payload), encoding="utf-8")
    return payload


def refresh_liquidity(
    *,
    provider_name: str,
    symbol_master_path: Path = DEFAULT_SYMBOL_MASTER_CSV,
    output_path: Path = DEFAULT_LIQUID_STOCKS_UNIVERSE,
    snapshot_path: Path = DEFAULT_LIQUIDITY_SNAPSHOT_CSV,
    theme_source_path: Path = DEFAULT_THEME_ETFS_SOURCE,
) -> dict[str, Any]:
    payload = build_liquid_universe(
        symbol_master_path=symbol_master_path,
        provider_name=provider_name,
        output_path=output_path,
        snapshot_path=snapshot_path,
    )
    refresh_theme_and_etf_universes(
        symbol_master_path=symbol_master_path,
        theme_source_path=theme_source_path,
    )
    return payload


def refresh_all_universes(
    *,
    provider_name: str,
    symbol_source: str = "nasdaqtrader",
    symbol_master_path: Path = DEFAULT_SYMBOL_MASTER_CSV,
    stock_output_path: Path = DEFAULT_LIQUID_STOCKS_UNIVERSE,
    snapshot_path: Path = DEFAULT_LIQUIDITY_SNAPSHOT_CSV,
    tracked_path: Path = Path("config/tracked_tickers.txt"),
    theme_source_path: Path = DEFAULT_THEME_ETFS_SOURCE,
) -> dict[str, Any]:
    symbol_payload = refresh_symbol_master(source=symbol_source, output_path=symbol_master_path)
    if not Path(symbol_payload["output_csv"]).exists():
        raise FileNotFoundError("Symbol master refresh did not produce a usable CSV.")
    liquidity_payload = build_liquid_universe(
        symbol_master_path=symbol_master_path,
        provider_name=provider_name,
        output_path=stock_output_path,
        snapshot_path=snapshot_path,
    )
    theme_payload = refresh_theme_and_etf_universes(
        symbol_master_path=symbol_master_path,
        theme_source_path=theme_source_path,
    )
    from .discovery import build_coverage_audit

    coverage_payload = build_coverage_audit(
        universe_path=stock_output_path,
        tracked_path=tracked_path,
    ).payload
    return {
        "generated_at": _utcnow(),
        "symbol_master": symbol_payload,
        "liquid_universe": liquidity_payload,
        "theme_universes": theme_payload,
        "coverage_audit": coverage_payload,
    }


def refresh_theme_and_etf_universes(
    *,
    symbol_master_path: Path = DEFAULT_SYMBOL_MASTER_CSV,
    theme_source_path: Path = DEFAULT_THEME_ETFS_SOURCE,
    theme_output_path: Path = DEFAULT_THEME_ETF_UNIVERSE,
    etf_output_path: Path = DEFAULT_LIQUID_ETF_UNIVERSE,
) -> dict[str, Any]:
    theme_rows = read_ticker_file(theme_source_path) if theme_source_path.exists() else []
    _write_universe_from_symbols(theme_output_path, theme_rows)

    etf_rows: list[str] = []
    if symbol_master_path.exists():
        for row in load_symbol_master(symbol_master_path):
            flags = classify_symbol_master_row(row)
            if _truthy(row.get("active"), default=True) and flags["is_etf"] and not _truthy(row.get("is_test_issue"), default=False):
                etf_rows.append(str(row.get("symbol") or ""))
    if not etf_rows:
        etf_rows = list(theme_rows)
    _write_universe_from_symbols(etf_output_path, etf_rows)
    return {
        "generated_at": _utcnow(),
        "theme_universe": str(theme_output_path),
        "theme_universe_count": len(theme_rows),
        "liquid_etf_universe": str(etf_output_path),
        "liquid_etf_universe_count": len(read_ticker_file(etf_output_path)),
    }


def load_symbol_master(path: Path = DEFAULT_SYMBOL_MASTER_CSV) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def parse_nasdaqtrader_listing_text(text: str, *, listing_type: str) -> list[dict[str, Any]]:
    rows = list(_pipe_rows_from_text(text))
    if listing_type == "nasdaqlisted":
        return _parse_nasdaqlisted_rows(rows)
    if listing_type == "otherlisted":
        return _parse_otherlisted_rows(rows)
    raise ValueError(f"Unsupported NasdaqTrader listing type: {listing_type}")


def classify_symbol_master_row(row: dict[str, Any]) -> dict[str, bool]:
    name = str(row.get("name") or "").strip().lower()
    raw_type = str(row.get("raw_type") or "").strip().lower()
    source = str(row.get("source") or "").strip().lower()
    symbol = str(row.get("symbol") or row.get("display_symbol") or "").strip().upper()
    symbol_marked = any(mark in symbol for mark in (".", "-", "/", "$"))
    is_etf = _truthy(row.get("is_etf"), default=False) or "etf" in name or raw_type == "etf"
    is_fund = any(token in name for token in (" fund", " funds", "mutual fund", " trust")) and not is_etf
    is_warrant = "warrant" in name or symbol.endswith("W") and symbol_marked
    is_right = " right" in name or " rights" in name or symbol.endswith("R") and symbol_marked
    is_unit = " unit" in name or " units" in name or symbol.endswith("U") and symbol_marked
    is_preferred = "preferred" in name or raw_type in {"preferred", "pref"} or "$" in symbol or symbol.endswith("P") and symbol_marked
    return {
        "is_etf": is_etf,
        "is_fund": is_fund,
        "is_warrant": is_warrant,
        "is_right": is_right,
        "is_unit": is_unit,
        "is_preferred": is_preferred,
        "from_source_nasdaqtrader": source.startswith("nasdaqtrader"),
    }


def resolve_discovery_universe(preferred_path: Path | None = None) -> dict[str, Any]:
    if preferred_path is not None:
        if not preferred_path.exists():
            raise FileNotFoundError(preferred_path)
        return {"path": preferred_path, "source": "explicit"}
    for path in DISCOVERY_UNIVERSE_PRIORITY:
        if path.exists():
            return {"path": path, "source": "default"}
    raise FileNotFoundError(
        "No discovery universe was found. Checked: "
        + ", ".join(str(path) for path in DISCOVERY_UNIVERSE_PRIORITY)
    )


def resolve_theme_basket(theme: str, *, baskets_dir: Path = DEFAULT_THEME_BASKETS_DIR) -> Path:
    ticker = display_ticker(theme)
    mapped_name = THEME_BASKET_MAP.get(ticker, f"{ticker.lower()}.txt")
    return baskets_dir / mapped_name


def read_ticker_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(path)
    return _normalize_symbols(path.read_text(encoding="utf-8").splitlines())


def build_universe_health_report(
    *,
    liquid_universe_path: Path = DEFAULT_LIQUID_STOCKS_UNIVERSE,
    symbol_master_path: Path = DEFAULT_SYMBOL_MASTER_CSV,
    theme_universe_path: Path = DEFAULT_THEME_ETF_UNIVERSE,
    theme_baskets_dir: Path = DEFAULT_THEME_BASKETS_DIR,
    stale_after_days: int = 3,
) -> dict[str, Any]:
    liquid_age = file_age_report(liquid_universe_path)
    symbol_master_age = file_age_report(symbol_master_path)
    theme_exists = theme_universe_path.exists()
    basket_files = sorted(theme_baskets_dir.glob("*.txt")) if theme_baskets_dir.exists() else []
    liquid_symbols = read_ticker_file(liquid_universe_path) if liquid_universe_path.exists() else []
    liquid_is_stale = bool(liquid_age.get("exists")) and float(liquid_age.get("age_days") or 0.0) > stale_after_days
    symbol_master_is_stale = bool(symbol_master_age.get("exists")) and float(symbol_master_age.get("age_days") or 0.0) > stale_after_days
    return {
        "symbol_master": symbol_master_age,
        "liquid_universe": liquid_age | {"symbol_count": len(liquid_symbols)},
        "theme_universe_exists": theme_exists,
        "theme_baskets_exist": bool(basket_files),
        "theme_basket_count": len(basket_files),
        "theme_basket_files": [str(path) for path in basket_files],
        "universe_is_stale": liquid_is_stale or symbol_master_is_stale,
        "stale_after_days": stale_after_days,
    }


def file_age_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "updated_at": None, "age_days": None}
    updated_at = datetime.fromtimestamp(path.stat().st_mtime)
    age = datetime.utcnow() - updated_at
    return {
        "path": str(path),
        "exists": True,
        "updated_at": updated_at.isoformat() + "Z",
        "age_days": round(age.total_seconds() / 86400.0, 2),
    }


def _symbol_master_source_candidates(source: str) -> list[str]:
    candidates = [source]
    if source != "nasdaqtrader":
        candidates.append("nasdaqtrader")
    return candidates


def _load_symbol_master_from_source(source: str, *, exclude_test_issues: bool) -> list[dict[str, Any]]:
    if source == "nasdaqtrader":
        rows: list[dict[str, Any]] = []
        for listing_type, url in NASDAQTRADER_URLS.items():
            text = _download_text(url)
            rows.extend(parse_nasdaqtrader_listing_text(text, listing_type=listing_type))
        return _dedupe_symbol_master_rows(rows, exclude_test_issues=exclude_test_issues)
    if source == "alphavantage":
        api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("ALPHA_VANTAGE_API_KEY is missing.")
        url = "https://www.alphavantage.co/query?" + urllib.parse.urlencode(
            {"function": "LISTING_STATUS", "state": "active", "apikey": api_key}
        )
        text = _download_text(url)
        return _dedupe_symbol_master_rows(_parse_alpha_vantage_listing_status(text), exclude_test_issues=exclude_test_issues)
    if source == "finnhub":
        api_key = os.getenv("FINNHUB_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("FINNHUB_API_KEY is missing.")
        payload = json.loads(_download_text("https://finnhub.io/api/v1/stock/symbol?exchange=US&token=" + urllib.parse.quote(api_key)))
        return _dedupe_symbol_master_rows(_parse_finnhub_symbols(payload), exclude_test_issues=exclude_test_issues)
    if source == "fmp":
        api_key = os.getenv("FINANCIAL_MODELING_PREP_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("FINANCIAL_MODELING_PREP_API_KEY is missing.")
        url = "https://financialmodelingprep.com/stable/actively-trading-list?" + urllib.parse.urlencode({"apikey": api_key})
        payload = json.loads(_download_text(url))
        return _dedupe_symbol_master_rows(_parse_fmp_symbols(payload), exclude_test_issues=exclude_test_issues)
    raise ValueError(f"Unsupported symbol-master source: {source}")


def _parse_nasdaqlisted_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for row in rows:
        raw_symbol = str(row.get("Symbol") or "").strip()
        if not raw_symbol or raw_symbol.lower().startswith("file creation time"):
            continue
        display_symbol = display_ticker(raw_symbol)
        parsed.append(
            {
                "symbol": display_symbol,
                "display_symbol": display_symbol,
                "provider_symbol": provider_ticker(display_symbol),
                "name": str(row.get("Security Name") or "").strip(),
                "exchange": "NASDAQ",
                "is_etf": str(row.get("ETF") or "").strip().upper() == "Y",
                "is_test_issue": str(row.get("Test Issue") or "").strip().upper() == "Y",
                "raw_type": str(row.get("ETF") or "").strip().upper() == "Y" and "ETF" or "stock",
                "source": "nasdaqtrader:nasdaqlisted",
                "active": True,
            }
        )
    return parsed


def _parse_otherlisted_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for row in rows:
        raw_symbol = str(row.get("ACT Symbol") or row.get("Nasdaq Symbol") or "").strip()
        if not raw_symbol or raw_symbol.lower().startswith("file creation time"):
            continue
        display_symbol = display_ticker(raw_symbol)
        exchange = _otherlisted_exchange_name(str(row.get("Exchange") or "").strip())
        parsed.append(
            {
                "symbol": display_symbol,
                "display_symbol": display_symbol,
                "provider_symbol": provider_ticker(display_symbol),
                "name": str(row.get("Security Name") or "").strip(),
                "exchange": exchange,
                "is_etf": str(row.get("ETF") or "").strip().upper() == "Y",
                "is_test_issue": str(row.get("Test Issue") or "").strip().upper() == "Y",
                "raw_type": str(row.get("ETF") or "").strip().upper() == "Y" and "ETF" or "stock",
                "source": "nasdaqtrader:otherlisted",
                "active": True,
            }
        )
    return parsed


def _parse_alpha_vantage_listing_status(text: str) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    reader = csv.DictReader(text.splitlines())
    for row in reader:
        raw_symbol = str(row.get("symbol") or "").strip()
        if not raw_symbol:
            continue
        display_symbol = display_ticker(raw_symbol)
        asset_type = str(row.get("assetType") or "").strip()
        parsed.append(
            {
                "symbol": display_symbol,
                "display_symbol": display_symbol,
                "provider_symbol": provider_ticker(display_symbol),
                "name": str(row.get("name") or "").strip(),
                "exchange": str(row.get("exchange") or "").strip() or "US",
                "is_etf": asset_type.upper() == "ETF" or "ETF" in str(row.get("name") or "").upper(),
                "is_test_issue": False,
                "raw_type": asset_type or "stock",
                "source": "alphavantage:listing_status",
                "active": str(row.get("status") or "active").strip().lower() == "active",
            }
        )
    return parsed


def _parse_finnhub_symbols(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for row in payload or []:
        raw_symbol = str(row.get("displaySymbol") or row.get("symbol") or "").strip()
        if not raw_symbol:
            continue
        display_symbol = display_ticker(raw_symbol)
        raw_type = str(row.get("type") or "").strip()
        parsed.append(
            {
                "symbol": display_symbol,
                "display_symbol": display_symbol,
                "provider_symbol": provider_ticker(display_symbol),
                "name": str(row.get("description") or row.get("displaySymbol") or display_symbol).strip(),
                "exchange": str(row.get("mic") or row.get("exchange") or "US").strip(),
                "is_etf": "ETF" in raw_type.upper() or "ETF" in str(row.get("description") or "").upper(),
                "is_test_issue": False,
                "raw_type": raw_type or "stock",
                "source": "finnhub:stock_symbols",
                "active": True,
            }
        )
    return parsed


def _parse_fmp_symbols(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for row in payload or []:
        raw_symbol = str(row.get("symbol") or "").strip()
        if not raw_symbol:
            continue
        display_symbol = display_ticker(raw_symbol)
        raw_type = str(row.get("type") or row.get("assetType") or "").strip()
        parsed.append(
            {
                "symbol": display_symbol,
                "display_symbol": display_symbol,
                "provider_symbol": provider_ticker(display_symbol),
                "name": str(row.get("name") or display_symbol).strip(),
                "exchange": str(row.get("exchange") or row.get("exchangeShortName") or "US").strip(),
                "is_etf": "ETF" in raw_type.upper() or "ETF" in str(row.get("name") or "").upper(),
                "is_test_issue": False,
                "raw_type": raw_type or "stock",
                "source": "fmp:actively_trading_list",
                "active": _truthy(row.get("activelyTrading"), default=True),
            }
        )
    return parsed


def _dedupe_symbol_master_rows(rows: list[dict[str, Any]], *, exclude_test_issues: bool) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        if exclude_test_issues and _truthy(row.get("is_test_issue"), default=False):
            continue
        existing = best.get(symbol)
        if existing is None or (_truthy(row.get("active"), default=True) and not _truthy(existing.get("active"), default=True)):
            best[symbol] = row
    return [best[key] for key in sorted(best)]


def _pipe_rows_from_text(text: str) -> list[dict[str, str]]:
    filtered_lines = [line for line in text.splitlines() if line.strip() and not line.startswith("File Creation Time")]
    reader = csv.DictReader(filtered_lines, delimiter="|")
    return [dict(row) for row in reader]


def _download_text(url: str, *, timeout: int = 30) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "TradeBruv/1.0 universe-refresh"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8-sig")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{url} returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{url} failed to download: {exc.reason}.") from exc


def _write_symbol_master_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
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
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def _symbol_master_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rows": len(rows),
        "active_rows": sum(1 for row in rows if _truthy(row.get("active"), default=True)),
        "etf_rows": sum(1 for row in rows if _truthy(row.get("is_etf"), default=False)),
        "stock_rows": sum(1 for row in rows if not _truthy(row.get("is_etf"), default=False)),
        "provider_symbol_changes": sum(
            1
            for row in rows
            if str(row.get("symbol") or "").strip() != str(row.get("provider_symbol") or "").strip()
        ),
    }


def _build_symbol_master_refresh_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Symbol Master Refresh",
        "",
        f"- Requested source: {payload.get('requested_source')}",
        f"- Effective source: {payload.get('effective_source')}",
        f"- Status: {payload.get('status')}",
        f"- Refresh succeeded: {payload.get('refresh_succeeded')}",
        f"- Fallback used: {payload.get('fallback_used')}",
        f"- Used cached master: {payload.get('used_cached_master')}",
        f"- Rows: {payload.get('row_count')}",
        "",
        payload.get("message") or "No additional notes.",
        "",
    ]
    for attempt in payload.get("attempts", []):
        lines.append(f"- Attempt failed: {attempt.get('source')} -> {attempt.get('reason')}")
    if payload.get("attempts"):
        lines.append("")
    counts = payload.get("counts") or {}
    lines.extend(
        [
            f"- ETF rows: {counts.get('etf_rows', 0)}",
            f"- Stock rows: {counts.get('stock_rows', 0)}",
            f"- Provider symbol remaps: {counts.get('provider_symbol_changes', 0)}",
        ]
    )
    return "\n".join(lines).strip()


def _build_liquidity_snapshot_row(
    *,
    row: dict[str, Any],
    security: Any,
    snapshot_date: str,
    min_price: float,
    min_dollar_volume: float,
    min_avg_volume: float,
) -> dict[str, Any]:
    bars = list(getattr(security, "bars", []) or [])
    latest = bars[-1]
    price = float(getattr(security, "quote_price_if_available", None) or getattr(security, "latest_available_close", None) or latest.close or 0.0)
    avg_volume = _average([float(bar.volume or 0.0) for bar in bars[-20:]])
    avg_dollar_volume = _average([float(bar.close or 0.0) * float(bar.volume or 0.0) for bar in bars[-20:]])
    last_volume = float(latest.volume or 0.0)
    dollar_volume = price * last_volume
    status = "passed"
    reason = ""
    if price < min_price:
        status = "below_min_price"
        reason = f"Price {round(price, 2)} below minimum {min_price}."
    elif avg_volume < min_avg_volume or dollar_volume < min_dollar_volume:
        status = "too_illiquid"
        reason = (
            f"Average volume {int(avg_volume)} / dollar volume {int(dollar_volume)} "
            f"did not meet minimum liquidity thresholds."
        )
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "display_symbol": row.get("display_symbol") or row.get("symbol"),
        "provider_symbol": row.get("provider_symbol") or provider_ticker(str(row.get("symbol") or "")),
        "name": row.get("name") or "",
        "exchange": row.get("exchange") or "",
        "is_etf": _truthy(row.get("is_etf"), default=False),
        "raw_type": row.get("raw_type") or "",
        "snapshot_date": snapshot_date,
        "last_price": round(price, 4),
        "last_volume": round(last_volume, 2),
        "avg_volume_20d": round(avg_volume, 2),
        "dollar_volume": round(dollar_volume, 2),
        "avg_dollar_volume_20d": round(avg_dollar_volume, 2),
        "last_market_date": latest.date.isoformat(),
        "status": status,
        "reason": reason,
        "provider_name": str(getattr(security, "provider_name", "") or "unavailable"),
        "refreshed_at": _utcnow(),
    }


def _failed_liquidity_snapshot_row(
    *,
    row: dict[str, Any],
    snapshot_date: str,
    status: str,
    reason: str,
    category: str,
) -> dict[str, Any]:
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "display_symbol": row.get("display_symbol") or row.get("symbol"),
        "provider_symbol": row.get("provider_symbol") or provider_ticker(str(row.get("symbol") or "")),
        "name": row.get("name") or "",
        "exchange": row.get("exchange") or "",
        "is_etf": _truthy(row.get("is_etf"), default=False),
        "raw_type": row.get("raw_type") or "",
        "snapshot_date": snapshot_date,
        "last_price": "",
        "last_volume": "",
        "avg_volume_20d": "",
        "dollar_volume": "",
        "avg_dollar_volume_20d": "",
        "last_market_date": "",
        "status": status,
        "reason": reason,
        "category": category,
        "provider_name": "unavailable",
        "refreshed_at": _utcnow(),
    }


def _load_liquidity_snapshot(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        output: dict[str, dict[str, Any]] = {}
        for row in reader:
            symbol = str(row.get("symbol") or "").upper()
            if symbol:
                output[symbol] = dict(row)
        return output


def _write_liquidity_snapshot(path: Path, rows_by_symbol: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "symbol",
        "display_symbol",
        "provider_symbol",
        "name",
        "exchange",
        "is_etf",
        "raw_type",
        "snapshot_date",
        "last_price",
        "last_volume",
        "avg_volume_20d",
        "dollar_volume",
        "avg_dollar_volume_20d",
        "last_market_date",
        "status",
        "reason",
        "category",
        "provider_name",
        "refreshed_at",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for symbol in sorted(rows_by_symbol):
            row = rows_by_symbol[symbol]
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _write_universe_from_snapshot(path: Path, rows_by_symbol: dict[str, dict[str, Any]], *, status: str) -> None:
    symbols = [
        row.get("symbol")
        for row in sorted(rows_by_symbol.values(), key=lambda item: str(item.get("symbol") or ""))
        if str(row_status := row.get("status") or "") == status and row.get("symbol")
    ]
    _write_universe_from_symbols(path, [str(symbol) for symbol in symbols if symbol])


def _write_universe_from_symbols(path: Path, symbols: list[str]) -> None:
    rows = _normalize_symbols(symbols)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")


def _liquid_universe_payload(
    *,
    symbol_master_path: Path,
    output_path: Path,
    snapshot_path: Path,
    provider_name: str,
    counts: dict[str, Any],
    output_snapshot: dict[str, dict[str, Any]],
    provider_health: dict[str, Any],
    partial: bool,
    message: str,
    exclusions_requested: dict[str, bool],
) -> dict[str, Any]:
    passed = [row for row in output_snapshot.values() if str(row.get("status") or "") == "passed"]
    failed = [row for row in output_snapshot.values() if str(row.get("status") or "") not in {"passed", "below_min_price", "too_illiquid"}]
    payload = {
        "generated_at": _utcnow(),
        "provider": provider_name,
        "symbol_master_path": str(symbol_master_path),
        "output_universe": str(output_path),
        "snapshot_path": str(snapshot_path),
        "partial": partial,
        "message": message,
        "counts": counts | {
            "final_universe_size": len(read_ticker_file(output_path)) if output_path.exists() else 0,
            "failed_symbols": len(failed),
            "passed_liquidity_filters": len(passed),
        },
        "exclusions_requested": exclusions_requested,
        "provider_health": provider_health,
        "passed_symbols_sample": [row.get("symbol") for row in passed[:15]],
        "failed_symbols_sample": [
            {"symbol": row.get("symbol"), "status": row.get("status"), "reason": row.get("reason")}
            for row in failed[:15]
        ],
    }
    return payload


def _build_liquid_universe_markdown(payload: dict[str, Any]) -> str:
    counts = payload.get("counts") or {}
    health = payload.get("provider_health") or {}
    lines = [
        "# Liquid Universe Build",
        "",
        f"- Provider: {payload.get('provider')}",
        f"- Partial: {payload.get('partial')}",
        f"- Message: {payload.get('message')}",
        f"- Raw symbols: {counts.get('raw_symbols', 0)}",
        f"- Eligible candidates: {counts.get('eligible_candidates', 0)}",
        f"- Final universe size: {counts.get('final_universe_size', 0)}",
        f"- Passed liquidity filters: {counts.get('passed_liquidity_filters', 0)}",
        f"- Failed symbols: {counts.get('failed_symbols', 0)}",
        f"- Cache hits: {counts.get('cache_hits', 0)}",
        f"- Cache misses: {counts.get('cache_misses', 0)}",
        f"- Provider health: {health.get('status', 'unknown')}",
        "",
        "## Exclusions",
        "",
        f"- ETFs: {counts.get('excluded_etfs', 0)}",
        f"- Funds: {counts.get('excluded_funds', 0)}",
        f"- Warrants: {counts.get('excluded_warrants', 0)}",
        f"- Rights: {counts.get('excluded_rights', 0)}",
        f"- Units: {counts.get('excluded_units', 0)}",
        f"- Preferreds: {counts.get('excluded_preferreds', 0)}",
        "",
    ]
    for item in payload.get("failed_symbols_sample", []):
        lines.append(f"- Failed sample: {item.get('symbol')} -> {item.get('status')} ({item.get('reason')})")
    return "\n".join(lines).strip()


def _build_market_provider(
    *,
    provider_name: str,
    analysis_date: date,
    history_period: str,
    data_dir: Path | None,
    refresh_cache: bool,
) -> Any:
    from .cli import build_provider

    provider = build_provider(
        args=SimpleNamespace(
            provider=provider_name,
            history_period=history_period,
            data_dir=data_dir,
        ),
        analysis_date=analysis_date,
    )
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
    return provider


def _normalize_symbols(values: list[str] | Any) -> list[str]:
    rows: list[str] = []
    for value in values:
        symbol = display_ticker(str(value or "").strip())
        if not symbol or symbol.startswith("#") or symbol in rows:
            continue
        rows.append(symbol)
    return rows


def _otherlisted_exchange_name(code: str) -> str:
    mapping = {
        "A": "NYSE American",
        "N": "NYSE",
        "P": "NYSE Arca",
        "Q": "NASDAQ",
        "V": "IEX",
        "Z": "Cboe",
    }
    return mapping.get(code.upper(), code.upper() or "OTHER")


def _average(values: list[float]) -> float:
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else 0.0


def _truthy(value: Any, *, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _utcnow() -> str:
    return datetime.utcnow().isoformat() + "Z"
