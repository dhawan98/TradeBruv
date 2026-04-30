from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from .models import AlternativeDataItem, SecurityData
from .providers import MarketDataProvider


DEFAULT_ALTERNATIVE_DATA_PATH = Path("config/alternative_data_watchlist.csv")
INSIDER_ACTOR_TYPES = {"CEO", "CFO", "Director", "Officer", "10% Owner"}
POLITICIAN_ACTOR_TYPES = {"Senator", "Representative", "Politician"}
BUY_TYPES = {"Buy"}
SELL_TYPES = {"Sell", "Disposal"}
PASSIVE_TYPES = {"Option Exercise", "Award", "Gift"}
STALE_DISCLOSURE_DAYS = 45


class AlternativeDataRepository:
    def __init__(self, items_by_ticker: dict[str, list[AlternativeDataItem]] | None = None, warnings: list[str] | None = None) -> None:
        self.items_by_ticker = items_by_ticker or {}
        self.warnings = warnings or []

    def items_for(self, ticker: str) -> list[AlternativeDataItem]:
        return list(self.items_by_ticker.get(ticker.upper(), []))


class AlternativeDataOverlayProvider:
    def __init__(self, base_provider: MarketDataProvider, repository: AlternativeDataRepository) -> None:
        self.base_provider = base_provider
        self.repository = repository

    def get_security_data(self, ticker: str) -> SecurityData:
        security = self.base_provider.get_security_data(ticker)
        items = self.repository.items_for(ticker)
        if not items:
            return security
        notes = [*security.data_notes, f"Alternative data overlay loaded {len(items)} source item(s)."]
        tags = sorted(dict.fromkeys([*security.catalyst_tags, "Insider/politician activity"]))
        return replace(security, alternative_data_items=[*security.alternative_data_items, *items], catalyst_tags=tags, data_notes=notes)

    def prefetch_many(self, tickers: list[str], *, batch_size: int = 25) -> None:
        prefetch = getattr(self.base_provider, "prefetch_many", None)
        if callable(prefetch):
            prefetch(tickers, batch_size=batch_size)


def load_alternative_data_repository(path: Path | None = DEFAULT_ALTERNATIVE_DATA_PATH) -> AlternativeDataRepository:
    if path is None or not path.exists():
        return AlternativeDataRepository()
    rows = _read_json_rows(path) if path.suffix.lower() == ".json" else _read_csv_rows(path)
    warnings: list[str] = []
    items_by_ticker: dict[str, list[AlternativeDataItem]] = {}
    for index, row in enumerate(rows, start=2):
        try:
            item = parse_alternative_data_row(row)
        except ValueError as exc:
            warnings.append(f"{path}:{index}: {exc}")
            continue
        items_by_ticker.setdefault(item.ticker, []).append(item)
    return AlternativeDataRepository(items_by_ticker, warnings)


def parse_alternative_data_row(row: dict[str, Any]) -> AlternativeDataItem:
    ticker = str(row.get("ticker", "")).strip().upper()
    if not ticker:
        raise ValueError("ticker is required")
    return AlternativeDataItem(
        ticker=ticker,
        source_type=_clean(row.get("source_type")) or "manual",
        source_name=_clean(row.get("source_name")),
        source_url=_clean(row.get("source_url")),
        timestamp=_clean(row.get("timestamp")),
        actor_name=_clean(row.get("actor_name")),
        actor_role=_normalize_choice(row.get("actor_role"), INSIDER_ACTOR_TYPES | POLITICIAN_ACTOR_TYPES | {"Institution", "Unknown"}, "Unknown"),
        actor_type=_normalize_choice(row.get("actor_type"), INSIDER_ACTOR_TYPES | POLITICIAN_ACTOR_TYPES | {"Institution", "Unknown"}, "Unknown"),
        transaction_type=_normalize_choice(row.get("transaction_type"), BUY_TYPES | SELL_TYPES | PASSIVE_TYPES | {"Unknown"}, "Unknown"),
        shares=_to_float(row.get("shares")),
        estimated_value=_to_float(row.get("estimated_value")),
        price=_to_float(row.get("price")),
        filing_date=_clean(row.get("filing_date")),
        transaction_date=_clean(row.get("transaction_date")),
        disclosure_lag_days=_to_int(row.get("disclosure_lag_days")),
        confidence=_to_float(row.get("confidence")),
        notes=_clean(row.get("notes")),
    )


def build_alternative_data_signal(*, security: SecurityData, features: Any, status_label: str) -> tuple[dict[str, Any], list[str]]:
    items = list(security.alternative_data_items)
    warnings: list[str] = []
    insider_items = [item for item in items if item.actor_type in INSIDER_ACTOR_TYPES or item.actor_role in INSIDER_ACTOR_TYPES]
    politician_items = [item for item in items if item.actor_type in POLITICIAN_ACTOR_TYPES or item.actor_role in POLITICIAN_ACTOR_TYPES]
    insider_buys = [item for item in insider_items if item.transaction_type in BUY_TYPES]
    insider_sells = [item for item in insider_items if item.transaction_type in SELL_TYPES]
    politician_buys = [item for item in politician_items if item.transaction_type in BUY_TYPES]
    politician_sells = [item for item in politician_items if item.transaction_type in SELL_TYPES]

    net_insider = _net_value(insider_buys, insider_sells)
    net_politician = _net_value(politician_buys, politician_sells)
    ceo_cfo_buy = any((item.actor_type in {"CEO", "CFO"} or item.actor_role in {"CEO", "CFO"}) and item.transaction_type in BUY_TYPES for item in items)
    cluster_buying = len({item.actor_name or item.actor_role for item in insider_buys}) >= 2 or len(insider_buys) >= 3
    insider_buy_value = sum(item.estimated_value or 0 for item in insider_buys)
    insider_sell_value = sum(item.estimated_value or 0 for item in insider_sells)
    heavy_selling = insider_sell_value >= 250_000 and insider_sell_value > max(insider_buy_value * 1.5, 250_000)
    price_confirms = bool(
        features.volume_confirmation
        and (
            features.breakout_confirmed
            or features.close_near_week_high
            or (features.return_5d is not None and features.return_5d > 0)
        )
    )
    stale_lags = [item.disclosure_lag_days for item in items if item.disclosure_lag_days is not None and item.disclosure_lag_days > STALE_DISCLOSURE_DAYS]
    if stale_lags:
        warnings.append("Alternative-data disclosure is stale or delayed.")
    for item in items:
        if not item.source_url:
            warnings.append(f"{item.ticker} alternative-data source URL unavailable.")
        if not item.filing_date:
            warnings.append(f"{item.ticker} filing date unavailable.")
        if item.actor_role == "Unknown" or item.actor_type == "Unknown":
            warnings.append(f"{item.ticker} actor role/type is unknown.")
        if item.transaction_type in PASSIVE_TYPES:
            warnings.append(f"{item.ticker} {item.transaction_type} is passive context, not an open-market buy/sell signal.")
    if heavy_selling:
        warnings.append("Heavy insider selling is present; treat as risk/context, not automatic sell.")
    if politician_buys or politician_sells:
        warnings.append("Politician trades can be delayed and are attention/context, not automatic buy/sell evidence.")
    if items and not price_confirms:
        warnings.append("Alternative data is not confirmed by price and volume.")
    if status_label == "Avoid" and (ceo_cfo_buy or cluster_buying or politician_buys):
        warnings.append("Alternative data cannot override hard deterministic Avoid status.")

    quality = "Unavailable"
    if items:
        quality = "Strong" if price_confirms and (ceo_cfo_buy or cluster_buying) else "Context Only" if price_confirms else "Unconfirmed"
    summary_bits = []
    if ceo_cfo_buy:
        summary_bits.append("CEO/CFO open-market buy present")
    if cluster_buying:
        summary_bits.append("cluster insider buying present")
    if heavy_selling:
        summary_bits.append("heavy insider selling present")
    if politician_buys or politician_sells:
        summary_bits.append("politician activity present")

    return {
        "items": [item.to_dict() for item in items],
        "summary": "; ".join(summary_bits) if summary_bits else ("Alternative data loaded as context." if items else "No insider, politician, or alternative-data evidence loaded."),
        "alternative_data_quality": quality,
        "alternative_data_source_count": len(items),
        "insider_buy_count": len(insider_buys),
        "insider_sell_count": len(insider_sells),
        "net_insider_value": round(net_insider, 2),
        "CEO_CFO_buy_flag": ceo_cfo_buy,
        "cluster_buying_flag": cluster_buying,
        "heavy_insider_selling_flag": heavy_selling,
        "politician_buy_count": len(politician_buys),
        "politician_sell_count": len(politician_sells),
        "net_politician_value": round(net_politician, 2),
        "recent_politician_activity": bool(politician_buys or politician_sells),
        "disclosure_lag_warning": "Delayed disclosure present." if stale_lags else "",
        "alternative_data_confirmed_by_price_volume": price_confirms,
        "warnings": sorted(dict.fromkeys(warnings)),
    }, sorted(dict.fromkeys(warnings))


def write_alternative_data_template(path: Path = DEFAULT_ALTERNATIVE_DATA_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    fieldnames = [
        "ticker",
        "source_type",
        "source_name",
        "source_url",
        "timestamp",
        "actor_name",
        "actor_role",
        "actor_type",
        "transaction_type",
        "shares",
        "estimated_value",
        "price",
        "filing_date",
        "transaction_date",
        "disclosure_lag_days",
        "confidence",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
    return path


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_json_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else list(payload.get("items", []))


def _normalize_choice(value: Any, allowed: set[str], default: str) -> str:
    text = _clean(value)
    if not text:
        return default
    lowered = {item.lower(): item for item in allowed}
    return lowered.get(text.lower(), default)


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"", "none", "nan", "unavailable"} else text


def _to_float(value: Any) -> float | None:
    text = _clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    parsed = _to_float(value)
    return int(parsed) if parsed is not None else None


def _net_value(buys: list[AlternativeDataItem], sells: list[AlternativeDataItem]) -> float:
    return sum(item.estimated_value or 0 for item in buys) - sum(item.estimated_value or 0 for item in sells)
