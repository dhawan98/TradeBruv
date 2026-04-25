from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DataSourceSpec:
    name: str
    category: str
    env_vars: tuple[str, ...]
    required: bool
    capabilities: tuple[str, ...]
    setup: str
    url: str
    notes: str = ""


DATA_SOURCE_SPECS: tuple[DataSourceSpec, ...] = (
    DataSourceSpec(
        name="yfinance",
        category="Market data",
        env_vars=(),
        required=True,
        capabilities=("Current free provider", "OHLCV history", "company metadata when available", "partial news/earnings"),
        setup="Install the real-data optional dependency and select provider=real. No API key is used.",
        url="https://ranaroussi.github.io/yfinance/",
        notes="Unofficial Yahoo Finance access. Treat coverage and fields as best-effort.",
    ),
    DataSourceSpec(
        name="Polygon.io",
        category="Market data",
        env_vars=("POLYGON_API_KEY",),
        required=False,
        capabilities=("Equities aggregates", "reference data", "corporate actions", "market/news feeds on paid plans"),
        setup="Create a Polygon key and set POLYGON_API_KEY in your shell or .env.",
        url="https://polygon.io/docs",
    ),
    DataSourceSpec(
        name="Finnhub",
        category="Market data / News",
        env_vars=("FINNHUB_API_KEY",),
        required=False,
        capabilities=("Quote/profile data", "earnings calendar", "company news", "analyst estimates on supported plans"),
        setup="Create a Finnhub key and set FINNHUB_API_KEY.",
        url="https://finnhub.io/docs/api",
    ),
    DataSourceSpec(
        name="Twelve Data",
        category="Market data",
        env_vars=("TWELVE_DATA_API_KEY",),
        required=False,
        capabilities=("Time series", "technical indicators", "fundamentals on supported plans"),
        setup="Create a Twelve Data key and set TWELVE_DATA_API_KEY.",
        url="https://twelvedata.com/docs",
    ),
    DataSourceSpec(
        name="Alpha Vantage",
        category="Market data / News",
        env_vars=("ALPHA_VANTAGE_API_KEY",),
        required=False,
        capabilities=("Daily/intraday time series", "company overview", "earnings", "news sentiment"),
        setup="Create an Alpha Vantage key and set ALPHA_VANTAGE_API_KEY.",
        url="https://www.alphavantage.co/documentation/",
    ),
    DataSourceSpec(
        name="IEX Cloud",
        category="Market data",
        env_vars=("IEX_CLOUD_API_KEY",),
        required=False,
        capabilities=("Legacy equities data if account/API access remains available",),
        setup="Only use if you already have a viable IEX Cloud account, then set IEX_CLOUD_API_KEY.",
        url="https://iexcloud.io/docs/api/",
        notes="Viability has changed over time; prefer Polygon/Finnhub/Twelve Data unless you confirm account access.",
    ),
    DataSourceSpec(
        name="Nasdaq Data Link",
        category="Market data / Fundamentals",
        env_vars=("NASDAQ_DATA_LINK_API_KEY",),
        required=False,
        capabilities=("Premium datasets", "economic/alternative datasets", "some fundamentals depending on dataset"),
        setup="Create a Nasdaq Data Link key and set NASDAQ_DATA_LINK_API_KEY.",
        url="https://docs.data.nasdaq.com/",
    ),
    DataSourceSpec(
        name="Benzinga",
        category="News/events",
        env_vars=("BENZINGA_API_KEY",),
        required=False,
        capabilities=("News", "earnings", "analyst ratings", "calendars on supported plans"),
        setup="Create a Benzinga API key and set BENZINGA_API_KEY.",
        url="https://docs.benzinga.io/",
    ),
    DataSourceSpec(
        name="NewsAPI",
        category="News/events",
        env_vars=("NEWSAPI_KEY",),
        required=False,
        capabilities=("General news search", "headline monitoring"),
        setup="Create a NewsAPI key and set NEWSAPI_KEY.",
        url="https://newsapi.org/docs",
        notes="Not stock-specific; use alongside ticker/company disambiguation.",
    ),
    DataSourceSpec(
        name="GDELT",
        category="News/events",
        env_vars=(),
        required=False,
        capabilities=("Global news/event search", "attention tracking", "narrative monitoring"),
        setup="No key for many public endpoints. Add rate limits/caching before heavy use.",
        url="https://www.gdeltproject.org/",
    ),
    DataSourceSpec(
        name="SEC EDGAR",
        category="News/events",
        env_vars=(),
        required=False,
        capabilities=("Company filings", "facts API", "10-K/10-Q/8-K source material"),
        setup="Use SEC data APIs with a descriptive User-Agent. No broker credentials involved.",
        url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
    ),
    DataSourceSpec(
        name="Earnings transcripts",
        category="News/events",
        env_vars=("FINNHUB_API_KEY", "BENZINGA_API_KEY"),
        required=False,
        capabilities=("Transcript or earnings commentary when your chosen vendor supports it",),
        setup="Use a licensed transcript-capable provider; store only source links/summaries unless licensing allows full text.",
        url="https://finnhub.io/docs/api",
        notes="Transcript licensing varies. The MVP should mark transcripts unavailable unless a configured source supports them.",
    ),
    DataSourceSpec(
        name="Reddit API",
        category="Social/attention",
        env_vars=("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"),
        required=False,
        capabilities=("Subreddit mention monitoring", "attention velocity", "source links"),
        setup="Create a Reddit app and set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET.",
        url="https://www.reddit.com/dev/api/",
    ),
    DataSourceSpec(
        name="X / Twitter API",
        category="Social/attention",
        env_vars=("X_BEARER_TOKEN",),
        required=False,
        capabilities=("Public post search if plan allows", "attention velocity", "source links"),
        setup="Create an X developer app and set X_BEARER_TOKEN.",
        url="https://developer.x.com/en/docs",
        notes="Plan limits and access change frequently; manual CSV fallback remains supported.",
    ),
    DataSourceSpec(
        name="Truth Social / political mentions",
        category="Social/attention",
        env_vars=(),
        required=False,
        capabilities=("Manual political/narrative event tagging",),
        setup="Use manual CSV fallback unless a compliant licensed source is selected later.",
        url="https://truthsocial.com/",
        notes="No credential scraping. Do not automate private accounts.",
    ),
    DataSourceSpec(
        name="StockTwits",
        category="Social/attention",
        env_vars=("STOCKTWITS_ACCESS_TOKEN",),
        required=False,
        capabilities=("Symbol stream monitoring", "sentiment/attention clues where available"),
        setup="Set STOCKTWITS_ACCESS_TOKEN if using an approved StockTwits API flow.",
        url="https://api.stocktwits.com/developers/docs",
    ),
    DataSourceSpec(
        name="Manual catalyst/social CSV",
        category="Social/attention",
        env_vars=(),
        required=False,
        capabilities=("Verified manual catalyst ingestion", "social fallback", "source URL tracking"),
        setup="Use config/catalysts_watchlist.csv or another CSV with the documented catalyst columns.",
        url="README.md",
    ),
    DataSourceSpec(
        name="OpenAI",
        category="AI providers",
        env_vars=("OPENAI_API_KEY",),
        required=False,
        capabilities=("AI explanations", "analyst committee via OpenAI-compatible chat completions"),
        setup="Set OPENAI_API_KEY. Optional: OPENAI_MODEL.",
        url="https://platform.openai.com/docs",
    ),
    DataSourceSpec(
        name="Anthropic Claude",
        category="AI providers",
        env_vars=("ANTHROPIC_API_KEY",),
        required=False,
        capabilities=("AI committee adapter when enabled", "bull/bear/risk/catalyst synthesis"),
        setup="Set ANTHROPIC_API_KEY. The current MVP detects readiness and keeps mock/offline flows available.",
        url="https://docs.anthropic.com/",
    ),
    DataSourceSpec(
        name="Google Gemini",
        category="AI providers",
        env_vars=("GEMINI_API_KEY",),
        required=False,
        capabilities=("AI committee adapter when enabled", "research synthesis"),
        setup="Set GEMINI_API_KEY. The current MVP detects readiness and keeps mock/offline flows available.",
        url="https://ai.google.dev/gemini-api/docs",
    ),
    DataSourceSpec(
        name="OpenRouter / OpenAI-compatible endpoint",
        category="AI providers",
        env_vars=("TRADEBRUV_LLM_API_KEY", "TRADEBRUV_LLM_BASE_URL"),
        required=False,
        capabilities=("OpenAI-compatible AI committee calls", "model routing through compatible providers"),
        setup="Set TRADEBRUV_LLM_API_KEY and TRADEBRUV_LLM_BASE_URL. Optional: TRADEBRUV_LLM_MODEL.",
        url="https://openrouter.ai/docs/api-reference/overview",
    ),
    DataSourceSpec(
        name="Manual portfolio CSV",
        category="Portfolio/brokerage",
        env_vars=(),
        required=True,
        capabilities=("Read/write local holdings", "import/export", "portfolio-aware recommendations"),
        setup="Use the Portfolio page or CLI portfolio import/export commands.",
        url="README.md",
    ),
    DataSourceSpec(
        name="Fidelity CSV export import",
        category="Portfolio/brokerage",
        env_vars=(),
        required=False,
        capabilities=("Local read-only import from exported holdings CSV", "no credentials stored"),
        setup="Export holdings from Fidelity, then import the CSV from the Portfolio page.",
        url="README.md",
        notes="CSV formats vary. Review imported quantities/cost basis before relying on analysis.",
    ),
    DataSourceSpec(
        name="Plaid Investments",
        category="Portfolio/brokerage",
        env_vars=("PLAID_CLIENT_ID", "PLAID_SECRET", "PLAID_ENV"),
        required=False,
        capabilities=("Read-only holdings/transactions integration if implemented later",),
        setup="Set PLAID_CLIENT_ID, PLAID_SECRET, and PLAID_ENV. This app does not connect broker accounts in the MVP.",
        url="https://plaid.com/docs/investments/",
        notes="Read-only research integration only. No order placement.",
    ),
    DataSourceSpec(
        name="SnapTrade",
        category="Portfolio/brokerage",
        env_vars=("SNAPTRADE_CLIENT_ID", "SNAPTRADE_CONSUMER_KEY"),
        required=False,
        capabilities=("Read-only brokerage holdings integration if implemented later",),
        setup="Set SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY. This app does not connect broker accounts in the MVP.",
        url="https://docs.snaptrade.com/",
        notes="Read-only research integration only. No credential scraping or trades.",
    ),
    DataSourceSpec(
        name="Fidelity Access",
        category="Portfolio/brokerage",
        env_vars=(),
        required=False,
        capabilities=("Potential read-only data access through approved partner channels",),
        setup="Use approved partner APIs only. Do not scrape credentials or web sessions.",
        url="https://clearingcustody.fidelity.com/app/proxy/content?literatureURL=/9901330.PDF",
        notes="Future research item, not implemented.",
    ),
)


def build_data_source_status(env: dict[str, str] | None = None) -> list[dict[str, Any]]:
    env_map = os.environ if env is None else env
    checked_at = datetime.utcnow().isoformat() + "Z"
    rows: list[dict[str, Any]] = []
    for spec in DATA_SOURCE_SPECS:
        configured_vars = [name for name in spec.env_vars if env_map.get(name)]
        missing_vars = [name for name in spec.env_vars if not env_map.get(name)]
        configured = not spec.env_vars or not missing_vars
        rows.append(
            {
                "name": spec.name,
                "category": spec.category,
                "required": spec.required,
                "configured": configured,
                "env_vars_needed": ", ".join(spec.env_vars) or "none",
                "missing_env_vars": ", ".join(missing_vars) or "none",
                "capabilities": "; ".join(spec.capabilities),
                "unlocks": "; ".join(spec.capabilities),
                "degraded_when_missing": _degraded_message(spec, configured),
                "last_successful_check": checked_at if configured else "not configured",
                "last_error": "none" if configured else f"Missing: {', '.join(missing_vars)}",
                "optional_or_required": "required" if spec.required else "optional",
                "setup": spec.setup,
                "url": spec.url,
                "notes": spec.notes,
                "configured_env_vars": ", ".join(configured_vars) or "none",
            }
        )
    return rows


def data_health_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    required_missing = [row for row in rows if row["required"] and not row["configured"]]
    optional_ready = [row for row in rows if not row["required"] and row["configured"]]
    optional_missing = [row for row in rows if not row["required"] and not row["configured"]]
    return {
        "providers": len(rows),
        "required_missing": len(required_missing),
        "optional_ready": len(optional_ready),
        "optional_missing": len(optional_missing),
        "degraded_capabilities": [row["degraded_when_missing"] for row in optional_missing if row["degraded_when_missing"]],
    }


def secret_values_present_in_text(text: str, env: dict[str, str] | None = None) -> list[str]:
    env_map = os.environ if env is None else env
    leaked: list[str] = []
    for spec in DATA_SOURCE_SPECS:
        for name in spec.env_vars:
            value = env_map.get(name)
            if value and len(value) >= 8 and value in text:
                leaked.append(name)
    return sorted(dict.fromkeys(leaked))


def _degraded_message(spec: DataSourceSpec, configured: bool) -> str:
    if configured:
        return "none"
    if spec.category == "AI providers":
        return f"{spec.name} AI analysis is unavailable; deterministic scanner and mock AI still work."
    if spec.category.startswith("Portfolio"):
        return f"{spec.name} live/read-only brokerage import is unavailable; manual CSV/local portfolio still works."
    if spec.category == "Social/attention":
        return f"{spec.name} social attention is unavailable; manual CSV fallback still works."
    if spec.category == "News/events":
        return f"{spec.name} event/news enrichment is unavailable; scanner uses price/catalyst fields that exist."
    return f"{spec.name} enrichment is unavailable; free/sample/local providers still run."
