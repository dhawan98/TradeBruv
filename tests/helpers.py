from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from functools import lru_cache

from tradebruv.models import (
    CatalystSnapshot,
    FundamentalsSnapshot,
    OptionsSnapshot,
    PriceBar,
    SecurityData,
    ShortInterestSnapshot,
    SocialAttentionSnapshot,
)
from tradebruv.providers import SampleMarketDataProvider
from tradebruv.scanner import DeterministicScanner


ANCHOR = date(2026, 4, 24)


@lru_cache(maxsize=1)
def sample_results():
    provider = SampleMarketDataProvider(end_date=ANCHOR)
    scanner = DeterministicScanner(provider=provider, analysis_date=ANCHOR)
    results = scanner.scan(["NVDA", "MSFT", "LLY", "PLTR", "ENPH", "RIVN"])
    return {result.ticker: result for result in results}


@lru_cache(maxsize=1)
def sample_outlier_results():
    provider = SampleMarketDataProvider(end_date=ANCHOR)
    scanner = DeterministicScanner(provider=provider, analysis_date=ANCHOR)
    results = scanner.scan(["NVDA", "LLY", "PLTR", "ENPH", "RIVN"], mode="outliers")
    return {result.ticker: result for result in results}


class StaticProvider:
    def __init__(self, data: dict[str, SecurityData]) -> None:
        self.data = {ticker.upper(): payload for ticker, payload in data.items()}

    def get_security_data(self, ticker: str) -> SecurityData:
        ticker = ticker.upper()
        if ticker not in self.data:
            raise KeyError(ticker)
        return self.data[ticker]


def make_trending_bars(
    *,
    start_price: float = 20.0,
    count: int = 300,
    drift: float = 0.002,
    amplitude: float = 0.01,
    base_volume: int = 2_000_000,
    boost_every: int | None = None,
    boost_size: float = 0.04,
    boost_volume: float = 2.5,
) -> list[PriceBar]:
    bars: list[PriceBar] = []
    current = start_price
    start_date = ANCHOR - timedelta(days=count + 80)
    day = 0
    while len(bars) < count:
        current_date = start_date + timedelta(days=day)
        day += 1
        if current_date.weekday() >= 5:
            continue
        move = drift
        if boost_every and len(bars) % boost_every == 0 and len(bars) > 0:
            move += boost_size
        open_price = current * (1.0 + move * 0.25)
        close_price = current * (1.0 + move)
        span = max(amplitude, abs(move) * 1.8)
        high_price = max(open_price, close_price) * (1.0 + span)
        low_price = min(open_price, close_price) * (1.0 - span * 0.8)
        volume = int(base_volume * (boost_volume if boost_every and len(bars) % boost_every == 0 and len(bars) > 0 else 1.0))
        bars.append(
            PriceBar(
                date=current_date,
                open=round(open_price, 2),
                high=round(high_price, 2),
                low=round(low_price, 2),
                close=round(close_price if not (boost_every and len(bars) % boost_every == 0 and len(bars) > 0) else high_price * 0.985, 2),
                volume=volume,
            )
        )
        current = close_price
    return bars


def squeeze_security(ticker: str = "MOCK") -> SecurityData:
    bars = make_trending_bars(
        start_price=18.0,
        count=320,
        drift=0.003,
        amplitude=0.012,
        base_volume=3_500_000,
        boost_every=18,
        boost_size=0.08,
        boost_volume=4.2,
    )
    return SecurityData(
        ticker=ticker,
        company_name="Mock Squeeze Corp.",
        sector="Consumer Discretionary",
        industry="Retail",
        bars=bars,
        market_cap=5_500_000_000,
        ipo_date=ANCHOR - timedelta(days=800),
        fundamentals=FundamentalsSnapshot(
            revenue_growth=0.12,
            eps_growth=0.15,
            analyst_revision_score=0.2,
            profitability_positive=True,
            recent_dilution=False,
        ),
        catalyst=CatalystSnapshot(
            has_catalyst=True,
            description="Short squeeze setup after earnings beat",
            price_reaction_positive=True,
            volume_confirmation=True,
            holds_gains=True,
            hype_risk=False,
            catalyst_tags=("Earnings beat", "Short squeeze conditions"),
        ),
        next_earnings_date=ANCHOR + timedelta(days=25),
        short_interest=ShortInterestSnapshot(
            short_interest_percent_float=0.26,
            days_to_cover=7.2,
            float_shares=28_000_000,
            borrow_cost=0.11,
        ),
        social_attention=SocialAttentionSnapshot(
            reddit_mention_count=1500,
            twitter_mention_count=2200,
            news_headline_count=18,
            attention_velocity=1.8,
            catalyst_source="mock",
        ),
        options_data=OptionsSnapshot(options_interest_available=True, options_daytrade_candidate=True),
        theme_tags=["Short squeeze", "Retail speculation"],
        catalyst_tags=["Earnings beat", "Short squeeze conditions"],
        provider_name="test",
        source_notes=["Source: unit test synthetic data."],
    )


def with_options_override(security: SecurityData, *, unusual_options_activity: bool | None) -> SecurityData:
    options_data = replace(
        security.options_data or OptionsSnapshot(options_interest_available=True),
        unusual_options_activity=unusual_options_activity,
        options_daytrade_candidate=unusual_options_activity,
    )
    return replace(security, options_data=options_data)
