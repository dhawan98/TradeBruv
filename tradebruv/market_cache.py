from __future__ import annotations

import json
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

    def get_security_data(self, ticker: str) -> SecurityData:
        ticker = ticker.upper()
        cache_path = self._cache_path(ticker)
        if not self.refresh_cache and cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            created_at = datetime.fromisoformat(str(cached["cached_at"]).replace("Z", "+00:00"))
            if datetime.utcnow() - created_at.replace(tzinfo=None) <= timedelta(minutes=self.ttl_minutes):
                self.cache_hits += 1
                return _security_from_dict(cached["security"])
        self.cache_misses += 1
        security = self.provider.get_security_data(ticker)
        payload = {
            "cached_at": datetime.utcnow().isoformat() + "Z",
            "ticker": ticker,
            "provider": self.provider_name,
            "history_period": self.history_period,
            "interval": self.interval,
            "security": _security_to_dict(security),
        }
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        return security

    def cache_stats(self) -> dict[str, Any]:
        return {
            "cache_dir": str(self.cache_dir),
            "ttl_minutes": self.ttl_minutes,
            "hits": self.cache_hits,
            "misses": self.cache_misses,
            "refresh_cache": self.refresh_cache,
        }

    def _cache_path(self, ticker: str) -> Path:
        key = f"{self.provider_name}_{ticker}_{self.history_period}_{self.interval}.json".replace("/", "_")
        return self.cache_dir / key


def _security_to_dict(security: SecurityData) -> dict[str, Any]:
    return {
        "ticker": security.ticker,
        "company_name": security.company_name,
        "sector": security.sector,
        "industry": security.industry,
        "bars": [
            {
                "date": bar.date.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in security.bars
        ],
        "market_cap": security.market_cap,
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
        "quote_price_if_available": security.quote_price_if_available,
        "quote_timestamp": security.quote_timestamp,
        "latest_available_close": security.latest_available_close,
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
    return float(value)
