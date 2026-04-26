from __future__ import annotations

from datetime import date, datetime
from typing import Any


def build_price_snapshot(
    *,
    provider_name: str,
    analysis_date: date | None,
    latest_available_close: float | None,
    last_market_date: date | None,
    quote_price_if_available: float | None = None,
    quote_timestamp: str | None = None,
    is_adjusted_price: bool = False,
) -> dict[str, Any]:
    is_sample_data = provider_name == "sample"
    is_stale_price = _business_days_between(last_market_date, analysis_date) > 1 if last_market_date and analysis_date else False
    price_source = "unavailable"
    if latest_available_close is not None:
        if is_sample_data:
            price_source = "sample latest close"
        elif quote_price_if_available is not None:
            price_source = "latest quote"
        elif is_adjusted_price:
            price_source = "latest adjusted close"
        else:
            price_source = "latest close"

    payload = {
        "price_source": price_source,
        "price_timestamp": quote_timestamp or (last_market_date.isoformat() if last_market_date else "unavailable"),
        "provider": provider_name,
        "is_sample_data": is_sample_data,
        "is_adjusted_price": bool(is_adjusted_price),
        "is_stale_price": bool(is_stale_price),
        "last_market_date": last_market_date.isoformat() if last_market_date else "unavailable",
        "latest_available_close": _round_or_unavailable(latest_available_close),
        "quote_price_if_available": _round_or_unavailable(quote_price_if_available),
    }
    return payload | build_price_sanity_from_row(payload | {"current_price": _round_or_unavailable(latest_available_close)})


def build_price_sanity_from_row(
    row: dict[str, Any],
    *,
    reference_date: date | None = None,
    scan_generated_at: str | None = None,
) -> dict[str, Any]:
    provider = str(row.get("provider") or row.get("provider_name") or row.get("data_used", {}).get("provider") or "unavailable")
    current_price = _to_float(row.get("current_price"))
    latest_close = _to_float(row.get("latest_available_close"))
    quote_price = _to_float(row.get("quote_price_if_available"))
    last_market_date = _parse_date(row.get("last_market_date"))
    quote_timestamp = str(row.get("price_timestamp") or "unavailable")
    is_sample_data = bool(row.get("is_sample_data")) or provider == "sample"
    is_adjusted_price = bool(row.get("is_adjusted_price"))
    is_stale_price = bool(row.get("is_stale_price"))
    if not is_stale_price and last_market_date and reference_date:
        is_stale_price = _business_days_between(last_market_date, reference_date) > 1

    warnings: list[str] = []
    if current_price is None or current_price <= 0:
        warnings.append("Data Insufficient: price unavailable.")
    if is_sample_data:
        warnings.append("Sample data — not real price.")
    if is_stale_price:
        warnings.append("Stale price data.")
    if latest_close is not None and quote_price is None and not is_sample_data:
        warnings.append("Latest close, not live quote.")
    if quote_price is not None and latest_close is not None and latest_close > 0:
        gap = abs(quote_price - latest_close) / latest_close
        if gap >= 0.05:
            warnings.append(f"Quote and latest close differ materially ({gap * 100:.1f}%).")
    if is_adjusted_price:
        warnings.append("Adjusted price series may include split-adjusted closes.")

    scan_generated = _parse_datetime(scan_generated_at)
    is_stale_scan = bool(
        scan_generated and reference_date and _business_days_between(scan_generated.date(), reference_date) > 1
    )
    if is_stale_scan:
        warnings.append("Stale scan.")

    price_confidence = "High"
    if is_sample_data or current_price is None or current_price <= 0:
        price_confidence = "Low"
    elif is_stale_price or is_stale_scan or any("materially" in warning.lower() for warning in warnings):
        price_confidence = "Medium"

    price_source = str(row.get("price_source") or "unavailable")
    if price_source == "unavailable":
        if is_sample_data:
            price_source = "sample latest close"
        elif quote_price is not None:
            price_source = "latest quote"
        elif latest_close is not None:
            price_source = "latest adjusted close" if is_adjusted_price else "latest close"

    return {
        "price_source": price_source,
        "price_timestamp": quote_timestamp,
        "provider": provider,
        "is_sample_data": is_sample_data,
        "is_adjusted_price": is_adjusted_price,
        "is_stale_price": is_stale_price,
        "last_market_date": last_market_date.isoformat() if last_market_date else "unavailable",
        "latest_available_close": _round_or_unavailable(latest_close),
        "quote_price_if_available": _round_or_unavailable(quote_price),
        "price_warning": " | ".join(warnings) if warnings else "No price sanity warning.",
        "price_warnings": warnings,
        "price_confidence": price_confidence,
        "scan_is_stale": is_stale_scan,
    }


def _parse_datetime(value: Any) -> datetime | None:
    if not value or value == "unavailable":
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    if not value or value == "unavailable":
        return None
    if isinstance(value, date):
        return value
    text = str(value)
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    if value in (None, "", "unavailable", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_or_unavailable(value: float | None) -> float | str:
    return round(value, 2) if value is not None else "unavailable"


def _business_days_between(start: date | None, end: date | None) -> int:
    if start is None or end is None or end <= start:
        return 0
    current = start
    business_days = 0
    while current < end:
        current = current.fromordinal(current.toordinal() + 1)
        if current.weekday() < 5:
            business_days += 1
    return business_days
