from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

from .cli import build_provider, load_universe
from .indicators import pct_change, sma
from .providers import MarketDataProvider
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
) -> DashboardReport:
    as_of = analysis_date or date.today()
    args = SimpleNamespace(
        provider=provider_name,
        data_dir=data_dir,
        history_period=history_period,
    )
    provider = build_provider(args=args, analysis_date=as_of)
    scanner = DeterministicScanner(provider=provider, analysis_date=as_of)
    results = scanner.scan(load_universe(universe_path), mode=mode)
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
    ):
        normalized[key] = _listify(normalized.get(key))
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
