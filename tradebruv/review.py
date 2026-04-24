from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from .models import PriceBar
from .providers import MarketDataProvider


DEFAULT_HORIZONS = (1, 5, 10, 20, 60, 120)
UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class LoadedScanReport:
    path: Path
    generated_at: str
    mode: str
    provider: str
    rows: list[dict[str, Any]]


def load_scan_report(path: str | Path) -> LoadedScanReport:
    report_path = Path(path)
    if report_path.suffix.lower() == ".csv":
        return _load_csv_report(report_path)
    return _load_json_report(report_path)


def load_reports_from_dir(path: str | Path) -> list[LoadedScanReport]:
    reports_dir = Path(path)
    candidates = sorted(
        item
        for item in reports_dir.rglob("*")
        if item.is_file() and item.suffix.lower() in {".json", ".csv"}
    )
    reports: list[LoadedScanReport] = []
    for candidate in candidates:
        try:
            report = load_scan_report(candidate)
        except Exception:
            continue
        if not _looks_like_scan_report(report):
            continue
        reports.append(report)
    return reports


def review_report(
    *,
    report: LoadedScanReport,
    provider: MarketDataProvider,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    signal_date: date | None = None,
) -> dict[str, Any]:
    parsed_horizons = sorted({int(horizon) for horizon in horizons if int(horizon) > 0})
    effective_signal_date = signal_date or _parse_report_date(report.generated_at)
    rows: list[dict[str, Any]] = []
    for scan_row in report.rows:
        rows.extend(
            review_scan_row(
                scan_row=scan_row,
                provider=provider,
                horizons=parsed_horizons,
                signal_date=effective_signal_date,
                report=report,
            )
        )
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "review_type": "saved_scan_forward_review",
        "disclaimer": (
            "Historical review evaluates what happened after saved scanner rows. "
            "It is not a predictive backtest and does not guarantee future performance."
        ),
        "source_report": str(report.path),
        "source_report_generated_at": report.generated_at,
        "signal_date": effective_signal_date.isoformat(),
        "horizons": parsed_horizons,
        "results": rows,
    }


def review_reports(
    *,
    reports: Iterable[LoadedScanReport],
    provider: MarketDataProvider,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    signal_date: date | None = None,
) -> dict[str, Any]:
    parsed_reports = list(reports)
    parsed_horizons = sorted({int(horizon) for horizon in horizons if int(horizon) > 0})
    rows: list[dict[str, Any]] = []
    for report in parsed_reports:
        rows.extend(
            review_report(
                report=report,
                provider=provider,
                horizons=parsed_horizons,
                signal_date=signal_date,
            )["results"]
        )
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "review_type": "saved_scan_forward_review_batch",
        "disclaimer": (
            "Historical review evaluates what happened after saved scanner rows. "
            "It is not a predictive backtest and does not guarantee future performance."
        ),
        "source_report_count": len(parsed_reports),
        "horizons": parsed_horizons,
        "results": rows,
    }


def review_scan_row(
    *,
    scan_row: dict[str, Any],
    provider: MarketDataProvider,
    horizons: Iterable[int],
    signal_date: date,
    report: LoadedScanReport | None = None,
) -> list[dict[str, Any]]:
    normalized = normalize_scan_row(scan_row)
    base = _base_review_row(normalized, signal_date=signal_date, report=report)
    try:
        security = provider.get_security_data(normalized["ticker"])
        bars = sorted(security.bars, key=lambda bar: bar.date)
    except Exception as exc:
        return [
            {
                **base,
                "horizon_days": horizon,
                "available": False,
                "unavailable_reason": f"Historical data unavailable: {exc}",
                **_empty_metrics(),
            }
            for horizon in horizons
        ]

    return [
        {
            **base,
            "horizon_days": horizon,
            **calculate_forward_metrics(
                bars=bars,
                signal_date=signal_date,
                signal_close=_to_float(normalized["current_price"]),
                tp1=_to_float(normalized["tp1"]),
                tp2=_to_float(normalized["tp2"]),
                invalidation_level=_to_float(normalized["invalidation_level"]),
                stop_reference=_to_float(normalized["stop_loss_reference"]),
                horizon_days=horizon,
            ),
        }
        for horizon in horizons
    ]


def calculate_forward_metrics(
    *,
    bars: list[PriceBar],
    signal_date: date,
    signal_close: float | None,
    tp1: float | None,
    tp2: float | None,
    invalidation_level: float | None,
    stop_reference: float | None,
    horizon_days: int,
) -> dict[str, Any]:
    if signal_close is None or signal_close <= 0:
        return {"available": False, "unavailable_reason": "Signal close unavailable.", **_empty_metrics()}

    future_bars = [bar for bar in sorted(bars, key=lambda item: item.date) if bar.date > signal_date]
    if len(future_bars) < horizon_days:
        return {
            "available": False,
            "unavailable_reason": f"Only {len(future_bars)} forward trading days available.",
            **_empty_metrics(),
        }

    window = future_bars[:horizon_days]
    final_bar = window[-1]
    best_close_bar = max(window, key=lambda bar: bar.close)
    worst_close_bar = min(window, key=lambda bar: bar.close)
    best_high_bar = max(window, key=lambda bar: bar.high)
    worst_low_bar = min(window, key=lambda bar: bar.low)
    stop_level = invalidation_level if invalidation_level is not None else stop_reference

    tp1_bar = _first_bar_at_or_above(window, tp1)
    tp2_bar = _first_bar_at_or_above(window, tp2)
    invalidation_bar = _first_bar_at_or_below(window, stop_level)

    return {
        "available": True,
        "unavailable_reason": "",
        "forward_return_pct": _pct(final_bar.close, signal_close),
        "max_favorable_excursion_pct": _pct(best_high_bar.high, signal_close),
        "max_adverse_excursion_pct": _pct(worst_low_bar.low, signal_close),
        "hit_tp1": tp1_bar is not None,
        "hit_tp2": tp2_bar is not None,
        "hit_stop_or_invalidation": invalidation_bar is not None,
        "days_to_tp1": _days_to(window, tp1_bar),
        "days_to_tp2": _days_to(window, tp2_bar),
        "days_to_invalidation": _days_to(window, invalidation_bar),
        "best_close_after_signal": round(best_close_bar.close, 4),
        "worst_close_after_signal": round(worst_close_bar.close, 4),
        "final_close_at_horizon": round(final_bar.close, 4),
    }


def write_review_json(payload: dict[str, Any], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def write_review_csv(payload: dict[str, Any], path: str | Path) -> Path:
    rows = list(payload.get("results", []))
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _review_fieldnames(rows)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})
    return output_path


def normalize_scan_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    defaults: dict[str, Any] = {
        "ticker": "UNKNOWN",
        "company_name": UNAVAILABLE,
        "current_price": UNAVAILABLE,
        "strategy_label": "No Clean Strategy",
        "outlier_type": "Watch Only",
        "status_label": "Watch Only",
        "winner_score": 0,
        "outlier_score": 0,
        "setup_quality_score": 0,
        "risk_score": 0,
        "outlier_risk": UNAVAILABLE,
        "confidence_label": UNAVAILABLE,
        "entry_zone": UNAVAILABLE,
        "invalidation_level": UNAVAILABLE,
        "stop_loss_reference": UNAVAILABLE,
        "tp1": UNAVAILABLE,
        "tp2": UNAVAILABLE,
        "reward_risk": UNAVAILABLE,
        "catalyst_quality": UNAVAILABLE,
        "catalyst_type": "Unknown/unconfirmed",
        "theme_tags": [],
        "warnings": [],
        "provider_name": UNAVAILABLE,
    }
    for key, value in defaults.items():
        normalized.setdefault(key, value)
    for key in ("theme_tags", "warnings"):
        normalized[key] = _listify(normalized.get(key))
    normalized["ticker"] = str(normalized["ticker"]).upper()
    return normalized


def _load_json_report(path: Path) -> LoadedScanReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = [normalize_scan_row(row) for row in payload.get("results", []) if isinstance(row, dict)]
    providers = {str(row.get("provider_name")) for row in rows if row.get("provider_name")}
    return LoadedScanReport(
        path=path,
        generated_at=str(payload.get("generated_at") or datetime.utcfromtimestamp(path.stat().st_mtime).date()),
        mode=str(payload.get("mode", UNAVAILABLE)),
        provider=str(payload.get("provider") or ", ".join(sorted(providers)) or UNAVAILABLE),
        rows=rows,
    )


def _looks_like_scan_report(report: LoadedScanReport) -> bool:
    return bool(report.rows) and any(row.get("current_price") != UNAVAILABLE for row in report.rows)


def _load_csv_report(path: Path) -> LoadedScanReport:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [normalize_scan_row(dict(row)) for row in csv.DictReader(handle)]
    providers = {str(row.get("provider_name")) for row in rows if row.get("provider_name")}
    return LoadedScanReport(
        path=path,
        generated_at=datetime.utcfromtimestamp(path.stat().st_mtime).date().isoformat(),
        mode=UNAVAILABLE,
        provider=", ".join(sorted(providers)) or UNAVAILABLE,
        rows=rows,
    )


def _base_review_row(
    row: dict[str, Any],
    *,
    signal_date: date,
    report: LoadedScanReport | None,
) -> dict[str, Any]:
    return {
        "ticker": row["ticker"],
        "company_name": row["company_name"],
        "signal_date": signal_date.isoformat(),
        "signal_close": row["current_price"],
        "strategy_label": row["strategy_label"],
        "outlier_type": row["outlier_type"],
        "status_label": row["status_label"],
        "winner_score": row["winner_score"],
        "outlier_score": row["outlier_score"],
        "setup_quality_score": row["setup_quality_score"],
        "risk_score": row["risk_score"],
        "risk_level": row["outlier_risk"],
        "confidence_label": row["confidence_label"],
        "entry_zone": row["entry_zone"],
        "invalidation_level": row["invalidation_level"],
        "stop_reference": row["stop_loss_reference"],
        "tp1": row["tp1"],
        "tp2": row["tp2"],
        "reward_risk": row["reward_risk"],
        "catalyst_quality": row["catalyst_quality"],
        "catalyst_type": row["catalyst_type"],
        "theme_tags": row["theme_tags"],
        "warnings": row["warnings"],
        "provider": row["provider_name"],
        "source_report": str(report.path) if report else UNAVAILABLE,
        "source_report_generated_at": report.generated_at if report else UNAVAILABLE,
        "report_mode": report.mode if report else UNAVAILABLE,
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "forward_return_pct": UNAVAILABLE,
        "max_favorable_excursion_pct": UNAVAILABLE,
        "max_adverse_excursion_pct": UNAVAILABLE,
        "hit_tp1": False,
        "hit_tp2": False,
        "hit_stop_or_invalidation": False,
        "days_to_tp1": UNAVAILABLE,
        "days_to_tp2": UNAVAILABLE,
        "days_to_invalidation": UNAVAILABLE,
        "best_close_after_signal": UNAVAILABLE,
        "worst_close_after_signal": UNAVAILABLE,
        "final_close_at_horizon": UNAVAILABLE,
    }


def _first_bar_at_or_above(bars: list[PriceBar], level: float | None) -> PriceBar | None:
    if level is None:
        return None
    return next((bar for bar in bars if bar.high >= level), None)


def _first_bar_at_or_below(bars: list[PriceBar], level: float | None) -> PriceBar | None:
    if level is None:
        return None
    return next((bar for bar in bars if bar.low <= level), None)


def _days_to(bars: list[PriceBar], target: PriceBar | None) -> int | str:
    if target is None:
        return UNAVAILABLE
    return bars.index(target) + 1


def _pct(value: float, base: float) -> float:
    return round(((value / base) - 1.0) * 100, 4)


def _parse_report_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return date.today()


def _to_float(value: Any) -> float | None:
    if value in (None, "", UNAVAILABLE):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        if not value or value == UNAVAILABLE:
            return []
        if " | " in value:
            return [item.strip() for item in value.split("|") if item.strip()]
        return [value]
    return [str(value)]


def _review_fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "ticker",
        "company_name",
        "signal_date",
        "horizon_days",
        "available",
        "unavailable_reason",
        "signal_close",
        "forward_return_pct",
        "max_favorable_excursion_pct",
        "max_adverse_excursion_pct",
        "hit_tp1",
        "hit_tp2",
        "hit_stop_or_invalidation",
        "days_to_tp1",
        "days_to_tp2",
        "days_to_invalidation",
        "best_close_after_signal",
        "worst_close_after_signal",
        "final_close_at_horizon",
        "strategy_label",
        "outlier_type",
        "status_label",
        "winner_score",
        "outlier_score",
        "setup_quality_score",
        "risk_score",
        "risk_level",
        "confidence_label",
        "catalyst_quality",
        "catalyst_type",
        "theme_tags",
        "warnings",
        "provider",
        "source_report",
    ]
    extra = sorted({key for row in rows for key in row if key not in preferred})
    return [*preferred, *extra]


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return " | ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return value
