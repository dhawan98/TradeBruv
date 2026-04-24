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
- a local research cockpit dashboard
- manual CSV/JSON catalyst, news, and social-attention ingestion
- optional AI-generated explanation layer, off by default
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

### Scan Without Catalyst Data

Catalyst data is optional. The scanner still runs without a catalyst file:

```bash
python3 -m tradebruv scan \
  --universe config/sample_universe.txt \
  --provider sample \
  --mode outliers \
  --as-of-date 2026-04-24
```

Missing catalyst/news/social evidence is reported as unavailable. It is never filled in by AI.

### Scan With Manual Catalyst Data

```bash
python3 -m tradebruv scan \
  --universe config/sample_universe.txt \
  --provider sample \
  --mode outliers \
  --catalyst-file config/catalysts_watchlist.csv \
  --as-of-date 2026-04-24
```

The file may be `.csv` or `.json`. Missing files produce a warning and do not crash the scan. Bad rows are skipped with warnings. Duplicate source rows are deduplicated where possible.

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

## Dashboard

The local Streamlit dashboard is for fast research triage. It does not replace the scanner and does not change deterministic scoring logic. The dashboard consumes scanner output, can trigger the existing scanner, and can load existing JSON reports.

Install dashboard dependencies:

```bash
python3 -m pip install '.[dashboard]'
```

Install dashboard plus real-data support:

```bash
python3 -m pip install '.[all]'
```

Run the dashboard:

```bash
python3 -m tradebruv.dashboard
```

Or, after installing the package entry point:

```bash
tradebruv-dashboard
```

The dashboard opens a local Streamlit server and shows the browser URL in the terminal.

### Sample Dashboard Mode

In the sidebar:
- Provider: `sample`
- Mode: `outliers` or `standard`
- Universe file: `config/sample_universe.txt`
- Catalyst CSV/JSON path: optional, for example `config/catalysts_watchlist.csv`
- Enable AI explanations: optional and off by default
- Optional fixed as-of date: `2026-04-24`
- Click `Run scan`

### Real-Data Dashboard Mode

Install the real dependency first:

```bash
python3 -m pip install '.[all]'
```

In the sidebar:
- Provider: `real`
- Mode: `outliers` or `standard`
- Universe file: `config/outlier_watchlist.txt`, `config/momentum_universe.txt`, or `config/mega_cap_universe.txt`
- History period: default `3y`
- Catalyst CSV/JSON path: optional
- Enable AI explanations: optional and requires an API key
- Click `Run scan`

Real-data mode uses the existing yfinance provider. If Yahoo/yfinance returns partial fields, the dashboard displays the scanner's data-availability notes instead of filling gaps.

### Loading Reports

The dashboard can work without live data:
- Click `Load latest JSON report` to load the newest `scan_report.json` or `outlier_scan_report.json` under `outputs/`
- Or enter a custom JSON report path and click `Load custom report`

Loaded reports show the same outlier feed, table, detail view, avoid panel, options placeholder fields, and deterministic daily summary. Market regime is live-provider based when running a scan; report-only mode marks SPY/QQQ regime data unavailable unless it is recomputed from a live provider.

### Dashboard Sections

- `Market Regime`: SPY/QQQ trend summary, Bullish/Mixed/Risk-Off stance, long exposure posture, leading and weak theme tags, provider/timestamp, and risk warnings.
- `Daily Summary`: rule-based aggregation of top outliers, normal winners, avoid names, common themes, common warnings, highest-risk name, best reward/risk, best long-term monster, and best high-risk/squeeze watch.
- `Outlier Feed`: ranked research cards centered on `outlier_score`, with winner score, risk, setup quality, entry zone, invalidation, targets, chase risk, big-winner case, and failure case.
- `Scanner Table`: sortable and filterable table for status, strategy, outlier type, scores, risk, reward/risk, relative strength notes, volume/accumulation notes, tags, and data availability.
- `Stock Detail`: full deterministic breakdown for one ticker. The `Why NOT to buy?` block is intentionally prominent.
- `Catalysts`: catalyst type, quality, source count, recency, official/narrative/hype flags, top source items, and URLs where supplied.
- `Social Attention`: Reddit, Twitter/X, Truth Social/policy, news attention, velocity, hype risk, pump risk, and price/volume confirmation flags.
- `AI Explanation`: optional AI-generated explanation, clearly labeled and grounded in scanner/report fields.
- `Avoid / Bad Setup Panel`: risk-first review of Avoid and bad-setup names, including falling-knife, broken-trend, failed-breakout, poor reward/risk, hype, liquidity, earnings, and invalidation warnings when present.
- `Watchlists`: uses existing universe files from `config/` without code edits.
- `Options Placeholder`: displays only existing options fields. It does not recommend contracts, calculate Greeks, or build strategies.

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

## Catalyst / News / Social Data

Manual catalyst ingestion is the primary Pass 3 path. Use `config/catalysts_watchlist.csv` as a template.

CSV fields:

```csv
ticker,source_type,source_name,source_url,timestamp,headline,summary,sentiment,catalyst_type,attention_count,attention_velocity,official_source,confidence,notes
NVDA,news,Example Source,https://example.com/story,2026-04-24T13:00:00Z,Headline,Short factual summary,positive,AI/data center narrative,120,0.4,false,0.7,Manual note
```

Supported source types:
- `news`
- `reddit`
- `twitter_x`
- `truth_social`
- `sec_filing`
- `earnings`
- `analyst`
- `insider`
- `institutional`
- `manual`

Supported catalyst types:
- `Earnings beat`
- `Guidance raise`
- `Analyst upgrade`
- `Estimate revision`
- `Major contract`
- `Product launch`
- `AI/data center narrative`
- `Semiconductor narrative`
- `Defense/geopolitical narrative`
- `Energy/nuclear narrative`
- `Financials/rate-cut narrative`
- `IPO/post-IPO narrative`
- `Regulatory/policy catalyst`
- `Insider/institutional activity`
- `Short squeeze / crowded repricing`
- `Social hype only`
- `Unknown/unconfirmed`

Catalyst quality labels:
- `Official Confirmed`: official-style source plus price/volume confirmation.
- `Price Confirmed`: source evidence exists and price/volume confirms, but the source is not official.
- `Narrative Supported`: narrative evidence exists, but price/volume confirmation is incomplete.
- `Social Attention Only`: social activity exists without official/narrative confirmation.
- `Hype Risk`: social-only, pump-like, or hype-risk source behavior is present.
- `Unconfirmed`: weak or incomplete catalyst evidence.
- `Unavailable`: no catalyst/news/social data was provided.

Social attention rules:
- Social attention alone is not a buy signal.
- Social/news attention does not override deterministic scanner scores.
- If social attention rises but price/volume does not confirm, the setup is kept at `Watch Only` unless the base scanner already says `Avoid`.
- If price spikes without an official catalyst, the scanner adds a warning.
- Low-float social spikes are flagged as pump risk or high-risk outlier context.
- Truth Social or political/policy mentions are treated as narrative/policy watch unless tied directly to the company.

No Reddit, Twitter/X, or Truth Social scraping is performed in this pass. Provide those observations manually through CSV/JSON.

## AI Explanations

AI explanations are optional and off by default. AI does not create scores, status labels, catalysts, trade signals, or targets. It can only summarize scanner output and provided catalyst/news/social evidence.

Enable AI explanations from the CLI:

```bash
python3 -m tradebruv scan \
  --universe config/sample_universe.txt \
  --provider sample \
  --mode outliers \
  --catalyst-file config/catalysts_watchlist.csv \
  --ai-explanations
```

Environment variables:
- `OPENAI_API_KEY` or `TRADEBRUV_LLM_API_KEY`
- `TRADEBRUV_LLM_MODEL` or `OPENAI_MODEL`, default `gpt-4o-mini`
- `TRADEBRUV_LLM_BASE_URL` or `OPENAI_BASE_URL`, default `https://api.openai.com/v1`

For offline tests or demos:

```bash
python3 -m tradebruv scan \
  --universe config/sample_universe.txt \
  --provider sample \
  --mode outliers \
  --catalyst-file config/catalysts_watchlist.csv \
  --ai-explanations \
  --mock-ai-explanations
```

If no API key is configured, the scan still works and reports `AI explanation unavailable.`

AI safety rules:
- It must say data is unavailable when evidence is unavailable.
- It must not say `buy`, `guaranteed`, or create new price targets.
- It must not invent news, fundamentals, analyst activity, social activity, or catalysts.
- It must cite/mention source items when available.
- It is not used by deterministic scoring.

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
- catalyst items, catalyst score, catalyst quality, catalyst type, source URLs/timestamps, social/news attention fields, hype/pump flags
- optional AI explanation payload and availability/provider fields

## Tests

Run the full suite with:

```bash
python3 -m pytest
```

Current test coverage includes:
- original winner scoring behavior
- rejection filters
- status classification
- trade-plan generation
- dashboard filtering, sorting, summary aggregation, report loading, and missing-field handling
- catalyst CSV parsing, bad rows, missing files, duplicate rows, official/narrative/social-only classification, social-only guardrails, and report fields
- optional AI unavailable/mock explanation behavior
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
- report-loaded dashboards cannot recompute SPY/QQQ market regime unless a live scan is run
- dashboard cards and summaries are workflow views, not buy/sell recommendations
- AI explanations require explicit opt-in and configured credentials unless using the mock provider
- live news remains lightweight/free-provider based; manual catalyst ingestion is the reliable path
- no broker integration, trade execution, social scraping, or options strategy builder is active yet
