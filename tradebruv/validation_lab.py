from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from .models import SecurityData
from .providers import MarketDataProvider
from .scanner import DeterministicScanner


DEFAULT_PREDICTIONS_PATH = Path("data/predictions.csv")
HORIZONS = (1, 5, 10, 20, 60, 120)
CASE_STUDY_TICKERS = ("CAR", "GME", "RDDT", "MU", "NVDA", "PLTR", "SMCI", "COIN", "HOOD", "ARM", "CAVA")

PREDICTION_FIELDS = [
    "prediction_id",
    "created_at",
    "ticker",
    "signal_price",
    "rule_based_recommendation",
    "ai_committee_recommendation",
    "final_combined_recommendation",
    "confidence_label",
    "winner_score",
    "outlier_score",
    "setup_quality",
    "risk_score",
    "strategy_label",
    "outlier_type",
    "catalyst_quality",
    "thesis",
    "invalidation",
    "TP1",
    "TP2",
    "expected_holding_period",
    "next_review_date",
    "events_to_watch",
    "data_quality",
    "evidence_snapshot",
    "recommendation_snapshot",
    "owned_at_signal",
    "portfolio_weight_at_signal",
    "return_1d",
    "return_5d",
    "return_10d",
    "return_20d",
    "return_60d",
    "return_120d",
    "max_favorable_excursion",
    "max_adverse_excursion",
    "hit_TP1",
    "hit_TP2",
    "hit_invalidation",
    "aged_well",
    "outcome_label",
    "last_updated_at",
]


def create_prediction_record(
    *,
    scanner_row: dict[str, Any],
    rule_based_recommendation: str,
    ai_committee_recommendation: str = "Data Insufficient",
    final_combined_recommendation: str | None = None,
    thesis: str = "",
    invalidation: float | str | None = None,
    tp1: float | str | None = None,
    tp2: float | str | None = None,
    expected_holding_period: str | None = None,
    events_to_watch: Iterable[str] | None = None,
    recommendation_snapshot: dict[str, Any] | str | None = None,
    owned_at_signal: bool = False,
    portfolio_weight_at_signal: float | str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or datetime.utcnow().isoformat() + "Z"
    ticker = str(scanner_row.get("ticker", "")).upper()
    record = {
        "prediction_id": f"{ticker}-{created.replace(':', '').replace('-', '').replace('.', '')[:20]}",
        "created_at": created,
        "ticker": ticker,
        "signal_price": scanner_row.get("current_price", ""),
        "rule_based_recommendation": rule_based_recommendation,
        "ai_committee_recommendation": ai_committee_recommendation,
        "final_combined_recommendation": final_combined_recommendation or rule_based_recommendation,
        "confidence_label": scanner_row.get("confidence_label", ""),
        "winner_score": scanner_row.get("winner_score", ""),
        "outlier_score": scanner_row.get("outlier_score", ""),
        "setup_quality": scanner_row.get("setup_quality_score", ""),
        "risk_score": scanner_row.get("risk_score", ""),
        "strategy_label": scanner_row.get("strategy_label", ""),
        "outlier_type": scanner_row.get("outlier_type", ""),
        "catalyst_quality": scanner_row.get("catalyst_quality", ""),
        "thesis": thesis,
        "invalidation": invalidation if invalidation not in (None, "") else scanner_row.get("invalidation_level", ""),
        "TP1": tp1 if tp1 not in (None, "") else scanner_row.get("tp1", ""),
        "TP2": tp2 if tp2 not in (None, "") else scanner_row.get("tp2", ""),
        "expected_holding_period": expected_holding_period or scanner_row.get("holding_period", ""),
        "next_review_date": _next_review_date(created, expected_holding_period or scanner_row.get("holding_period", "")),
        "events_to_watch": " | ".join(events_to_watch or []),
        "data_quality": _data_quality(scanner_row),
        "evidence_snapshot": json.dumps(_evidence_snapshot(scanner_row), sort_keys=True),
        "recommendation_snapshot": _snapshot_text(recommendation_snapshot),
        "owned_at_signal": str(bool(owned_at_signal)),
        "portfolio_weight_at_signal": portfolio_weight_at_signal,
        "return_1d": "",
        "return_5d": "",
        "return_10d": "",
        "return_20d": "",
        "return_60d": "",
        "return_120d": "",
        "max_favorable_excursion": "",
        "max_adverse_excursion": "",
        "hit_TP1": "",
        "hit_TP2": "",
        "hit_invalidation": "",
        "aged_well": "",
        "outcome_label": "Still Open",
        "last_updated_at": "",
    }
    return record


def _snapshot_text(value: dict[str, Any] | str | None) -> str:
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value or "")


def _next_review_date(created_at: str, expected_holding_period: str | None) -> str:
    signal_date = _parse_date(created_at) or date.today()
    text = str(expected_holding_period or "").lower()
    if "20" in text:
        days = 20
    elif "10" in text:
        days = 10
    elif "5" in text:
        days = 5
    elif "1" in text and "d" in text:
        days = 1
    else:
        days = 5
    return signal_date.fromordinal(signal_date.toordinal() + days).isoformat()


def load_predictions(path: Path = DEFAULT_PREDICTIONS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def save_predictions(records: Iterable[dict[str, Any]], path: Path = DEFAULT_PREDICTIONS_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PREDICTION_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in PREDICTION_FIELDS})
    return path


def add_prediction(record: dict[str, Any], path: Path = DEFAULT_PREDICTIONS_PATH) -> dict[str, Any]:
    records = load_predictions(path)
    records.append(record)
    save_predictions(records, path)
    return record


def update_prediction_outcomes(
    *,
    records: Iterable[dict[str, Any]],
    provider: MarketDataProvider,
    as_of_date: date | None = None,
) -> list[dict[str, Any]]:
    updated = []
    for record in records:
        updated.append(update_single_prediction(record=dict(record), provider=provider, as_of_date=as_of_date))
    return updated


def update_single_prediction(
    *,
    record: dict[str, Any],
    provider: MarketDataProvider,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    ticker = str(record.get("ticker", "")).upper()
    try:
        security = provider.get_security_data(ticker)
    except Exception as exc:
        record["outcome_label"] = "Data Unavailable"
        record["aged_well"] = f"Could not update: {exc}"
        record["last_updated_at"] = datetime.utcnow().isoformat() + "Z"
        return record
    signal_date = _parse_date(record.get("created_at")) or (security.bars[0].date if security.bars else None)
    signal_price = _to_float(record.get("signal_price"))
    if not signal_date or not signal_price:
        record["outcome_label"] = "Data Unavailable"
        record["aged_well"] = "Missing signal date or signal price."
        return record
    bars = [bar for bar in security.bars if bar.date >= signal_date and (as_of_date is None or bar.date <= as_of_date)]
    if not bars:
        record["outcome_label"] = "Data Unavailable"
        record["aged_well"] = "No bars available after signal date."
        return record

    for horizon in HORIZONS:
        field = f"return_{horizon}d"
        if len(bars) > horizon:
            record[field] = _round(((bars[horizon].close - signal_price) / signal_price) * 100)
        else:
            record[field] = ""
    max_high = max(bar.high for bar in bars)
    min_low = min(bar.low for bar in bars)
    record["max_favorable_excursion"] = _round(((max_high - signal_price) / signal_price) * 100)
    record["max_adverse_excursion"] = _round(((min_low - signal_price) / signal_price) * 100)
    tp1 = _to_float(record.get("TP1"))
    tp2 = _to_float(record.get("TP2"))
    invalidation = _to_float(record.get("invalidation"))
    record["hit_TP1"] = str(bool(tp1 and max_high >= tp1))
    record["hit_TP2"] = str(bool(tp2 and max_high >= tp2))
    record["hit_invalidation"] = str(bool(invalidation and min_low <= invalidation))
    record["outcome_label"] = _outcome_label(record)
    record["aged_well"] = _aged_well(record)
    record["last_updated_at"] = datetime.utcnow().isoformat() + "Z"
    return record


def validation_metrics(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(records)
    closed = [row for row in rows if row.get("outcome_label") not in {"", "Still Open"}]
    return {
        "open_predictions": [row for row in rows if row.get("outcome_label", "Still Open") == "Still Open"],
        "closed_predictions": closed,
        "by_recommendation_label": _bucket_metrics(rows, "final_combined_recommendation"),
        "by_ai_agreement": _bucket_metrics(rows, "ai_agreement"),
        "by_outlier_type": _bucket_metrics(rows, "outlier_type"),
        "by_catalyst_quality": _bucket_metrics(rows, "catalyst_quality"),
        "by_risk_bucket": _bucket_metrics(_with_risk_bucket(rows), "risk_bucket"),
        "best_examples": sorted(rows, key=lambda row: _to_float(row.get("return_20d")), reverse=True)[:5],
        "worst_examples": sorted(rows, key=lambda row: _to_float(row.get("return_20d")))[:5],
        "recent_predictions_needing_update": _predictions_needing_update(rows),
        "predictions_with_missing_outcome": [row for row in rows if row.get("outcome_label") in {"", "Still Open", "Data Unavailable"}],
        "predictions_with_hit_levels": [row for row in rows if row.get("hit_TP1") == "True" or row.get("hit_TP2") == "True" or row.get("hit_invalidation") == "True"],
        "sample_size_warning": "Small sample: do not tune rules from this yet." if len(closed) < 30 else "",
        "safety": "Paper validation only. Avoid look-ahead bias and do not treat this as proof.",
    }


def _predictions_needing_update(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    today = date.today()
    needing = []
    for row in rows:
        if row.get("outcome_label") not in {"", "Still Open", "Data Unavailable"}:
            continue
        next_review = _parse_date(row.get("next_review_date"))
        if not row.get("last_updated_at") or next_review is None or next_review <= today:
            needing.append(row)
    return needing


def famous_outlier_case_study(
    *,
    ticker: str,
    provider: MarketDataProvider,
    signal_date: date,
    end_date: date | None = None,
) -> dict[str, Any]:
    ticker = ticker.upper()
    if ticker not in CASE_STUDY_TICKERS:
        return {"ticker": ticker, "available": False, "reason": "Ticker is not in the default famous outlier case-study list."}
    try:
        security = provider.get_security_data(ticker)
    except Exception as exc:
        return {"ticker": ticker, "available": False, "reason": str(exc)}
    point_in_time = _point_in_time_security(security, signal_date)
    if len(point_in_time.bars) < 60:
        return {"ticker": ticker, "available": False, "reason": "Not enough point-in-time OHLCV bars before signal date."}
    point_provider = _SingleSecurityProvider(point_in_time)
    scanner_row = DeterministicScanner(point_provider, analysis_date=signal_date).scan([ticker], mode="outliers")[0].to_dict()
    prediction = create_prediction_record(
        scanner_row=scanner_row,
        rule_based_recommendation=scanner_row.get("status_label", "Data Insufficient"),
        created_at=signal_date.isoformat(),
        thesis="Famous outlier point-in-time scanner case study.",
    )
    outcome = update_single_prediction(record=prediction, provider=provider, as_of_date=end_date)
    return {
        "ticker": ticker,
        "available": True,
        "signal_date": signal_date.isoformat(),
        "end_date": end_date.isoformat() if end_date else "latest available",
        "point_in_time_note": "Uses only OHLCV/scanner fields available through the provider up to the selected signal date. Fundamentals/news are not point-in-time unless the provider supplied them historically.",
        "scanner_row": scanner_row,
        "outcome": outcome,
        "early_late_wrong": _early_late_wrong(outcome),
    }


class _SingleSecurityProvider:
    def __init__(self, security: SecurityData) -> None:
        self.security = security

    def get_security_data(self, ticker: str) -> SecurityData:
        requested = ticker.upper()
        if requested == self.security.ticker:
            return self.security
        raise ValueError(f"{requested} unavailable in point-in-time case-study provider.")


def _point_in_time_security(security: SecurityData, signal_date: date) -> SecurityData:
    return SecurityData(
        ticker=security.ticker,
        company_name=security.company_name,
        sector=security.sector,
        industry=security.industry,
        bars=[bar for bar in security.bars if bar.date <= signal_date],
        market_cap=security.market_cap,
        ipo_date=security.ipo_date,
        fundamentals=security.fundamentals,
        catalyst=None,
        next_earnings_date=None,
        short_interest=security.short_interest,
        social_attention=None,
        catalyst_items=[],
        options_data=None,
        theme_tags=security.theme_tags,
        catalyst_tags=[],
        provider_name=security.provider_name,
        source_notes=security.source_notes,
        data_notes=[
            *security.data_notes,
            "Case-study mode: OHLCV filtered to signal date; point-in-time fundamentals/news may be unavailable.",
        ],
    )


def _bucket_metrics(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get(field) or "Unclassified")
        buckets.setdefault(key, []).append(row)
    metrics = []
    for key, bucket in buckets.items():
        returns = [_to_float(row.get("return_20d")) for row in bucket if row.get("return_20d") not in ("", None)]
        metrics.append(
            {
                field: key,
                "sample_size": len(bucket),
                "avg_20d_return": _round(sum(returns) / len(returns)) if returns else "unavailable",
                "worked": sum(1 for row in bucket if row.get("outcome_label") == "Worked"),
                "failed": sum(1 for row in bucket if row.get("outcome_label") == "Failed"),
                "small_sample_warning": len(bucket) < 10,
            }
        )
    return sorted(metrics, key=lambda row: row["sample_size"], reverse=True)


def _with_risk_bucket(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for row in rows:
        risk = _to_float(row.get("risk_score"))
        bucket = "High" if risk >= 65 else "Medium" if risk >= 40 else "Low"
        enriched.append({**row, "risk_bucket": bucket})
    return enriched


def _outcome_label(record: dict[str, Any]) -> str:
    if record.get("hit_invalidation") == "True" and not record.get("hit_TP1") == "True":
        return "Failed"
    if record.get("hit_TP2") == "True" or _to_float(record.get("return_20d")) >= 10:
        return "Worked"
    if record.get("hit_TP1") == "True" and _to_float(record.get("return_20d")) >= 0:
        return "Worked"
    if _to_float(record.get("return_20d")) <= -8:
        return "Failed"
    if record.get("return_20d") not in ("", None):
        return "Mixed"
    return "Still Open"


def _aged_well(record: dict[str, Any]) -> str:
    outcome = record.get("outcome_label")
    if outcome == "Worked":
        return "Yes: forward outcome matched a constructive paper recommendation."
    if outcome == "Failed":
        return "No: invalidation/drawdown or poor forward return dominated."
    if outcome == "Mixed":
        return "Mixed: result was not clearly good or bad."
    return "Still open or unavailable."


def _early_late_wrong(record: dict[str, Any]) -> str:
    if record.get("outcome_label") == "Worked" and _to_float(record.get("max_adverse_excursion")) > -5:
        return "Reasonably timed"
    if record.get("outcome_label") == "Worked":
        return "Worked but with meaningful drawdown"
    if record.get("outcome_label") == "Failed":
        return "Wrong or too early"
    return "Still open / inconclusive"


def _data_quality(row: dict[str, Any]) -> str:
    if row.get("current_price") in (None, "", "unavailable"):
        return "Weak"
    notes = " ".join(map(str, row.get("data_availability_notes", []))).lower()
    if "unavailable" in notes:
        return "Partial"
    return "Good"


def _evidence_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "ticker",
        "current_price",
        "status_label",
        "strategy_label",
        "winner_score",
        "outlier_score",
        "setup_quality_score",
        "risk_score",
        "catalyst_quality",
        "warnings",
        "why_it_passed",
        "why_it_could_fail",
        "data_availability_notes",
    ]
    return {key: row.get(key) for key in keys}


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _to_float(value: Any) -> float:
    if value in (None, "", "unavailable"):
        return 0.0
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except ValueError:
        return 0.0


def _round(value: float) -> float:
    return round(float(value or 0), 4)
