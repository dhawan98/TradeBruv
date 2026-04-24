from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Iterable


SMALL_SAMPLE_THRESHOLD = 20
UNAVAILABLE = "unavailable"


def build_strategy_performance_report(review_payload: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in review_payload.get("results", []) if isinstance(row, dict)]
    performance_rows = aggregate_strategy_performance(rows)
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "review_source": review_payload.get("source_report", review_payload.get("review_type", UNAVAILABLE)),
        "disclaimer": (
            "Strategy performance summarizes historical scanner-review rows only. "
            "Small samples are unreliable, and results do not guarantee future returns."
        ),
        "small_sample_threshold": SMALL_SAMPLE_THRESHOLD,
        "results": performance_rows,
    }


def aggregate_strategy_performance(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not _is_available(row):
            continue
        horizon = _to_int(row.get("horizon_days"))
        if horizon is None:
            continue
        for dimension, bucket in _row_buckets(row):
            buckets[(dimension, bucket, horizon)].append(row)

    output = []
    for (dimension, bucket, horizon), bucket_rows in sorted(buckets.items()):
        output.append(_bucket_metrics(dimension, bucket, horizon, bucket_rows))
    return output


def write_performance_json(payload: dict[str, Any], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def write_performance_csv(payload: dict[str, Any], path: str | Path) -> Path:
    rows = list(payload.get("results", []))
    fieldnames = _performance_fieldnames(rows)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    return output_path


def _bucket_metrics(dimension: str, bucket: str, horizon: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [_to_float(row.get("forward_return_pct")) for row in rows]
    returns = [value for value in returns if value is not None]
    winners = [value for value in returns if value > 0]
    losers = [value for value in returns if value < 0]
    avg_winner = _avg(winners)
    avg_loser = _avg(losers)
    payoff_ratio = (
        round(avg_winner / abs(avg_loser), 4)
        if avg_winner not in (None, 0) and avg_loser not in (None, 0)
        else UNAVAILABLE
    )
    sample_size = len(returns)
    return {
        "dimension": dimension,
        "bucket": bucket,
        "horizon_days": horizon,
        "sample_size": sample_size,
        "small_sample_warning": sample_size < SMALL_SAMPLE_THRESHOLD,
        "average_forward_return": _round_or_unavailable(_avg(returns)),
        "median_forward_return": _round_or_unavailable(median(returns) if returns else None),
        "win_rate": _round_or_unavailable((len(winners) / sample_size) * 100 if sample_size else None),
        "average_winner": _round_or_unavailable(avg_winner),
        "average_loser": _round_or_unavailable(avg_loser),
        "payoff_ratio": payoff_ratio,
        "expectancy": _round_or_unavailable(_avg(returns)),
        "hit_tp1_rate": _rate(rows, "hit_tp1"),
        "hit_tp2_rate": _rate(rows, "hit_tp2"),
        "invalidation_rate": _rate(rows, "hit_stop_or_invalidation"),
        "max_adverse_excursion_average": _round_or_unavailable(
            _avg(_numbers(rows, "max_adverse_excursion_pct"))
        ),
        "max_favorable_excursion_average": _round_or_unavailable(
            _avg(_numbers(rows, "max_favorable_excursion_pct"))
        ),
        "best_result": _round_or_unavailable(max(returns) if returns else None),
        "worst_result": _round_or_unavailable(min(returns) if returns else None),
    }


def _row_buckets(row: dict[str, Any]) -> list[tuple[str, str]]:
    buckets = [
        ("strategy_label", _clean(row.get("strategy_label"))),
        ("outlier_type", _clean(row.get("outlier_type"))),
        ("status_label", _clean(row.get("status_label"))),
        ("confidence_label", _clean(row.get("confidence_label"))),
        ("risk_level", _clean(row.get("risk_level"))),
        ("catalyst_type", _clean(row.get("catalyst_type"))),
        ("catalyst_quality", _clean(row.get("catalyst_quality"))),
        ("provider", _clean(row.get("provider"))),
        ("universe_file", _clean(row.get("universe_file", UNAVAILABLE))),
        ("outlier_score_bucket", _score_bucket(row.get("outlier_score"), [(90, "90+"), (80, "80-89")])),
        ("winner_score_bucket", _score_bucket(row.get("winner_score"), [(80, "80+")])),
        ("setup_quality_bucket", _score_bucket(row.get("setup_quality_score"), [(80, "80+")])),
        ("risk_score_bucket", _risk_score_bucket(row.get("risk_score"))),
    ]
    for tag in _listify(row.get("theme_tags")):
        buckets.append(("theme_tags", tag))
    for warning in _listify(row.get("warnings")):
        buckets.append(("warnings", warning))
    return [(dimension, bucket) for dimension, bucket in buckets if bucket and bucket != UNAVAILABLE]


def _score_bucket(value: Any, thresholds: list[tuple[int, str]]) -> str:
    number = _to_float(value)
    if number is None:
        return UNAVAILABLE
    for minimum, label in thresholds:
        if number >= minimum:
            return label
    if len(thresholds) > 1 and number >= 80:
        return "80-89"
    return "below_threshold"


def _risk_score_bucket(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return UNAVAILABLE
    return "high" if number >= 60 else "low"


def _rate(rows: list[dict[str, Any]], key: str) -> float | str:
    if not rows:
        return UNAVAILABLE
    return round((sum(1 for row in rows if bool(row.get(key))) / len(rows)) * 100, 4)


def _numbers(rows: list[dict[str, Any]], key: str) -> list[float]:
    values = [_to_float(row.get(key)) for row in rows]
    return [value for value in values if value is not None]


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _round_or_unavailable(value: float | None) -> float | str:
    if value is None:
        return UNAVAILABLE
    return round(value, 4)


def _is_available(row: dict[str, Any]) -> bool:
    return bool(row.get("available")) and _to_float(row.get("forward_return_pct")) is not None


def _to_float(value: Any) -> float | None:
    if value in (None, "", UNAVAILABLE):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean(value: Any) -> str:
    if value in (None, ""):
        return UNAVAILABLE
    return str(value)


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


def _performance_fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "dimension",
        "bucket",
        "horizon_days",
        "sample_size",
        "small_sample_warning",
        "average_forward_return",
        "median_forward_return",
        "win_rate",
        "average_winner",
        "average_loser",
        "payoff_ratio",
        "expectancy",
        "hit_tp1_rate",
        "hit_tp2_rate",
        "invalidation_rate",
        "max_adverse_excursion_average",
        "max_favorable_excursion_average",
        "best_result",
        "worst_result",
    ]
    extra = sorted({key for row in rows for key in row if key not in preferred})
    return [*preferred, *extra]
