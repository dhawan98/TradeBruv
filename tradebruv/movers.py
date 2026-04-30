from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from .cli import build_provider
from .decision_engine import build_unified_decisions, build_validation_context
from .indicators import average
from .market_cache import DEFAULT_MARKET_CACHE_DIR, FileCacheMarketDataProvider
from .market_reliability import ResilientMarketDataProvider
from .price_sanity import build_price_sanity_from_row
from .scanner import DeterministicScanner


DEFAULT_MOVERS_OUTPUT_DIR = Path("outputs/movers")


@dataclass(frozen=True)
class MoversResult:
    payload: dict[str, Any]
    json_path: Path
    csv_path: Path
    markdown_path: Path


def run_movers_scan(
    *,
    universe: list[str],
    provider_name: str,
    analysis_date: date,
    history_period: str = "3y",
    data_dir: Path | None = None,
    top_n: int = 25,
    min_price: float = 5.0,
    min_dollar_volume: float = 20_000_000.0,
    min_average_volume: float = 500_000.0,
    include_speculative: bool = False,
    output_dir: Path = DEFAULT_MOVERS_OUTPUT_DIR,
    refresh_cache: bool = False,
    progress: Callable[[str], None] | None = None,
    continue_on_ticker_failure: bool = True,
    batch_size: int = 25,
    scanner_override: DeterministicScanner | None = None,
    provider_override: Any | None = None,
) -> MoversResult:
    if scanner_override is not None:
        scanner = scanner_override
        provider = provider_override or scanner.provider
    else:
        args = SimpleNamespace(provider=provider_name, data_dir=data_dir, history_period=history_period)
        provider = provider_override or build_provider(args=args, analysis_date=analysis_date)
        provider = ResilientMarketDataProvider(provider, provider_name=provider_name, history_period=history_period) if provider_name == "real" and not isinstance(provider, ResilientMarketDataProvider) else provider
        provider = FileCacheMarketDataProvider(
            provider,
            provider_name=provider_name,
            history_period=history_period,
            cache_dir=DEFAULT_MARKET_CACHE_DIR,
            refresh_cache=refresh_cache,
        )
        scanner = DeterministicScanner(provider=provider, analysis_date=analysis_date)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    tickers = _normalize_tickers(universe)
    prefetch = getattr(provider, "prefetch_many", None)
    if callable(prefetch):
        try:
            prefetch(tickers, batch_size=batch_size)
        except Exception:
            pass
    for index, ticker in enumerate(tickers, start=1):
        try:
            security = scanner._get_data(ticker)
            row = scanner._scan_security(security).to_dict()
            mover = _build_mover_row(row, security=security, min_price=min_price, min_dollar_volume=min_dollar_volume, min_average_volume=min_average_volume, include_speculative=include_speculative)
            if mover is not None:
                results.append(mover)
            if progress:
                progress(f"Movers {index}/{len(tickers)}: {ticker}")
        except Exception as exc:
            failures.append({"ticker": ticker, "reason": str(exc), "category": getattr(exc, "category", getattr(exc, "status", "fetch_error"))})
            if not continue_on_ticker_failure and not bool(getattr(provider, "should_stop_scan", lambda: False)()):
                break
            if bool(getattr(provider, "should_stop_scan", lambda: False)()):
                failures.extend(
                    {"ticker": remaining, "reason": getattr(provider, "health_report", lambda: {})().get("stop_reason") or "Provider stopped the scan.", "category": getattr(provider, "health_report", lambda: {})().get("status", "unavailable")}
                    for remaining in tickers[index:]
                )
                break

    enriched = [
        row | build_price_sanity_from_row(row, reference_date=analysis_date, scan_generated_at=datetime.utcnow().isoformat() + "Z")
        for row in results
    ]
    decisions = build_unified_decisions(
        enriched,
        scan_generated_at=datetime.utcnow().isoformat() + "Z",
        validation_context=build_validation_context(),
        reference_date=analysis_date,
        preferred_lane="Outlier",
    )
    decisions_by_ticker = {str(row.get("ticker")): row for row in decisions}
    final_rows = [
        mover | _decision_slice(decisions_by_ticker.get(str(mover.get("ticker")), {}))
        for mover in enriched
    ]
    payload = {
        "available": True,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "provider": provider_name,
        "analysis_date": analysis_date.isoformat(),
        "universe_size": len(universe),
        "skipped_tickers": max(len(tickers) - (len(results) + len(failures)), 0),
        "tickers_attempted": len(results) + len(failures),
        "tickers_successfully_scanned": len(results),
        "scan_failures": failures,
        "provider_health": getattr(provider, "health_report", lambda: {"provider": provider_name, "status": "healthy"})(),
        "cache": provider.cache_stats(),
        "results": final_rows,
        "top_gainers": _top(final_rows, key="percent_change", reverse=True, limit=top_n, predicate=lambda row: float(row.get("percent_change") or 0) > 0),
        "top_losers": _top(final_rows, key="percent_change", reverse=False, limit=top_n, predicate=lambda row: float(row.get("percent_change") or 0) < 0),
        "unusual_volume": _top(final_rows, key="relative_volume", reverse=True, limit=top_n, predicate=lambda row: float(row.get("relative_volume") or 0) >= 1.5),
        "relative_volume_leaders": _top(final_rows, key="relative_volume", reverse=True, limit=top_n),
        "high_relative_volume": _top(final_rows, key="relative_volume", reverse=True, limit=top_n, predicate=lambda row: float(row.get("relative_volume") or 0) >= 2.0),
        "breakout_volume": _top(final_rows, key="relative_volume", reverse=True, limit=top_n, predicate=lambda row: str(row.get("signal")) == "Breakout with Volume"),
        "tracked_signals": [],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "movers.json"
    csv_path = output_dir / "movers.csv"
    markdown_path = output_dir / "movers.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_movers_csv(csv_path, final_rows[:top_n])
    markdown_path.write_text(_build_movers_markdown(payload), encoding="utf-8")
    return MoversResult(payload=payload, json_path=json_path, csv_path=csv_path, markdown_path=markdown_path)


def _build_mover_row(
    row: dict[str, Any],
    *,
    security: Any,
    min_price: float,
    min_dollar_volume: float,
    min_average_volume: float,
    include_speculative: bool,
) -> dict[str, Any] | None:
    bars = list(security.bars)
    if len(bars) < 21:
        return None
    price = float(security.quote_price_if_available or security.latest_available_close or bars[-1].close or 0.0)
    avg_volume_20d = average([bar.volume for bar in bars[-20:]]) or 0.0
    latest_volume = float(bars[-1].volume or 0.0)
    relative_volume = round((latest_volume / avg_volume_20d), 2) if avg_volume_20d else 0.0
    dollar_volume = round(price * latest_volume, 2)
    if not include_speculative and (price < min_price or dollar_volume < min_dollar_volume or avg_volume_20d < min_average_volume):
        return None
    closes = [bar.close for bar in bars]
    recent_20d_high = max(closes[-20:])
    recent_52w_high = max(closes[-252:]) if len(closes) >= 252 else max(closes)
    percent_change = float(row.get("price_change_1d_pct") or 0.0)
    mover_categories: list[str] = []
    if percent_change > 0:
        mover_categories.append("Top Gainers")
    if percent_change < 0:
        mover_categories.append("Top Losers")
    if relative_volume >= 1.5:
        mover_categories.append("Unusual Volume")
    if relative_volume >= 2.0:
        mover_categories.append("Relative Volume Leaders")
    if str(row.get("signal_summary")) == "Breakout with Volume":
        mover_categories.append("Breakout with Volume")
    if bool(row.get("gap_up")):
        mover_categories.append("Gap Up")
    if bool(row.get("gap_down")):
        mover_categories.append("Gap Down")
    if price >= recent_20d_high:
        mover_categories.append("New 20D High")
    if price >= recent_52w_high:
        mover_categories.append("New 52W High")
    if bool(row.get("reclaim_ema_21")) or bool(row.get("reclaim_ema_50")):
        mover_categories.append("Reclaim EMA 21/50")
    if bool(row.get("distribution_warning")) or str(row.get("distribution_signal")) == "Distribution Warning":
        mover_categories.append("Distribution / Heavy Selling")
    return {
        "ticker": row.get("ticker"),
        "company": security.company_name or row.get("company_name") or row.get("ticker"),
        "price": round(price, 2),
        "percent_change": round(percent_change, 2),
        "volume": round(latest_volume, 2),
        "average_volume_20d": round(avg_volume_20d, 2),
        "relative_volume": relative_volume,
        "dollar_volume": dollar_volume,
        "market_cap": security.market_cap,
        "mover_type": mover_categories[0] if mover_categories else "No Clean Signal",
        "mover_categories": mover_categories,
        "signal": row.get("signal_summary"),
        "risk": row.get("outlier_risk") or row.get("risk_level") or row.get("investing_risk"),
        "source_provider": security.provider_name,
        "freshness": security.last_market_date.isoformat() if security.last_market_date else "unavailable",
        **row,
    }


def _decision_slice(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "actionability": decision.get("actionability_label"),
        "actionability_score": decision.get("actionability_score"),
        "entry_or_trigger": decision.get("action_trigger") if decision.get("trigger_needed") else decision.get("entry_zone"),
        "stop": decision.get("stop_loss"),
        "tp1": decision.get("tp1"),
        "tp2": decision.get("tp2"),
        "risk": decision.get("risk_level"),
    }


def _top(
    rows: list[dict[str, Any]],
    *,
    key: str,
    reverse: bool,
    limit: int,
    predicate: Callable[[dict[str, Any]], bool] | None = None,
) -> list[dict[str, Any]]:
    filtered = [row for row in rows if predicate(row)] if predicate else list(rows)
    return sorted(filtered, key=lambda row: float(row.get(key) or 0), reverse=reverse)[:limit]


def _normalize_tickers(tickers: list[str]) -> list[str]:
    output: list[str] = []
    for ticker in tickers:
        clean = ticker.strip().upper()
        if clean and clean not in output:
            output.append(clean)
    return output


def _write_movers_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ticker", "company", "price", "percent_change", "relative_volume", "dollar_volume", "signal", "actionability", "risk", "mover_type"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in writer.fieldnames})


def _build_movers_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Movers Scan",
        "",
        f"- Provider: {payload.get('provider')}",
        f"- Coverage: {payload.get('tickers_successfully_scanned')}/{payload.get('tickers_attempted')} scanned",
        f"- Failed tickers: {len(payload.get('scan_failures', []))}",
        f"- Skipped tickers: {payload.get('skipped_tickers', 0)}",
        f"- Provider health: {payload.get('provider_health', {}).get('status', 'unknown')}",
        "",
    ]
    if payload.get("provider_health", {}).get("stop_scan"):
        lines.extend(["## Scan Health", "", f"- Stopped after {payload.get('tickers_attempted')} symbols because {payload.get('provider_health', {}).get('stop_reason', 'the provider halted the scan.')}", ""])
    lines.append("## Top Gainers")
    for section, title in (
        ("top_gainers", "Top Gainers"),
        ("top_losers", "Top Losers"),
        ("unusual_volume", "Unusual Volume"),
        ("breakout_volume", "Breakout with Volume"),
    ):
        if title != "Top Gainers":
            lines.extend(["", f"## {title}"])
        rows = payload.get(section, [])
        if rows:
            lines.extend(
                f"- {row.get('ticker')}: {row.get('percent_change')}% | RV {row.get('relative_volume')} | {row.get('signal')}"
                for row in rows[:10]
            )
        else:
            lines.append("- None.")
    return "\n".join(lines)
