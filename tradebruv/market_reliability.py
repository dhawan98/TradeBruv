from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from .data_sources import redact_secrets
from .models import PriceBar, SecurityData
from .providers import MarketDataProvider, ProviderConfigurationError, ProviderFetchError
from .ticker_symbols import display_ticker, provider_ticker


RATE_LIMIT_PATTERNS = (
    "too many requests",
    "rate limit",
    "rate limited",
    "429",
    "invalid crumb",
    "too many",
)
UNAUTHORIZED_PATTERNS = ("unauthorized", "forbidden", "401", "403", "invalid api key", "apikey invalid")
TIMEOUT_PATTERNS = ("timed out", "timeout", "temporary failure", "name or service not known", "connection reset", "connection aborted")
NO_DATA_PATTERNS = (
    "no history returned",
    "no data found",
    "no candle data",
    "no time series",
    "no aggregate data",
    "returned no historical prices",
    "returned no daily series",
    "returned no ohlcv",
    "no valid ohlcv rows",
)
DELISTED_PATTERNS = ("possibly delisted", "delisted", "not found", "invalid symbol", "unknown symbol")
HEALTHY_STATUSES = {"healthy", "degraded", "rate_limited", "unauthorized", "unavailable"}


class ProviderStopError(RuntimeError):
    def __init__(self, message: str, *, status: str, provider: str) -> None:
        super().__init__(message)
        self.status = status
        self.provider = provider
        self.category = status


@dataclass
class ProviderHealthState:
    provider: str
    status: str = "healthy"
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    consecutive_failures: int = 0
    ticker_failures_count: int = 0
    provider_failures_count: int = 0
    consecutive_provider_failures: int = 0
    rate_limit_failures: int = 0
    unauthorized_failures: int = 0
    rate_limit_detected: bool = False
    stop_scan: bool = False
    stop_reason: str = ""
    message: str = ""
    fallback_providers_configured: list[str] = field(default_factory=list)
    fallback_providers_used: list[str] = field(default_factory=list)
    failure_samples: list[dict[str, str]] = field(default_factory=list)
    failure_category_counts: dict[str, int] = field(default_factory=dict)

    def record_success(self) -> None:
        self.attempted += 1
        self.succeeded += 1
        self.consecutive_failures = 0
        self.consecutive_provider_failures = 0
        if self.status not in {"rate_limited", "unauthorized", "unavailable"}:
            self.status = "healthy"
            self.message = "Provider responding normally."

    def record_failure(
        self,
        *,
        ticker: str,
        provider: str,
        status: str,
        reason: str,
        stop_scan: bool,
        scope: str,
        category: str,
    ) -> None:
        self.attempted += 1
        self.failed += 1
        self.consecutive_failures += 1
        self.failure_category_counts[category] = int(self.failure_category_counts.get(category, 0)) + 1
        if scope == "provider":
            self.provider_failures_count += 1
            self.consecutive_provider_failures += 1
        else:
            self.ticker_failures_count += 1
            self.consecutive_provider_failures = 0
        if category == "rate_limited":
            self.rate_limit_detected = True
            self.rate_limit_failures += 1
        if category == "unauthorized":
            self.unauthorized_failures += 1
        if scope == "provider" or status in {"rate_limited", "unauthorized", "unavailable"}:
            self.status = status
            self.message = reason
        if stop_scan:
            self.stop_scan = True
            self.stop_reason = reason
        sample = {"ticker": ticker, "provider": provider, "status": status, "reason": reason, "category": category}
        if sample not in self.failure_samples:
            self.failure_samples.append(sample)
        self.failure_samples = self.failure_samples[:10]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "consecutive_failures": self.consecutive_failures,
            "ticker_failures_count": self.ticker_failures_count,
            "provider_failures_count": self.provider_failures_count,
            "consecutive_provider_failures": self.consecutive_provider_failures,
            "rate_limit_detected": self.rate_limit_detected,
            "rate_limit_failures": self.rate_limit_failures,
            "unauthorized_failures": self.unauthorized_failures,
            "stop_scan": self.stop_scan,
            "stop_reason": self.stop_reason,
            "stop_scan_reason": self.stop_reason,
            "message": self.message,
            "fallback_providers_configured": self.fallback_providers_configured,
            "fallback_providers_used": self.fallback_providers_used,
            "failure_samples": self.failure_samples,
            "failure_category_counts": self.failure_category_counts,
        }


def classify_provider_error(exc: Exception) -> dict[str, Any]:
    text = redact_secrets(exc).lower()
    if any(pattern in text for pattern in RATE_LIMIT_PATTERNS):
        return {
            "status": "rate_limited",
            "reason": "Provider rate-limited or crumb invalid.",
            "stop_scan": False,
            "scope": "provider",
            "category": "rate_limited",
        }
    if any(pattern in text for pattern in UNAUTHORIZED_PATTERNS):
        return {
            "status": "unauthorized",
            "reason": "Provider rejected the request as unauthorized.",
            "stop_scan": False,
            "scope": "provider",
            "category": "unauthorized",
        }
    if any(pattern in text for pattern in TIMEOUT_PATTERNS):
        return {
            "status": "degraded",
            "reason": "Provider timed out or network resolution failed.",
            "stop_scan": False,
            "scope": "provider",
            "category": "timeout",
        }
    if any(pattern in text for pattern in DELISTED_PATTERNS):
        return {
            "status": "healthy",
            "reason": "Ticker appears delisted, invalid, or unavailable from the provider.",
            "stop_scan": False,
            "scope": "ticker",
            "category": "delisted_or_invalid",
        }
    if any(pattern in text for pattern in NO_DATA_PATTERNS):
        return {
            "status": "healthy",
            "reason": "Provider returned no usable market data for this ticker.",
            "stop_scan": False,
            "scope": "ticker",
            "category": "no_data",
        }
    return {
        "status": "degraded",
        "reason": redact_secrets(exc),
        "stop_scan": False,
        "scope": "provider",
        "category": "provider_error",
    }


def configured_fallback_provider_names() -> list[str]:
    configured: list[str] = []
    if os.getenv("POLYGON_API_KEY", "").strip():
        configured.append("polygon")
    if os.getenv("FINNHUB_API_KEY", "").strip():
        configured.append("finnhub")
    if os.getenv("FINANCIAL_MODELING_PREP_API_KEY", "").strip():
        configured.append("fmp")
    if os.getenv("TWELVE_DATA_API_KEY", "").strip():
        configured.append("twelve_data")
    if os.getenv("ALPHA_VANTAGE_API_KEY", "").strip():
        configured.append("alpha_vantage")
    return configured


class ResilientMarketDataProvider:
    def __init__(
        self,
        primary: MarketDataProvider,
        *,
        provider_name: str,
        history_period: str,
        max_provider_failures: int = 5,
        max_rate_limit_failures: int = 3,
    ) -> None:
        self.primary = primary
        self.provider_name = provider_name
        self.history_period = history_period
        self.max_provider_failures = max_provider_failures
        self.max_rate_limit_failures = max_rate_limit_failures
        self.health = ProviderHealthState(provider=provider_name)
        self.fallbacks = _build_fallback_providers(history_period=history_period)
        self.health.fallback_providers_configured = [name for name, _provider in self.fallbacks]

    def get_security_data(self, ticker: str) -> SecurityData:
        display = display_ticker(ticker)
        if self.health.stop_scan:
            raise ProviderStopError(self.health.stop_reason or "Provider scan halted.", status=self.health.status, provider=self.provider_name)
        providers: list[tuple[str, MarketDataProvider]] = [(self.provider_name, self.primary), *self.fallbacks]
        errors: list[str] = []
        primary_failure_reason = ""
        for index, (name, provider) in enumerate(providers):
            try:
                security = provider.get_security_data(display)
                if index > 0 and primary_failure_reason:
                    _annotate_security_with_fallback(
                        security,
                        primary_provider=self.provider_name,
                        primary_failure_reason=primary_failure_reason,
                        fallback_provider=name,
                    )
                self.health.record_success()
                if index > 0 and name not in self.health.fallback_providers_used:
                    self.health.fallback_providers_used.append(name)
                return security
            except Exception as exc:
                classification = classify_provider_error(exc)
                detail_reason = redact_secrets(exc)
                errors.append(f"{name}: {detail_reason or classification['reason']}")
                if index == 0:
                    primary_failure_reason = detail_reason or str(classification["reason"])
                self.health.record_failure(
                    ticker=display,
                    provider=name,
                    status=str(classification["status"]),
                    reason=str(detail_reason or classification["reason"]),
                    stop_scan=bool(classification["stop_scan"]),
                    scope=str(classification["scope"]),
                    category=str(classification["category"]),
                )
                self._update_stop_state()
                if str(classification["scope"]) == "ticker":
                    raise _build_ticker_failure(display, detail_reason or str(classification["reason"]), str(classification["category"])) from exc
                if name != self.provider_name:
                    continue
                if self.health.stop_scan and not self.fallbacks:
                    raise ProviderStopError(self.health.stop_reason or str(classification["reason"]), status=self.health.status, provider=name) from exc
                if self.fallbacks:
                    continue
                if self.health.stop_scan:
                    raise ProviderStopError(self.health.stop_reason, status=self.health.status, provider=name) from exc
        if self.health.stop_scan:
            raise ProviderStopError(self.health.stop_reason or "; ".join(errors), status=self.health.status, provider=self.provider_name)
        failure = ProviderFetchError("; ".join(errors) or f"No provider could load {display}.")
        failure.category = "provider_error"
        failure.status = "degraded"
        raise failure

    def prefetch_many(self, tickers: list[str], *, batch_size: int = 25) -> None:
        prefetch = getattr(self.primary, "prefetch_many", None)
        if not callable(prefetch):
            return
        try:
            prefetch(tickers, batch_size=batch_size)
        except Exception:
            return

    def health_report(self) -> dict[str, Any]:
        return self.health.to_dict()

    def should_stop_scan(self) -> bool:
        return self.health.stop_scan

    def _update_stop_state(self) -> None:
        if self.health.rate_limit_failures >= self.max_rate_limit_failures:
            self.health.status = "rate_limited"
            self.health.stop_scan = True
            self.health.stop_reason = f"Provider rate-limited after {self.health.rate_limit_failures} provider failures."
            return
        if self.health.unauthorized_failures >= 1:
            self.health.status = "unauthorized"
            self.health.stop_scan = True
            self.health.stop_reason = "Provider rejected authentication or authorization."
            return
        if self.health.consecutive_provider_failures >= self.max_provider_failures:
            self.health.status = "degraded"
            self.health.stop_scan = True
            self.health.stop_reason = f"Provider degraded after {self.health.consecutive_provider_failures} consecutive provider failures."


class FinnhubMarketDataProvider:
    def __init__(self, *, history_period: str) -> None:
        self.history_period = history_period
        self.api_key = os.getenv("FINNHUB_API_KEY", "").strip()
        if not self.api_key:
            raise ProviderConfigurationError("FINNHUB_API_KEY is not configured.")

    def get_security_data(self, ticker: str) -> SecurityData:
        symbol = provider_ticker(ticker)
        quote = _json_get("https://finnhub.io/api/v1/quote", {"symbol": symbol, "token": self.api_key})
        profile = _json_get("https://finnhub.io/api/v1/stock/profile2", {"symbol": symbol, "token": self.api_key})
        candles = _json_get("https://finnhub.io/api/v1/stock/candle", _finnhub_candle_params(symbol, self.api_key, self.history_period))
        if candles.get("s") != "ok":
            raise ProviderFetchError(f"Finnhub returned no candle data for {ticker}.")
        bars = [
            PriceBar(
                date=datetime.utcfromtimestamp(int(ts)).date(),
                open=float(open_),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=float(volume),
            )
            for ts, open_, high, low, close, volume in zip(
                candles.get("t", []),
                candles.get("o", []),
                candles.get("h", []),
                candles.get("l", []),
                candles.get("c", []),
                candles.get("v", []),
            )
        ]
        if not bars:
            raise ProviderFetchError(f"Finnhub returned no OHLCV bars for {ticker}.")
        return SecurityData(
            ticker=display_ticker(ticker),
            company_name=profile.get("name") or profile.get("ticker") or display_ticker(ticker),
            sector=profile.get("finnhubIndustry"),
            industry=profile.get("finnhubIndustry"),
            bars=bars,
            market_cap=_float_or_none(profile.get("marketCapitalization")),
            provider_name="finnhub",
            source_notes=["Source: Finnhub quote/profile/candle endpoints."],
            data_notes=[],
            quote_price_if_available=_float_or_none(quote.get("c")),
            quote_timestamp=datetime.utcnow().isoformat() + "Z",
            latest_available_close=bars[-1].close,
            last_market_date=bars[-1].date,
            is_adjusted_price=False,
        )


class AlphaVantageMarketDataProvider:
    def __init__(self, *, history_period: str) -> None:
        self.history_period = history_period
        self.api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
        if not self.api_key:
            raise ProviderConfigurationError("ALPHA_VANTAGE_API_KEY is not configured.")

    def get_security_data(self, ticker: str) -> SecurityData:
        symbol = provider_ticker(ticker)
        payload = _json_get(
            "https://www.alphavantage.co/query",
            {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": symbol,
                "outputsize": "full" if _history_days(self.history_period) > 200 else "compact",
                "apikey": self.api_key,
            },
        )
        if payload.get("Note") or payload.get("Information"):
            raise ProviderFetchError(str(payload.get("Note") or payload.get("Information")))
        series = payload.get("Time Series (Daily)") or {}
        if not series:
            raise ProviderFetchError(f"Alpha Vantage returned no daily series for {ticker}.")
        bars = _bars_from_alpha_series(series, adjusted=True, history_period=self.history_period)
        overview = _json_get(
            "https://www.alphavantage.co/query",
            {"function": "OVERVIEW", "symbol": symbol, "apikey": self.api_key},
        )
        return SecurityData(
            ticker=display_ticker(ticker),
            company_name=overview.get("Name") or display_ticker(ticker),
            sector=overview.get("Sector"),
            industry=overview.get("Industry"),
            bars=bars,
            market_cap=_float_or_none(overview.get("MarketCapitalization")),
            provider_name="alpha_vantage",
            source_notes=["Source: Alpha Vantage TIME_SERIES_DAILY_ADJUSTED and OVERVIEW."],
            data_notes=[],
            quote_price_if_available=bars[-1].close if bars else None,
            quote_timestamp=datetime.utcnow().isoformat() + "Z",
            latest_available_close=bars[-1].close if bars else None,
            last_market_date=bars[-1].date if bars else None,
            is_adjusted_price=True,
        )


class TwelveDataMarketDataProvider:
    def __init__(self, *, history_period: str) -> None:
        self.history_period = history_period
        self.api_key = os.getenv("TWELVE_DATA_API_KEY", "").strip()
        if not self.api_key:
            raise ProviderConfigurationError("TWELVE_DATA_API_KEY is not configured.")

    def get_security_data(self, ticker: str) -> SecurityData:
        symbol = provider_ticker(ticker)
        values = _json_get(
            "https://api.twelvedata.com/time_series",
            {
                "symbol": symbol,
                "interval": "1day",
                "outputsize": str(min(max(_history_days(self.history_period), 120), 5000)),
                "apikey": self.api_key,
            },
        )
        if values.get("status") == "error":
            raise ProviderFetchError(str(values.get("message") or "Twelve Data error"))
        series = values.get("values") or []
        bars = [
            PriceBar(
                date=date.fromisoformat(str(item["datetime"])[:10]),
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item.get("volume") or 0.0),
            )
            for item in reversed(series)
        ]
        if not bars:
            raise ProviderFetchError(f"Twelve Data returned no time series for {ticker}.")
        profile = _json_get("https://api.twelvedata.com/quote", {"symbol": symbol, "apikey": self.api_key})
        return SecurityData(
            ticker=display_ticker(ticker),
            company_name=profile.get("name") or display_ticker(ticker),
            sector=None,
            industry=profile.get("exchange"),
            bars=bars,
            market_cap=None,
            provider_name="twelve_data",
            source_notes=["Source: Twelve Data time_series and quote endpoints."],
            data_notes=[],
            quote_price_if_available=_float_or_none(profile.get("close")),
            quote_timestamp=datetime.utcnow().isoformat() + "Z",
            latest_available_close=bars[-1].close if bars else None,
            last_market_date=bars[-1].date if bars else None,
            is_adjusted_price=False,
        )


class PolygonMarketDataProvider:
    def __init__(self, *, history_period: str) -> None:
        self.history_period = history_period
        self.api_key = os.getenv("POLYGON_API_KEY", "").strip()
        if not self.api_key:
            raise ProviderConfigurationError("POLYGON_API_KEY is not configured.")

    def get_security_data(self, ticker: str) -> SecurityData:
        symbol = provider_ticker(ticker)
        end = date.today()
        start = end - timedelta(days=max(_history_days(self.history_period), 365))
        payload = _json_get(
            f"https://api.polygon.io/v2/aggs/ticker/{urllib.parse.quote(symbol)}/range/1/day/{start.isoformat()}/{end.isoformat()}",
            {"adjusted": "true", "sort": "asc", "limit": "5000", "apiKey": self.api_key},
        )
        if payload.get("status") == "ERROR":
            raise ProviderFetchError(str(payload.get("error") or payload.get("message") or "Polygon error"))
        results = payload.get("results") or []
        bars = [
            PriceBar(
                date=datetime.utcfromtimestamp(int(item["t"]) / 1000).date(),
                open=float(item["o"]),
                high=float(item["h"]),
                low=float(item["l"]),
                close=float(item["c"]),
                volume=float(item.get("v") or 0.0),
            )
            for item in results
        ]
        if not bars:
            raise ProviderFetchError(f"Polygon returned no aggregate data for {ticker}.")
        ref = _json_get(f"https://api.polygon.io/v3/reference/tickers/{urllib.parse.quote(symbol)}", {"apiKey": self.api_key})
        details = ref.get("results") or {}
        return SecurityData(
            ticker=display_ticker(ticker),
            company_name=details.get("name") or display_ticker(ticker),
            sector=None,
            industry=details.get("market"),
            bars=bars,
            market_cap=_float_or_none(details.get("market_cap")),
            provider_name="polygon",
            source_notes=["Source: Polygon aggregates and reference ticker endpoints."],
            data_notes=[],
            quote_price_if_available=bars[-1].close if bars else None,
            quote_timestamp=datetime.utcnow().isoformat() + "Z",
            latest_available_close=bars[-1].close if bars else None,
            last_market_date=bars[-1].date if bars else None,
            is_adjusted_price=True,
        )


class FMPMarketDataProvider:
    def __init__(self, *, history_period: str) -> None:
        self.history_period = history_period
        self.api_key = os.getenv("FINANCIAL_MODELING_PREP_API_KEY", "").strip()
        if not self.api_key:
            raise ProviderConfigurationError("FINANCIAL_MODELING_PREP_API_KEY is not configured.")

    def get_security_data(self, ticker: str) -> SecurityData:
        symbol = provider_ticker(ticker)
        payload = _json_get(
            f"https://financialmodelingprep.com/api/v3/historical-price-full/{urllib.parse.quote(symbol)}",
            {"apikey": self.api_key, "timeseries": str(min(max(_history_days(self.history_period), 180), 1000))},
        )
        series = payload.get("historical") or []
        bars = [
            PriceBar(
                date=date.fromisoformat(str(item["date"])[:10]),
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item.get("volume") or 0.0),
            )
            for item in reversed(series)
        ]
        if not bars:
            raise ProviderFetchError(f"FMP returned no historical prices for {ticker}.")
        profile_rows = _json_get(
            f"https://financialmodelingprep.com/api/v3/profile/{urllib.parse.quote(symbol)}",
            {"apikey": self.api_key},
        )
        profile = profile_rows[0] if isinstance(profile_rows, list) and profile_rows else {}
        return SecurityData(
            ticker=display_ticker(ticker),
            company_name=profile.get("companyName") or display_ticker(ticker),
            sector=profile.get("sector"),
            industry=profile.get("industry"),
            bars=bars,
            market_cap=_float_or_none(profile.get("mktCap")),
            provider_name="fmp",
            source_notes=["Source: Financial Modeling Prep historical-price-full and profile endpoints."],
            data_notes=[],
            quote_price_if_available=bars[-1].close if bars else None,
            quote_timestamp=datetime.utcnow().isoformat() + "Z",
            latest_available_close=bars[-1].close if bars else None,
            last_market_date=bars[-1].date if bars else None,
            is_adjusted_price=False,
        )


def build_market_health_report(provider_name: str, *, history_period: str = "6mo", sample_ticker: str = "SPY") -> dict[str, Any]:
    if provider_name != "real":
        return {
            "provider": provider_name,
            "status": "healthy",
            "sample_ticker": sample_ticker,
            "sample_ticker_success": True,
            "rate_limit_detected": False,
            "fallback_providers_configured": configured_fallback_provider_names(),
            "recommended_action": "Sample/local providers are available. Use provider=real to test live market data health.",
        }
    from .providers import YFinanceMarketDataProvider

    primary = YFinanceMarketDataProvider(history_period=history_period)
    resilient = ResilientMarketDataProvider(primary, provider_name="yfinance", history_period=history_period)
    try:
        resilient.get_security_data(sample_ticker)
        report = resilient.health_report()
        report.update(
            {
                "sample_ticker": sample_ticker,
                "sample_ticker_success": True,
                "recommended_action": _recommended_action(report),
            }
        )
        return report
    except Exception as exc:
        report = resilient.health_report()
        report.update(
            {
                "sample_ticker": sample_ticker,
                "sample_ticker_success": False,
                "error": redact_secrets(exc),
                "recommended_action": _recommended_action(report),
            }
        )
        return report


def build_provider_check_report(
    ticker: str,
    *,
    provider_name: str,
    history_period: str = "6mo",
    include_fallbacks: bool = False,
) -> dict[str, Any]:
    if provider_name != "real":
        raise ValueError("provider-check currently supports --provider real only.")
    from .providers import YFinanceMarketDataProvider

    primary = YFinanceMarketDataProvider(history_period=history_period)
    report: dict[str, Any] = {
        "ticker": display_ticker(ticker),
        "provider": provider_name,
        "primary_provider": "yfinance",
        "fallbacks_requested": include_fallbacks,
        "fallback_providers_configured": configured_fallback_provider_names(),
        "checks": [],
    }
    security: SecurityData | None = None
    primary_failed_reason = ""
    try:
        security = primary.get_security_data(ticker)
        report["checks"].append(_provider_check_row("yfinance", True, security=security))
    except Exception as exc:
        primary_failed_reason = redact_secrets(exc)
        report["checks"].append(_provider_check_row("yfinance", False, reason=primary_failed_reason))
    if security is None and include_fallbacks:
        for name, provider in _build_fallback_providers(history_period=history_period):
            try:
                security = provider.get_security_data(ticker)
                _annotate_security_with_fallback(
                    security,
                    primary_provider="yfinance",
                    primary_failure_reason=primary_failed_reason or "Primary provider failed.",
                    fallback_provider=name,
                )
                report["checks"].append(_provider_check_row(name, True, security=security))
                break
            except Exception as exc:
                report["checks"].append(_provider_check_row(name, False, reason=redact_secrets(exc)))
    report["final_selected_source"] = security.provider_name if security is not None else "unavailable"
    report["success"] = security is not None
    report["latest_close"] = security.latest_available_close if security is not None else None
    report["quote_price"] = security.quote_price_if_available if security is not None else None
    report["bars_count"] = len(security.bars) if security is not None else 0
    report["volume_available"] = bool(security and security.bars and security.bars[-1].volume is not None)
    report["provider_health"] = build_market_health_report("real", history_period=history_period, sample_ticker=ticker)
    if security is not None and getattr(security, "fallback_used", False):
        report["fallback_used"] = True
        report["primary_provider_failed_reason"] = getattr(security, "primary_provider_failed_reason", "")
    else:
        report["fallback_used"] = False
        report["primary_provider_failed_reason"] = primary_failed_reason
    return report


def _provider_check_row(
    provider: str,
    success: bool,
    *,
    security: SecurityData | None = None,
    reason: str = "",
) -> dict[str, Any]:
    return {
        "provider": provider,
        "success": success,
        "reason": reason,
        "latest_close": security.latest_available_close if security else None,
        "quote_price": security.quote_price_if_available if security else None,
        "bars_count": len(security.bars) if security else 0,
        "volume_available": bool(security and security.bars and security.bars[-1].volume is not None),
    }


def _recommended_action(report: dict[str, Any]) -> str:
    configured = report.get("fallback_providers_configured") or []
    status = str(report.get("status") or "unavailable")
    if status == "healthy":
        return "Primary provider looks healthy. Proceed with a live scan and keep caching enabled."
    if configured:
        return f"Primary provider is {status}. Fallback providers are configured: {', '.join(configured)}."
    return "Primary provider is degraded. Configure a free fallback key such as FINNHUB_API_KEY or ALPHA_VANTAGE_API_KEY to improve reliability."


def _build_fallback_providers(*, history_period: str) -> list[tuple[str, MarketDataProvider]]:
    fallbacks: list[tuple[str, MarketDataProvider]] = []
    for name, factory in (
        ("polygon", PolygonMarketDataProvider),
        ("finnhub", FinnhubMarketDataProvider),
        ("fmp", FMPMarketDataProvider),
        ("twelve_data", TwelveDataMarketDataProvider),
        ("alpha_vantage", AlphaVantageMarketDataProvider),
    ):
        try:
            fallbacks.append((name, factory(history_period=history_period)))
        except ProviderConfigurationError:
            continue
    return fallbacks


def _build_ticker_failure(ticker: str, reason: str, category: str) -> ProviderFetchError:
    error = ProviderFetchError(f"{ticker}: {reason}")
    error.category = category
    error.status = category
    return error


def _annotate_security_with_fallback(
    security: SecurityData,
    *,
    primary_provider: str,
    primary_failure_reason: str,
    fallback_provider: str,
) -> None:
    fallback_note = f"Fallback provider {fallback_provider} used after {primary_provider} failed: {primary_failure_reason}"
    if fallback_note not in security.data_notes:
        security.data_notes.append(fallback_note)
    security.fallback_used = True
    security.primary_provider_failed_reason = primary_failure_reason
    security.primary_provider_name = primary_provider
    security.selected_source_provider = fallback_provider


def _json_get(url: str, params: dict[str, Any]) -> dict[str, Any] | list[Any]:
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value not in (None, "")})
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "TradeBruv market reliability"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise ProviderFetchError(f"HTTP {exc.code}: {body or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ProviderFetchError(redact_secrets(exc)) from exc
    time.sleep(0.05)
    return payload


def _finnhub_candle_params(symbol: str, api_key: str, history_period: str) -> dict[str, Any]:
    end = int(time.time())
    start = end - (_history_days(history_period) * 86400)
    return {
        "symbol": symbol,
        "resolution": "D",
        "from": start,
        "to": end,
        "token": api_key,
    }


def _history_days(history_period: str) -> int:
    value = history_period.strip().lower()
    if value.endswith("y"):
        return max(int(value[:-1] or "1") * 365, 180)
    if value.endswith("mo"):
        return max(int(value[:-2] or "6") * 30, 90)
    if value.endswith("d"):
        return max(int(value[:-1] or "180"), 30)
    return 365


def _bars_from_alpha_series(series: dict[str, dict[str, str]], *, adjusted: bool, history_period: str) -> list[PriceBar]:
    bars: list[PriceBar] = []
    lookback = _history_days(history_period)
    cutoff = date.today() - timedelta(days=lookback + 7)
    for day, row in sorted(series.items()):
        dt = date.fromisoformat(day)
        if dt < cutoff:
            continue
        close_key = "5. adjusted close" if adjusted and "5. adjusted close" in row else "4. close"
        bars.append(
            PriceBar(
                date=dt,
                open=float(row["1. open"]),
                high=float(row["2. high"]),
                low=float(row["3. low"]),
                close=float(row[close_key]),
                volume=float(row.get("6. volume") or row.get("5. volume") or 0.0),
            )
        )
    return bars


def _float_or_none(value: Any) -> float | None:
    if value in (None, "", "None", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
