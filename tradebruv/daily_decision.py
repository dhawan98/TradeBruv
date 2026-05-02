from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .actionability import actionability_priority, is_fast_actionable_label, label_bucket
from .ai_analysis import (
    DEFAULT_AI_CACHE_DIR,
    DEFAULT_AI_MAX_NAMES,
    DEFAULT_AI_MAX_TOKENS,
    DEFAULT_AI_TIMEOUT_SECONDS,
    normalize_ai_provider,
    normalize_ai_providers,
    normalize_analysis_mode,
    resolve_default_ai_provider,
    review_candidates,
    run_ai_committee,
    shortlist_ai_candidates,
)
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
from .discovery import run_earnings_movers_scan, run_highs_scan, run_theme_basket_scan, run_theme_constituents_scan, run_theme_scan
from .market_cache import DEFAULT_MARKET_CACHE_DIR, FileCacheMarketDataProvider
from .market_reliability import ResilientMarketDataProvider
from .movers import run_movers_scan
from .price_sanity import build_price_sanity_from_row
from .providers import MarketDataProvider
from .scanner import DeterministicScanner
from .tracked import DEFAULT_TRACKED_TICKERS_PATH, list_tracked_tickers
from .universe_registry import validate_universe_file
from .universe_refresh import DEFAULT_THEME_BASKETS_DIR, resolve_theme_basket

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
    include_highs: bool = False,
    include_earnings_movers: bool = False,
    include_themes: bool = False,
    theme_etfs: Path = Path("config/theme_etfs.txt"),
    top_n: int = 25,
    history_period: str = "3y",
    data_dir: Path | None = None,
    refresh_cache: bool = False,
    analysis_date: date | None = None,
    output_dir: Path = DEFAULT_DAILY_DECISION_OUTPUT_DIR,
    analysis_mode: str = "deterministic",
    ai_provider: str | None = None,
    ai_providers: list[str] | str | None = None,
    ai_max_names: int = DEFAULT_AI_MAX_NAMES,
    ai_max_tokens: int = DEFAULT_AI_MAX_TOKENS,
    ai_timeout_seconds: int = DEFAULT_AI_TIMEOUT_SECONDS,
    ai_cache: bool = True,
    ai_force_refresh: bool = False,
    ai_cache_dir: Path = DEFAULT_AI_CACHE_DIR,
    ai_rerank: str = "off",
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
    highs_payload: dict[str, Any] | None = None
    earnings_payload: dict[str, Any] | None = None
    themes_payload: dict[str, Any] | None = None
    theme_constituent_payloads: list[dict[str, Any]] = []

    if broad_universe:
        broad_tickers = load_universe(broad_universe)
        scans.append(
            {
                "lane": "Outlier",
                "source_group": "Broad",
                "scan": _run_custom_scan(
                    tickers=broad_tickers,
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
                universe=broad_tickers,
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
                        results=[
                            (
                                dict(row.get("source_row") or {})
                                if row.get("source_row")
                                else {
                                    "ticker": row.get("ticker"),
                                    "company_name": row.get("company") or row.get("company_name") or row.get("ticker"),
                                    "current_price": row.get("current_price") or row.get("price"),
                                    "regular_investing_score": row.get("regular_investing_score", 0),
                                    "outlier_score": row.get("outlier_score", 0),
                                    "velocity_score": row.get("velocity_score", 0),
                                    "last_market_date": row.get("freshness"),
                                    "relative_volume_20d": row.get("relative_volume"),
                                    "ema_stack": row.get("ema_stack"),
                                    "signal_summary": row.get("signal") or row.get("signal_summary"),
                                    "price_change_1d_pct": row.get("percent_change"),
                                }
                            )
                            | {"scan_source_group": "Movers"}
                            for row in movers_result.payload.get("results", [])
                        ],
                        scan_failures=movers_result.payload.get("scan_failures", []),
                        provider_health=movers_result.payload.get("provider_health", {}),
                        cache_stats=movers_result.payload.get("cache", {}),
                    ),
                    "universe": f"{broad_universe} movers",
                }
            )
        if include_highs:
            highs_payload = run_highs_scan(
                universe=broad_tickers,
                provider_name=provider_name,
                analysis_date=as_of,
                history_period=history_period,
                data_dir=data_dir,
                top_n=top_n,
                refresh_cache=refresh_cache,
                scanner_override=shared_scanner,
                provider_override=shared_provider,
            ).payload
        if include_earnings_movers:
            earnings_payload = run_earnings_movers_scan(
                universe=broad_tickers,
                provider_name=provider_name,
                analysis_date=as_of,
                history_period=history_period,
                data_dir=data_dir,
                top_n=top_n,
                refresh_cache=refresh_cache,
                scanner_override=shared_scanner,
                provider_override=shared_provider,
            ).payload
    if include_themes and theme_etfs.exists():
        themes_payload = run_theme_scan(
            themes=load_universe(theme_etfs),
            provider_name=provider_name,
            analysis_date=as_of,
            history_period=history_period,
            data_dir=data_dir,
            top_n=top_n,
            refresh_cache=refresh_cache,
            scanner_override=shared_scanner,
            provider_override=shared_provider,
        ).payload
        constituent_dir = Path("config/theme_constituents")
        for row in (themes_payload.get("strongest_themes", []) if themes_payload else [])[:3]:
            theme = str(row.get("ticker") or "").upper()
            if not theme:
                continue
            constituent_file = constituent_dir / f"{theme}.csv"
            if constituent_file.exists():
                theme_constituent_payloads.append(
                    run_theme_constituents_scan(
                        theme=theme,
                        constituents_path=constituent_file,
                        provider_name=provider_name,
                        analysis_date=as_of,
                        history_period=history_period,
                        data_dir=data_dir,
                        top_n=top_n,
                        refresh_cache=refresh_cache,
                        scanner_override=shared_scanner,
                        provider_override=shared_provider,
                    ).payload
                )
                continue
            basket_file = resolve_theme_basket(theme, baskets_dir=DEFAULT_THEME_BASKETS_DIR)
            if basket_file.exists():
                theme_constituent_payloads.append(
                    run_theme_basket_scan(
                        basket_path=basket_file,
                        provider_name=provider_name,
                        analysis_date=as_of,
                        history_period=history_period,
                        data_dir=data_dir,
                        top_n=top_n,
                        refresh_cache=refresh_cache,
                        scanner_override=shared_scanner,
                        provider_override=shared_provider,
                    ).payload
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
    benchmark_health_rows: list[dict[str, Any]] = []
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
            if scan.provider_health.get("benchmark_health_details"):
                benchmark_health_rows.append(scan.provider_health.get("benchmark_health_details"))
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
                "benchmark_health": getattr(scan, "provider_health", {}).get("benchmark_health_details", {}),
            }
        )

    merged = merge_canonical_rows(combined_rows, combined_decisions)
    merged_rows = merged["canonical_rows"]
    merged_decisions = merged["canonical_decisions"]
    unique_scan_failures = _dedupe_scan_failures(scan_failures)
    data_issues = [decision for decision in merged_decisions if decision.get("price_validation_status") != "PASS"]
    picker_view = _build_picker_view(merged_decisions, data_issues=data_issues)
    resolved_analysis_mode = normalize_analysis_mode(analysis_mode, legacy_ai_rerank=ai_rerank)
    resolved_ai_provider = normalize_ai_provider(ai_provider, legacy_ai_rerank=ai_rerank) or resolve_default_ai_provider()
    resolved_ai_providers = normalize_ai_providers(ai_providers, fallback_provider=resolved_ai_provider)
    ai_candidates = shortlist_ai_candidates(
        {
            **picker_view,
            "earnings_news_movers": (earnings_payload or {}).get("earnings_movers", []),
            "decisions": merged_decisions,
        },
        max_names=ai_max_names,
    )
    ai_review_summary = _empty_ai_review_summary()
    ai_committee_summary: dict[str, Any] = {}
    if resolved_analysis_mode == "ai_review":
        chosen_provider = resolved_ai_provider or "openai"
        ai_review_summary = review_candidates(
            ai_candidates,
            provider_name=chosen_provider,
            ai_max_names=ai_max_names,
            timeout_seconds=ai_timeout_seconds,
            max_tokens=ai_max_tokens,
            cache=ai_cache,
            force_refresh=ai_force_refresh,
            cache_dir=ai_cache_dir,
        )
        review_map = ai_review_summary.get("reviews") or {}
        merged_decisions = [
            ({**decision, "ai_review": review_map[str(decision.get("ticker"))]})
            if str(decision.get("ticker")) in review_map
            else decision
            for decision in merged_decisions
        ]
    elif resolved_analysis_mode == "ai_committee":
        ai_committee_summary = run_ai_committee(
            ai_candidates,
            providers=resolved_ai_providers or ([resolved_ai_provider] if resolved_ai_provider else []),
            ai_max_names=ai_max_names,
            timeout_seconds=ai_timeout_seconds,
            max_tokens=ai_max_tokens,
            cache=ai_cache,
            force_refresh=ai_force_refresh,
            cache_dir=ai_cache_dir,
        )
        committee_reviews = {
            ticker: item.get("row_review")
            for ticker, item in (ai_committee_summary.get("per_ticker_reviews") or {}).items()
            if isinstance(item, dict) and item.get("row_review")
        }
        merged_decisions = [
            ({**decision, "ai_review": committee_reviews[str(decision.get("ticker"))]})
            if str(decision.get("ticker")) in committee_reviews
            else decision
            for decision in merged_decisions
        ]
    broad_universe_status = validate_universe_file(broad_universe) if broad_universe else {
        "universe_label": "Tracked + Active",
        "universe_file": "active configured universes",
        "universe_row_count": 0,
        "expected_universe_size": 0,
        "coverage_percent": 100.0,
        "is_partial_universe": False,
        "universe_warning": "",
    }
    coverage_limitation = (
        f"Coverage limitation: this scan can miss symbols outside {broad_universe}."
        if broad_universe
        else "Coverage limitation: this scan only evaluates configured active universes."
    )
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
        "benchmark_health_rows": benchmark_health_rows,
        "coverage_limitation": coverage_limitation,
        **broad_universe_status,
    }
    benchmark_health = getattr(shared_scanner, "_benchmark_manager", None).as_dict() if getattr(shared_scanner, "_benchmark_manager", None) else {}
    coverage_status |= benchmark_health
    workspace = _build_workspace_payload(
        merged_decisions,
        coverage_status=coverage_status,
        data_issues=data_issues,
        top_n=top_n,
    )
    theme_constituent_candidates = _merge_theme_constituent_candidates(theme_constituent_payloads, limit=top_n)
    coverage_missed_risk = _coverage_missed_risk_summary(
        coverage_status=coverage_status,
        broad_universe=broad_universe,
        theme_etfs=theme_etfs,
    )
    payload = {
        "available": True,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "analysis_date": as_of.isoformat(),
        "provider": provider_name,
        "analysis_mode": resolved_analysis_mode,
        "ai_provider": resolved_ai_provider or "unconfigured",
        "ai_providers": resolved_ai_providers,
        "ai_mode": "off" if resolved_analysis_mode == "deterministic" else resolved_analysis_mode,
        "ai_rerank": ai_rerank,
        "ai_rerank_summary": _legacy_ai_rerank_summary(
            analysis_mode=resolved_analysis_mode,
            ai_review_summary=ai_review_summary,
        ),
        "ai_review_summary": ai_review_summary,
        "ai_committee": ai_committee_summary,
        "mode": "daily-decision",
        "data_mode": "live_daily_decision",
        "results": merged_rows,
        "summary": build_daily_summary(merged_rows),
        "decisions": merged_decisions,
        "data_issues": data_issues,
        "overall_top_candidate": picker_view["top_candidate"],
        "top_candidate": picker_view["top_candidate"],
        "fast_actionable_setups": picker_view["fast_actionable_setups"],
        "best_tracked_setup": _best_from_source(merged_decisions, "Tracked"),
        "best_broad_setup": _best_from_source(merged_decisions, "Broad"),
        "best_mover_setup": _best_from_source(merged_decisions, "Movers"),
        "research_candidates": picker_view["research_candidates"],
        "long_term_research_candidates": picker_view["long_term_research_candidates"],
        "high_volume_mover_watch": picker_view["high_volume_mover_watch"],
        "tracked_watchlist_setups": picker_view["tracked_watchlist_setups"],
        "watch_candidates": picker_view["watch_candidates"],
        "avoid_candidates": picker_view["avoid_candidates"],
        "portfolio_actions": picker_view["portfolio_actions"],
        "earnings_news_movers": (earnings_payload or {}).get("earnings_movers", [])[:top_n],
        "new_52_week_highs": (highs_payload or {}).get("new_52_week_highs", [])[:top_n],
        "high_volume_movers": (movers_payload or {}).get("unusual_volume", [])[:top_n],
        "strong_themes": (themes_payload or {}).get("strongest_themes", [])[:top_n],
        "theme_constituent_candidates": theme_constituent_candidates,
        "coverage_missed_risk": coverage_missed_risk,
        "coverage_limitation": coverage_limitation,
        "compact_board": picker_view["compact_board"],
        "tracked_watchlist_table": _compact_signal_table(merged_decisions, source_group="Tracked", limit=10),
        "broad_scan_top_table": _compact_signal_table(merged_decisions, source_group="Broad", limit=top_n),
        "movers_table": _compact_signal_table(merged_decisions, source_group="Movers", limit=top_n),
        "signal_table": _compact_signal_table(merged_decisions, source_group=None, limit=max(top_n, 25)),
        "no_clean_candidate_reason": picker_view["no_clean_candidate_reason"],
        "data_coverage_status": coverage_status,
        "scan_health": coverage_status.get("provider_health", {}),
        "benchmark_health": benchmark_health,
        "benchmark_warnings": [benchmark_health["benchmark_warning"]] if benchmark_health.get("benchmark_warning") else [],
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
        "highs_scan_summary": _generic_scan_summary(highs_payload),
        "earnings_scan_summary": _generic_scan_summary(earnings_payload),
        "theme_scan_summary": _generic_scan_summary(themes_payload),
        "theme_constituent_scan_summaries": [_generic_scan_summary(item) for item in theme_constituent_payloads],
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
            "analysis_mode": "deterministic",
            "ai_mode": "off",
            "ai_rerank_summary": {},
            "ai_review_summary": _empty_ai_review_summary(),
            "ai_committee": {},
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
            "long_term_research_candidates": [],
            "high_volume_movers": [],
            "earnings_news_movers": [],
            "new_52_week_highs": [],
            "strong_themes": [],
            "theme_constituent_candidates": [],
            "coverage_missed_risk": [],
            "coverage_limitation": "",
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
            "benchmark_health": {},
            "benchmark_warnings": [],
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
            "highs_scan_summary": {},
            "earnings_scan_summary": {},
            "theme_scan_summary": {},
            "theme_constituent_scan_summaries": [],
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
    top_candidates = list(picker_view.get("fast_actionable_setups") or [])[:8]
    tracked_rows = [row for row in decisions if _has_source_group(row, "Tracked")]
    broad_rows = [row for row in decisions if _has_source_group(row, "Broad")]
    mover_rows = [row for row in decisions if _has_source_group(row, "Movers")]
    watch_rows = list(picker_view.get("watch_candidates") or [])[:5]
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
        "fast_actionable_setups": picker_view.get("fast_actionable_setups", []),
        "long_term_research_candidates": picker_view.get("long_term_research_candidates", []),
        "high_volume_mover_watch": picker_view.get("high_volume_mover_watch", []),
        "tracked_watchlist_setups": picker_view.get("tracked_watchlist_setups", []),
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
            "top": len([row for row in decisions if is_fast_actionable_label(_decision_label(row))]),
            "tracked": len(tracked_rows),
            "broad": len(broad_rows),
            "movers": len(mover_rows),
            "watch": len([row for row in decisions if label_bucket(_decision_label(row)) == "watch"]),
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
    fast_actionable = payload.get("fast_actionable_setups", [])
    research_candidates = payload.get("long_term_research_candidates", payload.get("research_candidates", []))
    mover_watch = payload.get("high_volume_mover_watch", [])
    tracked_watchlist = payload.get("tracked_watchlist_setups", [])
    watch_candidates = payload.get("watch_candidates", [])
    avoid_candidates = payload.get("avoid_candidates", [])
    data_issues = payload.get("data_issues", [])
    movers_summary = payload.get("movers_scan_summary") or {}
    highs_summary = payload.get("highs_scan_summary") or {}
    earnings_summary = payload.get("earnings_scan_summary") or {}
    theme_summary = payload.get("theme_scan_summary") or {}
    analysis_mode = str(payload.get("analysis_mode") or "")
    ai_review_summary = payload.get("ai_review_summary") or {}
    ai_committee = payload.get("ai_committee") or {}
    legacy_ai_rerank = not analysis_mode and bool(payload.get("ai_rerank_summary"))
    analysis_mode = analysis_mode or "deterministic"
    lines = [
        "# TradeBruv Daily Pick",
        "",
        f"- Generated: {payload.get('generated_at', 'unavailable')}",
        f"- Analysis date: {payload.get('analysis_date', 'unavailable')}",
        f"- Provider: {payload.get('provider', 'unavailable')}",
        f"- Analysis mode: {analysis_mode}",
        f"- AI mode: {'off' if analysis_mode == 'deterministic' else analysis_mode}",
        f"- Demo mode: {payload.get('demo_mode', False)}",
        f"- Scan health: {(payload.get('scan_health') or {}).get('status', 'healthy')}",
        f"- Benchmark health: {(payload.get('benchmark_health') or {}).get('benchmark_health', 'healthy')}",
        f"- Movers scan: {_movers_summary_line(movers_summary)}",
        f"- Highs scan: {_movers_summary_line(highs_summary)}",
        f"- Earnings scan: {_movers_summary_line(earnings_summary)}",
        f"- Theme scan: {_movers_summary_line(theme_summary)}",
        "",
    ]
    if legacy_ai_rerank:
        lines[5:5] = [
            f"- AI rerank: {payload.get('ai_rerank', 'off')}",
            f"- AI rerank provider: {(payload.get('ai_rerank_summary') or {}).get('provider', 'off')}",
            f"- AI rerank reviewed: {(payload.get('ai_rerank_summary') or {}).get('names_reviewed', 0)}",
            f"- AI rerank downgraded: {(payload.get('ai_rerank_summary') or {}).get('downgraded', 0)}",
            f"- AI unsupported claims detected: {(payload.get('ai_rerank_summary') or {}).get('unsupported_claims_detected', 0)}",
            f"- AI top label changed: {'yes' if (payload.get('ai_rerank_summary') or {}).get('top_label_changed') else 'no'}",
        ]
    for warning in payload.get("benchmark_warnings", [])[:1]:
        lines.extend([f"- Warning: {warning}", ""])
    if payload.get("coverage_limitation"):
        lines.extend([f"- {payload.get('coverage_limitation')}", ""])
    if analysis_mode == "ai_review":
        lines.extend(
            [
                "## AI Review Summary",
                f"- Provider: {ai_review_summary.get('provider', 'unavailable')}",
                f"- Model: {ai_review_summary.get('model', 'unavailable')}",
                f"- Names reviewed: {ai_review_summary.get('names_reviewed', 0)}",
                f"- Downgraded: {ai_review_summary.get('downgraded', 0)}",
                f"- Caution flags: {ai_review_summary.get('caution_flags', 0)}",
                f"- Top AI-agreed names: {', '.join(ai_review_summary.get('top_ai_agreed_names', [])) or 'None'}",
                f"- Names AI says not to chase: {', '.join(ai_review_summary.get('names_ai_says_not_to_chase', [])) or 'None'}",
                f"- Unsupported claims detected: {ai_review_summary.get('unsupported_claims_detected', 0)}",
                "",
            ]
        )
    if analysis_mode == "ai_committee":
        failed_models = ", ".join(
            f"{item.get('provider')}: {item.get('reason')}"
            for item in ai_committee.get("models_failed", [])
        ) or "None"
        lines.extend(
            [
                "## AI Committee Summary",
                f"- Providers used: {', '.join(ai_committee.get('models_used', [])) or 'None'}",
                f"- Providers failed: {failed_models}",
                f"- Consensus names: {', '.join(ai_committee.get('consensus_candidates', [])) or 'None'}",
                f"- Disagreement names: {', '.join(ai_committee.get('disagreement_candidates', [])) or 'None'}",
                f"- Names all models warned against: {', '.join(ai_committee.get('names_all_models_warn_against', [])) or 'None'}",
                f"- Committee one-line summary: {ai_committee.get('committee_summary', 'None')}",
                "",
            ]
        )
    lines.extend(["## Fast Actionable Setups"])
    if not fast_actionable:
        lines.append(f"- None. {payload.get('no_clean_candidate_reason') or 'No near-term setup cleared the actionability gate.'}")
    else:
        for row in fast_actionable[:5]:
            lines.append(
                f"- {row.get('ticker')}: {_decision_label(row)} ({_decision_score(row)}) | {row.get('actionability_reason') or row.get('reason')} | {row.get('entry_label')}: {row.get('entry_zone')}"
            )
            if row == top_candidate:
                lines.append(f"  Stop {row.get('stop_loss')} | TP1 {row.get('tp1')} | TP2 {row.get('tp2')}")
    lines.extend(["", "## Long-Term Research Candidates"])
    if not research_candidates:
        lines.append("- None.")
    else:
        for row in research_candidates[:5]:
            lines.append(
                f"- {row.get('ticker')}: {_decision_label(row)} ({_decision_score(row)}) | {row.get('reason')} | {row.get('entry_label')}: {row.get('entry_zone')}"
            )
    lines.extend(["", "## Earnings / News Movers"])
    _append_discovery_section(lines, payload.get("earnings_news_movers", []), limit=8)
    lines.extend(["", "## New 52-Week Highs"])
    _append_discovery_section(lines, payload.get("new_52_week_highs", []), limit=8)
    lines.extend(["", "## High-Volume Movers"])
    high_volume_rows = payload.get("high_volume_movers") or mover_watch
    if high_volume_rows is mover_watch:
        if not mover_watch:
            lines.append("- None.")
        else:
            for row in mover_watch[:5]:
                lines.append(
                    f"- {row.get('ticker')}: {_decision_label(row)} | RV {row.get('source_row', {}).get('relative_volume_20d', 'n/a')} | {row.get('source_row', {}).get('signal_summary') or row.get('action_trigger')}"
                )
    else:
        _append_discovery_section(lines, high_volume_rows, limit=8)
    lines.extend(["", "## Strong Themes"])
    _append_discovery_section(lines, payload.get("strong_themes", []), limit=8)
    lines.extend(["", "## Theme Constituent Candidates"])
    _append_discovery_section(lines, payload.get("theme_constituent_candidates", []), limit=8)
    lines.extend(["", "## Tracked Watchlist Setups"])
    if not tracked_watchlist:
        lines.append("- None.")
    else:
        for row in tracked_watchlist[:5]:
            lines.append(
                f"- {row.get('ticker')}: {_decision_label(row)} | {row.get('actionability_reason') or row.get('reason')}"
            )
    lines.extend(["", "## Watch for Better Entry"])
    if not watch_candidates:
        lines.append("- None.")
    else:
        for row in watch_candidates[:5]:
            lines.append(f"- {row.get('ticker')}: {_decision_label(row)} | trigger {row.get('action_trigger')}")
    lines.extend(["", "## Avoid / Do Not Chase"])
    if not avoid_candidates:
        lines.append("- None.")
    else:
        for row in avoid_candidates[:5]:
            lines.append(f"- {row.get('ticker')}: {row.get('why_not') or row.get('reason')}")
    lines.extend(["", "## Best Mover Setup"])
    best_mover_setup = payload.get("best_mover_setup")
    if best_mover_setup:
        lines.append(
            f"- {best_mover_setup.get('ticker')}: {best_mover_setup.get('actionability_label')} | {best_mover_setup.get('source_row', {}).get('signal_summary') or best_mover_setup.get('reason')}"
        )
        lines.append(
            f"- Trigger: {best_mover_setup.get('action_trigger') or best_mover_setup.get('entry_zone') or 'Review setup details.'}"
        )
    else:
        lines.append("- None.")
    lines.extend(["", "## Breakout with Volume"])
    _append_mover_list(lines, payload.get("breakout_volume", []), limit=5)
    lines.extend(["", "## Coverage / Missed Risk"])
    for item in payload.get("coverage_missed_risk", [])[:5]:
        lines.append(f"- {item}")
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
    research_candidates = payload.get("long_term_research_candidates", payload.get("research_candidates", []))
    watch_candidates = payload.get("watch_candidates", [])
    fast_actionable = payload.get("fast_actionable_setups", [])
    mover_watch = payload.get("high_volume_mover_watch", [])
    decisions = payload.get("decisions", [])
    movers_summary = payload.get("movers_scan_summary") or {}
    top_gainers = payload.get("top_gainers", [])
    breakout_volume = payload.get("breakout_volume", [])
    best_mover_setup = payload.get("best_mover_setup")
    excluded = [row for row in decisions if _decision_label(row) in {"Avoid / Do Not Chase", "Data Insufficient"}]
    tracked = {str(row.get("ticker")): row for row in decisions}
    mover_rows = {
        str(row.get("ticker"))
        for row in [*top_gainers[:5], *breakout_volume[:5]]
        if row.get("ticker")
    }
    excluded_summary = ", ".join(
        f"{row.get('ticker')} ({_decision_label(row)})"
        for row in excluded[:10]
    ) or "None"
    mover_promotion_summary = ", ".join(
        f"{ticker} ({_decision_label(tracked.get(ticker, {})) if tracked.get(ticker) else 'not promoted'})"
        for ticker in list(mover_rows)[:5]
    ) or "None"
    best_mover_summary = (
        f"{best_mover_setup.get('ticker')} ({_decision_label(best_mover_setup)})"
        if best_mover_setup
        else "None"
    )
    ticker_summary = "; ".join(
        f"{ticker}: {_decision_label(tracked.get(ticker, {})) if tracked.get(ticker) else 'missing'}"
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
        f"- Did the system produce a fast actionable candidate? {'Yes' if top_candidate else 'No'}",
        f"- If not, why not? {payload.get('no_clean_candidate_reason') or 'A top candidate was available.'}",
        f"- What are the fast actionable setups? {', '.join(str(row.get('ticker')) for row in fast_actionable[:5]) or 'None'}",
        f"- What are the long-term research candidates? {', '.join(str(row.get('ticker')) for row in research_candidates[:5]) or 'None'}",
        f"- What are the best watch names? {', '.join(str(row.get('ticker')) for row in watch_candidates[:5]) or 'None'}",
        f"- Did movers scan complete? {_movers_summary_line(movers_summary)}",
        f"- What were the best mover setups? {best_mover_summary} | extra mover watch names: {', '.join(str(row.get('ticker')) for row in mover_watch[:5]) or 'None'}",
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


def _append_discovery_section(lines: list[str], rows: list[dict[str, Any]], *, limit: int) -> None:
    if not rows:
        lines.append("- None.")
        return
    for row in rows[:limit]:
        ticker = row.get("ticker")
        label = row.get("actionability_label") or row.get("actionability") or "No decision"
        entry = row.get("entry_or_trigger") or row.get("entry_zone") or row.get("action_trigger") or "unavailable"
        why = row.get("why_it_is_interesting") or row.get("reason") or row.get("signal")
        risk = row.get("why_it_may_fail") or row.get("why_not") or row.get("risk")
        lines.append(f"- {ticker}: {label} | {why} | entry/trigger {entry} | risk {risk}")


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


def _generic_scan_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    attempted = int(payload.get("universe_size") or payload.get("themes_scanned") or payload.get("tickers_attempted") or 0)
    scanned = int(payload.get("tickers_successfully_scanned") or 0)
    failed = len(payload.get("scan_failures", []))
    provider_health = payload.get("provider_health") or {}
    return {
        "available": bool(payload.get("available", True)),
        "attempted": attempted,
        "scanned": scanned,
        "failed": failed,
        "status": provider_health.get("status", "healthy"),
        "message": payload.get("message") or provider_health.get("message") or "",
    }


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


def _coverage_missed_risk_summary(
    *,
    coverage_status: dict[str, Any],
    broad_universe: Path | None,
    theme_etfs: Path,
) -> list[str]:
    warnings = [
        str(coverage_status.get("coverage_limitation") or "Coverage limitation: configured universe only."),
    ]
    universe_warning = str(coverage_status.get("universe_warning") or "").strip()
    if universe_warning:
        warnings.append(universe_warning)
    if broad_universe:
        warnings.append(f"Configured universe file: {broad_universe}")
    if theme_etfs and not theme_etfs.exists():
        warnings.append(f"Theme ETF file missing: {theme_etfs}")
    if int(coverage_status.get("tickers_failed") or 0) > 0:
        warnings.append(f"{coverage_status.get('tickers_failed')} ticker(s) failed during scanning and may have reduced discovery coverage.")
    deduped: list[str] = []
    for warning in warnings:
        clean = warning.strip()
        if clean and clean not in deduped:
            deduped.append(clean)
    return deduped


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
    category = str(row.get("category") or "").strip().lower()
    if category == "malformed_response":
        return "Provider or cache returned malformed market data for this ticker."
    if category == "unauthorized":
        return "Provider rejected the request as unauthorized."
    if category == "rate_limited":
        return "Provider rate-limited the request."
    if category == "timeout":
        return "Provider timed out or network resolution failed."
    reason = str(row.get("reason") or "Provider failure.").strip()
    reason_lower = reason.lower()
    if any(pattern in reason_lower for pattern in ("extra data", "expecting value", "unterminated string", "jsondecodeerror")):
        return "Provider or cache returned malformed market data for this ticker."
    prefix = f"{ticker}: "
    if ticker and reason.upper().startswith(prefix):
        return reason[len(prefix):]
    return reason


def _build_ai_rerank_summary(
    original_decisions: list[dict[str, Any]],
    reviewed_decisions: list[dict[str, Any]],
    *,
    mode: str,
    provider_name: str,
) -> dict[str, Any]:
    enabled = mode != "off"
    original_by_ticker = {str(row.get("ticker")): row for row in original_decisions if row.get("ticker")}
    reviewed_rows = [row for row in reviewed_decisions if row.get("ai_review")]
    available_reviews = sum(bool((row.get("ai_review") or {}).get("available")) for row in reviewed_rows)
    downgraded = sum(
        1
        for row in reviewed_rows
        if _decision_label(row) != str((original_by_ticker.get(str(row.get("ticker"))) or {}).get("actionability_label") or _decision_label(row))
    )
    unsupported_claims = sum(
        1
        for row in reviewed_rows
        if bool((row.get("ai_review") or {}).get("unsupported_claims_detected"))
    )
    top_label_changed = downgraded > 0
    status = "off"
    if enabled:
        if not reviewed_rows:
            status = "no_eligible_names"
        elif available_reviews:
            status = "applied"
        else:
            status = "unavailable"
    return {
        "enabled": enabled,
        "mode": mode,
        "status": status,
        "provider": provider_name,
        "names_reviewed": len(reviewed_rows),
        "reviews_available": available_reviews,
        "reviews_unavailable": max(len(reviewed_rows) - available_reviews, 0),
        "downgraded": downgraded,
        "unsupported_claims_detected": unsupported_claims,
        "top_label_changed": top_label_changed,
    }


def _empty_ai_review_summary() -> dict[str, Any]:
    return {
        "enabled": False,
        "mode": "deterministic",
        "provider": "off",
        "model": "off",
        "names_reviewed": 0,
        "downgraded": 0,
        "caution_flags": 0,
        "top_ai_agreed_names": [],
        "names_ai_says_not_to_chase": [],
        "unsupported_claims_detected": 0,
        "reviews_unavailable": [],
        "reviews": {},
    }


def _legacy_ai_rerank_summary(*, analysis_mode: str, ai_review_summary: dict[str, Any]) -> dict[str, Any]:
    if analysis_mode != "ai_review":
        return _build_ai_rerank_summary([], [], mode="off", provider_name="off")
    return {
        "enabled": True,
        "mode": "ai_review",
        "status": "applied" if int(ai_review_summary.get("names_reviewed") or 0) else "no_eligible_names",
        "provider": ai_review_summary.get("provider", "unavailable"),
        "names_reviewed": ai_review_summary.get("names_reviewed", 0),
        "reviews_available": int(ai_review_summary.get("names_reviewed") or 0) - len(ai_review_summary.get("reviews_unavailable") or []),
        "reviews_unavailable": len(ai_review_summary.get("reviews_unavailable") or []),
        "downgraded": ai_review_summary.get("downgraded", 0),
        "unsupported_claims_detected": ai_review_summary.get("unsupported_claims_detected", 0),
        "top_label_changed": False,
    }


def _build_picker_view(decisions: list[dict[str, Any]], *, data_issues: list[dict[str, Any]]) -> dict[str, Any]:
    actionable = [row for row in decisions if is_fast_actionable_label(_decision_label(row)) and row.get("primary_action") == "Research / Buy Candidate"]
    research = [row for row in decisions if _decision_label(row) == "Long-Term Research Candidate" and row.get("primary_action") == "Research / Buy Candidate"]
    movers = [row for row in decisions if _decision_label(row) == "High-Volume Mover Watch"]
    watch = [row for row in decisions if _decision_label(row) in {"Watch for Better Entry", "Slow Compounder Watch"}]
    avoid = [row for row in decisions if _decision_label(row) == "Avoid / Do Not Chase"]
    portfolio_actions = [row for row in decisions if row.get("action_lane") == "Portfolio" and row.get("primary_action") not in {"Data Insufficient", "Avoid"}][:5]
    top_candidate = actionable[0] if actionable else None
    tracked_watchlist = [
        row
        for row in decisions
        if _has_source_group(row, "Tracked") and _decision_label(row) not in {"Avoid / Do Not Chase", "Data Insufficient"}
    ][:5]
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
            no_clean_candidate_reason = "There are solid research names, but none have true near-term confirmation."
        else:
            no_clean_candidate_reason = "No validated setup passed the actionability threshold."
    return {
        "top_candidate": top_candidate,
        "fast_actionable_setups": actionable[:5],
        "research_candidates": research[:5],
        "long_term_research_candidates": research[:5],
        "high_volume_mover_watch": movers[:5],
        "tracked_watchlist_setups": tracked_watchlist,
        "watch_candidates": watch[:5],
        "avoid_candidates": avoid[:5],
        "portfolio_actions": portfolio_actions,
        "compact_board": compact_board,
        "no_clean_candidate_reason": no_clean_candidate_reason,
    }


def _decision_label(row: dict[str, Any]) -> str:
    return str(row.get("actionability_label") or row.get("ai_adjusted_actionability_label") or "Data Insufficient")


def _decision_score(row: dict[str, Any]) -> int:
    score = row.get("actionability_score") or row.get("ai_rerank_score")
    try:
        return int(round(float(score or 0)))
    except (TypeError, ValueError):
        return 0
