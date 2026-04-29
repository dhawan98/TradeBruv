from __future__ import annotations

from datetime import date, datetime
from typing import Any

LIVE_PROVIDER_NAMES = {"real"}
FAIL_MISMATCH_PCT = 0.10
WARN_MISMATCH_PCT = 0.05
SPLIT_FACTORS = (2, 3, 4, 5, 8, 10, 20)


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
    current_price = quote_price_if_available or latest_available_close
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
    return payload | build_price_sanity_from_row(payload | {"current_price": _round_or_unavailable(current_price)})


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
    data_mode = str(row.get("data_mode") or "unavailable")
    raw_price_source = str(row.get("price_source") or "unavailable")
    is_sample_data = bool(row.get("is_sample_data")) or provider == "sample"
    is_adjusted_price = bool(row.get("is_adjusted_price"))
    is_stale_price = bool(row.get("is_stale_price"))
    is_replay = bool(row.get("is_replay")) or "replay" in data_mode
    is_case_study = bool(row.get("is_case_study")) or "case_study" in data_mode
    is_report_only = bool(row.get("is_report_only")) or data_mode == "report_snapshot"
    report_snapshot_selected = bool(row.get("report_snapshot_selected"))
    provider_is_live_capable = bool(row.get("provider_is_live_capable")) or provider in LIVE_PROVIDER_NAMES
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

    validated_price = quote_price if quote_price is not None and quote_price > 0 else latest_close
    validated_price_source = "unavailable"
    if quote_price is not None and quote_price > 0:
        validated_price_source = "live quote"
    elif latest_close is not None and latest_close > 0:
        validated_price_source = "sample latest close" if is_sample_data else "latest close"

    displayed_price = current_price
    price_mismatch_pct = None
    if validated_price is not None and validated_price > 0 and displayed_price is not None and displayed_price > 0:
        price_mismatch_pct = abs(displayed_price - validated_price) / validated_price

    possible_split_adjustment_mismatch = _is_possible_split_adjustment_mismatch(
        displayed_price=displayed_price,
        validated_price=validated_price,
        mismatch_pct=price_mismatch_pct,
    )

    validation_reasons: list[str] = []
    if not provider_is_live_capable:
        validation_reasons.append("Provider is not live-capable.")
    if is_sample_data or raw_price_source == "sample latest close":
        validation_reasons.append("Demo sample data — not real prices.")
    if is_replay:
        validation_reasons.append("Historical replay output cannot be used as a live decision.")
    if is_case_study:
        validation_reasons.append("Case-study output cannot be used as a live decision.")
    if is_report_only and not report_snapshot_selected:
        validation_reasons.append("Report-only / historical snapshot.")
    if validated_price is None or validated_price <= 0:
        validation_reasons.append("No validated live price.")
    if is_stale_price:
        validation_reasons.append("Latest market price is stale.")
    if is_stale_scan:
        validation_reasons.append("Scan is stale.")
    if price_mismatch_pct is not None and price_mismatch_pct > FAIL_MISMATCH_PCT:
        validation_reasons.append(f"Displayed price mismatches validated price by {price_mismatch_pct * 100:.1f}%.")
    if possible_split_adjustment_mismatch:
        validation_reasons.append("Possible split/adjustment mismatch.")

    price_validation_status = "PASS"
    if validation_reasons:
        price_validation_status = "FAIL"
    elif price_mismatch_pct is not None and price_mismatch_pct > WARN_MISMATCH_PCT:
        price_validation_status = "WARN"
        validation_reasons.append(f"Displayed price differs from validated price by {price_mismatch_pct * 100:.1f}%.")
    elif latest_close is not None and quote_price is None and not is_sample_data:
        validation_reasons.append("Validated against latest close because live quote was unavailable.")

    price_validation_reason = "Validated live price." if not validation_reasons else " | ".join(dict.fromkeys(validation_reasons))
    levels_allowed = price_validation_status == "PASS"

    price_confidence = "High"
    if is_sample_data or current_price is None or current_price <= 0:
        price_confidence = "Low"
    elif price_validation_status != "PASS" or any("materially" in warning.lower() for warning in warnings):
        price_confidence = "Medium"

    price_source = raw_price_source
    if price_source == "unavailable":
        if is_sample_data:
            price_source = "sample latest close"
        elif quote_price is not None:
            price_source = "latest quote"
        elif latest_close is not None:
            price_source = "latest adjusted close" if is_adjusted_price else "latest close"

    return {
        "data_mode": data_mode,
        "price_source": price_source,
        "price_timestamp": quote_timestamp,
        "provider": provider,
        "provider_is_live_capable": provider_is_live_capable,
        "is_sample_data": is_sample_data,
        "is_adjusted_price": is_adjusted_price,
        "is_stale_price": is_stale_price,
        "is_replay": is_replay,
        "is_case_study": is_case_study,
        "is_report_only": is_report_only,
        "last_market_date": last_market_date.isoformat() if last_market_date else "unavailable",
        "latest_available_close": _round_or_unavailable(latest_close),
        "quote_price_if_available": _round_or_unavailable(quote_price),
        "validated_price": _round_or_unavailable(validated_price),
        "validated_price_source": validated_price_source,
        "displayed_price": _round_or_unavailable(displayed_price),
        "price_mismatch_pct": _round_pct(price_mismatch_pct),
        "possible_split_adjustment_mismatch": possible_split_adjustment_mismatch,
        "price_validation_status": price_validation_status,
        "price_validation_reason": price_validation_reason,
        "has_validated_live_price": levels_allowed,
        "levels_allowed": levels_allowed,
        "price_warning": " | ".join(warnings) if warnings else "No price sanity warning.",
        "price_warnings": warnings,
        "price_confidence": price_confidence,
        "scan_is_stale": is_stale_scan,
        "is_stale": bool(is_stale_price or is_stale_scan),
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


def _round_pct(value: float | None) -> float | str:
    return round(value * 100, 2) if value is not None else "unavailable"


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


def _is_possible_split_adjustment_mismatch(
    *,
    displayed_price: float | None,
    validated_price: float | None,
    mismatch_pct: float | None,
) -> bool:
    if (
        displayed_price is None
        or displayed_price <= 0
        or validated_price is None
        or validated_price <= 0
        or mismatch_pct is None
        or mismatch_pct <= FAIL_MISMATCH_PCT
    ):
        return False
    ratio = max(displayed_price, validated_price) / min(displayed_price, validated_price)
    for factor in SPLIT_FACTORS:
        if abs(ratio - factor) / factor <= 0.12:
            return True
    return False
