from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Protocol
import json

from .models import CatalystSnapshot, FundamentalsSnapshot, PriceBar, SecurityData


SECTOR_BENCHMARKS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Consumer Discretionary": "XLY",
}


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
            raise KeyError(f"Ticker {ticker} is unavailable in the sample provider.")

        config = SAMPLE_CONFIG[ticker]
        bars = _build_sample_bars(
            end_date=self.end_date,
            start_price=config["start_price"],
            base_volume=config["base_volume"],
            phases=config["phases"],
            events=config.get("events", {}),
        )
        security = SecurityData(
            ticker=ticker,
            company_name=config.get("company_name"),
            sector=config.get("sector"),
            bars=bars,
            fundamentals=config.get("fundamentals"),
            catalyst=config.get("catalyst"),
            next_earnings_date=(
                self.end_date + timedelta(days=config["earnings_offset"])
                if config.get("earnings_offset") is not None
                else None
            ),
            data_notes=config.get("notes", []).copy(),
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
            raise FileNotFoundError(f"Missing price file: {price_path}")

        meta = self.metadata.get(ticker, {})
        bars = self._load_bars(price_path)
        return SecurityData(
            ticker=ticker,
            company_name=meta.get("company_name"),
            sector=meta.get("sector"),
            bars=bars,
            fundamentals=_parse_fundamentals(meta.get("fundamentals")),
            catalyst=_parse_catalyst(meta.get("catalyst")),
            next_earnings_date=(
                date.fromisoformat(meta["next_earnings_date"])
                if meta.get("next_earnings_date")
                else None
            ),
            data_notes=list(meta.get("data_notes", [])),
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
        return bars

    @staticmethod
    def _load_metadata(path: Path) -> dict[str, dict]:
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return {ticker.upper(): payload for ticker, payload in data.items()}


def _parse_fundamentals(payload: dict | None) -> FundamentalsSnapshot | None:
    if not payload:
        return None
    return FundamentalsSnapshot(**payload)


def _parse_catalyst(payload: dict | None) -> CatalystSnapshot | None:
    if not payload:
        return None
    return CatalystSnapshot(**payload)


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


SAMPLE_CONFIG: dict[str, dict] = {
    "SPY": {
        "company_name": "SPDR S&P 500 ETF Trust",
        "sector": None,
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
        ),
        "catalyst": CatalystSnapshot(
            has_catalyst=True,
            description="Enterprise AI demand and raised guidance",
            price_reaction_positive=True,
            volume_confirmation=True,
            holds_gains=True,
            hype_risk=False,
        ),
        "earnings_offset": 18,
    },
    "MSFT": {
        "company_name": "Microsoft Corporation",
        "sector": "Technology",
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
            guidance_improvement=None,
            profitability_positive=True,
            recent_dilution=False,
        ),
        "earnings_offset": 28,
    },
    "LLY": {
        "company_name": "Eli Lilly and Company",
        "sector": "Healthcare",
        "start_price": 720.0,
        "base_volume": 3_700_000,
        "phases": [
            Phase(120, 0.0011, 0.0035, 1.0),
            Phase(45, -0.0009, 0.0038, 1.0),
            Phase(35, 0.0001, 0.0018, 0.82),
            Phase(60, 0.0010, 0.0026, 1.06),
        ],
        "events": {
            204: Event(0.028, 2.2, close_near_high=True),
        },
        "fundamentals": FundamentalsSnapshot(
            revenue_growth=0.21,
            eps_growth=0.24,
            margin_change=0.03,
            free_cash_flow_growth=0.14,
            analyst_revision_score=0.5,
            guidance_improvement=True,
            profitability_positive=True,
            recent_dilution=False,
        ),
        "catalyst": CatalystSnapshot(
            has_catalyst=True,
            description="Clinical update with constructive price confirmation",
            price_reaction_positive=True,
            volume_confirmation=True,
            holds_gains=True,
            hype_risk=False,
        ),
        "earnings_offset": 24,
    },
    "PLTR": {
        "company_name": "Palantir Technologies Inc.",
        "sector": "Technology",
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
            guidance_improvement=None,
            profitability_positive=True,
            recent_dilution=False,
        ),
        "earnings_offset": 20,
    },
    "ENPH": {
        "company_name": "Enphase Energy, Inc.",
        "sector": "Technology",
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
        ),
        "earnings_offset": 6,
    },
    "RIVN": {
        "company_name": "Rivian Automotive, Inc.",
        "sector": "Consumer Discretionary",
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
        ),
        "earnings_offset": 4,
    },
}

