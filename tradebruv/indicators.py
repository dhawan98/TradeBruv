from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Iterable, Sequence

from .models import PriceBar


def average(values: Iterable[float]) -> float | None:
    values = _finite_values(values)
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
    current = _finite_float(values[-1])
    previous = _finite_float(values[-periods - 1])
    if current is None or previous is None:
        return None
    if previous == 0:
        return None
    return (current / previous) - 1.0


def sma(values: Sequence[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return average(values[-window:])


def ema(values: Sequence[float], window: int) -> float | None:
    if len(values) < window or window <= 0:
        return None
    finite_values = _finite_series(values)
    if finite_values is None:
        return None
    multiplier = 2.0 / (window + 1)
    current = mean(finite_values[:window])
    for value in finite_values[window:]:
        current = (value - current) * multiplier + current
    return current


def ema_series(values: Sequence[float], window: int) -> list[float | None]:
    if window <= 0:
        return [None for _ in values]
    if len(values) < window:
        return [None for _ in values]
    finite_values = _finite_series(values)
    if finite_values is None:
        return [None for _ in values]
    multiplier = 2.0 / (window + 1)
    seed = mean(finite_values[:window])
    output: list[float | None] = [None for _ in range(window - 1)] + [seed]
    current = seed
    for value in finite_values[window:]:
        current = (value - current) * multiplier + current
        output.append(current)
    return output


def sample_stddev(values: Sequence[float]) -> float | None:
    finite_values = _finite_values(values)
    if len(finite_values) < 2:
        return None
    return pstdev(finite_values)


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


def _finite_series(values: Sequence[float]) -> list[float] | None:
    output: list[float] = []
    for value in values:
        number = _finite_float(value)
        if number is None:
            return None
        output.append(number)
    return output


def _finite_values(values: Iterable[float]) -> list[float]:
    output: list[float] = []
    for value in values:
        number = _finite_float(value)
        if number is not None:
            output.append(number)
    return output


def _finite_float(value: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number
