# TradeBruv

TradeBruv is a deterministic stock scanner for personal research and trading workflow triage.

The project is deliberately not an AI stock picker. AI is not making decisions here. The source of truth is a rule-based scanner that scores stocks using objective price, volume, relative-strength, risk, and supporting fundamental signals.

## Roadmap

- Pass 1: deterministic scanner core
- Pass 1.5: real data + outlier winner engine
- Pass 2: dashboard
- Pass 3: news/social + AI explanation layer
- Pass 4: historical review + strategy feedback + journal
- Pass 5: daily scan automation, alerts, watchlist state, and daily summaries
- Pass 6: personal portfolio-aware stock picker, analyst cockpit, AI committee, and validation lab
- Pass 7: FastAPI backend, Vite/React primary UI, and safe local `.env` setup
- Pass 8: premium cockpit polish, cheap/free-first data sources, insider/politician context, doctor/readiness checks, and signal quality audit
- Pass 9: live-key smoke hardening, real provider degradation, Gemini adapter, app status reporting, and paper-tracking workflow

Options/day-trading remains deferred. TradeBruv stays stock-first.

## What Exists Now

TradeBruv currently supports:
- deterministic winner scoring
- deterministic outlier-winner scoring
- a local research cockpit dashboard
- manual CSV/JSON catalyst, news, and social-attention ingestion
- optional AI-generated explanation layer, off by default
- historical forward review of saved scanner reports
- strategy performance aggregation by labels, scores, catalysts, themes, and warnings
- a local CSV research/trade journal
- timestamped scan archives for daily history
- deterministic daily alerts and watchlist state tracking
- daily summary JSON/Markdown outputs
- strategy labels and status labels
- trade-plan levels
- avoid/risk flags
- JSON, CSV, and console output
- sample data scans
- local file scans
- optional real-data scans through `yfinance` when available
- local portfolio CSV import/export and manual holdings entry
- portfolio-aware recommendation labels for hold/add/trim/sell/review decisions
- single-stock Deep Research from the dashboard
- optional AI Analyst Committee with mock/OpenAI-compatible support and missing-key fallback
- paper prediction tracking and forward validation metrics
- famous outlier case-study mode for selected tickers
- Data Sources / API Setup dashboard page with env-var readiness and degraded capability notes
- premium dark-mode React cockpit with score cards, dense tables, risk panels, and workflow actions
- cheap/free-first provider readiness for yfinance, SEC EDGAR, GDELT, FMP, Finnhub, Alpha Vantage, and NewsAPI
- manual insider/politician/alternative-data CSV ingestion through [alternative_data_watchlist.csv](/Users/aashishdhawan/Desktop/AI Projects/TradeBruv/config/alternative_data_watchlist.csv)
- SEC/GDELT/FMP provider adapters that degrade safely when missing config or live checks fail
- SEC/GDELT/FMP/Finnhub provider checks that degrade safely when missing config or live checks fail
- doctor reports for imports, local directories, env status, yfinance, AI config, SEC/GDELT/FMP/Finnhub, backend, and frontend
- readiness reports for scanner, Deep Research, AI Committee, provider live/mock state, portfolio analysis, validation dry-runs, alerts, missing data, and guardrails
- Signal Quality Audit for saved reports, baseline comparison, random baseline comparison, and sample-size warnings
- AI output guardrails for unsupported claims, invented URLs, order-placement language, and deterministic Avoid conflicts
- real Gemini and OpenAI-compatible AI committee adapters when keys are configured
- app status report at `outputs/app_status_report.md`
- Start Paper Tracking forms from Stock Picker and Deep Research, with thesis, invalidation, TP1/TP2, horizon, snapshot, and next review date

The scanner does **not** do:
- broker integration
- trade execution
- broker order placement
- broker credential scraping
- storage of API keys in code
- crypto asset scanning
- options strategy building or day-trading modules
- AI-driven buy/sell decisions
- predictive backtest claims
- hype-driven alert decisions
- notification credential management
- guaranteed-profit claims

Every recommendation label is research support. It must be checked against risk, invalidation, data quality, and your own portfolio context before any manual decision outside the app.

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

## Pass 7/8 Primary UI and API

TradeBruv now has two local interfaces:
- Primary UI: Vite/React in [frontend/](/Users/aashishdhawan/Desktop/AI Projects/TradeBruv/frontend)
- Fallback/dev UI: the existing Streamlit dashboard through `tradebruv-dashboard`

The React UI is a cockpit for the existing Python logic. It calls the FastAPI backend and does not duplicate scanner, portfolio, research, AI committee, validation, alert, or journal scoring logic in TypeScript.

Pass 8 makes the React UI the main daily cockpit: dark-mode first, left navigation, dense tables, compact score cards, risk warnings, “Why NOT to buy?” panels, insider/politician context, Data Sources doctor/readiness controls, and Signal Quality views. Raw JSON stays hidden unless a developer/debug panel is opened.

### Install Backend API Dependencies

```bash
python3 -m pip install -e '.[api]'
```

For the full local stack, including Streamlit and yfinance:

```bash
python3 -m pip install -e '.[all]'
```

### Run the FastAPI Backend

```bash
python3 -m tradebruv.api
```

Equivalent entry point after install:

```bash
tradebruv-api
```

The backend listens on `http://127.0.0.1:8000` and loads `.env` automatically if it exists. The app still works without `.env`.

### Run the React Frontend

```bash
cd frontend
npm install
npm run dev
```

Optional public frontend config:

```bash
VITE_TRADEBRUV_API_URL=http://localhost:8000
```

Do not put API keys in frontend environment files.

### Convenience Commands

```bash
make api
make frontend
make app
```

`make app` prints the two terminal commands because the backend and frontend should run as separate processes.

## Local `.env` Setup

Create local secrets from the template:

```bash
cp .env.example .env
```

Then edit `.env` and restart the backend.

Important rules:
- `.env`, `.env.local`, and `.env.*.local` are ignored by git.
- Real keys should never be committed.
- The backend never sends secret values to the frontend.
- Data-source status only reports provider names, configured/missing status, missing env var names, capabilities, setup instructions, docs links, and last checked time.
- Doctor/readiness checks are explicit local actions. They never print full secret values.

### Recommended Cheap/Free-First Setup

Start here before considering paid feeds:
1. No key: `yfinance` for OHLCV/metadata, GDELT for global news/narratives, and manual catalyst/alternative-data CSVs.
2. Free config: `SEC_USER_AGENT` for SEC EDGAR company filings, facts, and Form 4 discovery.
3. Free/cheap keys: `FINANCIAL_MODELING_PREP_API_KEY`, `FINNHUB_API_KEY`, `ALPHA_VANTAGE_API_KEY`, and `NEWSAPI_KEY`.
4. AI keys: `OPENAI_API_KEY` and/or `GEMINI_API_KEY`.
5. Skip paid feeds for now unless you really need them: `POLYGON_API_KEY`, `BENZINGA_API_KEY`, `QUIVER_API_KEY`, Reddit/X/StockTwits, Plaid, and SnapTrade.

### OpenAI

```bash
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

OpenAI-compatible routing can use:

```bash
TRADEBRUV_LLM_API_KEY=your_key_here
TRADEBRUV_LLM_MODEL=gpt-4o-mini
TRADEBRUV_LLM_BASE_URL=https://openrouter.ai/api/v1
```

### Gemini

```bash
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-1.5-flash
```

Gemini is a real live adapter when `GEMINI_API_KEY` is present. If the key, model, quota, or network is unavailable, TradeBruv marks the committee unavailable/degraded and keeps deterministic rules plus mock AI available. Gemini output still runs through the same guardrail validator.

### Market, News, and Social Keys

Set only the providers you plan to use:

```bash
SEC_USER_AGENT=TradeBruv local research your-email@example.com
GDELT_ENABLED=true
FINANCIAL_MODELING_PREP_API_KEY=
POLYGON_API_KEY=
FINNHUB_API_KEY=
NEWSAPI_KEY=
ALPHA_VANTAGE_API_KEY=
TWELVE_DATA_API_KEY=
BENZINGA_API_KEY=
QUIVER_API_KEY=
CAPITOL_TRADES_API_KEY=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
X_BEARER_TOKEN=
STOCKTWITS_ACCESS_TOKEN=
```

`SEC_USER_AGENT` should identify your local app/contact. SEC EDGAR is free, but responsible access still matters. GDELT does not require a key and is used as narrative context, not a standalone buy signal.

### Data Sources Page

The React Data Sources page shows:
- No key / free
- Free key
- Paid / optional
- AI
- Future brokerage

Each provider card shows configured/missing state, required env vars, missing env vars, capabilities unlocked, degraded behavior, setup instructions, docs link, and last checked time. It also has a “Create `.env` from template” action that copies `.env.example` to `.env` only if `.env` does not already exist.

The page recommends first adding `OPENAI_API_KEY`, `GEMINI_API_KEY`, `FINANCIAL_MODELING_PREP_API_KEY`, `FINNHUB_API_KEY`, and `SEC_USER_AGENT`. It also shows what works with no keys, quota/limitation notes, Run Doctor, Run Live Doctor, and Run Readiness actions.

### Safe Local `.env` Editor

The local editor is disabled by default:

```bash
TRADEBRUV_ALLOW_LOCAL_ENV_EDITOR=false
```

Only enable it on a private local machine:

```bash
TRADEBRUV_ALLOW_LOCAL_ENV_EDITOR=true
```

When enabled, the Data Sources page can submit missing keys to the backend for local `.env` writing. Existing key values are never sent back to the frontend, saved values are not echoed in responses, and the backend should be restarted after saving.

Do not enable the local editor if TradeBruv is deployed or reachable by anyone else.

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

### Manual Insider / Politician / Alternative Data

Pass 8 adds a verified manual alternative-data template:

```text
config/alternative_data_watchlist.csv
```

Fields include ticker, source type/name/url, timestamp, actor name/role/type, transaction type, shares, estimated value, price, filing date, transaction date, disclosure lag, confidence, and notes.

Supported actor types include `CEO`, `CFO`, `Director`, `Officer`, `10% Owner`, `Senator`, `Representative`, `Politician`, `Institution`, and `Unknown`. Supported transaction types include `Buy`, `Sell`, `Option Exercise`, `Award`, `Gift`, `Disposal`, and `Unknown`.

Interpretation rules:
- CEO/CFO/director open-market buys are stronger than awards or option exercises.
- Cluster insider buying is stronger than one small buy.
- Heavy insider selling is risk/context, not an automatic sell.
- Politician buying is attention/context, not an automatic buy.
- Politician trades can be delayed; TradeBruv shows disclosure-lag warnings.
- Alternative data can support catalyst/attention context only when price/volume confirms.
- Alternative data alone never overrides a hard deterministic `Avoid`.

Run a scan with an explicit alternative-data file:

```bash
python3 -m tradebruv scan \
  --universe config/sample_universe.txt \
  --provider sample \
  --mode outliers \
  --alternative-data-file config/alternative_data_watchlist.csv
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

### Archive Scan Reports

Normal scan output still writes `scan_report.json/csv` or `outlier_scan_report.json/csv`. Add `--archive` to also save a timestamped copy under `reports/scans/YYYY-MM-DD/`:

```bash
python3 -m tradebruv scan \
  --universe config/outlier_watchlist.txt \
  --provider real \
  --mode outliers \
  --archive
```

Archived JSON includes metadata:
- `scan_id`
- `created_at`
- provider and mode
- universe and catalyst file paths
- AI enabled flag
- result count
- command used
- git commit when available

## Daily Scan Automation

The `daily` command runs a full deterministic workflow:
1. run the scanner
2. archive timestamped JSON/CSV reports
3. compare results with the previous local watchlist state
4. generate deterministic alerts
5. update watchlist state
6. write daily summary outputs

```bash
python3 -m tradebruv daily \
  --universe config/outlier_watchlist.txt \
  --provider real \
  --mode outliers
```

For deterministic sample checks:

```bash
python3 -m tradebruv daily \
  --universe config/outlier_watchlist.txt \
  --provider sample \
  --mode outliers \
  --as-of-date 2026-04-24
```

Default local outputs:
- `reports/scans/YYYY-MM-DD/scan_<mode>_<provider>_<time>.json`
- `reports/scans/YYYY-MM-DD/scan_<mode>_<provider>_<time>.csv`
- `reports/watchlist_state.json`
- `outputs/daily/alerts.json`
- `outputs/daily/alerts.csv`
- `outputs/daily/daily_summary.json`
- `outputs/daily/daily_summary.md`

### Watchlist State

The watchlist state file is local JSON. It stores the prior and current values needed to compare scans:
- status
- winner, outlier, risk, and setup quality scores
- outlier type
- price
- entry zone
- invalidation
- TP1/TP2
- warnings
- catalyst quality
- theme tags

It is intentionally inspectable and does not require a database or cloud service.

### Alerts

Alerts are deterministic comparisons between the previous state and the current scan. AI does not create alert decisions. Alerts never mean buy or guaranteed.

Alert severities:
- `Info`: data or workflow note
- `Watch`: monitor or review context
- `Important`: meaningful setup, target, or risk change
- `Critical`: avoid/invalidation/provider-risk style warning

Alert categories:
- `Opportunity`: upgrades, active setups, threshold crossings, entry-zone events, catalyst confirmation
- `Risk`: Avoid downgrades, invalidations, failed breakouts, risk score jumps, hype/pump warnings
- `Target/Management`: TP1/TP2, reward/risk changes, extended moves, journal review prompts
- `Data Quality`: missing ticker data, provider failures, missing catalyst data, unavailable AI explanation when enabled

Recommended actions are limited to:
- `Research`
- `Watch`
- `Avoid`
- `Review Journal`
- `No Action`

Use `daily_summary.md` as the quick daily brief. It is designed to be copied into notes, Slack, Discord, or email manually without adding credentials or paid notification dependencies.

## Doctor, Readiness, and Signal Quality

Doctor checks local health and optional live provider reachability. Without `--live`, it stays config-only where possible:

```bash
python3 -m tradebruv doctor
python3 -m tradebruv doctor --live
python3 -m tradebruv doctor --ai openai
python3 -m tradebruv doctor --ai gemini
python3 -m tradebruv doctor --ticker NVDA
```

Live AI checks:

```bash
python3 -m tradebruv doctor --live --ai openai --ticker NVDA
python3 -m tradebruv doctor --live --ai gemini --ticker NVDA
```

Outputs:
- `outputs/doctor_report.json`
- `outputs/doctor_report.md`

Interpretation:
- `PASS`: the local/config/live check completed.
- `WARN`: optional provider missing, degraded, rate-limited, unreachable, or skipped without blocking the app.
- `FAIL`: a requested check failed; the report should continue so other providers can still be inspected.
- `SKIPPED`: a live/API path was not requested or not configured.

Doctor should never print full API keys. If a provider error includes a URL or token-like value, TradeBruv redacts configured secrets before writing reports.

Readiness checks whether the system is operational as a stock picker/analyzer workflow. It runs scanner, outlier scan, Deep Research, mock AI Committee, optional configured AI, sample portfolio analysis, validation dry-run, alternative-data ingestion, alert dry-run, report completeness, and guardrail checks:

```bash
python3 -m tradebruv readiness \
  --universe config/outlier_watchlist.txt \
  --provider real \
  --tickers NVDA,PLTR,MU,RDDT,GME,CAR,SMCI,COIN,HOOD,ARM,CAVA,AAPL,MSFT,LLY,TSLA
```

Optional AI modes:

```bash
python3 -m tradebruv readiness --provider real --ai openai
python3 -m tradebruv readiness --provider real --ai gemini
```

Outputs:
- `outputs/readiness_report.json`
- `outputs/readiness_report.md`

The readiness report explicitly says:
- ready for manual research: yes/no
- ready for paper tracking: yes/no
- ready for real-money reliance: always no until future validation proves otherwise
- what data is missing
- which providers were live vs mock/config-only
- whether AI outputs passed guardrails
- whether Deep Research and portfolio-aware analysis worked
- whether the signal audit has enough samples

Readiness warnings are not automatically blockers. Missing optional providers should be fixed only if you need the capability they unlock.

Write the app status report:

```bash
python3 -m tradebruv app-status
```

Output:
- `outputs/app_status_report.md`

The Reports page shows this report. It summarizes working features, degraded/missing features, live-tested providers, mock-only providers, OpenAI/Gemini status, frontend/API status, validation sample sufficiency, and recommended next actions.

Signal Quality Audit asks whether saved signals look useful or indistinguishable from baseline/random noise:

```bash
python3 -m tradebruv signal-audit \
  --reports-dir reports/scans \
  --baseline SPY,QQQ \
  --random-baseline
```

Outputs:
- `outputs/signal_quality_report.json`
- `outputs/signal_quality_report.md`

Case-study workflow:

```bash
python3 -m tradebruv case-study \
  --ticker NVDA \
  --signal-date 2024-01-15 \
  --horizons 5,10,20,60,120
```

Signal audit reports average/median forward returns, win rate, rough confidence interval when possible, baseline excess return, random baseline comparison, drawdown-like adverse return, sample size, and warnings. It is evidence gathering, not proof. Small samples should be treated as “not enough evidence yet.”

Recommended workflow:
1. Add keys in `.env`.
2. Run live doctor.
3. Run readiness with the real provider and mock/OpenAI/Gemini as needed.
4. Run the real stock picker.
5. Use Start Paper Tracking to save the ticker, thesis, invalidation, TP1/TP2, expected horizon, and recommendation snapshot.
6. Update outcomes at 1D/5D/10D/20D checkpoints from Validation Lab.
7. Run signal audit weekly.
8. Use TradeBruv only as research support until enough validation exists.

## Paper Tracking Workflow

Paper tracking is the default evidence loop. It does not place orders.

From Stock Picker or Deep Research:
- select the ticker/setup
- choose expected horizon (`1D`, `5D`, `10D`, or `20D`)
- save thesis
- save invalidation
- save TP1/TP2
- save the deterministic/AI recommendation snapshot
- review the generated next review date

Validation Lab shows:
- predictions needing outcome updates
- predictions with missing outcomes
- predictions that hit TP1/TP2/invalidation
- open and closed validation records

Enough validation means at least 30 closed forward paper predictions before tuning rules or trusting labels more heavily. More is better, especially across different regimes. Small samples should be treated as directional notes, not evidence of accuracy.

## Reporting Provider Issues

When a provider fails:
- copy the provider name, `WARN`/`FAIL` status, and readable cause from doctor/readiness
- do not paste API keys or full URLs containing keys
- note whether the backend had been restarted after editing `.env`
- note whether the failure was config-only, live, quota/rate-limit, timeout, DNS/network, or bad response
- rerun with mock/sample mode to confirm the core app still works

Real-money use is not recommended yet because TradeBruv has not accumulated enough forward validation evidence, live provider coverage can degrade, AI outputs are advisory only, and deterministic labels are research triage rather than probability forecasts.

## Historical Review / Backtest Mode

Pass 4 adds a saved-report forward review mode. This is intentionally conservative: it does not recreate or tune historical scanner rules, and it does not claim future performance. It answers a narrower question: after a scanner row was saved, what happened to price over later trading-day horizons?

Review one saved report:

```bash
python3 -m tradebruv review \
  --report outputs/outlier_scan_report.json \
  --provider real \
  --horizons 5,10,20,60
```

Review a directory of saved reports:

```bash
python3 -m tradebruv review-batch \
  --reports-dir reports/history \
  --provider real \
  --horizons 5,10,20,60
```

For deterministic sample-data checks, use a fixed later price date and, when needed, an explicit signal date:

```bash
python3 -m tradebruv review \
  --report outputs/outlier_scan_report.json \
  --provider sample \
  --price-as-of-date 2026-04-24 \
  --signal-date 2026-01-01 \
  --horizons 5,10,20,60
```

Review output fields:
- `forward_return_pct`: close-to-close return from the scanner signal price to the horizon close.
- `max_favorable_excursion_pct`: best intraperiod high versus the signal price.
- `max_adverse_excursion_pct`: worst intraperiod low versus the signal price.
- `hit_tp1` / `hit_tp2`: whether the later high touched the saved scanner target.
- `hit_stop_or_invalidation`: whether the later low touched the invalidation level, or stop reference if invalidation is unavailable.
- `days_to_tp1`, `days_to_tp2`, `days_to_invalidation`: trading days until each event.
- `best_close_after_signal`, `worst_close_after_signal`, `final_close_at_horizon`: close-price context for each horizon.

If historical OHLCV data is unavailable, the review row is marked unavailable and the command keeps running.

## Strategy Performance

Every `review` and `review-batch` command also writes strategy performance files. These summarize historical review rows by:
- strategy label
- outlier type
- status label
- confidence label
- risk level
- theme tags
- catalyst type and catalyst quality
- warnings
- score buckets such as `outlier_score 90+`, `winner_score 80+`, `setup_quality 80+`, and high/low `risk_score`
- provider and universe file where known

Metrics include:
- sample size
- average and median forward return
- win rate
- average winner and average loser
- payoff ratio
- expectancy
- TP1/TP2 hit rates
- invalidation rate
- average MFE/MAE
- best and worst result

Small sample sizes are clearly flagged. Do not tighten or loosen scanner rules based on one tiny bucket. Use this as evidence gathering for scanner improvement, not as proof that a setup will work next time.

## Pass 6 Personal Portfolio Workflow

Pass 6 turns the dashboard into the main workflow for personal stock research:

1. Use `Home / Daily Brief` for market regime, candidates, portfolio review prompts, open predictions, alerts, and data health.
2. Use `Stock Picker` to run scanner-driven candidate triage and save names to journal, portfolio review, or Prediction Lab.
3. Use `Deep Research` to type any ticker such as NVDA, PLTR, MU, RDDT, GME, CAR, AAPL and get a full deterministic research card.
4. Use `Portfolio` to manually enter holdings, import a CSV, refresh prices, inspect allocation, and export holdings.
5. Use `Portfolio Analyst` to see hold/add/trim/sell/watch/review candidates based on scanner output and local position context.
6. Use `AI Committee` only when you want an optional grounded debate layered beside deterministic rules.
7. Use `Validation Lab` to save paper predictions and measure what happened later.
8. Use `Data Sources / API Setup` to see configured/missing API keys and what capabilities are degraded.

No broker execution exists. Broker integrations are read-only future research items unless explicitly changed later.

## Portfolio

Default local file:

```text
data/portfolio.csv
```

Supported workflow:
- manual position entry from the dashboard
- generic broker CSV import
- Fidelity-style CSV import when exported columns match common names such as `Symbol`, `Quantity`, `Average Cost`, `Last Price`, and `Market Value`
- local CSV export
- price refresh through the selected market data provider

Portfolio fields:

```csv
account_name,ticker,company_name,quantity,average_cost,current_price,market_value,cost_basis,unrealized_gain_loss,unrealized_gain_loss_pct,realized_gain_loss,position_weight_pct,sector,theme_tags,purchase_date,intended_holding_period,thesis,risk_notes,user_notes,stop_or_invalidation,target_price,decision_status,last_reviewed_at
```

Decision statuses:
- `Hold`
- `Buy More / Add`
- `Trim`
- `Sell / Exit`
- `Watch Closely`
- `Research More`
- `Avoid Adding`
- `Data Insufficient`

Portfolio CLI examples:

```bash
python3 -m tradebruv portfolio import --input holdings.csv
python3 -m tradebruv portfolio add --ticker NVDA --set quantity=2 --set average_cost=150 --set current_price=180
python3 -m tradebruv portfolio update-prices --provider sample
python3 -m tradebruv portfolio analyze --provider sample
python3 -m tradebruv portfolio export --output outputs/portfolio_export.csv
```

Portfolio-aware labels:
- `Strong Hold`
- `Hold`
- `Add on Strength`
- `Add on Pullback / Better Entry`
- `Trim`
- `Exit / Sell`
- `Watch Closely`
- `Do Not Add`
- `Data Insufficient`

Each portfolio recommendation includes confidence, conviction score, risk score, urgency, reason to hold, reason to add, reason to trim/sell, events to watch, invalidation, portfolio risk, suggested review date, and data quality.

## Deep Research

The `Deep Research` dashboard page analyzes one ticker from the frontend. It shows scanner status, winner/outlier/risk/setup scores, catalyst/news/social summary, entry zone, invalidation, TP1/TP2, reward/risk, bull case, bear case, risks, events to watch, portfolio context if owned, journal history if present, and a decision card.

Deep Research labels:
- `Strong Buy Candidate`
- `Buy Candidate`
- `Hold / Watch`
- `Wait for Better Entry`
- `Avoid`
- `Sell / Exit Candidate` only when owned and setup is broken
- `Data Insufficient`

`Strong Buy Candidate` means a research/action candidate inside this personal system. It is not a guarantee and not an order.

## AI Analyst Committee

The AI Committee is optional. The app works without any AI key.

Dashboard modes:
- `No AI`
- `OpenAI only`
- `Claude only`
- `Gemini only`
- `Multi-agent committee`
- `Mock AI for testing`

Implemented MVP behavior:
- mock committee works offline and is covered by tests
- OpenAI/OpenRouter-style chat completions are supported through an OpenAI-compatible endpoint
- Claude and Gemini readiness are detected through env vars, with adapters kept unavailable until explicitly enabled
- missing keys return a visible unavailable payload instead of crashing

Committee roles:
- Bull Analyst
- Bear Analyst
- Risk Manager
- Catalyst Analyst
- Final Decision Analyst

AI output includes bull case, bear case, risk manager view, catalyst view, debate summary, final recommendation label, confidence, evidence used, missing data, events to watch, what would change the view, portfolio-specific action, and recommended next step.

Pass 8 adds an AI output validator. It flags guaranteed/profit-certainty language, invented URLs, unsupported exact price claims, order-placement language, missing risk notes, missing invalidation notes, missing-data omissions, and AI recommendations that conflict with deterministic `Avoid`. The UI shows `ai_guardrail_warnings`, `ai_output_quality_score`, `evidence_grounding_score`, and `unsupported_claims_detected` beside the committee output.

Guardrails:
- AI must use only supplied scanner, portfolio, catalyst, and source fields
- AI must not invent news, fundamentals, social data, or positions
- AI must not place trades
- deterministic rules remain primary
- hard Avoid/risk flags stay visible and cannot be silently overridden
- rule-based, AI, and combined recommendations are shown side by side

## Validation Lab

The `Validation Lab` supports paper prediction tracking and historical case studies.

Default local file:

```text
data/predictions.csv
```

Prediction records include signal price, rule-based recommendation, AI committee recommendation, final combined recommendation, confidence, winner/outlier/setup/risk scores, strategy/outlier/catalyst labels, thesis, invalidation, TP1/TP2, expected holding period, events to watch, data quality, evidence snapshot, ownership flag, portfolio weight, forward returns, MFE/MAE, TP/invalidation hits, and outcome label.

Forward tracking horizons:
- 1D
- 5D
- 10D
- 20D
- 60D
- 120D

Outcome labels:
- `Worked`
- `Failed`
- `Mixed`
- `Still Open`
- `Data Unavailable`

Validation metrics group performance by recommendation label, AI agreement/disagreement field when available, outlier type, catalyst quality, and risk bucket. Small samples are flagged. This is paper validation, not proof.

Famous outlier case-study mode supports:
- CAR
- GME
- RDDT
- MU
- NVDA
- PLTR
- SMCI
- COIN
- HOOD
- ARM
- CAVA

Case-study mode filters OHLCV to the selected signal date before scanning. If true point-in-time fundamentals/news are unavailable, the output says so and relies only on available OHLCV/scanner fields.

Prediction CLI examples:

```bash
python3 -m tradebruv predictions update --provider sample
python3 -m tradebruv predictions summary
```

## Journal

The local journal is a simple CSV file by default at `outputs/journal.csv`. It is meant to track your decisions and process quality, not execute trades or connect to a broker.

Add a scanner idea from a saved report:

```bash
python3 -m tradebruv journal add \
  --from-report outputs/outlier_scan_report.json \
  --ticker NVDA \
  --set decision=Research
```

List journal entries:

```bash
python3 -m tradebruv journal list
```

Update an entry:

```bash
python3 -m tradebruv journal update \
  --id <id> \
  --set 'decision=Paper Trade' \
  --set actual_entry_price=100 \
  --set actual_exit_price=106 \
  --set result_pct=6 \
  --set followed_rules=true
```

Export journal data:

```bash
python3 -m tradebruv journal export --output journal.csv
```

Show journal/process stats:

```bash
python3 -m tradebruv journal stats
```

Journal fields include scanner context, decision, actual entry/exit, result percent/R, rule-following status, mistake category, and notes. Mistake categories include chasing, ignored invalidation, entering before confirmation, selling winners too early, holding losers too long, oversized positions, ignored market/catalyst/earnings risk, good-process/bad-outcome, bad-process/good-outcome, and other.

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

- `Home / Daily Brief`: market regime, top candidates, portfolio snapshot, open predictions needing review, and data source health.
- `Stock Picker`: scanner feed/table plus actions to save candidates to journal, portfolio review, or Prediction Lab.
- `Deep Research`: single-ticker research card with deterministic scores, risk, invalidation, portfolio context, and journal context.
- `Portfolio`: manual holdings entry, CSV import/export, price refresh, allocation, P/L, winners/losers, and concentration risk.
- `Portfolio Analyst`: portfolio-aware hold/add/trim/sell/watch/review labels.
- `AI Committee`: optional grounded analyst committee with rule-based, AI, and combined recommendations shown side by side.
- `Validation Lab`: paper predictions, forward outcome refresh, validation metrics, and famous outlier case studies.
- `Data Sources / API Setup`: API key readiness, missing env vars, setup instructions, last check, last error, and degraded capabilities.
- `Reports`: archived scanner, daily summary, alerts, and watchlist-change loaders.
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
- `Historical Review`: runs or loads forward review results, including TP/SL/invalidation status and MFE/MAE.
- `Strategy Performance`: shows best/worst historical buckets, warning buckets with negative outcomes, and small-sample warnings.
- `Journal`: adds scanner ideas to the local journal, updates decisions/entries/exits/notes, and separates open from closed ideas/trades.
- `Process Quality`: summarizes rule-following, mistakes, chasing frequency, invalidation violations, early exits, and results when rules were followed versus ignored.
- `Daily Brief`: loads the daily summary and shows market regime, top candidates, top avoid names, top alerts, and data issues.
- `Alerts`: loads `alerts.json`, filters by severity/type/ticker/category/search text, and can add alert tickers to the journal.
- `Watchlist Changes`: groups alerts into score, status, risk, setup, level, and catalyst changes.
- `Alert History`: loads `alerts.json`, `daily_summary.json`, `daily_summary.md`, and archived scan reports.

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

## Data Sources / API Key Setup

All optional keys are read from environment variables only. Do not commit secrets. Missing optional keys do not crash the app; the dashboard shows which capability is degraded.

Recommended optional sources, based on current public docs reviewed for Pass 6:

| Area | Provider | Env vars | Unlocks | Docs |
|---|---|---|---|---|
| Market data | yfinance/free provider | none | Current real provider, OHLCV, partial metadata/news | https://ranaroussi.github.io/yfinance/ |
| Market data | Polygon.io | `POLYGON_API_KEY` | Aggregates, reference data, corporate actions, paid news feeds | https://polygon.io/docs |
| Market data/news | Finnhub | `FINNHUB_API_KEY` | Quotes, profiles, earnings calendar, company news, analyst data on supported plans | https://finnhub.io/docs/api |
| Market data | Twelve Data | `TWELVE_DATA_API_KEY` | Time series, indicators, some fundamentals | https://twelvedata.com/docs |
| Market data/news | Alpha Vantage | `ALPHA_VANTAGE_API_KEY` | Time series, overview, earnings, news sentiment | https://www.alphavantage.co/documentation/ |
| Market data | IEX Cloud | `IEX_CLOUD_API_KEY` | Legacy equities data if your account/API access remains viable | https://iexcloud.io/docs/api/ |
| Data | Nasdaq Data Link | `NASDAQ_DATA_LINK_API_KEY` | Premium datasets and alternative/economic data | https://docs.data.nasdaq.com/ |
| News/events | Benzinga | `BENZINGA_API_KEY` | News, analyst ratings, earnings/calendars on supported plans | https://docs.benzinga.io/ |
| News/events | NewsAPI | `NEWSAPI_KEY` | General news search/headline monitoring | https://newsapi.org/docs |
| News/events | GDELT | none for many public endpoints | Global news/event/narrative monitoring | https://www.gdeltproject.org/ |
| Filings | SEC EDGAR | none | Company submissions/facts and filings | https://www.sec.gov/search-filings/edgar-application-programming-interfaces |
| Social | Reddit API | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | Subreddit mentions and attention velocity | https://www.reddit.com/dev/api/ |
| Social | X/Twitter API | `X_BEARER_TOKEN` | Public post search if plan allows | https://developer.x.com/en/docs |
| Social | StockTwits | `STOCKTWITS_ACCESS_TOKEN` | Symbol stream attention/sentiment clues where available | https://api.stocktwits.com/developers/docs |
| Social/political | Truth Social/political mentions | none in MVP | Manual CSV fallback only unless a compliant licensed source is selected | https://truthsocial.com/ |
| AI | OpenAI | `OPENAI_API_KEY` | AI explanations and committee through OpenAI API | https://platform.openai.com/docs |
| AI | Anthropic Claude | `ANTHROPIC_API_KEY` | Future committee adapter readiness | https://docs.anthropic.com/ |
| AI | Google Gemini | `GEMINI_API_KEY` | Future committee adapter readiness | https://ai.google.dev/gemini-api/docs |
| AI | OpenRouter/OpenAI-compatible | `TRADEBRUV_LLM_API_KEY`, `TRADEBRUV_LLM_BASE_URL` | OpenAI-compatible model routing | https://openrouter.ai/docs/api-reference/overview |
| Portfolio | Manual CSV/local file | none | Current local holdings workflow | this README |
| Portfolio | Plaid Investments | `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV` | Future read-only holdings/transactions | https://plaid.com/docs/investments/ |
| Portfolio | SnapTrade | `SNAPTRADE_CLIENT_ID`, `SNAPTRADE_CONSUMER_KEY` | Future read-only brokerage holdings | https://docs.snaptrade.com/ |

Portfolio/broker notes:
- Manual CSV and manual entry are the implemented default.
- Fidelity CSV export import is local file parsing only.
- Plaid/SnapTrade/Fidelity Access are documented as future read-only integration candidates.
- No broker credential scraping.
- No order placement.
- No trade execution.

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
- `review_report.json` / `review_report.csv`
- `strategy_performance.json` / `strategy_performance.csv`
- `journal.csv` unless a different journal path is supplied
- `alerts.json` / `alerts.csv`
- `daily_summary.json` / `daily_summary.md`

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
- insider/politician/alternative-data counts, net values, disclosure lag warnings, quality labels, and source counts
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
- forward review return/MFE/MAE calculations
- TP1/TP2 and invalidation hit detection
- missing historical data handling
- batch report review
- strategy aggregation and small-sample warnings
- journal add/list/update/export/stats
- dashboard review/performance/journal/process transformations
- scan archive naming and metadata
- watchlist state creation and update
- deterministic upgrade, downgrade, threshold, entry-zone, target, invalidation, failed-breakout, hype/pump, and missing-data alerts
- daily summary JSON and Markdown output
- dashboard alert filtering and watchlist-change transformations
- portfolio CSV import, manual add/update/delete, export, price refresh, allocation, P/L, concentration risk, and no broker execution path
- portfolio-aware recommendation labels and deep research portfolio context
- AI committee mock debate and missing-key handling
- data-source/API-key status detection and secret-leak guard
- prediction record creation, forward outcome updates, validation metrics, and famous outlier case-study mode
- cheap/free-first env vars and provider grouping
- SEC/GDELT/FMP missing/configured behavior
- doctor and readiness report creation without key leakage
- alternative-data CSV parsing, CEO/CFO buys, cluster buying, heavy insider selling, stale politician disclosures, and Avoid override guardrails
- signal audit/random baseline comparison
- AI guardrail validator for bad/good outputs
- frontend Data Sources doctor/readiness rendering and production build/lint

## Known Limitations

- sample data is synthetic and exists for deterministic development only
- the real provider is free-data based and therefore not institution-grade
- many advanced fields are optional and may be unavailable for some names
- theme/catalyst tagging is deterministic but intentionally lightweight
- report-loaded dashboards cannot recompute SPY/QQQ market regime unless a live scan is run
- dashboard cards and summaries are workflow views, not buy/sell recommendations
- historical review does not guarantee future performance
- small sample sizes are unreliable
- review results may be affected by survivorship bias if the historical universe was built poorly
- saved-report review depends on available later OHLCV data and does not reconstruct unavailable signals
- daily alerts are research prompts, not buy/sell instructions
- alert state depends on the previous local `watchlist_state.json`; deleting it resets change detection
- local notifications/email/SMS are not integrated in this pass
- AI explanations require explicit opt-in and configured credentials unless using the mock provider
- live news remains lightweight/free-provider based; manual catalyst ingestion is the reliable path
- broker API integrations are not active; portfolio work is local CSV/manual entry only
- no broker credential scraping, trade execution, order placement, social scraping, crypto scanning, or options/day-trading module is active
- AI committee Claude/Gemini adapters are readiness stubs in this MVP; use mock or OpenAI-compatible mode for active output
- Signal Quality Audit is measurement, not proof. It should say “not enough evidence yet” whenever sample size or data quality is weak.
- Validation Lab results are paper validation and can suffer from small samples, provider gaps, survivorship bias, and non-point-in-time fundamentals/news
