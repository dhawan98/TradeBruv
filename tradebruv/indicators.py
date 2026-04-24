from __future__ import annotations

from statistics import mean, pstdev
from typing import Iterable, Sequence

from .models import PriceBar


def average(values: Iterable[float]) -> float | None:
    values = list(values)
    if not values:
        return None
    return mean(values)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def close_location(bar: PriceBar) -> float:
    spread = bar.high - bar.low
    if spread <= 0:
        return 0.5
    return clamp((bar.close - bar.low) / spread, 0.0, 1.0)


def pct_change(values: Sequence[float], periods: int) -> float | None:
    if len(values) <= periods:
        return None
    previous = values[-periods - 1]
    if previous == 0:
        return None
    return (values[-1] / previous) - 1.0


def sma(values: Sequence[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return mean(values[-window:])


def sample_stddev(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    return pstdev(values)


def atr(bars: Sequence[PriceBar], window: int = 14) -> float | None:
    if len(bars) < window + 1:
        return None

    true_ranges: list[float] = []
    for previous, current in zip(bars[-window - 1 : -1], bars[-window:]):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return average(true_ranges)

