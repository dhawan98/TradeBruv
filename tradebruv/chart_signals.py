from __future__ import annotations

from datetime import date
from typing import Any

from .indicators import average, clamp, ema, ema_series
from .models import PriceBar, SecurityData


def build_signal_snapshot(security: SecurityData) -> dict[str, Any]:
    bars = security.bars
    if not bars:
        return _unavailable_signal_snapshot()

    closes = [bar.close for bar in bars]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    volumes = [bar.volume for bar in bars]
    latest = bars[-1]
    previous = bars[-2] if len(bars) >= 2 else latest
    current_price = security.quote_price_if_available or security.latest_available_close or latest.close

    ema_21 = ema(closes, 21)
    ema_50 = ema(closes, 50)
    ema_150 = ema(closes, 150)
    ema_200 = ema(closes, 200)
    avg_volume20 = average(volumes[-20:])
    avg_volume50 = average(volumes[-50:])
    relative_volume_20d = (latest.volume / avg_volume20) if avg_volume20 else None
    relative_volume_50d = (latest.volume / avg_volume50) if avg_volume50 else None
    recent_high = max(highs[-21:-1]) if len(highs) >= 21 else max(highs[:-1]) if len(highs) > 1 else latest.high
    gap_up = latest.open >= previous.high * 1.02 if len(bars) >= 2 else False
    gap_down = latest.open <= previous.low * 0.98 if len(bars) >= 2 else False
    close_strength = close_location(latest)
    high_volume_red = bool(latest.close < latest.open and relative_volume_20d and relative_volume_20d >= 1.5)
    distribution_warning = _distribution_warning(bars, avg_volume20)

    bullish_stack = bool(
        ema_21 is not None
        and ema_50 is not None
        and ema_150 is not None
        and ema_200 is not None
        and current_price > ema_21 > ema_50 > ema_150 > ema_200
    )
    bearish_stack = bool(
        ema_21 is not None
        and ema_50 is not None
        and ema_150 is not None
        and ema_200 is not None
        and current_price < ema_21 < ema_50 < ema_150 < ema_200
    )
    ema_stack = "Bullish Stack" if bullish_stack else "Bearish Stack" if bearish_stack else "Mixed Stack"

    reclaim_ema_21 = _reclaim_signal(closes, 21)
    reclaim_ema_50 = _reclaim_signal(closes, 50)
    pullback_to_ema_21 = _pullback_signal(current_price, ema_21, ema_50)
    pullback_to_ema_50 = _pullback_signal(current_price, ema_50, ema_150, tolerance=0.025)
    breakout_with_volume = bool(current_price > recent_high * 1.005 and relative_volume_20d and relative_volume_20d >= 1.5 and close_strength >= 0.6)
    volume_expansion = bool(relative_volume_20d and relative_volume_20d >= 1.3)

    if ema_200 is not None and current_price < ema_200:
        signal_summary = "Below 200D / Avoid"
        signal_grade = "D"
    elif distribution_warning or high_volume_red:
        signal_summary = "Distribution Warning"
        signal_grade = "D"
    elif breakout_with_volume:
        signal_summary = "Breakout with Volume"
        signal_grade = "A"
    elif pullback_to_ema_21:
        signal_summary = "Pullback to EMA 21"
        signal_grade = "A-"
    elif pullback_to_ema_50:
        signal_summary = "Pullback to EMA 50"
        signal_grade = "B+"
    elif reclaim_ema_21:
        signal_summary = "Reclaiming EMA 21"
        signal_grade = "B"
    elif reclaim_ema_50:
        signal_summary = "Reclaiming EMA 50"
        signal_grade = "B"
    elif bullish_stack:
        signal_summary = "Bullish Trend Stack"
        signal_grade = "B"
    elif ema_21 is not None and current_price > ema_21 * 1.08:
        signal_summary = "Extended Above EMA 21"
        signal_grade = "C"
    elif ema_50 is not None and current_price > ema_50 * 1.14:
        signal_summary = "Extended Above EMA 50"
        signal_grade = "C"
    else:
        signal_summary = "No Clean Signal"
        signal_grade = "C-"

    trend_signal = "Bullish Trend Stack" if bullish_stack else "Below 200D / Avoid" if ema_200 is not None and current_price < ema_200 else "Mixed Trend"
    pullback_signal = "Pullback to EMA 21" if pullback_to_ema_21 else "Pullback to EMA 50" if pullback_to_ema_50 else "No Clean Pullback"
    breakout_signal = "Breakout with Volume" if breakout_with_volume else "No Clean Breakout"
    distribution_signal = "Distribution Warning" if distribution_warning or high_volume_red else "No Distribution Warning"
    volume_signal = "Volume Expansion" if volume_expansion else "Normal Volume"

    return {
        "ema_21": _round_or_unavailable(ema_21),
        "ema_50": _round_or_unavailable(ema_50),
        "ema_150": _round_or_unavailable(ema_150),
        "ema_200": _round_or_unavailable(ema_200),
        "ema_stack": ema_stack,
        "price_vs_ema_21_pct": _pct_vs(current_price, ema_21),
        "price_vs_ema_50_pct": _pct_vs(current_price, ema_50),
        "price_vs_ema_150_pct": _pct_vs(current_price, ema_150),
        "price_vs_ema_200_pct": _pct_vs(current_price, ema_200),
        "relative_volume_20d": _round_or_unavailable(relative_volume_20d, digits=2),
        "relative_volume_50d": _round_or_unavailable(relative_volume_50d, digits=2),
        "volume_signal": volume_signal,
        "trend_signal": trend_signal,
        "pullback_signal": pullback_signal,
        "breakout_signal": breakout_signal,
        "distribution_signal": distribution_signal,
        "signal_summary": signal_summary,
        "signal_grade": signal_grade,
        "close_below_ema_21": bool(ema_21 is not None and current_price < ema_21),
        "close_below_ema_50": bool(ema_50 is not None and current_price < ema_50),
        "close_below_ema_150": bool(ema_150 is not None and current_price < ema_150),
        "close_below_ema_200": bool(ema_200 is not None and current_price < ema_200),
        "reclaim_ema_21": reclaim_ema_21,
        "reclaim_ema_50": reclaim_ema_50,
        "pullback_to_ema_21": pullback_to_ema_21,
        "pullback_to_ema_50": pullback_to_ema_50,
        "breakout_with_volume": breakout_with_volume,
        "gap_up": gap_up,
        "gap_down": gap_down,
        "close_strength": round(close_strength, 3),
        "high_volume_red_candle_warning": high_volume_red,
        "distribution_warning": distribution_warning,
    }


def build_chart_payload(
    security: SecurityData,
    *,
    timeframes: tuple[str, ...] = ("6M", "1Y", "2Y"),
) -> dict[str, Any]:
    bars = security.bars
    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    ema21 = ema_series(closes, 21)
    ema50 = ema_series(closes, 50)
    ema150 = ema_series(closes, 150)
    ema200 = ema_series(closes, 200)
    markers = _signal_markers(bars)
    signal_snapshot = build_signal_snapshot(security)
    return {
        "ticker": security.ticker,
        "provider": security.provider_name,
        "last_market_date": security.last_market_date.isoformat() if security.last_market_date else "unavailable",
        "quote_timestamp": security.quote_timestamp or "unavailable",
        "price_source": "live quote" if security.quote_price_if_available is not None else "latest close",
        "signals": signal_snapshot,
        "markers": markers,
        "series": [
            {
                "date": bar.date.isoformat(),
                "open": round(bar.open, 2),
                "high": round(bar.high, 2),
                "low": round(bar.low, 2),
                "close": round(bar.close, 2),
                "volume": round(bar.volume, 2),
                "ema_21": _round_or_none(ema21[index]),
                "ema_50": _round_or_none(ema50[index]),
                "ema_150": _round_or_none(ema150[index]),
                "ema_200": _round_or_none(ema200[index]),
            }
            for index, bar in enumerate(bars)
        ],
        "available_timeframes": list(timeframes),
    }


def close_location(bar: PriceBar) -> float:
    spread = bar.high - bar.low
    if spread <= 0:
        return 0.5
    return clamp((bar.close - bar.low) / spread, 0.0, 1.0)


def _distribution_warning(bars: list[PriceBar], avg_volume20: float | None) -> bool:
    if len(bars) < 5 or not avg_volume20:
        return False
    count = 0
    for previous, current in zip(bars[-6:-1], bars[-5:]):
        if current.close < previous.close and current.close < current.open and current.volume >= avg_volume20 * 1.2:
            count += 1
    return count >= 2


def _reclaim_signal(closes: list[float], window: int) -> bool:
    if len(closes) < window + 3:
        return False
    previous_ema = ema(closes[:-1], window)
    current_ema = ema(closes, window)
    if previous_ema is None or current_ema is None:
        return False
    return closes[-2] < previous_ema and closes[-1] > current_ema


def _pullback_signal(price: float, ema_value: float | None, trend_reference: float | None, *, tolerance: float = 0.018) -> bool:
    if ema_value is None or trend_reference is None:
        return False
    return price >= trend_reference and abs(price - ema_value) / ema_value <= tolerance


def _pct_vs(price: float, ema_value: float | None) -> float | str:
    if ema_value in (None, 0):
        return "unavailable"
    return round(((price / ema_value) - 1.0) * 100, 2)


def _round_or_unavailable(value: float | None, *, digits: int = 2) -> float | str:
    if value is None:
        return "unavailable"
    return round(value, digits)


def _round_or_none(value: float | None, *, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _signal_markers(bars: list[PriceBar]) -> list[dict[str, Any]]:
    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    markers: list[dict[str, Any]] = []
    avg_volume20 = average(volumes[-20:])
    for index in range(max(1, len(bars) - 40), len(bars)):
        window_bars = bars[: index + 1]
        current = window_bars[-1]
        prev = window_bars[-2]
        close_values = closes[: index + 1]
        ema21 = ema(close_values, 21)
        ema50 = ema(close_values, 50)
        rel_vol = (current.volume / avg_volume20) if avg_volume20 else None
        recent_high = max(bar.high for bar in window_bars[-21:-1]) if len(window_bars) >= 21 else None
        if recent_high and current.close > recent_high * 1.005 and rel_vol and rel_vol >= 1.5:
            markers.append({"date": current.date.isoformat(), "label": "Breakout", "tone": "good"})
        if ema21 is not None and prev.close < ema21 <= current.close:
            markers.append({"date": current.date.isoformat(), "label": "Reclaim 21", "tone": "neutral"})
        if ema50 is not None and prev.close < ema50 <= current.close:
            markers.append({"date": current.date.isoformat(), "label": "Reclaim 50", "tone": "neutral"})
        if current.close < current.open and rel_vol and rel_vol >= 1.5:
            markers.append({"date": current.date.isoformat(), "label": "Distribution", "tone": "bad"})
    return markers[-12:]


def _unavailable_signal_snapshot() -> dict[str, Any]:
    return {
        "ema_21": "unavailable",
        "ema_50": "unavailable",
        "ema_150": "unavailable",
        "ema_200": "unavailable",
        "ema_stack": "Mixed Stack",
        "price_vs_ema_21_pct": "unavailable",
        "price_vs_ema_50_pct": "unavailable",
        "price_vs_ema_150_pct": "unavailable",
        "price_vs_ema_200_pct": "unavailable",
        "relative_volume_20d": "unavailable",
        "relative_volume_50d": "unavailable",
        "volume_signal": "No Clean Signal",
        "trend_signal": "No Clean Signal",
        "pullback_signal": "No Clean Signal",
        "breakout_signal": "No Clean Signal",
        "distribution_signal": "No Clean Signal",
        "signal_summary": "No Clean Signal",
        "signal_grade": "F",
    }
