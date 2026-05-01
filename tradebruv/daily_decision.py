from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alternative_data import DEFAULT_ALTERNATIVE_DATA_PATH, AlternativeDataOverlayProvider, load_alternative_data_repository
from .catalysts import CatalystOverlayProvider, load_catalyst_repository
from .cli import build_provider, load_universe
from .dashboard_data import (
    build_daily_summary,
    load_dashboard_portfolio,
    run_dashboard_scan,
)
from .decision_merge import merge_canonical_rows
from .decision_engine import build_unified_decisions, build_validation_context
from .market_cache import DEFAULT_MARKET_CACHE_DIR, FileCacheMarketDataProvider
from .market_reliability import ResilientMarketDataProvider
from .movers import run_movers_scan
from .price_sanity import build_price_sanity_from_row
from .providers import MarketDataProvider
from .scanner import DeterministicScanner
from .tracked import DEFAULT_TRACKED_TICKERS_PATH, list_tracked_tickers
from .universe_registry import validate_universe_file

DEFAULT_DAILY_DECISION_OUTPUT_DIR = Path("outputs/daily")
DEFAULT_DAILY_DECISION_JSON_PATH = DEFAULT_DAILY_DECISION_OUTPUT_DIR / "decision_today.json"
DEFAULT_DAILY_DECISION_MD_PATH = DEFAULT_DAILY_DECISION_OUTPUT_DIR / "decision_today.md"


def run_daily_decision(
    *,
    provider_name: str,
    core_universe: Path,
    outlier_universe: Path,
    velocity_universe: Path,
    broad_universe: Path | None = None,
    tracked: Path | None = None,
    include_movers: bool = False,
    top_n: int = 25,
    history_period: str = "3y",
    data_dir: Path | None = None,
    refresh_cache: bool = False,
    analysis_date: date | None = None,
    output_dir: Path = DEFAULT_DAILY_DECISION_OUTPUT_DIR,
) -> dict[str, Any]:
    as_of = analysis_date or date.today()
    validation_context = build_validation_context()
    portfolio_rows = load_dashboard_portfolio()
    shared_provider, shared_scanner = _build_shared_scan_stack(
        provider_name=provider_name,
        analysis_date=as_of,
        history_period=history_period,
        data_dir=data_dir,
        refresh_cache=refresh_cache,
    )
    requested_ticker_groups: dict[str, list[str]] = {
        "Core Investing": load_universe(core_universe),
        "Outlier": load_universe(outlier_universe),
        "Velocity": load_universe(velocity_universe),
    }
    if broad_universe:
        requested_ticker_groups["Broad"] = load_universe(broad_universe)
    tracked_path = tracked or DEFAULT_TRACKED_TICKERS_PATH
    tracked_tickers = list_tracked_tickers(tracked_path)
    if tracked_tickers:
        requested_ticker_groups["Tracked"] = tracked_tickers
    portfolio_tickers = [str(row.get("ticker")).upper() for row in portfolio_rows if row.get("ticker")]
    if portfolio_tickers:
        requested_ticker_groups["Portfolio"] = portfolio_tickers
    unique_requested_tickers = _unique_tickers(
        ticker
        for tickers in requested_ticker_groups.values()
        for ticker in tickers
    )
    scans = [
        {
            "lane": "Core Investing",
            "source_group": "Core Investing",
            "scan": run_dashboard_scan(
                provider_name=provider_name,
                mode="investing",
                universe_path=core_universe,
                analysis_date=as_of,
                scanner_override=shared_scanner,
                provider_override=shared_provider,
            ),
            "universe": str(core_universe),
        },
        {
            "lane": "Outlier",
            "source_group": "Outlier",
            "scan": run_dashboard_scan(
                provider_name=provider_name,
                mode="outliers",
                universe_path=outlier_universe,
                analysis_date=as_of,
                scanner_override=shared_scanner,
                provider_override=shared_provider,
            ),
            "universe": str(outlier_universe),
        },
        {
            "lane": "Velocity",
            "source_group": "Velocity",
            "scan": run_dashboard_scan(
                provider_name=provider_name,
                mode="velocity",
                universe_path=velocity_universe,
                analysis_date=as_of,
                scanner_override=shared_scanner,
                provider_override=shared_provider,
            ),
            "universe": str(velocity_universe),
        },
    ]
    movers_payload: dict[str, Any] | None = None

    if broad_universe:
        scans.append(
            {
                "lane": "Outlier",
                "source_group": "Broad",
                "scan": _run_custom_scan(
                    tickers=load_universe(broad_universe),
                    provider_name=provider_name,
                    analysis_date=as_of,
                    history_period=history_period,
                    data_dir=data_dir,
                    refresh_cache=refresh_cache,
                    mode="outliers",
                    scanner_override=shared_scanner,
                    provider_override=shared_provider,
                ),
                "universe": str(broad_universe),
            }
        )
        if include_movers:
            movers_result = run_movers_scan(
                universe=load_universe(broad_universe),
                provider_name=provider_name,
                analysis_date=as_of,
                history_period=history_period,
                data_dir=data_dir,
                top_n=top_n,
                refresh_cache=refresh_cache,
                scanner_override=shared_scanner,
                provider_override=shared_provider,
            )
            movers_payload = movers_result.payload
            scans.append(
                {
                    "lane": "Outlier",
                    "source_group": "Movers",
                    "scan": SimpleNamespace(
                        generated_at=movers_result.payload["generated_at"],
                        provider=provider_name,
                        source="movers scan",
                        market_regime={},
                        results=movers_result.payload["results"],
                        scan_failures=movers_result.payload.get("scan_failures", []),
                        provider_health=movers_result.payload.get("provider_health", {}),
                        cache_stats=movers_result.payload.get("cache", {}),
                    ),
                    "universe": f"{broad_universe} movers",
                }
            )
    if tracked_tickers:
        scans.append(
            {
                "lane": "Outlier",
                "source_group": "Tracked",
                "scan": _run_custom_scan(
                    tickers=tracked_tickers,
                    provider_name=provider_name,
                    analysis_date=as_of,
                    history_period=history_period,
                    data_dir=data_dir,
                    refresh_cache=refresh_cache,
                    mode="outliers",
                    scanner_override=shared_scanner,
                    provider_override=shared_provider,
                ),
                "universe": str(tracked_path),
            }
        )
    if portfolio_tickers:
        scans.append(
            {
                "lane": "Outlier",
                "source_group": "Portfolio",
                "scan": _run_custom_scan(
                    tickers=portfolio_tickers,
                    provider_name=provider_name,
                    analysis_date=as_of,
                    history_period=history_period,
                    data_dir=data_dir,
                    refresh_cache=refresh_cache,
                    mode="outliers",
                    scanner_override=shared_scanner,
                    provider_override=shared_provider,
                ),
                "universe": "portfolio positions",
            }
        )

    combined_rows: list[dict[str, Any]] = []
    combined_decisions: list[dict[str, Any]] = []
    scan_failures: list[dict[str, Any]] = []
    scan_summaries: list[dict[str, Any]] = []
    coverage_attempted = 0
    coverage_success = 0
    coverage_failed = 0
    cache_stats: dict[str, Any] = {"hits": 0, "misses": 0, "ttl_minutes": "unavailable"}
    provider_health_rows: list[dict[str, Any]] = []
    for item in scans:
        lane = item["lane"]
        source_group = item["source_group"]
        scan = item["scan"]
        rows = [
            _enrich_row(
                row,
                generated_at=scan.generated_at,
                reference_date=as_of,
                extra={
                    "data_mode": "live_daily_decision",
                    "selected_provider": provider_name,
                    "provider_is_live_capable": provider_name == "real",
                    "decision_source_lane": lane,
                    "scan_source_group": source_group,
                    "report_snapshot_selected": False,
                    "is_report_only": False,
                },
            )
            for row in scan.results
        ]
        decisions = build_unified_decisions(
            rows,
            portfolio_rows=portfolio_rows,
            scan_generated_at=scan.generated_at,
            validation_context=validation_context,
            reference_date=as_of,
            preferred_lane=lane,
        )
        combined_rows.extend(rows)
        combined_decisions.extend(decisions)
        item_failures = [
            dict(failure) | {"source_group": source_group, "lane": lane}
            for failure in (getattr(scan, "scan_failures", []) or [])
        ]
        coverage_attempted += len(rows) + len(item_failures)
        coverage_success += len(rows)
        coverage_failed += len(item_failures)
        scan_failures.extend(item_failures)
        if getattr(scan, "provider_health", None):
            provider_health_rows.append(scan.provider_health)
        if getattr(scan, "cache_stats", None):
            cache_stats["hits"] = int(cache_stats.get("hits", 0)) + int(scan.cache_stats.get("hits", 0))
            cache_stats["misses"] = int(cache_stats.get("misses", 0)) + int(scan.cache_stats.get("misses", 0))
            cache_stats["stale_hits"] = int(cache_stats.get("stale_hits", 0)) + int(scan.cache_stats.get("stale_hits", 0))
            cache_stats["fallback_hits"] = int(cache_stats.get("fallback_hits", 0)) + int(scan.cache_stats.get("fallback_hits", 0))
            if scan.cache_stats.get("ttl_minutes") not in (None, "unavailable"):
                cache_stats["ttl_minutes"] = scan.cache_stats.get("ttl_minutes")
        scan_summaries.append(
            {
                "lane": lane,
                "source_group": source_group,
                "generated_at": scan.generated_at,
                "provider": scan.provider,
                "source": scan.source,
                "universe": item["universe"],
                "result_count": len(rows),
                "market_regime": scan.market_regime,
                "scan_failures": item_failures,
                "provider_health": getattr(scan, "provider_health", {}),
            }
        )

    merged = merge_canonical_rows(combined_rows, combined_decisions)
    merged_rows = merged["canonical_rows"]
    merged_decisions = merged["canonical_decisions"]
    unique_scan_failures = _dedupe_scan_failures(scan_failures)
    data_issues = [decision for decision in merged_decisions if decision.get("price_validation_status") != "PASS"]
    picker_view = _build_picker_view(merged_decisions, data_issues=data_issues)
    broad_universe_status = validate_universe_file(broad_universe) if broad_universe else {
        "universe_label": "Tracked + Active",
        "universe_file": "active configured universes",
        "universe_row_count": 0,
        "expected_universe_size": 0,
        "coverage_percent": 100.0,
        "is_partial_universe": False,
        "universe_warning": "",
    }
    coverage_status = {
        "universe_scanned": [item["source_group"] for item in scans],
        "scan_groups": [
            {
                "source_group": item["source_group"],
                "lane": item["lane"],
                "universe": item["universe"],
                "result_count": len(item["scan"].results),
            }
            for item in scans
        ],
        "tickers_attempted": coverage_attempted,
        "tickers_successfully_scanned": coverage_success,
        "tickers_failed": len(unique_scan_failures),
        "failure_events": coverage_failed,
        "scan_failures": unique_scan_failures,
        "tracked_tickers_count": len(tracked_tickers),
        "portfolio_tickers_count": len(portfolio_tickers),
        "unique_candidate_tickers_requested": len(unique_requested_tickers),
        "unique_market_data_tickers_fetched": len([ticker for ticker in getattr(shared_scanner, "_cache", {}).keys() if ticker not in {"SPY", "QQQ"}]),
        "last_broad_scan_time": next((item["generated_at"] for item in scan_summaries if item["source_group"] == "Broad"), "not run"),
        "provider": provider_name,
        "cache_age_ttl_minutes": cache_stats.get("ttl_minutes", "unavailable"),
        "cache_hits": cache_stats.get("hits", 0),
        "cache_misses": cache_stats.get("misses", 0),
        "cache_stale_hits": cache_stats.get("stale_hits", 0),
        "cache_fallback_hits": cache_stats.get("fallback_hits", 0),
        "provider_health_rows": provider_health_rows,
        "provider_health": _overall_provider_health(provider_health_rows),
        **broad_universe_status,
    }
    workspace = _build_workspace_payload(
        merged_decisions,
        coverage_status=coverage_status,
        data_issues=data_issues,
        top_n=top_n,
    )
    payload = {
        "available": True,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "analysis_date": as_of.isoformat(),
        "provider": provider_name,
        "mode": "daily-decision",
        "data_mode": "live_daily_decision",
        "results": merged_rows,
        "summary": build_daily_summary(merged_rows),
        "decisions": merged_decisions,
        "data_issues": data_issues,
        "overall_top_candidate": picker_view["top_candidate"],
        "top_candidate": picker_view["top_candidate"],
        "best_tracked_setup": _best_from_source(merged_decisions, "Tracked"),
        "best_broad_setup": _best_from_source(merged_decisions, "Broad"),
        "best_mover_setup": _best_from_source(merged_decisions, "Movers"),
        "research_candidates": picker_view["research_candidates"],
        "watch_candidates": picker_view["watch_candidates"],
        "avoid_candidates": picker_view["avoid_candidates"],
        "portfolio_actions": picker_view["portfolio_actions"],
        "compact_board": picker_view["compact_board"],
        "tracked_watchlist_table": _compact_signal_table(merged_decisions, source_group="Tracked", limit=10),
        "broad_scan_top_table": _compact_signal_table(merged_decisions, source_group="Broad", limit=top_n),
        "movers_table": _compact_signal_table(merged_decisions, source_group="Movers", limit=top_n),
        "signal_table": _compact_signal_table(merged_decisions, source_group=None, limit=max(top_n, 25)),
        "no_clean_candidate_reason": picker_view["no_clean_candidate_reason"],
        "data_coverage_status": coverage_status,
        "scan_health": coverage_status.get("provider_health", {}),
        "scan_failures": unique_scan_failures,
        "validation_context": validation_context,
        "market_regime": _pick_market_regime(scan_summaries),
        "scans": scan_summaries,
        "demo_mode": provider_name == "sample",
        "report_snapshot": False,
        "stale_data": any(bool(decision.get("price_sanity", {}).get("is_stale")) for decision in merged_decisions),
        "workspace": workspace,
        "top_gainers": _daily_mover_rows(movers_payload, merged_decisions, section="top_gainers", limit=10),
        "top_losers": _daily_mover_rows(movers_payload, merged_decisions, section="top_losers", limit=10),
        "unusual_volume": _daily_mover_rows(movers_payload, merged_decisions, section="unusual_volume", limit=10),
        "breakout_volume": _daily_mover_rows(movers_payload, merged_decisions, section="breakout_volume", limit=10),
        "movers_scan_summary": _movers_scan_summary(movers_payload),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "decision_today.json"
    markdown_path = output_dir / "decision_today.md"
    quality_review_path = output_dir / "decision_quality_review.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(_build_daily_decision_markdown(payload), encoding="utf-8")
    quality_review_path.write_text(_build_decision_quality_review(payload), encoding="utf-8")
    payload["json_path"] = str(json_path)
    payload["markdown_path"] = str(markdown_path)
    payload["quality_review_path"] = str(quality_review_path)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_daily_decision(path: Path = DEFAULT_DAILY_DECISION_JSON_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "available": False,
            "generated_at": "unavailable",
            "provider": "unavailable",
            "mode": "daily-decision",
            "data_mode": "live_daily_decision",
            "results": [],
            "summary": {},
            "decisions": [],
            "data_issues": [],
            "top_candidate": None,
            "overall_top_candidate": None,
            "best_tracked_setup": None,
            "best_broad_setup": None,
            "best_mover_setup": None,
            "research_candidates": [],
            "watch_candidates": [],
            "avoid_candidates": [],
            "portfolio_actions": [],
            "compact_board": [],
            "tracked_watchlist_table": [],
            "broad_scan_top_table": [],
            "movers_table": [],
            "signal_table": [],
            "no_clean_candidate_reason": "No live daily decision has been built yet.",
            "data_coverage_status": {},
            "validation_context": build_validation_context(),
            "market_regime": {},
            "demo_mode": False,
            "report_snapshot": False,
            "stale_data": False,
            "workspace": {},
            "top_gainers": [],
            "top_losers": [],
            "unusual_volume": [],
            "breakout_volume": [],
            "movers_scan_summary": {},
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _enrich_row(
    row: dict[str, Any],
    *,
    generated_at: str,
    reference_date: date,
    extra: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(row) | extra
    enriched.update(
        build_price_sanity_from_row(
            enriched,
            reference_date=reference_date,
            scan_generated_at=generated_at,
        )
    )
    return enriched


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        existing = best.get(ticker)
        if existing is None or _row_rank(row) < _row_rank(existing):
            best[ticker] = row
    return sorted(best.values(), key=lambda row: (_row_rank(row), str(row.get("ticker"))))


def _dedupe_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        ticker = str(decision.get("ticker") or "").upper()
        if not ticker:
            continue
        existing = best.get(ticker)
        if existing is None or _decision_rank(decision) < _decision_rank(existing):
            best[ticker] = decision
    return sorted(best.values(), key=lambda row: (_decision_rank(row), str(row.get("ticker"))))


def _row_rank(row: dict[str, Any]) -> tuple[int, int, float]:
    status = _validation_order(str(row.get("price_validation_status") or row.get("price_sanity", {}).get("price_validation_status") or "FAIL"))
    source = _source_order(str(row.get("scan_source_group") or row.get("decision_source_lane") or ""))
    lane = _lane_order(str(row.get("decision_source_lane") or ""))
    score = -float(row.get("regular_investing_score") or row.get("outlier_score") or row.get("velocity_score") or 0)
    return (status, source, lane, score)


def _decision_rank(decision: dict[str, Any]) -> tuple[int, int, int, int, float]:
    status = _validation_order(str(decision.get("price_validation_status") or "FAIL"))
    source = _source_order(str(decision.get("source_group") or decision.get("action_lane") or ""))
    action = _action_order(str(decision.get("primary_action") or "Data Insufficient"))
    lane = _lane_order(str(decision.get("action_lane") or ""))
    score = -float(decision.get("score") or 0)
    return (status, source, action, lane, score)


def _validation_order(status: str) -> int:
    return {"PASS": 0, "WARN": 1, "FAIL": 2}.get(status, 3)


def _lane_order(lane: str) -> int:
    return {"Core Investing": 0, "Outlier": 1, "Velocity": 2}.get(lane, 3)


def _source_order(source: str) -> int:
    return {"Tracked": 0, "Portfolio": 1, "Broad": 2, "Core Investing": 3, "Outlier": 4, "Velocity": 5}.get(source, 6)


def _action_order(action: str) -> int:
    return {
        "Research / Buy Candidate": 0,
        "Add": 1,
        "Hold": 2,
        "Trim": 3,
        "Sell / Exit Candidate": 4,
        "Watch": 5,
        "Watch Closely": 6,
        "Avoid": 7,
        "Data Insufficient": 8,
    }.get(action, 9)


def _pick_market_regime(scan_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    for item in scan_summaries:
        regime = item.get("market_regime") or {}
        if regime:
            return regime
    return {}


def _universe_for_lane(
    lane: str,
    *,
    core_universe: Path,
    outlier_universe: Path,
    velocity_universe: Path,
) -> str:
    if lane == "Core Investing":
        return str(core_universe)
    if lane == "Outlier":
        return str(outlier_universe)
    return str(velocity_universe)


def _run_custom_scan(
    *,
    tickers: list[str],
    provider_name: str,
    analysis_date: date,
    history_period: str,
    data_dir: Path | None,
    refresh_cache: bool,
    mode: str,
    scanner_override: DeterministicScanner | None = None,
    provider_override: MarketDataProvider | None = None,
) -> SimpleNamespace:
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
    diagnostics = scanner.scan_with_diagnostics(tickers, mode=mode, include_failures_in_results=False)
    return SimpleNamespace(
        generated_at=datetime.utcnow().isoformat() + "Z",
        provider=provider_name,
        source=f"custom scan: {mode}",
        market_regime={},
        results=[result.to_dict() for result in diagnostics.results],
        scan_failures=diagnostics.failures + [
            {"ticker": ticker, "reason": diagnostics.provider_health.get("stop_reason") or "Scan aborted after provider failure.", "category": diagnostics.provider_health.get("status", "unavailable")}
            for ticker in diagnostics.aborted_tickers
        ],
        provider_health=diagnostics.provider_health,
        cache_stats=provider.cache_stats(),
    )


def _overall_provider_health(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"provider": "unavailable", "status": "healthy", "message": ""}
    for status in ("rate_limited", "unauthorized", "unavailable", "degraded"):
        match = next((row for row in rows if row.get("status") == status), None)
        if match:
            return match
    return rows[0]


def _build_shared_scan_stack(
    *,
    provider_name: str,
    analysis_date: date,
    history_period: str,
    data_dir: Path | None,
    refresh_cache: bool,
) -> tuple[MarketDataProvider, DeterministicScanner]:
    args = SimpleNamespace(provider=provider_name, data_dir=data_dir, history_period=history_period)
    provider: MarketDataProvider = build_provider(args=args, analysis_date=analysis_date)
    if provider_name == "real" and not isinstance(provider, ResilientMarketDataProvider):
        provider = ResilientMarketDataProvider(provider, provider_name=provider_name, history_period=history_period)
    catalyst_repository = load_catalyst_repository(None)
    if catalyst_repository.items_by_ticker:
        provider = CatalystOverlayProvider(provider, catalyst_repository)
    alternative_repository = load_alternative_data_repository(DEFAULT_ALTERNATIVE_DATA_PATH)
    if alternative_repository.items_by_ticker:
        provider = AlternativeDataOverlayProvider(provider, alternative_repository)
    provider = FileCacheMarketDataProvider(
        provider,
        provider_name=provider_name,
        history_period=history_period,
        cache_dir=DEFAULT_MARKET_CACHE_DIR,
        refresh_cache=refresh_cache,
    )
    return provider, DeterministicScanner(provider=provider, analysis_date=analysis_date)


def _unique_tickers(tickers: Any) -> list[str]:
    output: list[str] = []
    for ticker in tickers:
        clean = str(ticker or "").strip().upper()
        if clean and clean not in output:
            output.append(clean)
    return output


def _dedupe_scan_failures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        current = deduped.get(ticker)
        if current is None:
            deduped[ticker] = {
                "ticker": ticker,
                "reason": str(row.get("reason") or "Provider failure."),
                "category": str(row.get("category") or "fetch_error"),
                "source_groups": [str(row.get("source_group"))] if row.get("source_group") else [],
                "lanes": [str(row.get("lane"))] if row.get("lane") else [],
            }
            continue
        reasons = [part.strip() for part in str(current.get("reason") or "").split(" | ") if part.strip()]
        candidate_reason = str(row.get("reason") or "").strip()
        if candidate_reason and candidate_reason not in reasons:
            reasons.append(candidate_reason)
        current["reason"] = " | ".join(reasons[:3]) or "Provider failure."
        category = str(row.get("category") or current.get("category") or "fetch_error")
        current["category"] = _worse_failure_category(str(current.get("category") or ""), category)
        for field in ("source_groups", "lanes"):
            value = str(row.get("source_group" if field == "source_groups" else "lane") or "").strip()
            if value and value not in current[field]:
                current[field].append(value)
    return sorted(deduped.values(), key=lambda item: item["ticker"])


def _worse_failure_category(left: str, right: str) -> str:
    order = {"rate_limited": 0, "unauthorized": 1, "unavailable": 2, "degraded": 3, "fetch_error": 4}
    return left if order.get(left, 99) <= order.get(right, 99) else right


def _daily_mover_rows(
    movers_payload: dict[str, Any] | None,
    decisions: list[dict[str, Any]],
    *,
    section: str,
    limit: int,
) -> list[dict[str, Any]]:
    if not movers_payload:
        return []
    decisions_by_ticker = {str(row.get("ticker")): row for row in decisions}
    output: list[dict[str, Any]] = []
    for row in movers_payload.get(section, [])[:limit]:
        decision = decisions_by_ticker.get(str(row.get("ticker")), {})
        output.append(
            {
                "ticker": row.get("ticker"),
                "company": row.get("company"),
                "price": row.get("price"),
                "percent_change": row.get("percent_change"),
                "relative_volume": row.get("relative_volume"),
                "dollar_volume": row.get("dollar_volume"),
                "mover_type": row.get("mover_type"),
                "signal": row.get("signal"),
                "actionability": decision.get("actionability_label"),
                "actionability_score": decision.get("actionability_score"),
                "risk": decision.get("risk_level"),
                "freshness": row.get("freshness"),
            }
        )
    return output


def _best_from_source(decisions: list[dict[str, Any]], source_group: str) -> dict[str, Any] | None:
    rows = [row for row in decisions if _has_source_group(row, source_group) and row.get("price_validation_status") == "PASS"]
    return rows[0] if rows else None


def _compact_signal_table(decisions: list[dict[str, Any]], *, source_group: str | None, limit: int) -> list[dict[str, Any]]:
    rows = [row for row in decisions if source_group is None or _has_source_group(row, source_group)]
    table = []
    for row in rows[:limit]:
        table.append(
            {
                "ticker": row.get("ticker"),
                "source": " + ".join(row.get("source_groups") or [row.get("source_group")]),
                "price": row.get("source_row", {}).get("current_price"),
                "price_change_1d_pct": row.get("source_row", {}).get("price_change_1d_pct"),
                "price_change_5d_pct": row.get("source_row", {}).get("price_change_5d_pct"),
                "relative_volume_20d": row.get("source_row", {}).get("relative_volume_20d"),
                "ema_stack": row.get("source_row", {}).get("ema_stack"),
                "signal": row.get("source_row", {}).get("signal_summary"),
                "signal_explanation": row.get("source_row", {}).get("signal_explanation"),
                "actionability": row.get("actionability_label"),
                "risk": row.get("risk_level"),
                "entry_or_trigger": row.get("action_trigger") if row.get("trigger_needed") else row.get("entry_zone"),
                "stop": row.get("stop_loss"),
                "tp1": row.get("tp1"),
                "updated": row.get("latest_market_date"),
            }
        )
    return table


def _build_workspace_payload(
    decisions: list[dict[str, Any]],
    *,
    coverage_status: dict[str, Any],
    data_issues: list[dict[str, Any]],
    top_n: int,
) -> dict[str, Any]:
    picker_view = _build_picker_view(decisions, data_issues=data_issues)
    top_candidates = [row for row in decisions if row.get("actionability_label") in {"Actionable Today", "Research First"}][:8]
    tracked_rows = [row for row in decisions if _has_source_group(row, "Tracked")]
    broad_rows = [row for row in decisions if _has_source_group(row, "Broad")]
    mover_rows = [row for row in decisions if _has_source_group(row, "Movers")]
    watch_rows = [row for row in decisions if row.get("actionability_label") in {"Wait for Better Entry", "Watch for Trigger"}][:5]
    avoid_rows = [row for row in decisions if row.get("actionability_label") == "Avoid / Do Not Chase"][:5]
    selected_ticker = (
        (picker_view.get("top_candidate") or {}).get("ticker")
        or (_best_from_source(decisions, "Tracked") or {}).get("ticker")
        or (_best_from_source(decisions, "Broad") or {}).get("ticker")
        or (decisions[0] or {}).get("ticker")
        or ""
    )
    decision_by_ticker = {str(row.get("ticker")): row for row in decisions if row.get("ticker")}
    selected_decision = decision_by_ticker.get(str(selected_ticker))
    consistency_status = "PASS" if selected_decision else "FAIL"
    consistency_reason = (
        "Selected ticker is canonical and drives the workspace panels."
        if selected_decision
        else "Selected ticker was not found in canonical rows."
    )
    if selected_decision and selected_decision.get("price_validation_status") == "PASS":
        consistency_reason = "Selected ticker uses the canonical validated row across the chart, decision panel, and screener."
    return {
        "selected_ticker": selected_ticker,
        "canonical_rows": decisions,
        "top_candidates": top_candidates,
        "tracked_rows": tracked_rows[:10],
        "broad_rows": broad_rows[:top_n],
        "mover_rows": mover_rows[:top_n],
        "watch_rows": watch_rows,
        "avoid_rows": avoid_rows,
        "signal_table_rows": _compact_signal_table(decisions, source_group=None, limit=max(25, top_n)),
        "decision_by_ticker": decision_by_ticker,
        "chart_data_by_ticker": {},
        "coverage_status": coverage_status,
        "data_issues": data_issues,
        "view_counts": {
            "all": len(decisions),
            "top": len([row for row in decisions if row.get("actionability_label") in {"Actionable Today", "Research First"}]),
            "tracked": len(tracked_rows),
            "broad": len(broad_rows),
            "movers": len(mover_rows),
            "watch": len([row for row in decisions if row.get("actionability_label") in {"Wait for Better Entry", "Watch for Trigger"}]),
            "avoid": len([row for row in decisions if row.get("actionability_label") == "Avoid / Do Not Chase"]),
            "data_issues": len(data_issues),
        },
        "status_bar": {
            "provider": coverage_status.get("provider"),
            "last_scan": coverage_status.get("last_broad_scan_time"),
            "coverage_summary": f"{coverage_status.get('tickers_successfully_scanned', 0)}/{coverage_status.get('tickers_attempted', 0)} scanned",
            "universe_label": coverage_status.get("universe_label"),
            "tracked_count": coverage_status.get("tracked_tickers_count", 0),
            "provider_health": coverage_status.get("provider_health", {}).get("status", "healthy"),
            "data_issues": len(data_issues),
        },
        "source_aware_top": {
            "overall_top_setup": picker_view.get("top_candidate"),
            "best_tracked_setup": _best_from_source(decisions, "Tracked"),
            "best_broad_setup": _best_from_source(decisions, "Broad"),
            "best_mover_setup": _best_from_source(decisions, "Movers"),
        },
        "selected_ticker_consistency_status": consistency_status,
        "selected_ticker_consistency_reason": consistency_reason,
    }


def _has_source_group(row: dict[str, Any], source_group: str) -> bool:
    if row.get("source_group") == source_group:
        return True
    return source_group in list(row.get("source_groups") or [])


def _build_daily_decision_markdown(payload: dict[str, Any]) -> str:
    top_candidate = payload.get("top_candidate")
    research_candidates = payload.get("research_candidates", [])
    watch_candidates = payload.get("watch_candidates", [])
    avoid_candidates = payload.get("avoid_candidates", [])
    data_issues = payload.get("data_issues", [])
    best_mover_setup = payload.get("best_mover_setup")
    movers_summary = payload.get("movers_scan_summary") or {}
    lines = [
        "# TradeBruv Daily Pick",
        "",
        f"- Generated: {payload.get('generated_at', 'unavailable')}",
        f"- Analysis date: {payload.get('analysis_date', 'unavailable')}",
        f"- Provider: {payload.get('provider', 'unavailable')}",
        f"- Demo mode: {payload.get('demo_mode', False)}",
        f"- Scan health: {(payload.get('scan_health') or {}).get('status', 'healthy')}",
        f"- Movers scan: {_movers_summary_line(movers_summary)}",
        "",
    ]
    if top_candidate:
        lines.extend(
            [
                "## Top Candidate",
                f"Ticker: {top_candidate.get('ticker')}",
                f"Action: {top_candidate.get('primary_action')}",
                f"Actionability: {top_candidate.get('actionability_label')} ({top_candidate.get('actionability_score')})",
                f"Why now: {top_candidate.get('actionability_reason') or top_candidate.get('reason')}",
                f"Why not: {top_candidate.get('why_not')}",
                f"{top_candidate.get('entry_label', 'Entry')}: {top_candidate.get('entry_zone')}",
                f"Stop: {top_candidate.get('stop_loss')}",
                f"TP1: {top_candidate.get('tp1')}",
                f"TP2: {top_candidate.get('tp2')}",
                f"Data freshness: {top_candidate.get('data_freshness')}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "# No Clean Candidate Today",
                f"Reason: {payload.get('no_clean_candidate_reason') or 'No validated setup passed the actionability gate.'}",
                "",
                "Best Watch Names:",
            ]
        )
        if watch_candidates:
            for row in watch_candidates[:5]:
                lines.append(f"- {row.get('ticker')}: {row.get('action_trigger')}")
        else:
            lines.append("- None.")
    lines.extend(["", "## Next 3 Research Candidates"])
    if not research_candidates:
        lines.append("- None.")
    else:
        for row in research_candidates[:3]:
            lines.append(
                f"- {row.get('ticker')}: {row.get('actionability_label')} | {row.get('reason')} | {row.get('entry_label')}: {row.get('entry_zone')}"
            )
    lines.extend(["", "## Watch / Wait"])
    if not watch_candidates:
        lines.append("- None.")
    else:
        for row in watch_candidates[:5]:
            lines.append(f"- {row.get('ticker')}: {row.get('actionability_label')} | trigger {row.get('action_trigger')}")
    lines.extend(["", "## Avoid / Do Not Chase"])
    if not avoid_candidates:
        lines.append("- None.")
    else:
        for row in avoid_candidates[:5]:
            lines.append(f"- {row.get('ticker')}: {row.get('why_not') or row.get('reason')}")
    lines.extend(["", "## Best Mover Setup"])
    if best_mover_setup:
        lines.append(
            f"- {best_mover_setup.get('ticker')}: {best_mover_setup.get('actionability_label')} | {best_mover_setup.get('source_row', {}).get('signal_summary') or best_mover_setup.get('reason')}"
        )
        lines.append(
            f"- Trigger: {best_mover_setup.get('action_trigger') or best_mover_setup.get('entry_zone') or 'Review setup details.'}"
        )
    else:
        lines.append("- None.")
    lines.extend(["", "## Top Gainers"])
    _append_mover_list(lines, payload.get("top_gainers", []), limit=5)
    lines.extend(["", "## Top Losers"])
    _append_mover_list(lines, payload.get("top_losers", []), limit=5)
    lines.extend(["", "## Unusual Volume"])
    _append_mover_list(lines, payload.get("unusual_volume", []), limit=5)
    lines.extend(["", "## Breakout with Volume"])
    _append_mover_list(lines, payload.get("breakout_volume", []), limit=5)
    if data_issues:
        lines.extend(["", "## Data Issues"])
        for row in data_issues[:10]:
            lines.append(f"- {row.get('ticker')}: {row.get('price_validation_reason') or row.get('reason')}")
    failures = payload.get("scan_failures", [])
    if failures:
        lines.extend(["", "## Scan Failures"])
        for row in failures[:10]:
            lines.append(f"- {row.get('ticker')}: {_clean_failure_reason_for_display(row)}")
    return "\n".join(lines)


def _build_decision_quality_review(payload: dict[str, Any]) -> str:
    top_candidate = payload.get("top_candidate")
    research_candidates = payload.get("research_candidates", [])
    watch_candidates = payload.get("watch_candidates", [])
    decisions = payload.get("decisions", [])
    movers_summary = payload.get("movers_scan_summary") or {}
    top_gainers = payload.get("top_gainers", [])
    breakout_volume = payload.get("breakout_volume", [])
    best_mover_setup = payload.get("best_mover_setup")
    excluded = [row for row in decisions if row.get("actionability_label") in {"Avoid / Do Not Chase", "Data Insufficient"}]
    tracked = {str(row.get("ticker")): row for row in decisions}
    mover_rows = {
        str(row.get("ticker"))
        for row in [*top_gainers[:5], *breakout_volume[:5]]
        if row.get("ticker")
    }
    excluded_summary = ", ".join(
        f"{row.get('ticker')} ({row.get('actionability_label')})"
        for row in excluded[:10]
    ) or "None"
    mover_promotion_summary = ", ".join(
        f"{ticker} ({tracked.get(ticker, {}).get('actionability_label', 'not promoted')})"
        for ticker in list(mover_rows)[:5]
    ) or "None"
    best_mover_summary = (
        f"{best_mover_setup.get('ticker')} ({best_mover_setup.get('actionability_label')})"
        if best_mover_setup
        else "None"
    )
    ticker_summary = "; ".join(
        f"{ticker}: {tracked.get(ticker, {}).get('actionability_label', 'missing')}"
        for ticker in ("NVDA", "PLTR", "MU")
    )
    watch_trigger_summary = (
        "N/A (no watch names)"
        if not watch_candidates
        else "Yes" if all(row.get("action_trigger") for row in watch_candidates) else "No"
    )
    lines = [
        "# Decision Quality Review",
        "",
        f"- Did the system produce a top candidate? {'Yes' if top_candidate else 'No'}",
        f"- If not, why not? {payload.get('no_clean_candidate_reason') or 'A top candidate was available.'}",
        f"- What are the top 3 research candidates? {', '.join(str(row.get('ticker')) for row in research_candidates[:3]) or 'None'}",
        f"- What are the best watch names? {', '.join(str(row.get('ticker')) for row in watch_candidates[:5]) or 'None'}",
        f"- Did movers scan complete? {_movers_summary_line(movers_summary)}",
        f"- What were the best mover setups? {best_mover_summary}",
        f"- Were top mover names promoted into daily decision? {mover_promotion_summary}",
        f"- If not actionable, why not? {best_mover_setup.get('actionability_reason') if best_mover_setup else payload.get('no_clean_candidate_reason') or 'No mover setup qualified.'}",
        f"- Which names were excluded and why? {excluded_summary}",
        f"- Are NVDA/PLTR/MU classified clearly? {ticker_summary}",
        f"- Are 'Watch' names given triggers? {watch_trigger_summary}",
        f"- Are TP/SL levels hidden/conditional/actionable correctly? {'Yes' if all(row.get('level_status') in {'Actionable', 'Preliminary', 'Conditional', 'Hidden'} for row in decisions) else 'No'}",
        f"- Is the output readable in under 60 seconds? {'Yes' if len(research_candidates) <= 3 and len(watch_candidates) <= 5 else 'No'}",
        "",
    ]
    return "\n".join(lines)


def _append_mover_list(lines: list[str], rows: list[dict[str, Any]], *, limit: int) -> None:
    if not rows:
        lines.append("- None.")
        return
    for row in rows[:limit]:
        lines.append(
            f"- {row.get('ticker')}: {row.get('percent_change')}% | RV {row.get('relative_volume')} | {row.get('signal')} | {row.get('actionability') or 'No decision'}"
        )


def _movers_scan_summary(movers_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not movers_payload:
        return {}
    attempted = int(movers_payload.get("tickers_attempted") or 0)
    scanned = int(movers_payload.get("tickers_successfully_scanned") or 0)
    failed = len(movers_payload.get("scan_failures", []))
    provider_health = movers_payload.get("provider_health") or {}
    return {
        "available": True,
        "attempted": attempted,
        "scanned": scanned,
        "failed": failed,
        "status": provider_health.get("status", "healthy"),
        "stop_reason": provider_health.get("stop_reason") or provider_health.get("message") or "",
        "completed": bool(attempted and (attempted >= scanned + failed) and not provider_health.get("stop_scan")),
    }


def _movers_summary_line(summary: dict[str, Any]) -> str:
    if not summary:
        return "Not run."
    attempted = int(summary.get("attempted") or 0)
    scanned = int(summary.get("scanned") or 0)
    failed = int(summary.get("failed") or 0)
    status = str(summary.get("status") or "unknown")
    stop_reason = str(summary.get("stop_reason") or "").strip()
    line = f"{scanned}/{attempted} scanned"
    if failed:
        line += f", {failed} failed"
    line += f" ({status})"
    if stop_reason and not (status == "healthy" and stop_reason == "Provider responding normally."):
        line += f" - {stop_reason}"
    return line


def _clean_failure_reason_for_display(row: dict[str, Any]) -> str:
    ticker = str(row.get("ticker") or "").strip().upper()
    reason = str(row.get("reason") or "Provider failure.").strip()
    prefix = f"{ticker}: "
    if ticker and reason.upper().startswith(prefix):
        return reason[len(prefix):]
    return reason


def _build_picker_view(decisions: list[dict[str, Any]], *, data_issues: list[dict[str, Any]]) -> dict[str, Any]:
    actionable = [row for row in decisions if row.get("actionability_label") == "Actionable Today" and row.get("primary_action") == "Research / Buy Candidate"]
    research = [row for row in decisions if row.get("actionability_label") == "Research First" and row.get("primary_action") == "Research / Buy Candidate"]
    watch = [row for row in decisions if row.get("actionability_label") in {"Wait for Better Entry", "Watch for Trigger"}]
    avoid = [row for row in decisions if row.get("actionability_label") == "Avoid / Do Not Chase"]
    portfolio_actions = [row for row in decisions if row.get("action_lane") == "Portfolio" and row.get("primary_action") not in {"Data Insufficient", "Avoid"}][:5]
    top_candidate = actionable[0] if actionable else None
    research_candidates = [row for row in actionable[1:]] + research
    compact_board = [
        row
        for row in decisions
        if row.get("level_status") in {"Actionable", "Preliminary", "Conditional"}
    ][:8]
    no_clean_candidate_reason = ""
    if not top_candidate:
        if data_issues and len(data_issues) == len(decisions):
            no_clean_candidate_reason = "Every candidate failed the live price or freshness gate."
        elif watch:
            no_clean_candidate_reason = "The best names are valid, but they still need a trigger or a better entry."
        elif research:
            no_clean_candidate_reason = "There are research names, but none are clean enough to call actionable today."
        else:
            no_clean_candidate_reason = "No validated setup passed the actionability threshold."
    return {
        "top_candidate": top_candidate,
        "research_candidates": research_candidates[:3],
        "watch_candidates": watch[:5],
        "avoid_candidates": avoid[:5],
        "portfolio_actions": portfolio_actions,
        "compact_board": compact_board,
        "no_clean_candidate_reason": no_clean_candidate_reason,
    }
