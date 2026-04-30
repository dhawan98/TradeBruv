from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from .cli import build_provider
from .decision_engine import build_unified_decisions, build_validation_context
from .market_cache import DEFAULT_MARKET_CACHE_DIR, FileCacheMarketDataProvider
from .market_reliability import ResilientMarketDataProvider
from .price_sanity import build_price_sanity_from_row
from .scanner import DeterministicScanner
from .tracked import DEFAULT_TRACKED_TICKERS_PATH, list_tracked_tickers


DEFAULT_BROAD_SCAN_OUTPUT_DIR = Path("outputs/broad_scan")


@dataclass(frozen=True)
class BroadScanResult:
    payload: dict[str, Any]
    json_path: Path
    csv_path: Path
    markdown_path: Path


def run_broad_scan(
    *,
    universe: list[str],
    provider_name: str,
    analysis_date: date,
    history_period: str = "3y",
    data_dir: Path | None = None,
    limit: int = 0,
    batch_size: int = 25,
    top_n: int = 25,
    tracked_path: Path = DEFAULT_TRACKED_TICKERS_PATH,
    output_dir: Path = DEFAULT_BROAD_SCAN_OUTPUT_DIR,
    refresh_cache: bool = False,
    progress: Callable[[str], None] | None = None,
) -> BroadScanResult:
    args = type(
        "BroadScanArgs",
        (),
        {
            "provider": provider_name,
            "data_dir": data_dir,
            "history_period": history_period,
        },
    )()
    provider = build_provider(args=args, analysis_date=analysis_date)
    provider = ResilientMarketDataProvider(provider, provider_name=provider_name, history_period=history_period) if provider_name == "real" else provider
    provider = FileCacheMarketDataProvider(
        provider,
        provider_name=provider_name,
        history_period=history_period,
        cache_dir=DEFAULT_MARKET_CACHE_DIR,
        refresh_cache=refresh_cache,
    )
    scanner = DeterministicScanner(provider=provider, analysis_date=analysis_date)

    tickers = _normalize_tickers(universe)
    if limit:
        tickers = tickers[:limit]
    rows: list[dict[str, Any]] = []
    failed_rows: list[dict[str, Any]] = []
    provider_health: dict[str, Any] = {"provider": provider_name, "status": "healthy"}
    attempted = 0
    aborted_tickers: list[str] = []
    for start in range(0, len(tickers), batch_size):
        batch = tickers[start : start + batch_size]
        if progress:
            progress(f"Scanning batch {start // batch_size + 1} of {(len(tickers) + batch_size - 1) // batch_size}: {', '.join(batch[:3])}{'...' if len(batch) > 3 else ''}")
        diagnostics = scanner.scan_with_diagnostics(batch, mode="outliers", include_failures_in_results=False)
        attempted += diagnostics.attempted
        provider_health = diagnostics.provider_health
        aborted_tickers.extend(diagnostics.aborted_tickers)
        rows.extend(result.to_dict() | {"scan_source_group": "Broad"} for result in diagnostics.results)
        failed_rows.extend(diagnostics.failures)
        if diagnostics.aborted_tickers:
            failed_rows.extend(
                {"ticker": ticker, "reason": provider_health.get("stop_reason") or "Scan aborted after provider failure.", "category": provider_health.get("status", "unavailable")}
                for ticker in diagnostics.aborted_tickers
            )
            break

    validation_context = build_validation_context()
    enriched_rows = [
        row | build_price_sanity_from_row(row, reference_date=analysis_date, scan_generated_at=datetime.utcnow().isoformat() + "Z")
        for row in rows
    ]
    decisions = build_unified_decisions(
        enriched_rows,
        scan_generated_at=datetime.utcnow().isoformat() + "Z",
        validation_context=validation_context,
        reference_date=analysis_date,
        preferred_lane="Outlier",
    )
    decisions_by_ticker = {str(row.get("ticker")): row for row in decisions}

    tracked = set(list_tracked_tickers(tracked_path))
    signal_rows = []
    for row in enriched_rows:
        decision = decisions_by_ticker.get(str(row.get("ticker")), {})
        signal_rows.append(
            {
                "ticker": row.get("ticker"),
                "source": "Tracked" if row.get("ticker") in tracked else "Broad",
                "price": row.get("current_price"),
                "price_change_1d_pct": row.get("price_change_1d_pct"),
                "signal": row.get("signal_summary"),
                "signal_grade": row.get("signal_grade"),
                "relative_volume_20d": row.get("relative_volume_20d"),
                "ema_stack": row.get("ema_stack"),
                "actionability_label": decision.get("actionability_label"),
                "actionability_score": decision.get("actionability_score"),
                "entry_or_trigger": decision.get("action_trigger") if decision.get("trigger_needed") else decision.get("entry_zone"),
                "stop": decision.get("stop_loss"),
                "tp1": decision.get("tp1"),
                "risk": decision.get("risk_level"),
                "updated": row.get("last_market_date"),
            }
        )

    ranked = sorted(
        decisions,
        key=lambda row: (
            -float(row.get("actionability_score") or 0),
            -_signal_rank(next((signal.get("signal_grade") for signal in signal_rows if signal["ticker"] == row.get("ticker")), "F")),
            -float(row.get("regular_investing_score") or row.get("score") or 0),
            -float(row.get("source_row", {}).get("winner_score") or 0),
            -float(row.get("source_row", {}).get("outlier_score") or 0),
            -float(row.get("source_row", {}).get("velocity_score") or 0),
            str(row.get("ticker")),
        ),
    )
    buy_research = [row for row in ranked if row.get("primary_action") == "Research / Buy Candidate"][:top_n]
    watch = [row for row in ranked if row.get("primary_action") == "Watch"][:top_n]
    avoid = [row for row in ranked if row.get("primary_action") == "Avoid"][:top_n]
    top_signal_rows = sorted(signal_rows, key=lambda row: (-_signal_rank(str(row.get("signal_grade"))), -float(row.get("actionability_score") or 0), str(row.get("ticker"))))[:top_n]

    tracked_opportunities = [
        row for row in ranked if row.get("ticker") in tracked and row.get("price_validation_status") == "PASS"
    ][:top_n]
    best_tracked = tracked_opportunities[0] if tracked_opportunities else None
    best_broad = next(
        (row for row in ranked if row.get("ticker") not in tracked and row.get("price_validation_status") == "PASS"),
        None,
    )
    payload = {
        "available": True,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "provider": provider_name,
        "analysis_date": analysis_date.isoformat(),
        "universe_size": len(universe),
        "tickers_attempted": attempted or len(tickers),
        "successfully_scanned": len(enriched_rows),
        "failed_tickers": failed_rows,
        "scan_failures": failed_rows,
        "provider_health": provider_health,
        "scan_incomplete": bool(provider_health.get("stop_scan")),
        "scan_health_message": provider_health.get("stop_reason") or provider_health.get("message") or "",
        "aborted_tickers": aborted_tickers,
        "cache": provider.cache_stats(),
        "results": enriched_rows,
        "decisions": ranked[:top_n],
        "top_buy_research_candidates": buy_research,
        "top_watch_names": watch,
        "top_avoid_names": avoid,
        "top_ema_volume_signals": top_signal_rows,
        "top_tracked_ticker_opportunities": tracked_opportunities[:5],
        "best_tracked_setup": best_tracked,
        "best_broad_setup": best_broad,
        "tracked_ticker_outranks_broad": bool(
            best_tracked
            and best_broad
            and float(best_tracked.get("actionability_score") or 0) >= float(best_broad.get("actionability_score") or 0)
        ),
        "signal_table": signal_rows[: max(top_n, 25)],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "broad_scan_results.json"
    csv_path = output_dir / "broad_scan_top.csv"
    markdown_path = output_dir / "broad_scan_summary.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_top_csv(csv_path, buy_research, signal_rows)
    markdown_path.write_text(_build_summary_markdown(payload), encoding="utf-8")
    return BroadScanResult(payload=payload, json_path=json_path, csv_path=csv_path, markdown_path=markdown_path)


def _normalize_tickers(tickers: Iterable[str]) -> list[str]:
    output: list[str] = []
    for ticker in tickers:
        clean = ticker.strip().upper()
        if clean and clean not in output:
            output.append(clean)
    return output


def _signal_rank(grade: str) -> int:
    mapping = {"A": 5, "A-": 5, "B+": 4, "B": 4, "C": 3, "C-": 2, "D": 1, "F": 0}
    return mapping.get(grade, 0)


def _write_top_csv(path: Path, decisions: list[dict[str, Any]], signal_rows: list[dict[str, Any]]) -> None:
    signal_by_ticker = {str(row["ticker"]): row for row in signal_rows}
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ticker",
                "actionability_label",
                "actionability_score",
                "primary_action",
                "signal",
                "signal_grade",
                "relative_volume_20d",
                "ema_stack",
                "entry_or_trigger",
                "stop",
                "tp1",
            ],
        )
        writer.writeheader()
        for decision in decisions:
            signal = signal_by_ticker.get(str(decision.get("ticker")), {})
            writer.writerow(
                {
                    "ticker": decision.get("ticker"),
                    "actionability_label": decision.get("actionability_label"),
                    "actionability_score": decision.get("actionability_score"),
                    "primary_action": decision.get("primary_action"),
                    "signal": signal.get("signal"),
                    "signal_grade": signal.get("signal_grade"),
                    "relative_volume_20d": signal.get("relative_volume_20d"),
                    "ema_stack": signal.get("ema_stack"),
                    "entry_or_trigger": decision.get("action_trigger") if decision.get("trigger_needed") else decision.get("entry_zone"),
                    "stop": decision.get("stop_loss"),
                    "tp1": decision.get("tp1"),
                }
            )


def _build_summary_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Broad Scan Summary",
        "",
        f"- Universe size: {payload.get('universe_size')}",
        f"- Tickers attempted: {payload.get('tickers_attempted')}",
        f"- Successfully scanned: {payload.get('successfully_scanned')}",
        f"- Failed tickers: {len(payload.get('failed_tickers', []))}",
        f"- Provider: {payload.get('provider')}",
        f"- Provider health: {payload.get('provider_health', {}).get('status', 'unknown')}",
        f"- Cache hits / misses: {payload.get('cache', {}).get('hits', 0)} / {payload.get('cache', {}).get('misses', 0)}",
        "",
    ]
    if payload.get("scan_incomplete"):
        lines.extend(
            [
                "## Scan Health",
                "",
                f"- {payload.get('scan_health_message') or 'Provider scan stopped early.'}",
                "",
            ]
        )
    lines.extend(
        [
        "## Top Buy / Research Candidates",
        ]
    )
    top_buy = payload.get("top_buy_research_candidates", [])
    if top_buy:
        lines.extend(
            f"- {row.get('ticker')}: {row.get('actionability_label')} ({row.get('actionability_score')}) | {row.get('reason')}"
            for row in top_buy[:10]
        )
    else:
        lines.append("- None.")
    lines.extend(["", "## Top Watch Names"])
    watch = payload.get("top_watch_names", [])
    if watch:
        lines.extend(
            f"- {row.get('ticker')}: {row.get('actionability_label')} | {row.get('action_trigger')}"
            for row in watch[:10]
        )
    else:
        lines.append("- None.")
    lines.extend(["", "## Top Avoid / Do Not Chase"])
    avoid = payload.get("top_avoid_names", [])
    if avoid:
        lines.extend(
            f"- {row.get('ticker')}: {row.get('why_not') or row.get('reason')}"
            for row in avoid[:10]
        )
    else:
        lines.append("- None.")
    lines.extend(["", "## Top EMA / Volume Signals"])
    signals = payload.get("top_ema_volume_signals", [])
    if signals:
        lines.extend(
            f"- {row.get('ticker')}: {row.get('signal')} ({row.get('signal_grade')}) | rel vol {row.get('relative_volume_20d')}"
            for row in signals[:10]
        )
    else:
        lines.append("- None.")
    lines.extend(["", "## Tracked Ticker Opportunities"])
    tracked = payload.get("top_tracked_ticker_opportunities", [])
    if tracked:
        lines.extend(
            f"- {row.get('ticker')}: {row.get('actionability_label')} ({row.get('actionability_score')})"
            for row in tracked[:5]
        )
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            f"Tracked ticker outranks broad-market names: {payload.get('tracked_ticker_outranks_broad')}",
        ]
    )
    return "\n".join(lines)
