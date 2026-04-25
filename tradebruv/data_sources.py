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
    tier: str = "Paid / optional"
    recommended_priority: int = 99
    quota_notes: str = ""


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
        tier="No key / free",
        recommended_priority=1,
    ),
    DataSourceSpec(
        name="SEC EDGAR",
        category="No key / free",
        env_vars=("SEC_USER_AGENT",),
        required=False,
        capabilities=("Company filings", "company facts", "8-K/10-Q/10-K discovery", "Form 4 insider filing discovery"),
        setup="Set SEC_USER_AGENT to a descriptive contact string such as 'TradeBruv local research your@email.com'.",
        url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        notes="Free public SEC data. A descriptive User-Agent is required for responsible access.",
        tier="No key / free",
        recommended_priority=5,
        quota_notes="Use caching and gentle request rates; do not hammer SEC endpoints.",
    ),
    DataSourceSpec(
        name="GDELT",
        category="No key / free",
        env_vars=(),
        required=False,
        capabilities=("Global news/event search", "attention tracking", "narrative monitoring"),
        setup="No key is required. Set GDELT_ENABLED=false only if you want to disable this adapter.",
        url="https://www.gdeltproject.org/",
        notes="Use as narrative context, not as a standalone buy/sell signal.",
        tier="No key / free",
        recommended_priority=3,
        quota_notes="Public endpoint; keep queries targeted and cached.",
    ),
    DataSourceSpec(
        name="Financial Modeling Prep",
        category="Free key",
        env_vars=("FINANCIAL_MODELING_PREP_API_KEY",),
        required=False,
        capabilities=("Fundamentals", "financial statements", "ratios", "company profile"),
        setup="Create a Financial Modeling Prep free/cheap tier key and set FINANCIAL_MODELING_PREP_API_KEY.",
        url="https://site.financialmodelingprep.com/developer/docs",
        tier="Free key",
        recommended_priority=3,
        quota_notes="Respect free-tier daily limits and cache fundamentals.",
    ),
    DataSourceSpec(
        name="Polygon.io",
        category="Paid / optional",
        env_vars=("POLYGON_API_KEY",),
        required=False,
        capabilities=("Equities aggregates", "reference data", "corporate actions", "market/news feeds on paid plans"),
        setup="Create a Polygon key and set POLYGON_API_KEY in your shell or .env.",
        url="https://polygon.io/docs",
        tier="Paid / optional",
        recommended_priority=20,
    ),
    DataSourceSpec(
        name="Finnhub",
        category="Free key",
        env_vars=("FINNHUB_API_KEY",),
        required=False,
        capabilities=("Quote/profile data", "earnings calendar", "company news", "analyst estimates on supported plans"),
        setup="Create a Finnhub key and set FINNHUB_API_KEY.",
        url="https://finnhub.io/docs/api",
        tier="Free key",
        recommended_priority=4,
        quota_notes="Free tier is useful but limited; avoid high-frequency polling.",
    ),
    DataSourceSpec(
        name="Twelve Data",
        category="Paid / optional",
        env_vars=("TWELVE_DATA_API_KEY",),
        required=False,
        capabilities=("Time series", "technical indicators", "fundamentals on supported plans"),
        setup="Create a Twelve Data key and set TWELVE_DATA_API_KEY.",
        url="https://twelvedata.com/docs",
        tier="Paid / optional",
    ),
    DataSourceSpec(
        name="Alpha Vantage",
        category="Free key",
        env_vars=("ALPHA_VANTAGE_API_KEY",),
        required=False,
        capabilities=("Daily/intraday time series", "company overview", "earnings", "news sentiment"),
        setup="Create an Alpha Vantage key and set ALPHA_VANTAGE_API_KEY.",
        url="https://www.alphavantage.co/documentation/",
        tier="Free key",
        recommended_priority=6,
        quota_notes="Free tier has low request limits; use as fallback.",
    ),
    DataSourceSpec(
        name="IEX Cloud",
        category="Paid / optional",
        env_vars=("IEX_CLOUD_API_KEY",),
        required=False,
        capabilities=("Legacy equities data if account/API access remains available",),
        setup="Only use if you already have a viable IEX Cloud account, then set IEX_CLOUD_API_KEY.",
        url="https://iexcloud.io/docs/api/",
        notes="Viability has changed over time; prefer Polygon/Finnhub/Twelve Data unless you confirm account access.",
        tier="Paid / optional",
    ),
    DataSourceSpec(
        name="Nasdaq Data Link",
        category="Paid / optional",
        env_vars=("NASDAQ_DATA_LINK_API_KEY",),
        required=False,
        capabilities=("Premium datasets", "economic/alternative datasets", "some fundamentals depending on dataset"),
        setup="Create a Nasdaq Data Link key and set NASDAQ_DATA_LINK_API_KEY.",
        url="https://docs.data.nasdaq.com/",
        tier="Paid / optional",
    ),
    DataSourceSpec(
        name="Benzinga",
        category="Paid / optional",
        env_vars=("BENZINGA_API_KEY",),
        required=False,
        capabilities=("News", "earnings", "analyst ratings", "calendars on supported plans"),
        setup="Create a Benzinga API key and set BENZINGA_API_KEY.",
        url="https://docs.benzinga.io/",
        tier="Paid / optional",
        recommended_priority=21,
    ),
    DataSourceSpec(
        name="NewsAPI",
        category="Free key",
        env_vars=("NEWSAPI_KEY",),
        required=False,
        capabilities=("General news search", "headline monitoring"),
        setup="Create a NewsAPI key and set NEWSAPI_KEY.",
        url="https://newsapi.org/docs",
        notes="Not stock-specific; use alongside ticker/company disambiguation.",
        tier="Free key",
        recommended_priority=7,
        quota_notes="Developer tier can be delayed/limited and is not stock-specific.",
    ),
    DataSourceSpec(
        name="Earnings transcripts",
        category="Paid / optional",
        env_vars=("FINNHUB_API_KEY", "BENZINGA_API_KEY"),
        required=False,
        capabilities=("Transcript or earnings commentary when your chosen vendor supports it",),
        setup="Use a licensed transcript-capable provider; store only source links/summaries unless licensing allows full text.",
        url="https://finnhub.io/docs/api",
        notes="Transcript licensing varies. The MVP should mark transcripts unavailable unless a configured source supports them.",
        tier="Paid / optional",
    ),
    DataSourceSpec(
        name="Reddit API",
        category="Paid / optional",
        env_vars=("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"),
        required=False,
        capabilities=("Subreddit mention monitoring", "attention velocity", "source links"),
        setup="Create a Reddit app and set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET.",
        url="https://www.reddit.com/dev/api/",
        tier="Paid / optional",
    ),
    DataSourceSpec(
        name="X / Twitter API",
        category="Paid / optional",
        env_vars=("X_BEARER_TOKEN",),
        required=False,
        capabilities=("Public post search if plan allows", "attention velocity", "source links"),
        setup="Create an X developer app and set X_BEARER_TOKEN.",
        url="https://developer.x.com/en/docs",
        notes="Plan limits and access change frequently; manual CSV fallback remains supported.",
        tier="Paid / optional",
    ),
    DataSourceSpec(
        name="Truth Social / political mentions",
        category="Paid / optional",
        env_vars=(),
        required=False,
        capabilities=("Manual political/narrative event tagging",),
        setup="Use manual CSV fallback unless a compliant licensed source is selected later.",
        url="https://truthsocial.com/",
        notes="No credential scraping. Do not automate private accounts.",
        tier="Paid / optional",
    ),
    DataSourceSpec(
        name="StockTwits",
        category="Paid / optional",
        env_vars=("STOCKTWITS_ACCESS_TOKEN",),
        required=False,
        capabilities=("Symbol stream monitoring", "sentiment/attention clues where available"),
        setup="Set STOCKTWITS_ACCESS_TOKEN if using an approved StockTwits API flow.",
        url="https://api.stocktwits.com/developers/docs",
        tier="Paid / optional",
    ),
    DataSourceSpec(
        name="Manual catalyst/social CSV",
        category="No key / free",
        env_vars=(),
        required=False,
        capabilities=("Verified manual catalyst ingestion", "social fallback", "source URL tracking"),
        setup="Use config/catalysts_watchlist.csv or another CSV with the documented catalyst columns.",
        url="README.md",
        tier="No key / free",
        recommended_priority=2,
    ),
    DataSourceSpec(
        name="Manual insider/politician CSV",
        category="No key / free",
        env_vars=(),
        required=False,
        capabilities=("Manual insider trade context", "manual politician trade context", "source URL tracking", "disclosure lag warnings"),
        setup="Use config/alternative_data_watchlist.csv with verified source links. This never fabricates insider or politician data.",
        url="README.md",
        tier="No key / free",
        recommended_priority=2,
    ),
    DataSourceSpec(
        name="Quiver Insider Trading",
        category="Paid / optional",
        env_vars=("QUIVER_API_KEY",),
        required=False,
        capabilities=("Insider trading datasets if your Quiver plan supports them", "alternative-data context"),
        setup="Set QUIVER_API_KEY later if you add Quiver. Manual CSV remains the local fallback.",
        url="https://www.quiverquant.com/",
        notes="Optional paid source; not required for the scanner.",
        tier="Paid / optional",
        recommended_priority=22,
    ),
    DataSourceSpec(
        name="Quiver Congressional Trading",
        category="Paid / optional",
        env_vars=("QUIVER_API_KEY",),
        required=False,
        capabilities=("Congressional/politician trade datasets if your Quiver plan supports them", "disclosure context"),
        setup="Set QUIVER_API_KEY later if you add Quiver congressional data.",
        url="https://www.quiverquant.com/",
        notes="Politician trades can be delayed. Treat as context, not an automatic buy/sell signal.",
        tier="Paid / optional",
        recommended_priority=23,
    ),
    DataSourceSpec(
        name="Capitol Trades compatible API",
        category="Paid / optional",
        env_vars=("CAPITOL_TRADES_API_KEY",),
        required=False,
        capabilities=("Future compliant congressional trade adapter",),
        setup="Set CAPITOL_TRADES_API_KEY only after selecting a compliant source and license.",
        url="https://www.capitoltrades.com/",
        notes="Placeholder readiness only; manual CSV is supported today.",
        tier="Paid / optional",
    ),
    DataSourceSpec(
        name="Institutional 13F placeholder",
        category="Paid / optional",
        env_vars=(),
        required=False,
        capabilities=("Future institutional ownership and 13F context",),
        setup="Deferred. Use only licensed/public filings and preserve source links.",
        url="https://www.sec.gov/edgar/search/",
        tier="Paid / optional",
    ),
    DataSourceSpec(
        name="Lobbying / government contracts placeholder",
        category="Paid / optional",
        env_vars=("QUIVER_API_KEY",),
        required=False,
        capabilities=("Future government-contract/lobbying context if licensed source supports it",),
        setup="Deferred optional Quiver-style enrichment.",
        url="https://www.quiverquant.com/",
        tier="Paid / optional",
    ),
    DataSourceSpec(
        name="OpenAI",
        category="AI providers",
        env_vars=("OPENAI_API_KEY",),
        required=False,
        capabilities=("AI explanations", "analyst committee via OpenAI-compatible chat completions"),
        setup="Set OPENAI_API_KEY. Optional: OPENAI_MODEL.",
        url="https://platform.openai.com/docs",
        tier="AI",
        recommended_priority=1,
    ),
    DataSourceSpec(
        name="Anthropic Claude",
        category="AI providers",
        env_vars=("ANTHROPIC_API_KEY",),
        required=False,
        capabilities=("AI committee adapter when enabled", "bull/bear/risk/catalyst synthesis"),
        setup="Set ANTHROPIC_API_KEY. The current MVP detects readiness and keeps mock/offline flows available.",
        url="https://docs.anthropic.com/",
        tier="AI",
        recommended_priority=10,
    ),
    DataSourceSpec(
        name="Google Gemini",
        category="AI providers",
        env_vars=("GEMINI_API_KEY",),
        required=False,
        capabilities=("AI committee adapter when enabled", "research synthesis"),
        setup="Set GEMINI_API_KEY. The current MVP detects readiness and keeps mock/offline flows available.",
        url="https://ai.google.dev/gemini-api/docs",
        tier="AI",
        recommended_priority=2,
    ),
    DataSourceSpec(
        name="OpenRouter / OpenAI-compatible endpoint",
        category="AI providers",
        env_vars=("TRADEBRUV_LLM_API_KEY", "TRADEBRUV_LLM_BASE_URL"),
        required=False,
        capabilities=("OpenAI-compatible AI committee calls", "model routing through compatible providers"),
        setup="Set TRADEBRUV_LLM_API_KEY and TRADEBRUV_LLM_BASE_URL. Optional: TRADEBRUV_LLM_MODEL.",
        url="https://openrouter.ai/docs/api-reference/overview",
        tier="AI",
        recommended_priority=9,
    ),
    DataSourceSpec(
        name="Manual portfolio CSV",
        category="Future brokerage",
        env_vars=(),
        required=True,
        capabilities=("Read/write local holdings", "import/export", "portfolio-aware recommendations"),
        setup="Use the Portfolio page or CLI portfolio import/export commands.",
        url="README.md",
        tier="Future brokerage",
        recommended_priority=1,
    ),
    DataSourceSpec(
        name="Fidelity CSV export import",
        category="Future brokerage",
        env_vars=(),
        required=False,
        capabilities=("Local read-only import from exported holdings CSV", "no credentials stored"),
        setup="Export holdings from Fidelity, then import the CSV from the Portfolio page.",
        url="README.md",
        notes="CSV formats vary. Review imported quantities/cost basis before relying on analysis.",
        tier="Future brokerage",
    ),
    DataSourceSpec(
        name="Plaid Investments",
        category="Future brokerage",
        env_vars=("PLAID_CLIENT_ID", "PLAID_SECRET", "PLAID_ENV"),
        required=False,
        capabilities=("Read-only holdings/transactions integration if implemented later",),
        setup="Set PLAID_CLIENT_ID, PLAID_SECRET, and PLAID_ENV. This app does not connect broker accounts in the MVP.",
        url="https://plaid.com/docs/investments/",
        notes="Read-only research integration only. No order placement.",
        tier="Future brokerage",
    ),
    DataSourceSpec(
        name="SnapTrade",
        category="Future brokerage",
        env_vars=("SNAPTRADE_CLIENT_ID", "SNAPTRADE_CONSUMER_KEY"),
        required=False,
        capabilities=("Read-only brokerage holdings integration if implemented later",),
        setup="Set SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY. This app does not connect broker accounts in the MVP.",
        url="https://docs.snaptrade.com/",
        notes="Read-only research integration only. No credential scraping or trades.",
        tier="Future brokerage",
    ),
    DataSourceSpec(
        name="Fidelity Access",
        category="Future brokerage",
        env_vars=(),
        required=False,
        capabilities=("Potential read-only data access through approved partner channels",),
        setup="Use approved partner APIs only. Do not scrape credentials or web sessions.",
        url="https://clearingcustody.fidelity.com/app/proxy/content?literatureURL=/9901330.PDF",
        notes="Future research item, not implemented.",
        tier="Future brokerage",
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
                "tier": spec.tier,
                "recommended_priority": spec.recommended_priority,
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
                "quota_notes": spec.quota_notes,
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
    if spec.category.startswith("Future brokerage"):
        return f"{spec.name} live/read-only brokerage import is unavailable; manual CSV/local portfolio still works."
    if spec.name == "SEC EDGAR":
        return "SEC filings/Form 4 enrichment is unavailable until SEC_USER_AGENT is configured; price scanner still works."
    if spec.name == "Financial Modeling Prep":
        return "FMP fundamentals/statements enrichment is unavailable; yfinance/sample/local flows still work."
    if spec.name in {"Finnhub", "Alpha Vantage", "NewsAPI"}:
        return f"{spec.name} enrichment is unavailable; cheaper/no-key providers and manual source files still work."
    if spec.category in {"Social/attention", "No key / free", "Free key"}:
        return f"{spec.name} social attention is unavailable; manual CSV fallback still works."
    if spec.category == "News/events":
        return f"{spec.name} event/news enrichment is unavailable; scanner uses price/catalyst fields that exist."
    return f"{spec.name} enrichment is unavailable; free/sample/local providers still run."
