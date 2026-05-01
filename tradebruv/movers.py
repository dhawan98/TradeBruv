from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from .cli import build_provider
from .discovery import collect_prepared_tickers
from .market_cache import DEFAULT_MARKET_CACHE_DIR, FileCacheMarketDataProvider
from .market_reliability import ResilientMarketDataProvider
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
    if scanner_override is None:
        args = SimpleNamespace(provider=provider_name, data_dir=data_dir, history_period=history_period)
        provider = provider_override or build_provider(args=args, analysis_date=analysis_date)
        if provider_name == "real" and not isinstance(provider, ResilientMarketDataProvider):
            provider = ResilientMarketDataProvider(provider, provider_name=provider_name, history_period=history_period)
        provider = FileCacheMarketDataProvider(
            provider,
            provider_name=provider_name,
            history_period=history_period,
            cache_dir=DEFAULT_MARKET_CACHE_DIR,
            refresh_cache=refresh_cache,
        )
        provider_override = provider
        scanner_override = DeterministicScanner(provider=provider, analysis_date=analysis_date)
    del batch_size
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
        progress=progress,
    )
    failures = list(prepared_payload["failures"])
    if not continue_on_ticker_failure and failures:
        failures = failures[:1]
    final_rows = []
    for item in prepared_payload["prepared"]:
        mover = _build_mover_row(
            item.discovery,
            min_price=min_price,
            min_dollar_volume=min_dollar_volume,
            min_average_volume=min_average_volume,
            include_speculative=include_speculative,
        )
        if mover is not None:
            final_rows.append(mover)
    tickers = _normalize_tickers(universe)
    payload = {
        "available": True,
        "generated_at": prepared_payload["generated_at"],
        "provider": provider_name,
        "analysis_date": analysis_date.isoformat(),
        "universe_size": len(tickers),
        "skipped_tickers": max(len(tickers) - (len(prepared_payload["prepared"]) + len(failures)), 0),
        "tickers_attempted": len(tickers),
        "tickers_successfully_scanned": len(prepared_payload["prepared"]),
        "scan_failures": failures,
        "provider_health": prepared_payload["provider_health"],
        "benchmark_health": {},
        "benchmark_warnings": [],
        "cache": prepared_payload["cache"],
        "results": final_rows,
        "top_gainers": _top(final_rows, key="percent_change", reverse=True, limit=top_n, predicate=lambda row: float(row.get("percent_change") or 0) > 0),
        "top_losers": _top(final_rows, key="percent_change", reverse=False, limit=top_n, predicate=lambda row: float(row.get("percent_change") or 0) < 0),
        "unusual_volume": _top(final_rows, key="relative_volume", reverse=True, limit=top_n, predicate=lambda row: float(row.get("relative_volume") or 0) >= 1.5),
        "relative_volume_leaders": _top(final_rows, key="relative_volume", reverse=True, limit=top_n),
        "high_relative_volume": _top(final_rows, key="relative_volume", reverse=True, limit=top_n, predicate=lambda row: float(row.get("relative_volume") or 0) >= 2.0),
        "highest_dollar_volume": _top(final_rows, key="dollar_volume", reverse=True, limit=top_n),
        "gap_up": _top(final_rows, key="percent_change", reverse=True, limit=top_n, predicate=lambda row: bool(row.get("gap_up"))),
        "gap_down": _top(final_rows, key="percent_change", reverse=False, limit=top_n, predicate=lambda row: bool(row.get("gap_down"))),
        "breakout_volume": _top(final_rows, key="relative_volume", reverse=True, limit=top_n, predicate=lambda row: bool(row.get("breakout_with_volume"))),
        "distribution_heavy_selling": _top(final_rows, key="relative_volume", reverse=True, limit=top_n, predicate=lambda row: bool(row.get("distribution_or_heavy_selling"))),
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
    min_price: float,
    min_dollar_volume: float,
    min_average_volume: float,
    include_speculative: bool,
) -> dict[str, Any] | None:
    price = float(row.get("current_price") or 0.0)
    avg_volume_20d = float(row.get("average_volume_20d") or 0.0)
    latest_volume = float(row.get("volume") or 0.0)
    relative_volume = float(row.get("relative_volume") or 0.0)
    dollar_volume = float(row.get("dollar_volume") or 0.0)
    if not include_speculative and (price < min_price or dollar_volume < min_dollar_volume or avg_volume_20d < min_average_volume):
        return None
    percent_change = float(row.get("percent_change") or 0.0)
    mover_categories: list[str] = []
    if percent_change > 0:
        mover_categories.append("Top Gainers")
    if percent_change < 0:
        mover_categories.append("Top Losers")
    if relative_volume >= 1.5:
        mover_categories.append("Unusual Volume")
    if relative_volume >= 2.0:
        mover_categories.append("Relative Volume Leaders")
    if bool(row.get("breakout_with_volume")):
        mover_categories.append("Breakout with Volume")
    if bool(row.get("gap_up")):
        mover_categories.append("Gap Up")
    if bool(row.get("gap_down")):
        mover_categories.append("Gap Down")
    if bool(row.get("new_52_week_high")):
        mover_categories.append("New 52W High")
    if bool(row.get("distribution_or_heavy_selling")):
        mover_categories.append("Distribution / Heavy Selling")
    return {
        "ticker": row.get("ticker"),
        "company": row.get("company") or row.get("ticker"),
        "price": round(price, 2),
        "percent_change": round(percent_change, 2),
        "volume": round(latest_volume, 2),
        "average_volume_20d": round(avg_volume_20d, 2),
        "relative_volume": round(relative_volume, 2),
        "dollar_volume": round(dollar_volume, 2),
        "market_cap": row.get("market_cap"),
        "mover_type": mover_categories[0] if mover_categories else "No Clean Signal",
        "mover_categories": mover_categories,
        "signal": row.get("signal_summary"),
        "risk": row.get("risk_level"),
        "source_provider": row.get("decision", {}).get("price_source") or "unavailable",
        "freshness": row.get("freshness") or "unavailable",
        **row,
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
        clean = str(ticker or "").strip().upper()
        if clean and clean not in output:
            output.append(clean)
    return output


def _write_movers_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ticker", "company", "price", "percent_change", "relative_volume", "dollar_volume", "signal", "actionability_label", "risk", "mover_type"],
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
    for section, title in (
        ("top_gainers", "Top Gainers"),
        ("top_losers", "Top Losers"),
        ("unusual_volume", "Unusual Volume"),
        ("highest_dollar_volume", "Highest Dollar Volume"),
        ("gap_up", "Gap Up"),
        ("gap_down", "Gap Down"),
        ("breakout_volume", "Breakout with Volume"),
        ("distribution_heavy_selling", "Distribution / Heavy Selling"),
    ):
        lines.append(f"## {title}")
        rows = payload.get(section, [])
        if rows:
            lines.extend(
                f"- {row.get('ticker')}: {row.get('percent_change')}% | RV {row.get('relative_volume')} | {row.get('signal')} | {row.get('actionability_label')}"
                for row in rows[:10]
            )
        else:
            lines.append("- None.")
        lines.append("")
    return "\n".join(lines).strip()
