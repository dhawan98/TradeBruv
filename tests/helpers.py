from __future__ import annotations

from datetime import date
from functools import lru_cache

from tradebruv.providers import SampleMarketDataProvider
from tradebruv.scanner import DeterministicScanner


@lru_cache(maxsize=1)
def sample_results():
    anchor = date(2026, 4, 24)
    provider = SampleMarketDataProvider(end_date=anchor)
    scanner = DeterministicScanner(provider=provider, analysis_date=anchor)
    results = scanner.scan(["NVDA", "MSFT", "LLY", "PLTR", "ENPH", "RIVN"])
    return {result.ticker: result for result in results}

