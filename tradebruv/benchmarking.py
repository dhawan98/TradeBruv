from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .market_cache import FileCacheMarketDataProvider
from .market_reliability import classify_provider_error
from .models import SecurityData
from .providers import BENCHMARK_SYMBOLS, CORE_BENCHMARK_SYMBOLS


BENCHMARK_DEGRADED_WARNING = "Sector benchmark data unavailable/rate-limited; relative strength features degraded."
MAJOR_SECTOR_BENCHMARKS = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")
DEFAULT_BENCHMARK_SYMBOLS = (*CORE_BENCHMARK_SYMBOLS, *MAJOR_SECTOR_BENCHMARKS)


@dataclass
class BenchmarkLoadRecord:
    symbol: str
    security: SecurityData | None
    status: str
    reason: str = ""
    fresh_cache: bool = False


class BenchmarkDataManager:
    def __init__(self, provider: Any) -> None:
        self.provider = provider
        self._records: dict[str, BenchmarkLoadRecord] = {}
        self.benchmark_cache_hits = 0
        self.benchmark_cache_misses = 0
        self.benchmark_failures = 0
        self.benchmark_rate_limit_detected = False
        self.benchmark_degraded = False
        self.benchmark_health = "healthy"

    def get(self, symbol: str | None) -> SecurityData | None:
        clean = str(symbol or "").strip().upper()
        if not clean:
            return None
        existing = self._records.get(clean)
        if existing is not None:
            self.benchmark_cache_hits += 1
            return existing.security

        if self._has_fresh_disk_cache(clean):
            self.benchmark_cache_hits += 1
            security = self.provider.get_security_data(clean)
            self._records[clean] = BenchmarkLoadRecord(symbol=clean, security=security, status="cache_hit", fresh_cache=True)
            return security

        self.benchmark_cache_misses += 1
        if self.benchmark_rate_limit_detected:
            self._record_failure(clean, status="rate_limited", reason="Skipped after benchmark provider rate limit was detected.")
            return None

        live_provider = _unwrap_live_provider(self.provider)
        try:
            security = live_provider.get_security_data(clean)
        except Exception as exc:
            classification = classify_provider_error(exc)
            status = "rate_limited" if str(classification.get("status")) == "rate_limited" else "failed"
            self._record_failure(clean, status=status, reason=str(exc))
            return None

        self._records[clean] = BenchmarkLoadRecord(symbol=clean, security=security, status="fetched_live")
        cache_provider = _find_file_cache_provider(self.provider)
        if cache_provider is not None:
            cache_provider.store_security(security, ticker=clean)
        return security

    def status_for(self, symbol: str) -> str:
        record = self._records.get(symbol.upper())
        return record.status if record is not None else "unrequested"

    def reason_for(self, symbol: str) -> str:
        record = self._records.get(symbol.upper())
        return record.reason if record is not None else ""

    def as_dict(self) -> dict[str, Any]:
        loaded = [symbol for symbol, record in self._records.items() if record.security is not None]
        failed = [symbol for symbol, record in self._records.items() if record.security is None]
        return {
            "benchmark_health": self.benchmark_health,
            "benchmark_cache_hits": self.benchmark_cache_hits,
            "benchmark_cache_misses": self.benchmark_cache_misses,
            "benchmark_failures": self.benchmark_failures,
            "benchmark_rate_limit_detected": self.benchmark_rate_limit_detected,
            "benchmark_symbols_loaded": loaded,
            "benchmark_symbols_failed": failed,
            "benchmark_degraded": self.benchmark_degraded,
            "benchmark_warning": BENCHMARK_DEGRADED_WARNING if self.benchmark_degraded else "",
        }

    def _record_failure(self, symbol: str, *, status: str, reason: str) -> None:
        if symbol not in self._records:
            self.benchmark_failures += 1
        self._records[symbol] = BenchmarkLoadRecord(symbol=symbol, security=None, status=status, reason=reason)
        self.benchmark_degraded = True
        if status == "rate_limited":
            self.benchmark_rate_limit_detected = True
            self.benchmark_health = "rate_limited"
        elif self.benchmark_health == "healthy":
            self.benchmark_health = "degraded"

    def _has_fresh_disk_cache(self, symbol: str) -> bool:
        cache_provider = _find_file_cache_provider(self.provider)
        if cache_provider is None or bool(getattr(cache_provider, "refresh_cache", False)):
            return False
        load_cached_security = getattr(cache_provider, "load_cached_security", None)
        if not callable(load_cached_security):
            return False
        try:
            return load_cached_security(symbol, allow_stale=False) is not None
        except Exception:
            return False


def is_benchmark_symbol(symbol: str | None) -> bool:
    return str(symbol or "").strip().upper() in BENCHMARK_SYMBOLS


def build_benchmark_health_report(provider: Any, *, symbols: tuple[str, ...] = DEFAULT_BENCHMARK_SYMBOLS) -> dict[str, Any]:
    manager = BenchmarkDataManager(provider)
    rows: list[dict[str, Any]] = []
    for symbol in dict.fromkeys(symbol.upper() for symbol in symbols if symbol):
        security = manager.get(symbol)
        status = manager.status_for(symbol)
        rows.append(
            {
                "symbol": symbol,
                "status": status,
                "fresh_cache": status == "cache_hit",
                "loaded": security is not None,
                "last_market_date": security.last_market_date.isoformat() if security and security.last_market_date else None,
                "bars_count": len(security.bars) if security else 0,
                "reason": manager.reason_for(symbol),
            }
        )
    report = manager.as_dict()
    report["symbols_checked"] = [row["symbol"] for row in rows]
    report["benchmarks"] = rows
    return report


def _find_file_cache_provider(provider: Any) -> FileCacheMarketDataProvider | None:
    current = provider
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, FileCacheMarketDataProvider):
            return current
        current = getattr(current, "provider", None) or getattr(current, "base_provider", None) or getattr(current, "primary", None)
    return None


def _unwrap_live_provider(provider: Any) -> Any:
    current = provider
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, FileCacheMarketDataProvider):
            current = current.provider
            continue
        next_provider = getattr(current, "base_provider", None)
        if next_provider is not None:
            current = next_provider
            continue
        primary = getattr(current, "primary", None)
        if primary is not None:
            current = primary
            continue
        break
    return current or provider
