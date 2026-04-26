from __future__ import annotations

import csv
import importlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from .models import (
    CatalystSnapshot,
    FundamentalsSnapshot,
    OptionsSnapshot,
    PriceBar,
    SecurityData,
    ShortInterestSnapshot,
    SocialAttentionSnapshot,
)
from .taxonomy import infer_catalyst_tags, infer_theme_tags


SECTOR_BENCHMARKS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Consumer Discretionary": "XLY",
    "Communication Services": "XLC",
    "Financial Services": "XLF",
    "Financial": "XLF",
    "Industrials": "XLI",
    "Energy": "XLE",
}

BENCHMARK_SYMBOLS = {"SPY", "QQQ", *SECTOR_BENCHMARKS.values()}


class ProviderConfigurationError(RuntimeError):
    """Raised when a provider dependency or config is unavailable."""


class ProviderFetchError(RuntimeError):
    """Raised when a provider cannot load a symbol."""


class MarketDataProvider(Protocol):
    def get_security_data(self, ticker: str) -> SecurityData:
        ...


@dataclass(frozen=True)
class Phase:
    days: int
    drift: float
    amplitude: float
    volume_multiplier: float
    cycle: float = 4.0
    open_bias: float = 0.2


@dataclass(frozen=True)
class Event:
    price_boost: float
    volume_multiplier: float
    close_near_high: bool = True
    close_near_low: bool = False


class SampleMarketDataProvider:
    """Built-in deterministic data for development and tests."""

    def __init__(self, end_date: date | None = None) -> None:
        self.end_date = end_date or date.today()
        self._cache: dict[str, SecurityData] = {}

    def get_security_data(self, ticker: str) -> SecurityData:
        ticker = ticker.upper()
        if ticker in self._cache:
            return self._cache[ticker]
        if ticker not in SAMPLE_CONFIG:
            raise ProviderFetchError(f"Ticker {ticker} is unavailable in the sample provider.")

        config = SAMPLE_CONFIG[ticker]
        bars = _build_sample_bars(
            end_date=self.end_date,
            start_price=config["start_price"],
            base_volume=config["base_volume"],
            phases=config["phases"],
            events=config.get("events", {}),
        )
        catalyst = config.get("catalyst")
        catalyst_tags = list(config.get("catalyst_tags", ()))
        if catalyst and catalyst.catalyst_tags:
            catalyst_tags.extend(catalyst.catalyst_tags)
        theme_tags = list(
            config.get(
                "theme_tags",
                infer_theme_tags(
                    ticker=ticker,
                    sector=config.get("sector"),
                    industry=config.get("industry"),
                    texts=[config.get("company_name", ""), catalyst.description if catalyst else ""],
                ),
            )
        )
        security = SecurityData(
            ticker=ticker,
            company_name=config.get("company_name"),
            sector=config.get("sector"),
            industry=config.get("industry"),
            bars=bars,
            market_cap=config.get("market_cap"),
            ipo_date=(
                self.end_date - timedelta(days=config["ipo_age_days"])
                if config.get("ipo_age_days") is not None
                else None
            ),
            fundamentals=config.get("fundamentals"),
            catalyst=catalyst,
            next_earnings_date=(
                self.end_date + timedelta(days=config["earnings_offset"])
                if config.get("earnings_offset") is not None
                else None
            ),
            short_interest=config.get("short_interest"),
            social_attention=config.get("social_attention"),
            options_data=config.get("options_data"),
            theme_tags=theme_tags,
            catalyst_tags=sorted(dict.fromkeys(catalyst_tags)),
            provider_name="sample",
            source_notes=["Source: built-in deterministic sample data."],
            data_notes=config.get("notes", []).copy(),
            latest_available_close=bars[-1].close if bars else None,
            last_market_date=bars[-1].date if bars else None,
            is_adjusted_price=False,
        )
        self._cache[ticker] = security
        return security


class LocalFileMarketDataProvider:
    """
    Reads local market data from:
    - prices/<TICKER>.csv with date,open,high,low,close,volume
    - metadata.json keyed by ticker with optional company/fundamental/catalyst fields
    """

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.price_dir = self.data_dir / "prices"
        self.metadata = self._load_metadata(self.data_dir / "metadata.json")

    def get_security_data(self, ticker: str) -> SecurityData:
        ticker = ticker.upper()
        price_path = self.price_dir / f"{ticker}.csv"
        if not price_path.exists():
            raise ProviderFetchError(f"Missing price file: {price_path}")

        meta = self.metadata.get(ticker, {})
        catalyst = _parse_catalyst(meta.get("catalyst"))
        theme_tags = _normalize_str_list(meta.get("theme_tags"))
        catalyst_tags = _normalize_str_list(meta.get("catalyst_tags"))
        texts = [
            meta.get("company_name", ""),
            meta.get("industry", ""),
            catalyst.description if catalyst else "",
        ]
        if not theme_tags:
            theme_tags = infer_theme_tags(
                ticker=ticker,
                sector=meta.get("sector"),
                industry=meta.get("industry"),
                texts=texts,
            )
        if not catalyst_tags and catalyst:
            catalyst_tags = infer_catalyst_tags(catalyst.description or "")

        bars = self._load_bars(price_path)
        return SecurityData(
            ticker=ticker,
            company_name=meta.get("company_name"),
            sector=meta.get("sector"),
            industry=meta.get("industry"),
            bars=bars,
            market_cap=_coerce_float(meta.get("market_cap")),
            ipo_date=_parse_optional_date(meta.get("ipo_date")),
            fundamentals=_parse_fundamentals(meta.get("fundamentals")),
            catalyst=catalyst,
            next_earnings_date=_parse_optional_date(meta.get("next_earnings_date")),
            short_interest=_parse_short_interest(meta.get("short_interest")),
            social_attention=_parse_social_attention(meta.get("social_attention")),
            options_data=_parse_options(meta.get("options_data")),
            theme_tags=theme_tags,
            catalyst_tags=catalyst_tags,
            provider_name="local",
            source_notes=list(meta.get("source_notes", ["Source: local prices CSV + metadata.json."])),
            data_notes=list(meta.get("data_notes", [])),
            latest_available_close=bars[-1].close if bars else None,
            last_market_date=bars[-1].date if bars else None,
            is_adjusted_price=bool(meta.get("is_adjusted_price", False)),
        )

    @staticmethod
    def _load_bars(path: Path) -> list[PriceBar]:
        bars: list[PriceBar] = []
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                bars.append(
                    PriceBar(
                        date=date.fromisoformat(row["date"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    )
                )
        bars.sort(key=lambda bar: bar.date)
        if not bars:
            raise ProviderFetchError(f"Price file {path} contained no data.")
        return bars

    @staticmethod
    def _load_metadata(path: Path) -> dict[str, dict]:
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return {ticker.upper(): payload for ticker, payload in data.items()}


class YFinanceMarketDataProvider:
    """Real-data provider backed by yfinance."""

    def __init__(self, history_period: str = "3y") -> None:
        self.history_period = history_period
        self._cache: dict[str, SecurityData] = {}
        spec = importlib.util.find_spec("yfinance")
        if spec is None:
            raise ProviderConfigurationError(
                "yfinance is not installed. Install the optional real-data dependency to use --provider real."
            )
        self._yf = importlib.import_module("yfinance")

    def get_security_data(self, ticker: str) -> SecurityData:
        ticker = ticker.upper()
        if ticker in self._cache:
            return self._cache[ticker]
        benchmark_symbol = ticker in BENCHMARK_SYMBOLS

        try:
            instrument = self._yf.Ticker(ticker)
            history = instrument.history(period=self.history_period, interval="1d", auto_adjust=True)
        except Exception as exc:
            raise ProviderFetchError(f"Could not fetch {ticker} history from yfinance: {exc}") from exc
        if history is None or history.empty:
            raise ProviderFetchError(f"No history returned for {ticker} from yfinance.")

        bars = self._history_to_bars(history)
        info = self._safe_info(instrument)
        fast_info = self._safe_fast_info(instrument)
        news_items = [] if benchmark_symbol else self._safe_news(instrument)
        news_titles = [item["title"] for item in news_items if item.get("title")]
        next_earnings_date = None if benchmark_symbol else self._safe_earnings_date(instrument)
        short_interest = self._build_short_interest(info)
        social_attention = self._build_attention(news_items)
        options_data = None if benchmark_symbol else self._build_options(instrument, next_earnings_date)
        fundamentals = None if benchmark_symbol else self._build_fundamentals(instrument, info)
        catalyst = self._build_catalyst(bars, news_titles)

        sector = info.get("sector")
        industry = info.get("industry")
        company_name = info.get("longName") or info.get("shortName") or ticker
        theme_tags = infer_theme_tags(
            ticker=ticker,
            sector=sector,
            industry=industry,
            texts=[company_name, info.get("longBusinessSummary", ""), *news_titles[:5]],
        )
        catalyst_tags = infer_catalyst_tags(*(news_titles[:5] + ([catalyst.description] if catalyst and catalyst.description else [])))

        security = SecurityData(
            ticker=ticker,
            company_name=company_name,
            sector=sector,
            industry=industry,
            bars=bars,
            market_cap=_coerce_float(
                fast_info.get("market_cap") or fast_info.get("marketCap") or info.get("marketCap")
            ),
            ipo_date=_coerce_ipo_date(info, bars),
            fundamentals=fundamentals,
            catalyst=catalyst,
            next_earnings_date=next_earnings_date,
            short_interest=short_interest,
            social_attention=social_attention,
            options_data=options_data,
            theme_tags=theme_tags,
            catalyst_tags=catalyst_tags,
            provider_name="real",
            source_notes=[
                "Source: yfinance history/info/earnings/news endpoints.",
                "Short interest, earnings, and news fields may be partial depending on Yahoo availability.",
            ],
            data_notes=[],
            quote_price_if_available=_coerce_float(fast_info.get("last_price") or fast_info.get("lastPrice") or info.get("currentPrice")),
            quote_timestamp=datetime.utcnow().isoformat() + "Z",
            latest_available_close=bars[-1].close if bars else None,
            last_market_date=bars[-1].date if bars else None,
            is_adjusted_price=True,
        )
        self._cache[ticker] = security
        return security

    @staticmethod
    def _history_to_bars(history: Any) -> list[PriceBar]:
        bars: list[PriceBar] = []
        for index, row in history.iterrows():
            if any(column not in row for column in ("Open", "High", "Low", "Close", "Volume")):
                continue
            bars.append(
                PriceBar(
                    date=index.date() if hasattr(index, "date") else date.fromisoformat(str(index)[:10]),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
            )
        if not bars:
            raise ProviderFetchError("History payload contained no valid OHLCV rows.")
        return bars

    @staticmethod
    def _safe_info(instrument: Any) -> dict[str, Any]:
        try:
            return dict(instrument.info or {})
        except Exception:
            return {}

    @staticmethod
    def _safe_fast_info(instrument: Any) -> dict[str, Any]:
        try:
            fast_info = instrument.fast_info
        except Exception:
            return {}
        try:
            return dict(fast_info)
        except Exception:
            payload: dict[str, Any] = {}
            for key in (
                "market_cap",
                "last_price",
                "year_high",
                "year_low",
                "shares",
            ):
                try:
                    payload[key] = getattr(fast_info, key)
                except Exception:
                    continue
            return payload

    @staticmethod
    def _safe_news(instrument: Any) -> list[dict[str, Any]]:
        try:
            news = instrument.get_news(count=20)
        except Exception:
            try:
                news = instrument.news
            except Exception:
                news = []
        return list(news or [])

    @staticmethod
    def _safe_earnings_date(instrument: Any) -> date | None:
        try:
            earnings_dates = instrument.get_earnings_dates(limit=1)
        except Exception:
            earnings_dates = None
        if earnings_dates is None or getattr(earnings_dates, "empty", True):
            return None
        try:
            index = earnings_dates.index[0]
            return index.date() if hasattr(index, "date") else date.fromisoformat(str(index)[:10])
        except Exception:
            return None

    def _build_fundamentals(self, instrument: Any, info: dict[str, Any]) -> FundamentalsSnapshot | None:
        revenue_growth = _coerce_float(info.get("revenueGrowth"))
        eps_growth = _coerce_float(info.get("earningsGrowth"))
        profitability_positive = None
        profit_margins = _coerce_float(info.get("profitMargins"))
        if profit_margins is not None:
            profitability_positive = profit_margins > 0

        analyst_revision_score = None
        try:
            revisions = instrument.get_eps_revisions(as_dict=False)
        except Exception:
            revisions = None
        if revisions is not None and not getattr(revisions, "empty", True):
            up = down = 0.0
            for column in ("upLast7days", "upLast30days"):
                if column in revisions.columns:
                    up += float(revisions[column].fillna(0).sum())
            for column in ("downLast7days", "downLast30days"):
                if column in revisions.columns:
                    down += float(revisions[column].fillna(0).sum())
            total = up + down
            analyst_revision_score = ((up - down) / total) if total else None

        recent_dilution = None
        try:
            shares = instrument.get_shares_full(start=(date.today() - timedelta(days=550)).isoformat())
        except Exception:
            shares = None
        if shares is not None and not getattr(shares, "empty", True):
            try:
                first = float(shares.iloc[0])
                last = float(shares.iloc[-1])
                if first > 0:
                    recent_dilution = ((last / first) - 1.0) > 0.05
            except Exception:
                recent_dilution = None

        institutional_support = None
        held_percent = _coerce_float(info.get("heldPercentInstitutions"))
        if held_percent is not None:
            institutional_support = held_percent >= 0.35

        if all(
            value is None
            for value in (
                revenue_growth,
                eps_growth,
                analyst_revision_score,
                profit_margins,
                recent_dilution,
                institutional_support,
            )
        ):
            return None

        return FundamentalsSnapshot(
            revenue_growth=revenue_growth,
            eps_growth=eps_growth,
            margin_change=None,
            free_cash_flow_growth=None,
            analyst_revision_score=analyst_revision_score,
            guidance_improvement=None,
            profitability_positive=profitability_positive,
            recent_dilution=recent_dilution,
            earnings_beat=None,
            estimate_revision_trend=analyst_revision_score,
            institutional_support=institutional_support,
        )

    @staticmethod
    def _build_catalyst(bars: list[PriceBar], news_titles: list[str]) -> CatalystSnapshot | None:
        catalyst_tags = infer_catalyst_tags(*news_titles[:5])
        has_catalyst = bool(catalyst_tags)
        if not has_catalyst:
            return None
        recent_bars = bars[-5:]
        avg_recent_volume = sum(bar.volume for bar in recent_bars) / max(len(recent_bars), 1)
        avg_prior_volume = sum(bar.volume for bar in bars[-25:-5]) / max(len(bars[-25:-5]), 1)
        recent_return = (recent_bars[-1].close / recent_bars[0].close) - 1.0 if len(recent_bars) >= 2 else 0.0
        return CatalystSnapshot(
            has_catalyst=True,
            description="; ".join(news_titles[:3]),
            price_reaction_positive=recent_return > 0.03,
            volume_confirmation=avg_prior_volume > 0 and avg_recent_volume >= avg_prior_volume * 1.2,
            holds_gains=recent_bars[-1].close >= max(bar.close for bar in recent_bars[:-1]),
            hype_risk=False,
            catalyst_tags=tuple(catalyst_tags),
        )

    @staticmethod
    def _build_short_interest(info: dict[str, Any]) -> ShortInterestSnapshot | None:
        short_percent = _coerce_float(info.get("shortPercentOfFloat"))
        short_ratio = _coerce_float(info.get("shortRatio"))
        float_shares = _coerce_float(info.get("floatShares"))
        borrow_cost = _coerce_float(info.get("borrowRate"))
        if all(value is None for value in (short_percent, short_ratio, float_shares, borrow_cost)):
            return None
        return ShortInterestSnapshot(
            short_interest_percent_float=short_percent,
            days_to_cover=short_ratio,
            float_shares=float_shares,
            borrow_cost=borrow_cost,
            institutional_activity_positive=None,
            insider_activity_positive=None,
        )

    @staticmethod
    def _build_attention(news_items: list[dict[str, Any]]) -> SocialAttentionSnapshot | None:
        if not news_items:
            return None
        return SocialAttentionSnapshot(
            reddit_mention_count=None,
            twitter_mention_count=None,
            truth_social_mention_flag=None,
            news_headline_count=len(news_items),
            news_sentiment=None,
            catalyst_source="Yahoo Finance news",
            attention_velocity=None,
        )

    @staticmethod
    def _build_options(instrument: Any, earnings_date: date | None) -> OptionsSnapshot | None:
        try:
            expiries = list(instrument.options or [])
        except Exception:
            expiries = []
        if not expiries and earnings_date is None:
            return None
        days_to_earnings = (earnings_date - date.today()).days if earnings_date else None
        return OptionsSnapshot(
            options_interest_available=bool(expiries),
            unusual_options_activity=None,
            options_daytrade_candidate=None,
            implied_volatility_warning=None,
            earnings_iv_risk=bool(expiries and days_to_earnings is not None and days_to_earnings <= 14),
        )


def _normalize_str_list(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        return [values]
    return [str(value) for value in values]


def _parse_optional_date(raw: Any) -> date | None:
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    return date.fromisoformat(str(raw))


def _parse_fundamentals(payload: dict | None) -> FundamentalsSnapshot | None:
    if not payload:
        return None
    return FundamentalsSnapshot(**payload)


def _parse_catalyst(payload: dict | None) -> CatalystSnapshot | None:
    if not payload:
        return None
    if "catalyst_tags" in payload and isinstance(payload["catalyst_tags"], list):
        payload = {**payload, "catalyst_tags": tuple(payload["catalyst_tags"])}
    return CatalystSnapshot(**payload)


def _parse_short_interest(payload: dict | None) -> ShortInterestSnapshot | None:
    if not payload:
        return None
    return ShortInterestSnapshot(**payload)


def _parse_social_attention(payload: dict | None) -> SocialAttentionSnapshot | None:
    if not payload:
        return None
    return SocialAttentionSnapshot(**payload)


def _parse_options(payload: dict | None) -> OptionsSnapshot | None:
    if not payload:
        return None
    return OptionsSnapshot(**payload)


def _coerce_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_ipo_date(info: dict[str, Any], bars: list[PriceBar]) -> date | None:
    raw = info.get("firstTradeDateEpochUtc") or info.get("firstTradeDateMilliseconds")
    if raw:
        try:
            raw_value = float(raw)
            if raw_value > 10_000_000_000:
                raw_value /= 1000
            return datetime.utcfromtimestamp(raw_value).date()
        except Exception:
            return None
    if len(bars) < 252:
        return bars[0].date
    return None


def _build_sample_bars(
    *,
    end_date: date,
    start_price: float,
    base_volume: int,
    phases: list[Phase],
    events: dict[int, Event],
) -> list[PriceBar]:
    trading_days = _business_days(end_date=end_date, count=sum(phase.days for phase in phases))
    bars: list[PriceBar] = []
    price = start_price
    day_index = 0

    for phase in phases:
        for _ in range(phase.days):
            wave = phase.amplitude * math.sin(day_index / phase.cycle)
            daily_move = phase.drift + wave
            event = events.get(day_index)
            if event:
                daily_move += event.price_boost

            previous_close = price
            open_price = max(1.0, previous_close * (1.0 + daily_move * phase.open_bias))
            close_price = max(1.0, previous_close * (1.0 + daily_move))
            intraday_span = max(abs(daily_move) * 1.75, 0.012)
            high_price = max(open_price, close_price) * (1.0 + intraday_span)
            low_price = min(open_price, close_price) * (1.0 - intraday_span * 0.92)

            if event and event.close_near_high:
                close_price = high_price * 0.985
            if event and event.close_near_low:
                close_price = low_price * 1.015

            volume = int(base_volume * phase.volume_multiplier * (1.0 + abs(daily_move) * 10))
            if event:
                volume = int(volume * event.volume_multiplier)

            bars.append(
                PriceBar(
                    date=trading_days[day_index],
                    open=round(open_price, 2),
                    high=round(max(high_price, open_price, close_price), 2),
                    low=round(min(low_price, open_price, close_price), 2),
                    close=round(close_price, 2),
                    volume=volume,
                )
            )
            price = close_price
            day_index += 1
    return bars


def _business_days(*, end_date: date, count: int) -> list[date]:
    days: list[date] = []
    current = end_date
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    days.reverse()
    return days


SAMPLE_CONFIG: dict[str, dict[str, Any]] = {
    "SPY": {
        "company_name": "SPDR S&P 500 ETF Trust",
        "sector": None,
        "industry": "Broad Market ETF",
        "start_price": 470.0,
        "base_volume": 38_000_000,
        "phases": [
            Phase(90, 0.0005, 0.0028, 1.0),
            Phase(90, 0.0004, 0.0025, 0.95),
            Phase(80, 0.0007, 0.0022, 1.05),
        ],
    },
    "QQQ": {
        "company_name": "Invesco QQQ Trust",
        "sector": None,
        "industry": "Broad Market ETF",
        "start_price": 395.0,
        "base_volume": 31_000_000,
        "phases": [
            Phase(90, 0.0007, 0.0030, 1.0),
            Phase(90, 0.0006, 0.0027, 0.98),
            Phase(80, 0.0009, 0.0025, 1.04),
        ],
    },
    "XLK": {
        "company_name": "Technology Select Sector SPDR Fund",
        "sector": None,
        "industry": "Sector ETF",
        "start_price": 185.0,
        "base_volume": 7_100_000,
        "phases": [
            Phase(110, 0.0008, 0.0030, 1.0),
            Phase(70, 0.0006, 0.0028, 0.97),
            Phase(80, 0.0010, 0.0024, 1.05),
        ],
    },
    "XLV": {
        "company_name": "Health Care Select Sector SPDR Fund",
        "sector": None,
        "industry": "Sector ETF",
        "start_price": 140.0,
        "base_volume": 9_400_000,
        "phases": [
            Phase(100, 0.0005, 0.0022, 1.0),
            Phase(80, 0.0003, 0.0020, 0.96),
            Phase(80, 0.0007, 0.0018, 1.02),
        ],
    },
    "XLY": {
        "company_name": "Consumer Discretionary Select Sector SPDR Fund",
        "sector": None,
        "industry": "Sector ETF",
        "start_price": 174.0,
        "base_volume": 4_700_000,
        "phases": [
            Phase(120, 0.0003, 0.0024, 1.0),
            Phase(70, 0.0002, 0.0022, 0.94),
            Phase(70, 0.0005, 0.0020, 1.0),
        ],
    },
    "NVDA": {
        "company_name": "NVIDIA Corporation",
        "sector": "Technology",
        "industry": "Semiconductors",
        "market_cap": 2_700_000_000_000,
        "start_price": 690.0,
        "base_volume": 49_000_000,
        "phases": [
            Phase(110, 0.0014, 0.0055, 1.0),
            Phase(60, 0.0004, 0.0030, 0.84),
            Phase(30, 0.0012, 0.0035, 1.18),
            Phase(60, 0.0010, 0.0032, 1.05),
        ],
        "events": {
            185: Event(0.038, 2.6, close_near_high=True),
            208: Event(0.018, 1.8, close_near_high=True),
        },
        "fundamentals": FundamentalsSnapshot(
            revenue_growth=0.48,
            eps_growth=0.61,
            margin_change=0.05,
            free_cash_flow_growth=0.39,
            analyst_revision_score=0.8,
            guidance_improvement=True,
            profitability_positive=True,
            recent_dilution=False,
            estimate_revision_trend=0.8,
            institutional_support=True,
        ),
        "catalyst": CatalystSnapshot(
            has_catalyst=True,
            description="Enterprise AI demand and raised guidance",
            price_reaction_positive=True,
            volume_confirmation=True,
            holds_gains=True,
            hype_risk=False,
            catalyst_tags=("Guidance raise", "AI/data center/semiconductor narrative"),
        ),
        "short_interest": ShortInterestSnapshot(
            short_interest_percent_float=0.012,
            days_to_cover=0.7,
            float_shares=24_800_000_000,
            borrow_cost=0.01,
            institutional_activity_positive=True,
        ),
        "social_attention": SocialAttentionSnapshot(
            news_headline_count=18,
            news_sentiment=0.7,
            catalyst_source="sample",
            attention_velocity=0.4,
        ),
        "options_data": OptionsSnapshot(
            options_interest_available=True,
            unusual_options_activity=None,
            options_daytrade_candidate=None,
            implied_volatility_warning=None,
            earnings_iv_risk=False,
        ),
        "earnings_offset": 18,
        "theme_tags": ["AI", "Semiconductors", "Data center"],
        "catalyst_tags": ["Guidance raise", "AI/data center/semiconductor narrative"],
    },
    "MSFT": {
        "company_name": "Microsoft Corporation",
        "sector": "Technology",
        "industry": "Cloud/software",
        "market_cap": 3_000_000_000_000,
        "start_price": 380.0,
        "base_volume": 23_000_000,
        "phases": [
            Phase(120, 0.0010, 0.0032, 1.0),
            Phase(50, 0.0004, 0.0024, 0.9),
            Phase(90, 0.0009, 0.0026, 1.02),
        ],
        "fundamentals": FundamentalsSnapshot(
            revenue_growth=0.15,
            eps_growth=0.18,
            margin_change=0.02,
            free_cash_flow_growth=0.12,
            analyst_revision_score=0.4,
            profitability_positive=True,
            recent_dilution=False,
            institutional_support=True,
        ),
        "social_attention": SocialAttentionSnapshot(
            news_headline_count=8,
            news_sentiment=0.5,
            catalyst_source="sample",
        ),
        "options_data": OptionsSnapshot(options_interest_available=True),
        "earnings_offset": 28,
        "theme_tags": ["AI", "Cloud/software", "Data center"],
    },
    "LLY": {
        "company_name": "Eli Lilly and Company",
        "sector": "Healthcare",
        "industry": "Biopharma",
        "market_cap": 850_000_000_000,
        "start_price": 720.0,
        "base_volume": 3_700_000,
        "phases": [
            Phase(120, 0.0011, 0.0035, 1.0),
            Phase(45, -0.0009, 0.0038, 1.0),
            Phase(35, 0.0001, 0.0018, 0.82),
            Phase(60, 0.0010, 0.0026, 1.06),
        ],
        "events": {204: Event(0.028, 2.2, close_near_high=True)},
        "fundamentals": FundamentalsSnapshot(
            revenue_growth=0.21,
            eps_growth=0.24,
            margin_change=0.03,
            free_cash_flow_growth=0.14,
            analyst_revision_score=0.5,
            guidance_improvement=True,
            profitability_positive=True,
            recent_dilution=False,
            institutional_support=True,
        ),
        "catalyst": CatalystSnapshot(
            has_catalyst=True,
            description="Clinical update with constructive price confirmation",
            price_reaction_positive=True,
            volume_confirmation=True,
            holds_gains=True,
            hype_risk=False,
            catalyst_tags=("Major contract",),
        ),
        "earnings_offset": 24,
    },
    "PLTR": {
        "company_name": "Palantir Technologies Inc.",
        "sector": "Technology",
        "industry": "Cloud/software",
        "market_cap": 90_000_000_000,
        "start_price": 24.0,
        "base_volume": 62_000_000,
        "phases": [
            Phase(90, 0.0013, 0.0060, 1.0),
            Phase(60, 0.0007, 0.0046, 0.9),
            Phase(50, 0.0010, 0.0042, 1.12),
            Phase(60, 0.0009, 0.0038, 1.0),
        ],
        "events": {
            155: Event(0.024, 2.0, close_near_high=True),
            182: Event(0.019, 1.8, close_near_high=True),
            219: Event(0.022, 2.1, close_near_high=True),
        },
        "fundamentals": FundamentalsSnapshot(
            revenue_growth=0.19,
            eps_growth=0.25,
            margin_change=0.04,
            free_cash_flow_growth=0.17,
            analyst_revision_score=0.3,
            profitability_positive=True,
            recent_dilution=False,
            institutional_support=True,
        ),
        "short_interest": ShortInterestSnapshot(
            short_interest_percent_float=0.055,
            days_to_cover=1.5,
            float_shares=2_000_000_000,
            institutional_activity_positive=True,
        ),
        "social_attention": SocialAttentionSnapshot(
            reddit_mention_count=140,
            twitter_mention_count=320,
            news_headline_count=10,
            attention_velocity=0.6,
            catalyst_source="sample",
        ),
        "options_data": OptionsSnapshot(options_interest_available=True),
        "earnings_offset": 20,
        "theme_tags": ["AI", "Defense", "Cloud/software"],
    },
    "ENPH": {
        "company_name": "Enphase Energy, Inc.",
        "sector": "Technology",
        "industry": "Solar",
        "market_cap": 16_000_000_000,
        "start_price": 135.0,
        "base_volume": 5_900_000,
        "phases": [
            Phase(70, 0.0006, 0.0040, 1.0),
            Phase(40, 0.0003, 0.0020, 0.84),
            Phase(30, 0.0009, 0.0028, 1.2),
            Phase(120, -0.0010, 0.0048, 1.08),
        ],
        "events": {
            116: Event(0.051, 3.2, close_near_high=False, close_near_low=True),
            130: Event(-0.032, 2.4, close_near_high=False, close_near_low=True),
        },
        "fundamentals": FundamentalsSnapshot(
            revenue_growth=-0.08,
            eps_growth=-0.14,
            margin_change=-0.03,
            free_cash_flow_growth=-0.19,
            analyst_revision_score=-0.5,
            guidance_improvement=False,
            profitability_positive=False,
            recent_dilution=False,
        ),
        "catalyst": CatalystSnapshot(
            has_catalyst=True,
            description="Headline pop that failed to hold",
            price_reaction_positive=False,
            volume_confirmation=False,
            holds_gains=False,
            hype_risk=True,
            catalyst_tags=("Regulatory/policy shift",),
        ),
        "social_attention": SocialAttentionSnapshot(
            reddit_mention_count=30,
            news_headline_count=15,
            attention_velocity=0.9,
            catalyst_source="sample",
        ),
        "options_data": OptionsSnapshot(options_interest_available=True),
        "earnings_offset": 6,
    },
    "RIVN": {
        "company_name": "Rivian Automotive, Inc.",
        "sector": "Consumer Discretionary",
        "industry": "EV",
        "market_cap": 11_000_000_000,
        "start_price": 21.0,
        "base_volume": 34_000_000,
        "phases": [
            Phase(90, -0.0010, 0.0052, 1.0),
            Phase(70, -0.0008, 0.0048, 1.04),
            Phase(40, -0.0014, 0.0060, 1.18),
            Phase(60, -0.0009, 0.0056, 1.12),
        ],
        "events": {
            122: Event(-0.055, 2.8, close_near_high=False, close_near_low=True),
            174: Event(-0.048, 3.0, close_near_high=False, close_near_low=True),
            233: Event(-0.052, 2.9, close_near_high=False, close_near_low=True),
        },
        "fundamentals": FundamentalsSnapshot(
            revenue_growth=0.02,
            eps_growth=-0.12,
            margin_change=-0.04,
            free_cash_flow_growth=-0.26,
            analyst_revision_score=-0.6,
            guidance_improvement=False,
            profitability_positive=False,
            recent_dilution=True,
        ),
        "catalyst": CatalystSnapshot(
            has_catalyst=True,
            description="Attention spike without durable confirmation",
            price_reaction_positive=False,
            volume_confirmation=False,
            holds_gains=False,
            hype_risk=True,
            catalyst_tags=("Short squeeze conditions",),
        ),
        "short_interest": ShortInterestSnapshot(
            short_interest_percent_float=0.14,
            days_to_cover=5.1,
            float_shares=950_000_000,
            borrow_cost=0.06,
        ),
        "social_attention": SocialAttentionSnapshot(
            reddit_mention_count=220,
            twitter_mention_count=450,
            news_headline_count=20,
            attention_velocity=1.4,
            catalyst_source="sample",
        ),
        "options_data": OptionsSnapshot(options_interest_available=True, earnings_iv_risk=True),
        "earnings_offset": 4,
    },
    "MU": {
        "company_name": "Micron Technology, Inc.",
        "sector": "Technology",
        "industry": "Semiconductors",
        "market_cap": 150_000_000_000,
        "start_price": 78.0,
        "base_volume": 17_000_000,
        "phases": [
            Phase(100, 0.0010, 0.0045, 1.0),
            Phase(50, 0.0004, 0.0020, 0.82),
            Phase(35, 0.0013, 0.0034, 1.30),
            Phase(65, 0.0010, 0.0032, 1.02),
        ],
        "events": {192: Event(0.032, 2.2, close_near_high=True)},
        "fundamentals": FundamentalsSnapshot(
            revenue_growth=0.26,
            eps_growth=0.42,
            margin_change=0.07,
            free_cash_flow_growth=0.31,
            analyst_revision_score=0.55,
            guidance_improvement=True,
            profitability_positive=True,
            recent_dilution=False,
            institutional_support=True,
        ),
        "catalyst": CatalystSnapshot(
            has_catalyst=True,
            description="Memory cycle repricing with pricing power confirmation",
            price_reaction_positive=True,
            volume_confirmation=True,
            holds_gains=True,
            hype_risk=False,
            catalyst_tags=("Raised estimates", "AI/data center/semiconductor narrative"),
        ),
        "theme_tags": ["AI", "Semiconductors", "Data center"],
        "earnings_offset": 32,
    },
    "RDDT": {
        "company_name": "Reddit, Inc.",
        "sector": "Communication Services",
        "industry": "Social platforms",
        "market_cap": 18_000_000_000,
        "start_price": 45.0,
        "base_volume": 9_000_000,
        "phases": [
            Phase(60, 0.0008, 0.0050, 1.0),
            Phase(35, 0.0002, 0.0022, 0.82),
            Phase(45, 0.0015, 0.0042, 1.35),
            Phase(40, 0.0010, 0.0034, 1.04),
        ],
        "events": {132: Event(0.041, 2.8, close_near_high=True)},
        "fundamentals": FundamentalsSnapshot(
            revenue_growth=0.38,
            eps_growth=0.12,
            margin_change=0.05,
            analyst_revision_score=0.35,
            profitability_positive=True,
            recent_dilution=False,
            institutional_support=True,
        ),
        "catalyst": CatalystSnapshot(
            has_catalyst=True,
            description="Post-IPO breakout backed by strong advertising narrative",
            price_reaction_positive=True,
            volume_confirmation=True,
            holds_gains=True,
            hype_risk=False,
            catalyst_tags=("IPO/post-IPO breakout",),
        ),
        "social_attention": SocialAttentionSnapshot(
            reddit_mention_count=800,
            twitter_mention_count=500,
            news_headline_count=22,
            attention_velocity=1.1,
            catalyst_source="sample",
        ),
        "options_data": OptionsSnapshot(options_interest_available=True),
        "earnings_offset": 26,
        "ipo_age_days": 220,
        "theme_tags": ["IPO", "Social platforms", "Advertising"],
    },
    "GME": {
        "company_name": "GameStop Corp.",
        "sector": "Consumer Discretionary",
        "industry": "Retail",
        "market_cap": 9_000_000_000,
        "start_price": 18.0,
        "base_volume": 26_000_000,
        "phases": [
            Phase(100, 0.0002, 0.0060, 0.95),
            Phase(20, -0.0004, 0.0040, 0.84),
            Phase(12, 0.0060, 0.0100, 2.2),
            Phase(20, 0.0020, 0.0068, 1.8),
            Phase(100, -0.0006, 0.0065, 1.1),
        ],
        "events": {
            125: Event(0.085, 4.2, close_near_high=True),
            126: Event(0.062, 3.8, close_near_high=True),
        },
        "fundamentals": FundamentalsSnapshot(
            revenue_growth=-0.05,
            eps_growth=-0.10,
            analyst_revision_score=-0.2,
            profitability_positive=False,
            recent_dilution=True,
        ),
        "catalyst": CatalystSnapshot(
            has_catalyst=True,
            description="Short squeeze narrative with unstable follow-through",
            price_reaction_positive=True,
            volume_confirmation=True,
            holds_gains=False,
            hype_risk=True,
            catalyst_tags=("Short squeeze conditions",),
        ),
        "short_interest": ShortInterestSnapshot(
            short_interest_percent_float=0.28,
            days_to_cover=6.8,
            float_shares=270_000_000,
            borrow_cost=0.12,
        ),
        "social_attention": SocialAttentionSnapshot(
            reddit_mention_count=2200,
            twitter_mention_count=3400,
            truth_social_mention_flag=True,
            news_headline_count=30,
            attention_velocity=2.2,
            catalyst_source="sample",
        ),
        "options_data": OptionsSnapshot(options_interest_available=True, options_daytrade_candidate=True),
        "earnings_offset": 11,
        "theme_tags": ["Short squeeze", "Retail speculation"],
    },
    "CAR": {
        "company_name": "Avis Budget Group, Inc.",
        "sector": "Consumer Discretionary",
        "industry": "Travel services",
        "market_cap": 4_500_000_000,
        "start_price": 93.0,
        "base_volume": 1_300_000,
        "phases": [
            Phase(110, 0.0009, 0.0042, 0.95),
            Phase(25, 0.0001, 0.0020, 0.80),
            Phase(10, 0.0090, 0.0120, 3.4),
            Phase(35, 0.0018, 0.0060, 1.6),
            Phase(70, -0.0006, 0.0044, 1.0),
        ],
        "events": {136: Event(0.12, 4.8, close_near_high=True)},
        "fundamentals": FundamentalsSnapshot(
            revenue_growth=0.11,
            eps_growth=0.25,
            margin_change=0.02,
            analyst_revision_score=0.15,
            profitability_positive=True,
            recent_dilution=False,
        ),
        "catalyst": CatalystSnapshot(
            has_catalyst=True,
            description="Explosive repricing with squeeze conditions after strong results",
            price_reaction_positive=True,
            volume_confirmation=True,
            holds_gains=True,
            hype_risk=False,
            catalyst_tags=("Earnings beat", "Short squeeze conditions"),
        ),
        "short_interest": ShortInterestSnapshot(
            short_interest_percent_float=0.22,
            days_to_cover=7.0,
            float_shares=28_000_000,
            borrow_cost=0.09,
        ),
        "social_attention": SocialAttentionSnapshot(
            news_headline_count=12,
            attention_velocity=1.4,
            catalyst_source="sample",
        ),
        "options_data": OptionsSnapshot(options_interest_available=True),
        "earnings_offset": 29,
        "theme_tags": ["Travel/reopening", "Short squeeze"],
    },
    "COIN": {
        "company_name": "Coinbase Global, Inc.",
        "sector": "Financial Services",
        "industry": "Fintech",
        "market_cap": 75_000_000_000,
        "start_price": 140.0,
        "base_volume": 11_000_000,
        "phases": [
            Phase(90, 0.0012, 0.0062, 1.0),
            Phase(40, -0.0005, 0.0040, 0.92),
            Phase(40, 0.0016, 0.0050, 1.4),
            Phase(60, 0.0010, 0.0040, 1.08),
        ],
        "events": {170: Event(0.044, 2.5, close_near_high=True)},
        "fundamentals": FundamentalsSnapshot(
            revenue_growth=0.30,
            eps_growth=0.45,
            margin_change=0.06,
            analyst_revision_score=0.4,
            profitability_positive=True,
            recent_dilution=False,
        ),
        "catalyst": CatalystSnapshot(
            has_catalyst=True,
            description="Crypto-related equity repricing with real volume follow-through",
            price_reaction_positive=True,
            volume_confirmation=True,
            holds_gains=True,
            hype_risk=False,
            catalyst_tags=("Regulatory/policy shift",),
        ),
        "short_interest": ShortInterestSnapshot(
            short_interest_percent_float=0.09,
            days_to_cover=2.5,
            float_shares=200_000_000,
            borrow_cost=0.04,
        ),
        "social_attention": SocialAttentionSnapshot(
            twitter_mention_count=1200,
            news_headline_count=26,
            attention_velocity=1.0,
            catalyst_source="sample",
        ),
        "options_data": OptionsSnapshot(options_interest_available=True),
        "earnings_offset": 22,
        "theme_tags": ["Crypto-related equities", "Fintech"],
    },
}
