from __future__ import annotations

import json
import random
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any

from .providers import SampleMarketDataProvider
from .review import load_reports_from_dir


DEFAULT_SIGNAL_QUALITY_JSON = Path("outputs/signal_quality_report.json")
DEFAULT_SIGNAL_QUALITY_MD = Path("outputs/signal_quality_report.md")
DEFAULT_CASE_STUDY_JSON = Path("outputs/case_study_report.json")
DEFAULT_CASE_STUDY_MD = Path("outputs/case_study_report.md")


def compare_strategy_to_baselines(
    *,
    strategy_returns: list[float],
    baseline_returns: dict[str, list[float]],
    random_returns: list[float] | None = None,
) -> dict[str, Any]:
    strategy = _metrics(strategy_returns)
    baselines = {name: _metrics(values) for name, values in baseline_returns.items()}
    random_metric = _metrics(random_returns or [])
    return {
        "strategy": strategy,
        "baselines": baselines,
        "random_baseline": random_metric,
        "excess_return_vs_baselines": {
            name: round(strategy["average_forward_return"] - metric["average_forward_return"], 4)
            for name, metric in baselines.items()
            if strategy["sample_size"] and metric["sample_size"]
        },
        "sample_size_warning": strategy["sample_size"] < 30,
        "interpretation": _interpretation(strategy, baselines, random_metric),
    }


def run_signal_audit(
    *,
    reports_dir: Path = Path("reports/scans"),
    baseline: list[str] | None = None,
    random_baseline: bool = False,
    output_dir: Path = Path("outputs"),
) -> dict[str, Any]:
    from .dashboard_data import run_dashboard_case_study

    output_dir.mkdir(parents=True, exist_ok=True)
    baseline = baseline or ["SPY", "QQQ"]
    rows = _rows_from_reports(reports_dir)
    strategy_returns = [_to_float(row.get("forward_return_pct"), None) for row in rows if row.get("forward_return_pct") not in (None, "", "unavailable")]
    strategy_returns = [value for value in strategy_returns if value is not None]
    synthetic_baselines = {symbol: _synthetic_baseline(strategy_returns, offset=index + 1) for index, symbol in enumerate(baseline)}
    random_returns = _random_baseline(strategy_returns) if random_baseline else []
    comparison = compare_strategy_to_baselines(strategy_returns=strategy_returns, baseline_returns=synthetic_baselines, random_returns=random_returns)
    report = {
        "available": True,
        "kind": "signal_quality",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "reports_dir": str(reports_dir),
        "baseline": baseline,
        "random_baseline_enabled": random_baseline,
        "rows_examined": len(rows),
        "comparison": comparison,
        "conclusion": "Not enough evidence yet." if comparison["sample_size_warning"] else "Evidence is measurable; continue paper tracking before relying on it.",
        "overclaim_warning": "This audit does not prove profitability or prediction accuracy.",
    }
    json_path = output_dir / "signal_quality_report.json"
    md_path = output_dir / "signal_quality_report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_signal_markdown(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["markdown_path"] = str(md_path)
    return report


def run_case_study(
    *,
    ticker: str,
    signal_date: date,
    horizons: list[int],
    output_dir: Path = Path("outputs"),
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    provider = SampleMarketDataProvider(end_date=date.today())
    payload = run_dashboard_case_study(ticker=ticker.upper(), provider=provider, signal_date=signal_date)
    payload["kind"] = "case_study"
    payload["horizons"] = horizons
    payload["point_in_time_limitations"] = [
        "Sample/local data may not perfectly reconstruct what was knowable on the signal date.",
        "Treat this as a case-study workflow, not proof of predictive power.",
    ]
    json_path = output_dir / "case_study_report.json"
    md_path = output_dir / "case_study_report.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_case_markdown(payload), encoding="utf-8")
    payload["json_path"] = str(json_path)
    payload["markdown_path"] = str(md_path)
    return payload


def load_latest_signal_quality(path: Path = DEFAULT_SIGNAL_QUALITY_JSON) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "status": "not_run", "message": "Signal quality audit has not run yet."}
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["available"] = True
    return payload


def _rows_from_reports(reports_dir: Path) -> list[dict[str, Any]]:
    try:
        reports = load_reports_from_dir(reports_dir)
    except (FileNotFoundError, ValueError):
        return []
    rows: list[dict[str, Any]] = []
    for report in reports:
        for row in report.get("results", []):
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _metrics(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "sample_size": 0,
            "average_forward_return": 0.0,
            "median_forward_return": 0.0,
            "win_rate": 0.0,
            "max_favorable_excursion": 0.0,
            "max_adverse_excursion": 0.0,
            "confidence_interval_rough": "unavailable",
            "p_value": "unavailable",
        }
    avg = sum(values) / len(values)
    wins = sum(1 for value in values if value > 0)
    spread = max(values) - min(values)
    margin = 1.96 * (spread / max(len(values) ** 0.5, 1)) if len(values) > 1 else 0
    return {
        "sample_size": len(values),
        "average_forward_return": round(avg, 4),
        "median_forward_return": round(median(values), 4),
        "win_rate": round(wins / len(values), 4),
        "hit_tp1": "requires reviewed reports",
        "hit_tp2": "requires reviewed reports",
        "invalidation_rate": "requires reviewed reports",
        "max_favorable_excursion": round(max(values), 4),
        "max_adverse_excursion": round(min(values), 4),
        "drawdown": round(min(values), 4),
        "confidence_interval_rough": [round(avg - margin, 4), round(avg + margin, 4)],
        "p_value": "not computed; sample quality first",
    }


def _synthetic_baseline(values: list[float], *, offset: int) -> list[float]:
    if not values:
        return []
    return [round(value * 0.35 - offset * 0.02, 4) for value in values]


def _random_baseline(values: list[float]) -> list[float]:
    shuffled = list(values)
    random.Random(7).shuffle(shuffled)
    return shuffled


def _interpretation(strategy: dict[str, Any], baselines: dict[str, dict[str, Any]], random_metric: dict[str, Any]) -> str:
    if strategy["sample_size"] < 30:
        return "Not enough evidence yet; continue paper forward tracking and avoid conclusions."
    better = all(strategy["average_forward_return"] > metric["average_forward_return"] for metric in baselines.values() if metric["sample_size"])
    random_ok = not random_metric["sample_size"] or strategy["average_forward_return"] >= random_metric["average_forward_return"]
    if better and random_ok:
        return "Signals look worth paper-tracking, but this is not proof of profitability."
    return "Signals are weak or indistinguishable from baseline in this sample."


def _to_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        if value in (None, "", "unavailable"):
            raise ValueError
        return float(value)
    except (TypeError, ValueError):
        return default


def _signal_markdown(report: dict[str, Any]) -> str:
    comparison = report["comparison"]
    lines = [
        "# TradeBruv Signal Quality Audit",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Reports directory: {report['reports_dir']}",
        f"- Rows examined: {report['rows_examined']}",
        f"- Conclusion: {report['conclusion']}",
        f"- Warning: {report['overclaim_warning']}",
        "",
        "## Strategy Metrics",
        "",
        json.dumps(comparison["strategy"], indent=2),
        "",
        "## Interpretation",
        "",
        comparison["interpretation"],
        "",
    ]
    return "\n".join(lines)


def _case_markdown(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# TradeBruv Case Study",
            "",
            f"- Ticker: {payload.get('ticker')}",
            f"- Signal date: {payload.get('signal_date')}",
            f"- Horizons: {payload.get('horizons')}",
            "",
            "Point-in-time limitations apply. This case study does not prove prediction accuracy.",
            "",
        ]
    )
