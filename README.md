# TradeBruv

TradeBruv is a deterministic stock scanner for personal research and trading workflow triage.

The project is deliberately not an AI stock picker. AI is not making decisions here. The source of truth is a rule-based scanner that scores stocks using objective price, volume, relative-strength, risk, and supporting fundamental signals.

## Roadmap

- Pass 1: deterministic scanner core
- Pass 1.5: real data + outlier winner engine
- Pass 2: dashboard
- Pass 3: news/social + AI explanation layer
- Pass 4: journal + backtest
- Pass 5: optional day-trading/options module

## What Exists Now

TradeBruv currently supports:
- deterministic winner scoring
- deterministic outlier-winner scoring
- strategy labels and status labels
- trade-plan levels
- avoid/risk flags
- JSON, CSV, and console output
- sample data scans
- local file scans
- optional real-data scans through `yfinance` when available

The scanner does **not** do:
- broker integration
- trade execution
- crypto asset scanning
- options strategy building
- AI-driven buy/sell decisions
- guaranteed-profit claims

## Scanner Modes

### Standard Mode

Ranks stocks by `winner_score` and classifies them into:
- `Strong Research Candidate`
- `Trade Setup Forming`
- `Active Setup`
- `Watch Only`
- `Avoid`

### Outliers Mode

Ranks stocks by `outlier_score` and classifies them into:
- `Explosive Momentum`
- `Breakout Repricing`
- `Short Squeeze Watch`
- `IPO Leader`
- `Long-Term Monster`
- `Theme/Narrative Leader`
- `Institutional Accumulation`
- `Watch Only`
- `Avoid`

`Short Squeeze Watch` is intentionally separated from normal leadership setups because it can be high-risk and unstable.

## Scores

### Winner Score

0-100 deterministic score built from:
- price leadership: 20
- relative strength: 20
- volume / accumulation: 15
- fundamental / revision support: 15
- catalyst / attention: 15
- setup cleanliness / risk-reward: 15

Related fields:
- `bullish_score`
- `bearish_pressure_score`
- `risk_score`
- `setup_quality_score`
- `confidence_percent`

`confidence_percent` is **not** probability of profit. It only reflects the degree of deterministic signal agreement and data completeness.

### Outlier Score

0-100 deterministic score built from:
- explosive price strength: 20
- relative strength acceleration: 20
- volume / attention expansion: 20
- catalyst / repricing support: 15
- float / short-squeeze or institutional-demand signal: 10
- setup cleanliness / risk-reward: 15

Related fields:
- `outlier_type`
- `outlier_risk`
- `outlier_reason`
- `chase_risk_warning`

## Universe Files

Included starter universes:
- [sample_universe.txt](/Users/aashishdhawan/Desktop/AI Projects/TradeBruv/config/sample_universe.txt)
- [mega_cap_universe.txt](/Users/aashishdhawan/Desktop/AI Projects/TradeBruv/config/mega_cap_universe.txt)
- [momentum_universe.txt](/Users/aashishdhawan/Desktop/AI Projects/TradeBruv/config/momentum_universe.txt)
- [outlier_watchlist.txt](/Users/aashishdhawan/Desktop/AI Projects/TradeBruv/config/outlier_watchlist.txt)

These files are inputs only. The scanner does not hardcode any universe inside the ranking logic.

## Quick Start

### Sample Scan

```bash
python3 -m tradebruv scan \
  --universe config/sample_universe.txt \
  --provider sample \
  --as-of-date 2026-04-24
```

### Sample Outlier Scan

```bash
python3 -m tradebruv scan \
  --universe config/sample_universe.txt \
  --provider sample \
  --mode outliers \
  --as-of-date 2026-04-24
```

### Real Scan

Install the optional dependency first:

```bash
python3 -m pip install '.[real]'
```

Then run:

```bash
python3 -m tradebruv scan \
  --universe config/mega_cap_universe.txt \
  --provider real
```

### Real Outlier Scan

```bash
python3 -m tradebruv scan \
  --universe config/outlier_watchlist.txt \
  --provider real \
  --mode outliers
```

### Local Data Scan

```bash
python3 -m tradebruv scan \
  --universe config/outlier_watchlist.txt \
  --provider local \
  --data-dir path/to/data
```

Expected layout:

```text
path/to/data/
  metadata.json
  prices/
    NVDA.csv
    MSFT.csv
    SPY.csv
    QQQ.csv
    XLK.csv
```

Each CSV:

```csv
date,open,high,low,close,volume
2026-01-02,100.0,101.5,99.4,101.1,5200000
```

`metadata.json` can optionally include:
- company name
- sector / industry
- market cap
- IPO date
- fundamentals
- catalyst tags
- short-interest fields
- social/news placeholder fields
- options placeholder fields

If data is missing, the scanner keeps running and marks the field unavailable instead of hallucinating.

## Real Data Provider

The optional real provider is currently a `yfinance` adapter. It aims to pull:
- daily OHLCV history
- company name
- sector / industry
- market cap
- earnings date when available
- basic growth / profitability / revision fields when available
- short-interest fields when available
- Yahoo news headline counts as a lightweight attention placeholder

Known constraints:
- `yfinance` can return partial metadata depending on the ticker
- short-interest, earnings, and news coverage can be incomplete
- Reddit/X/social data is not scraped directly yet
- if `yfinance` is unavailable or a field is missing, the scanner degrades gracefully and records that gap

## Social / News Placeholder

This pass adds support for future attention inputs without making them mandatory. Current behavior:
- local/manual metadata can inject placeholder attention fields
- real scans can use Yahoo news headline counts if available
- missing social/news fields are explicitly marked unavailable

No social data is hallucinated.

## Options Placeholder

Options are not part of the main workflow in this pass. The scanner only reserves future-compatible fields:
- `options_interest_available`
- `unusual_options_activity`
- `options_daytrade_candidate`
- `implied_volatility_warning`
- `earnings_iv_risk`

These fields do **not** drive stock scoring in this version. No contract recommendations, strategy builders, Greeks, or execution flows are included.

## Output

Reports are written to `outputs/` by default:
- `scan_report.json` / `scan_report.csv`
- `outlier_scan_report.json` / `outlier_scan_report.csv`

Each row includes:
- ticker and company
- current price
- winner and outlier scores
- strategy and outlier labels
- risk and confidence labels
- theme tags and catalyst tags
- trade plan levels
- squeeze-watch payload
- options placeholder payload
- why it passed
- why it could be a big winner
- why it could fail
- warnings
- source / provider notes
- data availability notes

## Tests

Run the full suite with:

```bash
python3 -m unittest discover -s tests -v
```

Current test coverage includes:
- original winner scoring behavior
- rejection filters
- status classification
- trade-plan generation
- outlier score ranking
- long-term monster detection
- short squeeze watch classification with mocked data
- unavailable social/news handling
- options placeholder isolation from stock scoring
- provider failure handling

## Known Limitations

- sample data is synthetic and exists for deterministic development only
- the real provider is free-data based and therefore not institution-grade
- many advanced fields are optional and may be unavailable for some names
- theme/catalyst tagging is deterministic but intentionally lightweight
- no AI explanation layer is active yet

