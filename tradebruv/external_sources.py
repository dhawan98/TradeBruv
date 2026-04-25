from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_CACHE_DIR = Path(os.getenv("TRADEBRUV_DATA_DIR", "data")) / "provider_cache"


@dataclass(frozen=True)
class ProviderCheck:
    name: str
    status: str
    mode: str
    configured: bool
    message: str
    capabilities: tuple[str, ...]
    checked_at: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "mode": self.mode,
            "configured": self.configured,
            "message": self.message,
            "capabilities": list(self.capabilities),
            "checked_at": self.checked_at,
            "details": self.details or {},
        }


def sec_edgar_status(*, live: bool = False, ticker: str = "NVDA", cache_dir: Path = DEFAULT_CACHE_DIR) -> ProviderCheck:
    user_agent = os.getenv("SEC_USER_AGENT", "").strip()
    if not user_agent:
        return _check(
            "SEC EDGAR",
            "WARN",
            "config-only",
            False,
            "SEC_USER_AGENT is missing; SEC discovery is disabled until a descriptive User-Agent is configured.",
            ("filings", "company facts", "Form 4 discovery"),
        )
    if not live:
        return _check("SEC EDGAR", "PASS", "config-only", True, "SEC_USER_AGENT configured.", ("filings", "company facts", "Form 4 discovery"))
    try:
        payload = _cached_get_json(
            "sec_company_tickers",
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate", "Host": "www.sec.gov"},
            cache_dir=cache_dir,
        )
        matches = [row for row in payload.values() if str(row.get("ticker", "")).upper() == ticker.upper()] if isinstance(payload, dict) else []
        details = {"ticker": ticker.upper(), "matches": len(matches)}
        status = "PASS" if matches else "WARN"
        message = "SEC company ticker lookup reached successfully." if matches else "SEC reachable, but ticker was not found in company_tickers.json."
        return _check("SEC EDGAR", status, "live", True, message, ("filings", "company facts", "Form 4 discovery"), details)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return _check("SEC EDGAR", "FAIL", "live", True, f"SEC EDGAR check failed: {exc}", ("filings", "company facts", "Form 4 discovery"))


def gdelt_status(*, live: bool = False, ticker: str = "NVDA", cache_dir: Path = DEFAULT_CACHE_DIR) -> ProviderCheck:
    enabled = os.getenv("GDELT_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
    if not enabled:
        return _check("GDELT", "SKIPPED", "config-only", False, "GDELT_ENABLED=false.", ("news/event search", "narrative monitoring"))
    if not live:
        return _check("GDELT", "PASS", "config-only", True, "No key required; adapter is enabled.", ("news/event search", "narrative monitoring"))
    query = urllib.parse.urlencode(
        {
            "query": ticker.upper(),
            "mode": "artlist",
            "format": "json",
            "maxrecords": "5",
            "sort": "hybridrel",
        }
    )
    url = f"https://api.gdeltproject.org/api/v2/doc/doc?{query}"
    try:
        payload = _cached_get_json(f"gdelt_{ticker.upper()}", url, headers={"User-Agent": "TradeBruv local research"}, cache_dir=cache_dir)
        articles = payload.get("articles", []) if isinstance(payload, dict) else []
        return _check(
            "GDELT",
            "PASS",
            "live",
            True,
            f"GDELT reached successfully; {len(articles)} recent article candidates returned.",
            ("news/event search", "narrative monitoring"),
            {"article_count": len(articles), "sample_urls": [article.get("url") for article in articles[:3] if article.get("url")]},
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return _check("GDELT", "WARN", "live", True, f"GDELT check failed gracefully: {exc}", ("news/event search", "narrative monitoring"))


def fmp_status(*, live: bool = False, ticker: str = "NVDA", cache_dir: Path = DEFAULT_CACHE_DIR) -> ProviderCheck:
    api_key = os.getenv("FINANCIAL_MODELING_PREP_API_KEY", "").strip()
    if not api_key:
        return _check("Financial Modeling Prep", "WARN", "config-only", False, "FINANCIAL_MODELING_PREP_API_KEY is missing.", ("fundamentals", "ratios", "statements"))
    if not live:
        return _check("Financial Modeling Prep", "PASS", "config-only", True, "FMP key configured; live quota test skipped.", ("fundamentals", "ratios", "statements"))
    query = urllib.parse.urlencode({"apikey": api_key})
    url = f"https://financialmodelingprep.com/api/v3/profile/{ticker.upper()}?{query}"
    try:
        payload = _cached_get_json(f"fmp_profile_{ticker.upper()}", url, headers={"User-Agent": "TradeBruv local research"}, cache_dir=cache_dir)
        count = len(payload) if isinstance(payload, list) else 0
        return _check(
            "Financial Modeling Prep",
            "PASS" if count else "WARN",
            "live",
            True,
            f"FMP profile endpoint returned {count} row(s).",
            ("fundamentals", "ratios", "statements"),
            {"ticker": ticker.upper(), "rows": count},
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return _check("Financial Modeling Prep", "FAIL", "live", True, f"FMP check failed: {exc}", ("fundamentals", "ratios", "statements"))


def quiver_status() -> ProviderCheck:
    configured = bool(os.getenv("QUIVER_API_KEY", "").strip())
    return _check(
        "Quiver Quantitative",
        "PASS" if configured else "SKIPPED",
        "config-only",
        configured,
        "QUIVER_API_KEY configured; paid alternative-data adapters remain optional." if configured else "QUIVER_API_KEY missing; manual CSV and SEC discovery remain the supported local path.",
        ("insider trading", "congressional trading", "government/lobbying context"),
    )


def cheap_provider_statuses(*, live: bool = False, ticker: str = "NVDA") -> list[dict[str, Any]]:
    return [
        sec_edgar_status(live=live, ticker=ticker).to_dict(),
        gdelt_status(live=live, ticker=ticker).to_dict(),
        fmp_status(live=live, ticker=ticker).to_dict(),
        quiver_status().to_dict(),
    ]


def _check(
    name: str,
    status: str,
    mode: str,
    configured: bool,
    message: str,
    capabilities: tuple[str, ...],
    details: dict[str, Any] | None = None,
) -> ProviderCheck:
    return ProviderCheck(
        name=name,
        status=status,
        mode=mode,
        configured=configured,
        message=message,
        capabilities=capabilities,
        checked_at=datetime.utcnow().isoformat() + "Z",
        details=details,
    )


def _cached_get_json(cache_key: str, url: str, *, headers: dict[str, str], cache_dir: Path, ttl_seconds: int = 900) -> Any:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{_safe_cache_key(cache_key)}.json"
    if cache_file.exists() and time.time() - cache_file.stat().st_mtime < ttl_seconds:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    cache_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _safe_cache_key(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)[:80]
