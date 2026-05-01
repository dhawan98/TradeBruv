from __future__ import annotations

import json
import math
import os
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import (
    AlternativeDataItem,
    CatalystItem,
    CatalystSnapshot,
    FundamentalsSnapshot,
    OptionsSnapshot,
    PriceBar,
    SecurityData,
    ShortInterestSnapshot,
    SocialAttentionSnapshot,
)
from .providers import MarketDataProvider


DEFAULT_MARKET_CACHE_DIR = Path("data/cache/market")


class FileCacheMarketDataProvider:
    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        provider_name: str,
        history_period: str = "3y",
        interval: str = "1d",
        cache_dir: Path = DEFAULT_MARKET_CACHE_DIR,
        ttl_minutes: int | None = None,
        refresh_cache: bool = False,
    ) -> None:
        self.provider = provider
        self.provider_name = provider_name
        self.history_period = history_period
        self.interval = interval
        self.cache_dir = cache_dir
        self.refresh_cache = refresh_cache
        self.ttl_minutes = ttl_minutes if ttl_minutes is not None else int(os.getenv("TRADEBRUV_MARKET_CACHE_TTL_MINUTES", "60"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_hits = 0
        self.cache_misses = 0
        self.cache_stale_hits = 0
        self.cache_fallback_hits = 0

    def get_security_data(self, ticker: str) -> SecurityData:
        ticker = ticker.upper()
        fresh = self.load_cached_security(ticker, allow_stale=False)
        if not self.refresh_cache and fresh is not None:
            self.cache_hits += 1
            return fresh
        self.cache_misses += 1
        try:
            security = self.provider.get_security_data(ticker)
        except Exception:
            cached_fallback = self.load_cached_security(
                ticker,
                allow_stale=bool(_truthy_env("TRADEBRUV_ALLOW_CACHE_ON_PROVIDER_FAILURE", default=True)),
                max_age_hours=int(os.getenv("TRADEBRUV_MAX_CACHE_AGE_HOURS", "24")),
            )
            if cached_fallback is None:
                raise
            self.cache_fallback_hits += 1
            return _with_cache_note(cached_fallback, "cached stale" if self.is_cached_stale(ticker) else "cached fresh")
        payload = {
            "cached_at": datetime.utcnow().isoformat() + "Z",
            "ticker": ticker,
            "provider": self.provider_name,
            "history_period": self.history_period,
            "interval": self.interval,
            "security": _security_to_dict(security),
        }
        self._cache_path(ticker).write_text(json.dumps(payload), encoding="utf-8")
        return security

    def cache_stats(self) -> dict[str, Any]:
        return {
            "cache_dir": str(self.cache_dir),
            "ttl_minutes": self.ttl_minutes,
            "hits": self.cache_hits,
            "misses": self.cache_misses,
            "stale_hits": self.cache_stale_hits,
            "fallback_hits": self.cache_fallback_hits,
            "refresh_cache": self.refresh_cache,
        }

    def load_cached_security(
        self,
        ticker: str,
        *,
        allow_stale: bool,
        max_age_hours: int | None = None,
    ) -> SecurityData | None:
        cached = self.load_cached_entry(ticker)
        if cached is None:
            return None
        created_at = _coerce_cached_at(cached)
        if created_at is None:
            return None
        age = datetime.utcnow() - created_at
        fresh = age <= timedelta(minutes=self.ttl_minutes)
        within_stale_window = max_age_hours is None or age <= timedelta(hours=max_age_hours)
        if fresh:
            security = _security_from_dict(cached["security"])
            return security if security.bars else None
        if allow_stale and within_stale_window:
            self.cache_stale_hits += 1
            security = _security_from_dict(cached["security"])
            return _with_cache_note(security, "cached stale") if security.bars else None
        return None

    def load_cached_entry(self, ticker: str) -> dict[str, Any] | None:
        cache_path = self._cache_path(ticker.upper())
        if not cache_path.exists():
            return None
        return json.loads(cache_path.read_text(encoding="utf-8"))

    def is_cached_stale(self, ticker: str) -> bool:
        cached = self.load_cached_entry(ticker)
        if cached is None:
            return False
        created_at = _coerce_cached_at(cached)
        if created_at is None:
            return False
        return datetime.utcnow() - created_at > timedelta(minutes=self.ttl_minutes)

    def health_report(self) -> dict[str, Any]:
        report = getattr(self.provider, "health_report", None)
        if callable(report):
            return report()
        return {"provider": self.provider_name, "status": "healthy"}

    def should_stop_scan(self) -> bool:
        return bool(getattr(self.provider, "should_stop_scan", lambda: False)())

    def prefetch_many(self, tickers: list[str], *, batch_size: int = 25) -> None:
        prefetch = getattr(self.provider, "prefetch_many", None)
        if not callable(prefetch):
            return
        pending = [ticker.upper() for ticker in tickers if ticker and (self.refresh_cache or self.load_cached_security(ticker.upper(), allow_stale=False) is None)]
        if not pending:
            return
        prefetch(pending, batch_size=batch_size)
        for ticker in pending:
            fresh = getattr(self.provider, "get_security_data", None)
            if not callable(fresh):
                continue
            try:
                security = fresh(ticker)
            except Exception:
                continue
            payload = {
                "cached_at": datetime.utcnow().isoformat() + "Z",
                "ticker": ticker,
                "provider": self.provider_name,
                "history_period": self.history_period,
                "interval": self.interval,
                "security": _security_to_dict(security),
            }
            self._cache_path(ticker).write_text(json.dumps(payload), encoding="utf-8")

    def _cache_path(self, ticker: str) -> Path:
        key = f"{self.provider_name}_{ticker}_{self.history_period}_{self.interval}.json".replace("/", "_")
        return self.cache_dir / key


def _coerce_cached_at(payload: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(payload["cached_at"]).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _truthy_env(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _with_cache_note(security: SecurityData, cache_source: str) -> SecurityData:
    notes = list(security.data_notes)
    note = f"Loaded from {cache_source} market cache."
    if note not in notes:
        notes.append(note)
    return SecurityData(
        ticker=security.ticker,
        company_name=security.company_name,
        sector=security.sector,
        industry=security.industry,
        bars=security.bars,
        market_cap=security.market_cap,
        ipo_date=security.ipo_date,
        fundamentals=security.fundamentals,
        catalyst=security.catalyst,
        next_earnings_date=security.next_earnings_date,
        short_interest=security.short_interest,
        social_attention=security.social_attention,
        catalyst_items=security.catalyst_items,
        alternative_data_items=security.alternative_data_items,
        options_data=security.options_data,
        theme_tags=security.theme_tags,
        catalyst_tags=security.catalyst_tags,
        provider_name=security.provider_name,
        source_notes=list(security.source_notes),
        data_notes=notes,
        quote_price_if_available=security.quote_price_if_available,
        quote_timestamp=security.quote_timestamp,
        latest_available_close=security.latest_available_close,
        last_market_date=security.last_market_date,
        is_adjusted_price=security.is_adjusted_price,
    )


def _security_to_dict(security: SecurityData) -> dict[str, Any]:
    return {
        "ticker": security.ticker,
        "company_name": security.company_name,
        "sector": security.sector,
        "industry": security.industry,
        "bars": [
            {
                "date": bar.date.isoformat(),
                "open": _float_or_none(bar.open),
                "high": _float_or_none(bar.high),
                "low": _float_or_none(bar.low),
                "close": _float_or_none(bar.close),
                "volume": _float_or_none(bar.volume),
            }
            for bar in security.bars
            if _valid_bar_payload(
                {
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
            )
        ],
        "market_cap": _float_or_none(security.market_cap),
        "ipo_date": security.ipo_date.isoformat() if security.ipo_date else None,
        "fundamentals": asdict(security.fundamentals) if security.fundamentals else None,
        "catalyst": asdict(security.catalyst) if security.catalyst else None,
        "next_earnings_date": security.next_earnings_date.isoformat() if security.next_earnings_date else None,
        "short_interest": asdict(security.short_interest) if security.short_interest else None,
        "social_attention": asdict(security.social_attention) if security.social_attention else None,
        "catalyst_items": [asdict(item) for item in security.catalyst_items],
        "alternative_data_items": [asdict(item) for item in security.alternative_data_items],
        "options_data": asdict(security.options_data) if security.options_data else None,
        "theme_tags": security.theme_tags,
        "catalyst_tags": security.catalyst_tags,
        "provider_name": security.provider_name,
        "source_notes": security.source_notes,
        "data_notes": security.data_notes,
        "quote_price_if_available": _float_or_none(security.quote_price_if_available),
        "quote_timestamp": security.quote_timestamp,
        "latest_available_close": _float_or_none(security.latest_available_close),
        "last_market_date": security.last_market_date.isoformat() if security.last_market_date else None,
        "is_adjusted_price": security.is_adjusted_price,
    }


def _security_from_dict(payload: dict[str, Any]) -> SecurityData:
    return SecurityData(
        ticker=str(payload["ticker"]),
        company_name=payload.get("company_name"),
        sector=payload.get("sector"),
        industry=payload.get("industry"),
        bars=[
            PriceBar(
                date=date.fromisoformat(str(bar["date"])),
                open=float(bar["open"]),
                high=float(bar["high"]),
                low=float(bar["low"]),
                close=float(bar["close"]),
                volume=float(bar["volume"]),
            )
            for bar in payload.get("bars", [])
            if _valid_bar_payload(bar)
        ],
        market_cap=_float_or_none(payload.get("market_cap")),
        ipo_date=date.fromisoformat(payload["ipo_date"]) if payload.get("ipo_date") else None,
        fundamentals=FundamentalsSnapshot(**payload["fundamentals"]) if payload.get("fundamentals") else None,
        catalyst=CatalystSnapshot(**payload["catalyst"]) if payload.get("catalyst") else None,
        next_earnings_date=date.fromisoformat(payload["next_earnings_date"]) if payload.get("next_earnings_date") else None,
        short_interest=ShortInterestSnapshot(**payload["short_interest"]) if payload.get("short_interest") else None,
        social_attention=SocialAttentionSnapshot(**payload["social_attention"]) if payload.get("social_attention") else None,
        catalyst_items=[CatalystItem(**item) for item in payload.get("catalyst_items", [])],
        alternative_data_items=[AlternativeDataItem(**item) for item in payload.get("alternative_data_items", [])],
        options_data=OptionsSnapshot(**payload["options_data"]) if payload.get("options_data") else None,
        theme_tags=list(payload.get("theme_tags", [])),
        catalyst_tags=list(payload.get("catalyst_tags", [])),
        provider_name=str(payload.get("provider_name") or "unavailable"),
        source_notes=list(payload.get("source_notes", [])),
        data_notes=list(payload.get("data_notes", [])),
        quote_price_if_available=_float_or_none(payload.get("quote_price_if_available")),
        quote_timestamp=payload.get("quote_timestamp"),
        latest_available_close=_float_or_none(payload.get("latest_available_close")),
        last_market_date=date.fromisoformat(payload["last_market_date"]) if payload.get("last_market_date") else None,
        is_adjusted_price=bool(payload.get("is_adjusted_price", False)),
    )


def _float_or_none(value: Any) -> float | None:
    if value in (None, "", "unavailable"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _valid_bar_payload(bar: dict[str, Any]) -> bool:
    fields = ("open", "high", "low", "close", "volume")
    try:
        return all(_float_or_none(bar.get(field)) is not None for field in fields)
    except Exception:
        return False
