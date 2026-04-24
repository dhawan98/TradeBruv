from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

from .ai_explanations import apply_ai_explanations, build_explanation_provider
from .ai_committee import combine_recommendations, run_ai_committee
from .analysis import analyze_portfolio, build_portfolio_recommendation, deep_research
from .automation import filter_alerts, summarize_watchlist_changes
from .catalysts import CatalystOverlayProvider, load_catalyst_repository
from .cli import build_provider, load_universe
from .data_sources import build_data_source_status, data_health_summary
from .journal import DEFAULT_JOURNAL_PATH, journal_stats, read_journal
from .portfolio import (
    DEFAULT_PORTFOLIO_PATH,
    delete_position,
    export_portfolio_csv,
    import_portfolio_csv,
    load_portfolio,
    portfolio_summary,
    refresh_portfolio_prices,
    save_portfolio,
    upsert_position,
)
from .validation_lab import (
    add_prediction,
    create_prediction_record,
    famous_outlier_case_study,
    load_predictions,
    save_predictions,
    update_prediction_outcomes,
    validation_metrics,
)
from .indicators import pct_change, sma
from .performance import aggregate_strategy_performance
from .providers import MarketDataProvider
from .review import load_reports_from_dir, load_scan_report, review_report, review_reports
from .scanner import DeterministicScanner


DEFAULT_UNIVERSE_FILES = {
    "Outlier watchlist": Path("config/outlier_watchlist.txt"),
    "Momentum universe": Path("config/momentum_universe.txt"),
    "Mega-cap universe": Path("config/mega_cap_universe.txt"),
    "Sample universe": Path("config/sample_universe.txt"),
}

AVOID_STATUS = "Avoid"
WATCH_ONLY_STATUS = "Watch Only"
HIGH_RISK_OUTLIER_TYPES = {"Short Squeeze Watch"}
HIGH_RISK_LABELS = {"High", "Extreme"}


@dataclass(frozen=True)
class DashboardReport:
    generated_at: str
    scanner: str
    mode: str
    provider: str
    results: list[dict[str, Any]]
    source: str
    market_regime: dict[str, Any]


def run_dashboard_scan(
    *,
    provider_name: str,
    mode: str,
    universe_path: Path,
    limit: int = 0,
    analysis_date: date | None = None,
    data_dir: Path | None = None,
    history_period: str = "3y",
    catalyst_file: Path | None = None,
    ai_explanations: bool = False,
    mock_ai_explanations: bool = False,
) -> DashboardReport:
    as_of = analysis_date or date.today()
    args = SimpleNamespace(
        provider=provider_name,
        data_dir=data_dir,
        history_period=history_period,
    )
    provider = build_provider(args=args, analysis_date=as_of)
    catalyst_repository = load_catalyst_repository(catalyst_file)
    if catalyst_repository.items_by_ticker:
        provider = CatalystOverlayProvider(provider, catalyst_repository)
    scanner = DeterministicScanner(provider=provider, analysis_date=as_of)
    results = scanner.scan(load_universe(universe_path), mode=mode)
    if ai_explanations:
        explanation_provider = build_explanation_provider(enabled=True, mock=mock_ai_explanations)
        apply_ai_explanations(results, explanation_provider)
    if limit:
        results = results[:limit]
    result_rows = [result.to_dict() for result in results]
    return DashboardReport(
        generated_at=datetime.utcnow().isoformat() + "Z",
        scanner="TradeBruv deterministic scanner",
        mode=mode,
        provider=provider_name,
        results=result_rows,
        source=f"live scan: {universe_path}",
        market_regime=build_market_regime(provider=provider, results=result_rows),
    )


def load_dashboard_report(path: Path) -> DashboardReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    results = [_normalize_result(row) for row in payload.get("results", []) if isinstance(row, dict)]
    provider = _infer_provider(payload, results)
    return DashboardReport(
        generated_at=str(payload.get("generated_at", "unavailable")),
        scanner=str(payload.get("scanner", "TradeBruv deterministic scanner")),
        mode=str(payload.get("mode", "standard")),
        provider=provider,
        results=results,
        source=str(path),
        market_regime=build_market_regime(provider=None, results=results),
    )


def run_dashboard_review(
    *,
    report_path: Path,
    provider: MarketDataProvider,
    horizons: list[int],
    signal_date: date | None = None,
) -> dict[str, Any]:
    report = load_scan_report(report_path)
    return review_report(report=report, provider=provider, horizons=horizons, signal_date=signal_date)


def run_dashboard_review_batch(
    *,
    reports_dir: Path,
    provider: MarketDataProvider,
    horizons: list[int],
    signal_date: date | None = None,
) -> dict[str, Any]:
    reports = load_reports_from_dir(reports_dir)
    return review_reports(reports=reports, provider=provider, horizons=horizons, signal_date=signal_date)


def load_review_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("results", [])
    return payload


def load_strategy_performance(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("results", [])
    return payload


def filter_review_results(results: Iterable[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in results]
    strategy = set(filters.get("strategy") or [])
    outlier_type = set(filters.get("outlier_type") or [])
    status = set(filters.get("status") or [])
    only_available = bool(filters.get("only_available"))
    filtered = []
    for row in rows:
        if strategy and row.get("strategy_label") not in strategy:
            continue
        if outlier_type and row.get("outlier_type") not in outlier_type:
            continue
        if status and row.get("status_label") not in status:
            continue
        if only_available and not row.get("available"):
            continue
        filtered.append(row)
    return filtered


def build_review_summary(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [dict(row) for row in results]
    available = [row for row in rows if row.get("available")]
    returns = [_to_float(row.get("forward_return_pct"), default=None) for row in available]
    returns = [value for value in returns if value is not None]
    return {
        "total_rows": len(rows),
        "available_rows": len(available),
        "unavailable_rows": len(rows) - len(available),
        "average_forward_return": _safe_avg(returns),
        "best_result": round(max(returns), 4) if returns else "unavailable",
        "worst_result": round(min(returns), 4) if returns else "unavailable",
        "tp1_hits": sum(1 for row in available if row.get("hit_tp1")),
        "tp2_hits": sum(1 for row in available if row.get("hit_tp2")),
        "invalidation_hits": sum(1 for row in available if row.get("hit_stop_or_invalidation")),
    }


def build_strategy_performance_highlights(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    performance_rows = list(rows)
    if performance_rows and "dimension" not in performance_rows[0]:
        performance_rows = aggregate_strategy_performance(performance_rows)

    def top(dimension: str, metric: str, reverse: bool = True) -> dict[str, Any] | None:
        candidates = [
            row
            for row in performance_rows
            if row.get("dimension") == dimension and _to_float(row.get(metric), default=None) is not None
        ]
        return max(candidates, key=lambda row: _to_float(row.get(metric), default=0), default=None) if reverse else min(
            candidates,
            key=lambda row: _to_float(row.get(metric), default=0),
            default=None,
        )

    return {
        "best_strategy_by_expectancy": top("strategy_label", "expectancy"),
        "best_outlier_type": top("outlier_type", "expectancy"),
        "best_catalyst_quality": top("catalyst_quality", "expectancy"),
        "worst_strategy": top("strategy_label", "expectancy", reverse=False),
        "highest_invalidation_rate": top("strategy_label", "invalidation_rate"),
        "best_theme_tag": top("theme_tags", "expectancy"),
        "warning_types_that_predicted_bad_outcomes": [
            row
            for row in performance_rows
            if row.get("dimension") == "warnings" and _to_float(row.get("expectancy"), default=0) < 0
        ][:10],
        "small_sample_warnings": [row for row in performance_rows if row.get("small_sample_warning")][:10],
    }


def load_dashboard_journal(path: Path = DEFAULT_JOURNAL_PATH) -> list[dict[str, Any]]:
    return read_journal(path)


def load_dashboard_portfolio(path: Path = DEFAULT_PORTFOLIO_PATH) -> list[dict[str, Any]]:
    return [position.to_dict() for position in load_portfolio(path)]


def save_dashboard_portfolio(rows: Iterable[dict[str, Any]], path: Path = DEFAULT_PORTFOLIO_PATH) -> Path:
    return save_portfolio(list(rows), path)


def import_dashboard_portfolio_csv(import_path: Path, portfolio_path: Path = DEFAULT_PORTFOLIO_PATH) -> list[dict[str, Any]]:
    return [position.to_dict() for position in import_portfolio_csv(import_path, portfolio_path)]


def export_dashboard_portfolio_csv(rows: Iterable[dict[str, Any]], output_path: Path) -> Path:
    return export_portfolio_csv(list(rows), output_path)


def upsert_dashboard_position(position: dict[str, Any], portfolio_path: Path = DEFAULT_PORTFOLIO_PATH) -> dict[str, Any]:
    return upsert_position(position=position, portfolio_path=portfolio_path).to_dict()


def delete_dashboard_position(ticker: str, portfolio_path: Path = DEFAULT_PORTFOLIO_PATH, account_name: str | None = None) -> bool:
    return delete_position(ticker=ticker, account_name=account_name, portfolio_path=portfolio_path)


def refresh_dashboard_portfolio_prices(
    *,
    rows: Iterable[dict[str, Any]],
    provider: MarketDataProvider,
) -> list[dict[str, Any]]:
    return [position.to_dict() for position in refresh_portfolio_prices(positions=rows, provider=provider)]


def build_dashboard_portfolio_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return portfolio_summary(list(rows))


def run_dashboard_portfolio_analysis(
    *,
    rows: Iterable[dict[str, Any]],
    provider: MarketDataProvider,
    analysis_date: date | None = None,
) -> dict[str, Any]:
    return analyze_portfolio(positions=list(rows), provider=provider, analysis_date=analysis_date)


def run_dashboard_deep_research(
    *,
    ticker: str,
    provider: MarketDataProvider,
    portfolio_rows: Iterable[dict[str, Any]] | None = None,
    journal_rows: Iterable[dict[str, Any]] | None = None,
    analysis_date: date | None = None,
) -> dict[str, Any]:
    return deep_research(
        ticker=ticker,
        provider=provider,
        portfolio_positions=list(portfolio_rows or []),
        journal_rows=list(journal_rows or []),
        analysis_date=analysis_date,
    )


def run_dashboard_ai_committee(
    *,
    scanner_row: dict[str, Any],
    portfolio_context: dict[str, Any] | None = None,
    mode: str = "Mock AI for testing",
) -> dict[str, Any]:
    return run_ai_committee(scanner_row=scanner_row, portfolio_context=portfolio_context, mode=mode)


def build_dashboard_combined_recommendation(
    *,
    rule_based: str,
    ai_output: dict[str, Any],
    scanner_row: dict[str, Any],
) -> dict[str, Any]:
    return combine_recommendations(rule_based, ai_output, scanner_row)


def build_dashboard_data_source_status() -> dict[str, Any]:
    rows = build_data_source_status()
    return {"rows": rows, "summary": data_health_summary(rows)}


def load_dashboard_predictions(path: Path) -> list[dict[str, Any]]:
    return load_predictions(path)


def save_dashboard_predictions(records: Iterable[dict[str, Any]], path: Path) -> Path:
    return save_predictions(list(records), path)


def create_dashboard_prediction(
    *,
    scanner_row: dict[str, Any],
    rule_based_recommendation: str,
    ai_committee_recommendation: str = "Data Insufficient",
    final_combined_recommendation: str | None = None,
    thesis: str = "",
    events_to_watch: Iterable[str] | None = None,
    owned_at_signal: bool = False,
    portfolio_weight_at_signal: float | str = "",
) -> dict[str, Any]:
    return create_prediction_record(
        scanner_row=scanner_row,
        rule_based_recommendation=rule_based_recommendation,
        ai_committee_recommendation=ai_committee_recommendation,
        final_combined_recommendation=final_combined_recommendation,
        thesis=thesis,
        events_to_watch=events_to_watch,
        owned_at_signal=owned_at_signal,
        portfolio_weight_at_signal=portfolio_weight_at_signal,
    )


def add_dashboard_prediction(record: dict[str, Any], path: Path) -> dict[str, Any]:
    return add_prediction(record, path)


def update_dashboard_prediction_outcomes(
    *,
    records: Iterable[dict[str, Any]],
    provider: MarketDataProvider,
    as_of_date: date | None = None,
) -> list[dict[str, Any]]:
    return update_prediction_outcomes(records=list(records), provider=provider, as_of_date=as_of_date)


def build_dashboard_validation_metrics(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return validation_metrics(list(records))


def run_dashboard_case_study(
    *,
    ticker: str,
    provider: MarketDataProvider,
    signal_date: date,
    end_date: date | None = None,
) -> dict[str, Any]:
    return famous_outlier_case_study(ticker=ticker, provider=provider, signal_date=signal_date, end_date=end_date)


def build_process_quality_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return journal_stats(list(rows))


def load_alerts_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"generated_at": "unavailable", "alerts": payload}
    payload.setdefault("alerts", [])
    return payload


def load_daily_summary_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def filter_dashboard_alerts(alerts: Iterable[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    return filter_alerts(alerts, filters)


def build_watchlist_change_summary(alerts: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return summarize_watchlist_changes(alerts)


def build_daily_brief_view(summary: dict[str, Any], alerts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    alert_rows = list(alerts)
    return {
        "market_regime": summary.get("market_regime", {}),
        "top_candidates": summary.get("top_outlier_candidates", []),
        "top_avoid_names": summary.get("top_avoid_names", []),
        "top_alerts": summary.get("top_alerts", alert_rows[:10]),
        "daily_summary_markdown": summary.get("markdown", ""),
        "data_issues": summary.get("data_quality_issues", []),
    }


def find_latest_report(output_dir: Path = Path("outputs")) -> Path | None:
    if not output_dir.exists():
        return None
    candidates = [
        path
        for path in output_dir.rglob("*.json")
        if path.name in {"scan_report.json", "outlier_scan_report.json"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def filter_results(results: Iterable[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [_normalize_result(row) for row in results]
    status = set(filters.get("status") or [])
    strategy = set(filters.get("strategy") or [])
    outlier_type = set(filters.get("outlier_type") or [])
    risk_level = set(filters.get("risk_level") or [])
    theme_tag = filters.get("theme_tag") or ""
    min_outlier_score = _to_float(filters.get("min_outlier_score"), default=0)
    min_winner_score = _to_float(filters.get("min_winner_score"), default=0)

    filtered: list[dict[str, Any]] = []
    for row in rows:
        if status and row["status_label"] not in status:
            continue
        if strategy and row["strategy_label"] not in strategy:
            continue
        if outlier_type and row["outlier_type"] not in outlier_type:
            continue
        if risk_level and row["outlier_risk"] not in risk_level:
            continue
        if theme_tag and theme_tag not in row["theme_tags"]:
            continue
        if _to_float(row["outlier_score"]) < min_outlier_score:
            continue
        if _to_float(row["winner_score"]) < min_winner_score:
            continue
        if filters.get("exclude_avoid") and is_avoid(row):
            continue
        if filters.get("active_only") and row["status_label"] != "Active Setup":
            continue
        if filters.get("watch_only") and row["status_label"] != WATCH_ONLY_STATUS:
            continue
        if filters.get("high_risk_outlier_only") and not is_high_risk_outlier(row):
            continue
        filtered.append(row)
    return filtered


def sort_results(
    results: Iterable[dict[str, Any]],
    *,
    sort_by: str = "outlier_score",
    descending: bool = True,
) -> list[dict[str, Any]]:
    rows = [_normalize_result(row) for row in results]

    def sort_key(row: dict[str, Any]) -> tuple[Any, str]:
        value = row.get(sort_by, "")
        number = _to_float(value, default=None)
        return (number if number is not None else str(value), row["ticker"])

    return sorted(rows, key=sort_key, reverse=descending)


def build_daily_summary(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [_normalize_result(row) for row in results]
    investable = [row for row in rows if not is_avoid(row)]
    avoid_rows = [row for row in rows if is_avoid(row)]
    warnings = Counter(warning for row in rows for warning in row["warnings"])
    themes = Counter(tag for row in rows for tag in row["theme_tags"])

    return {
        "top_outlier_candidates": _compact_rows(sort_results(investable, sort_by="outlier_score")[:5]),
        "top_winner_candidates": _compact_rows(sort_results(investable, sort_by="winner_score")[:5]),
        "top_avoid_names": _compact_rows(sort_results(avoid_rows, sort_by="risk_score")[:5]),
        "common_theme_tags": themes.most_common(8),
        "common_warnings": warnings.most_common(8),
        "highest_risk_candidate": _compact_row(max(rows, key=lambda row: _to_float(row["risk_score"]), default=None)),
        "best_reward_risk_candidate": _compact_row(
            max(rows, key=lambda row: _to_float(row["reward_risk"]), default=None)
        ),
        "best_long_term_monster_candidate": _compact_row(
            max(
                (row for row in rows if row["outlier_type"] == "Long-Term Monster"),
                key=lambda row: _to_float(row["outlier_score"]),
                default=None,
            )
        ),
        "best_squeeze_watch_candidate": _compact_row(
            max(
                (row for row in rows if is_high_risk_outlier(row) and not is_avoid(row)),
                key=lambda row: _to_float(row["outlier_score"]),
                default=None,
            )
        ),
        "top_official_catalysts": _compact_rows(
            sort_results((row for row in rows if row["official_catalyst_found"]), sort_by="catalyst_score")[:5]
        ),
        "top_narrative_catalysts": _compact_rows(
            sort_results((row for row in rows if row["narrative_catalyst_found"]), sort_by="catalyst_score")[:5]
        ),
        "top_social_attention_names": _compact_rows(
            sort_results((row for row in rows if _to_float(row["social_attention_score"]) > 0), sort_by="social_attention_score")[:5]
        ),
        "highest_hype_risk_names": _compact_rows(
            sort_results((row for row in rows if row["hype_risk"] or row["pump_risk"]), sort_by="risk_score")[:5]
        ),
        "top_price_confirmed_catalysts": _compact_rows(
            sort_results((row for row in rows if row["price_volume_confirms_catalyst"]), sort_by="catalyst_score")[:5]
        ),
        "watch_only_attention_names": _compact_rows(
            sort_results(
                (row for row in rows if row["status_label"] == WATCH_ONLY_STATUS and _to_float(row["social_attention_score"]) > 0),
                sort_by="social_attention_score",
            )[:5]
        ),
    }


def build_market_regime(
    *,
    provider: MarketDataProvider | None,
    results: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    rows = [_normalize_result(row) for row in results]
    spy = _benchmark_summary(provider, "SPY") if provider else _unavailable_benchmark("SPY")
    qqq = _benchmark_summary(provider, "QQQ") if provider else _unavailable_benchmark("QQQ")
    bullish_count = sum(1 for item in (spy, qqq) if item["trend_state"] in {"Strong Uptrend", "Uptrend"})
    risk_off_count = sum(1 for item in (spy, qqq) if item["trend_state"] in {"Downtrend", "Below 200-DMA"})

    if bullish_count == 2:
        regime = "Bullish"
    elif risk_off_count >= 1:
        regime = "Risk-Off"
    else:
        regime = "Mixed"

    avoid_ratio = (sum(1 for row in rows if is_avoid(row)) / len(rows)) if rows else 0
    warnings: list[str] = []
    if spy["warning"]:
        warnings.append(spy["warning"])
    if qqq["warning"]:
        warnings.append(qqq["warning"])
    if avoid_ratio >= 0.45:
        warnings.append("High share of scanned names are flagged Avoid.")

    leading_tags = Counter(
        tag
        for row in rows
        if not is_avoid(row) and _to_float(row["outlier_score"]) >= 40
        for tag in row["theme_tags"]
    )
    weak_tags = Counter(tag for row in rows if is_avoid(row) for tag in row["theme_tags"])
    return {
        "regime": regime,
        "aggressive_longs_allowed": regime == "Bullish",
        "be_selective": regime in {"Mixed", "Bullish"},
        "mostly_watch_cash": regime == "Risk-Off",
        "spy": spy,
        "qqq": qqq,
        "leading_tags": [tag for tag, _ in leading_tags.most_common(6)],
        "weak_tags": [tag for tag, _ in weak_tags.most_common(6)],
        "risk_warnings": warnings,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "provider": provider.__class__.__name__ if provider else "report-only",
    }


def classify_avoid_reasons(row: dict[str, Any]) -> list[str]:
    normalized = _normalize_result(row)
    reasons: list[str] = []
    text_items = [*normalized["warnings"], *normalized["why_it_could_fail"], normalized["outlier_reason"]]
    text = " ".join(str(item).lower() for item in text_items)
    mapping = {
        "Falling knife": ("falling knife", "sharp downside", "waterfall"),
        "Broken trend": ("below the 200", "broken trend", "downtrend", "lost moving average"),
        "Failed breakout": ("failed breakout", "breakout attempt failed", "bad close after breakout"),
        "Poor reward/risk": ("poor reward", "reward/risk", "no clear invalidation"),
        "Overextended": ("overextended", "chase risk", "extended"),
        "Heavy selling volume": ("selling volume", "distribution", "gap and fade"),
        "Hype/pump risk": ("hype", "pump"),
        "Social-only hype": ("social-only", "social only"),
        "No clear invalidation": ("no clear invalidation", "invalidation unavailable"),
        "Low liquidity": ("low liquidity", "thin liquidity"),
        "Earnings too close": ("earnings are too close", "earnings too close"),
        "Bad close after breakout": ("weak breakout close", "bad close after breakout"),
    }
    for label, needles in mapping.items():
        if any(needle in text for needle in needles):
            reasons.append(label)
    if normalized["status_label"] == AVOID_STATUS and not reasons:
        reasons.append("Bad setup")
    return sorted(dict.fromkeys(reasons))


def extract_options_fields(row: dict[str, Any]) -> dict[str, Any]:
    options = _normalize_result(row).get("options_placeholders", {})
    if not isinstance(options, dict):
        return {}
    allowed = {
        "options_interest_available",
        "unusual_options_activity",
        "options_daytrade_candidate",
        "implied_volatility_warning",
        "earnings_iv_risk",
    }
    return {
        key: value
        for key, value in options.items()
        if key in allowed and str(value).lower() not in {"unavailable", "none", ""}
    }


def is_avoid(row: dict[str, Any]) -> bool:
    return _normalize_result(row)["status_label"] == AVOID_STATUS


def is_high_risk_outlier(row: dict[str, Any]) -> bool:
    normalized = _normalize_result(row)
    return (
        normalized["outlier_type"] in HIGH_RISK_OUTLIER_TYPES
        or normalized["outlier_risk"] in HIGH_RISK_LABELS
    )


def unique_values(results: Iterable[dict[str, Any]], key: str) -> list[str]:
    values = {str(_normalize_result(row).get(key, "")) for row in results}
    return sorted(value for value in values if value and value != "unavailable")


def unique_theme_tags(results: Iterable[dict[str, Any]]) -> list[str]:
    tags = {tag for row in results for tag in _normalize_result(row)["theme_tags"]}
    return sorted(tags)


def _benchmark_summary(provider: MarketDataProvider | None, ticker: str) -> dict[str, Any]:
    if provider is None:
        return _unavailable_benchmark(ticker)
    try:
        security = provider.get_security_data(ticker)
    except Exception as exc:
        summary = _unavailable_benchmark(ticker)
        summary["warning"] = f"{ticker} benchmark unavailable: {exc}"
        return summary
    closes = [bar.close for bar in security.bars]
    latest = closes[-1] if closes else None
    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200)
    return_1m = pct_change(closes, 21)
    return_3m = pct_change(closes, 63)
    above_50 = latest is not None and sma50 is not None and latest >= sma50
    above_200 = latest is not None and sma200 is not None and latest >= sma200
    if above_50 and above_200 and (return_1m or 0) > 0 and (return_3m or 0) > 0:
        trend_state = "Strong Uptrend"
    elif above_200 and ((return_1m or 0) >= 0 or above_50):
        trend_state = "Uptrend"
    elif not above_200:
        trend_state = "Below 200-DMA"
    else:
        trend_state = "Mixed"
    warning = ""
    if not above_200:
        warning = f"{ticker} is below its 200-day average."
    elif not above_50:
        warning = f"{ticker} is below its 50-day average."
    return {
        "ticker": ticker,
        "trend_state": trend_state,
        "latest_close": _round_or_unavailable(latest),
        "sma50": _round_or_unavailable(sma50),
        "sma200": _round_or_unavailable(sma200),
        "return_1m": _percent_or_unavailable(return_1m),
        "return_3m": _percent_or_unavailable(return_3m),
        "summary": _benchmark_sentence(ticker, trend_state, above_50, above_200),
        "warning": warning,
    }


def _unavailable_benchmark(ticker: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "trend_state": "Unavailable",
        "latest_close": "unavailable",
        "sma50": "unavailable",
        "sma200": "unavailable",
        "return_1m": "unavailable",
        "return_3m": "unavailable",
        "summary": f"{ticker} benchmark data unavailable in loaded report.",
        "warning": "",
    }


def _benchmark_sentence(ticker: str, trend_state: str, above_50: bool, above_200: bool) -> str:
    position = []
    position.append("above 50-DMA" if above_50 else "below 50-DMA")
    position.append("above 200-DMA" if above_200 else "below 200-DMA")
    return f"{ticker}: {trend_state}; {', '.join(position)}."


def _normalize_result(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    defaults: dict[str, Any] = {
        "ticker": "UNKNOWN",
        "company_name": "unavailable",
        "current_price": "unavailable",
        "status_label": WATCH_ONLY_STATUS,
        "strategy_label": "No Clean Strategy",
        "outlier_type": WATCH_ONLY_STATUS,
        "outlier_risk": "High",
        "outlier_score": 0,
        "winner_score": 0,
        "setup_quality_score": 0,
        "risk_score": 0,
        "bullish_score": 0,
        "bearish_pressure_score": 0,
        "confidence_label": "Low",
        "theme_tags": [],
        "catalyst_tags": [],
        "warnings": [],
        "why_it_passed": [],
        "why_it_could_fail": [],
        "why_it_could_be_a_big_winner": [],
        "signals_used": [],
        "data_availability_notes": [],
        "source_notes": [],
        "component_scores": {},
        "strategy_alignment": {},
        "data_used": {},
        "squeeze_watch": {},
        "options_placeholders": {},
        "catalyst_items": [],
        "catalyst_score": 0,
        "catalyst_quality": "Unavailable",
        "catalyst_type": "Unknown/unconfirmed",
        "catalyst_source_count": 0,
        "catalyst_recency": "unavailable",
        "official_catalyst_found": False,
        "narrative_catalyst_found": False,
        "hype_catalyst_found": False,
        "social_attention_available": False,
        "social_attention_score": 0,
        "social_attention_velocity": "unavailable",
        "news_attention_score": 0,
        "news_sentiment_label": "unavailable",
        "source_urls": [],
        "source_timestamps": [],
        "source_provider_notes": [],
        "catalyst_data_available": False,
        "catalyst_data_missing_reason": "Catalyst data unavailable.",
        "price_volume_confirms_catalyst": False,
        "attention_spike": False,
        "hype_risk": False,
        "pump_risk": False,
        "ai_explanation": {},
        "ai_explanation_available": False,
        "ai_explanation_provider": "unavailable",
        "entry_zone": "unavailable",
        "invalidation_level": "unavailable",
        "stop_loss_reference": "unavailable",
        "tp1": "unavailable",
        "tp2": "unavailable",
        "reward_risk": "unavailable",
        "holding_period": "unavailable",
        "outlier_reason": "unavailable",
        "chase_risk_warning": "unavailable",
        "provider_name": "unavailable",
    }
    for key, value in defaults.items():
        normalized.setdefault(key, value)
    for key in (
        "theme_tags",
        "catalyst_tags",
        "warnings",
        "why_it_passed",
        "why_it_could_fail",
        "why_it_could_be_a_big_winner",
        "signals_used",
        "data_availability_notes",
        "source_notes",
        "source_urls",
        "source_timestamps",
        "source_provider_notes",
    ):
        normalized[key] = _listify(normalized.get(key))
    if not isinstance(normalized["catalyst_items"], list):
        normalized["catalyst_items"] = []
    if not isinstance(normalized["ai_explanation"], dict):
        normalized["ai_explanation"] = {}
    normalized["ticker"] = str(normalized["ticker"]).upper()
    return normalized


def _compact_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_compact_row(row) for row in rows if row is not None]


def _compact_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    normalized = _normalize_result(row)
    return {
        "ticker": normalized["ticker"],
        "status": normalized["status_label"],
        "strategy": normalized["strategy_label"],
        "outlier_type": normalized["outlier_type"],
        "outlier_score": normalized["outlier_score"],
        "winner_score": normalized["winner_score"],
        "risk_score": normalized["risk_score"],
        "reward_risk": normalized["reward_risk"],
        "catalyst_score": normalized["catalyst_score"],
        "catalyst_quality": normalized["catalyst_quality"],
        "social_attention_score": normalized["social_attention_score"],
    }


def _infer_provider(payload: dict[str, Any], results: list[dict[str, Any]]) -> str:
    if payload.get("provider"):
        return str(payload["provider"])
    providers = {str(row.get("provider_name", "")) for row in results if row.get("provider_name")}
    if len(providers) == 1:
        return next(iter(providers))
    if providers:
        return ", ".join(sorted(providers))
    return "unavailable"


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        if not value or value == "unavailable":
            return []
        return [value]
    return [str(value)]


def _to_float(value: Any, default: float | None = 0) -> float:
    try:
        if value in (None, "unavailable", ""):
            raise ValueError
        return float(value)
    except (TypeError, ValueError):
        if default is None:
            return float("-inf")
        return default


def _round_or_unavailable(value: float | None) -> float | str:
    if value is None:
        return "unavailable"
    return round(value, 2)


def _percent_or_unavailable(value: float | None) -> float | str:
    if value is None:
        return "unavailable"
    return round(value * 100, 2)


def _safe_avg(values: list[float]) -> float | str:
    if not values:
        return "unavailable"
    return round(sum(values) / len(values), 4)
