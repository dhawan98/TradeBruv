# TradeBruv

TradeBruv is a deterministic stock market scanner for personal research and trading workflow triage.

This first version is intentionally rule-based:
- No AI stock picker
- No broker integration
- No trade execution
- No crypto
- No options builder
- No guaranteed-profit language

The scanner ranks stocks for further research using objective technical signals, risk filters, and repeatable scoring. AI can be layered on later for explanations, but it is not required for this pass.

## What It Does

TradeBruv evaluates a watchlist against these deterministic strategy families:
- Momentum Winner
- Breakout Winner
- Relative Strength Leader
- Long-Term Leader
- Confirmed Strength Reset
- Institutional Accumulation

It also adds support checks for:
- Fundamental / estimate revision support
- Catalyst confirmation only when price and volume agree

And it always runs an avoid/risk pass for:
- Falling knife behavior
- Failed breakouts
- Heavy-volume selling
- Overextension
- Low liquidity
- Earnings too close
- Dilution risk when data is available
- Hype without confirmation
- Weak sector backdrop when available

## Scores

The scanner calculates deterministic 0-100 scores:
- `winner_score`
- `bullish_score`
- `bearish_pressure_score`
- `risk_score`
- `setup_quality_score`

Winner score components:
- Price leadership: 20
- Relative strength: 20
- Volume / accumulation: 15
- Fundamental / revision support: 15
- Catalyst / attention: 15
- Risk / reward / setup cleanliness: 15

`confidence_percent` and `confidence_label` describe rule agreement and setup quality only. They do **not** represent probability of profit.

## Quick Start

Run the built-in sample universe:

```bash
python3 -m tradebruv scan \
  --universe config/sample_universe.txt \
  --provider sample \
  --as-of-date 2026-04-24
```

This prints a console summary and writes:
- `outputs/scan_report.json`
- `outputs/scan_report.csv`

## Local Data Adapter

If you want to scan your own local market data, use the `local` provider:

```bash
python3 -m tradebruv scan \
  --universe path/to/universe.txt \
  --provider local \
  --data-dir path/to/data
```

Expected directory layout:

```text
path/to/data/
  metadata.json
  prices/
    AAPL.csv
    MSFT.csv
    NVDA.csv
    SPY.csv
    QQQ.csv
    XLK.csv
```

Each price CSV should contain:

```csv
date,open,high,low,close,volume
2026-01-02,100.0,101.5,99.4,101.1,5200000
```

`metadata.json` is optional and keyed by ticker:

```json
{
  "NVDA": {
    "company_name": "NVIDIA Corporation",
    "sector": "Technology",
    "next_earnings_date": "2026-05-21",
    "data_notes": ["Analyst revisions unavailable."],
    "fundamentals": {
      "revenue_growth": 0.32,
      "eps_growth": 0.41,
      "margin_change": 0.03,
      "free_cash_flow_growth": 0.18,
      "analyst_revision_score": 0.5,
      "guidance_improvement": true,
      "profitability_positive": true,
      "recent_dilution": false
    },
    "catalyst": {
      "has_catalyst": true,
      "description": "Raised guidance",
      "price_reaction_positive": true,
      "volume_confirmation": true,
      "holds_gains": true,
      "hype_risk": false
    }
  }
}
```

If fundamentals, catalyst, sector, or earnings data are missing, the scanner keeps running and marks them as unavailable instead of hallucinating values.

## Tests

Run the test suite with:

```bash
python3 -m unittest discover -s tests -v
```

The tests cover:
- scoring logic
- rejection filters
- status classification
- trade plan generation

## Output Fields

Each result includes:
- ticker and company name
- current price
- strategy label
- status label
- deterministic scores
- holding period estimate
- entry zone
- invalidation level
- stop-loss reference
- TP1 and TP2
- reward/risk estimate
- why it passed
- why it could fail
- warnings
- signals used
- data availability notes

## Notes

- The default sample provider is for development and testing only.
- The scanner is modular so new adapters can be added later without changing the core scoring engine.
- AI is not required anywhere in this version.

