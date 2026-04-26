# Pass 11 Core Investing Summary

Generated from the real-provider Pass 11 evidence workflow on 2026-04-26.

## Baseline

- `origin/main` was fetched and local `main` was already aligned before implementation.
- Initial worktree was clean.
- Baseline Python tests passed: 83 passed.
- Baseline frontend lint passed.
- Baseline frontend tests passed: 6 passed.
- Baseline frontend build passed with the existing Vite chunk-size warning.
- Doctor without live passed with warnings only: PASS 12, WARN 2, FAIL 0, SKIPPED 2.
- Readiness with sample/mock passed for paper tracking: PASS 15, WARN 2, FAIL 0, SKIPPED 1; ready for paper tracking true; ready for real-money reliance false.

## What Changed

- Added a regular-investing lane with `regular_investing_score` and long-term research labels.
- Added investing outputs for style, risk, horizon, action label, bull case, bear case, invalidation, events to watch, value-trap warning, thesis quality, and investing data quality.
- Updated portfolio-aware decisions with Core Investing Decision fields and explicit hold/add/trim/exit reasoning.
- Added `investing-replay`, `portfolio-replay`, and `investing-proof-report` CLI workflows.
- Added API endpoints and frontend views for Core Investing, Investing Replay, Portfolio Replay, and Investing Proof Report.
- Added unit and frontend coverage for scoring, classification, warnings, portfolio labels, replay output generation, and UI rendering.

## Real Evidence Results

Universe: `config/mega_cap_universe.txt`

Period: 2020-01-01 through 2026-04-24

Provider: `real` yfinance-backed provider

Frequency: monthly

Horizons: 20, 60, 120, 252 trading days

- Replay dates: 76
- Regular investing candidates: 664
- 20D average return: 3.0393%; median: 2.0425%; win rate: 55.57%
- 60D average return: 8.9058%; median: 5.9888%; win rate: 61.85%
- 120D average return: 20.0146%; median: 14.8337%; win rate: 69.34%
- 252D average return: 43.0575%; median: 30.4651%; win rate: 77.96%
- False-positive rate: 52.21%
- Invalidation hit rate: 47.29%
- Average max adverse excursion: -19.3694%

## Baseline Comparison

- Beat SPY: yes in this replay window, by 25.8748 percentage points on average at 252D.
- Beat QQQ: yes in this replay window, by 22.7980 percentage points on average at 252D.
- Beat random baseline: no, lagged by 0.8091 percentage points at 252D.
- Beat equal-weight universe baseline: no, lagged by 1.8078 percentage points at 252D.
- Beat standard `winner_score`: no, `winner_score` top picks averaged 44.8653% at 252D vs 43.0575% for `regular_investing_score`.

## Style And Label Evidence

- Best regular style by 20D average in this run: Value + Improving Trend, 254 samples, 3.3686% average, 59.06% win rate.
- Watchlist Only was positive but noisy: 208 samples, 3.1838% average, 53.85% win rate.
- Exit / Broken Thesis did not clearly protect capital in this limited mega-cap universe: 91 samples, 2.4777% average, median -0.0625%, 49.45% win rate.
- Data Insufficient still produced positive forward returns, which means missing fundamentals are a major limitation and should not be treated as a reliable negative signal.
- Action labels were not strongly proven. Hold averaged 3.0002% at 20D with 58.36% win rate; Watchlist Only averaged 3.2586%; Exit / Sell Candidate averaged 2.4777%.

## Portfolio Replay

- Simulated portfolio decisions: 678
- Hold 252D forward return: 39.9335%
- Trim 252D forward return: 12.4858%
- Exit 252D forward return: 31.6745%
- Add label forward return: unavailable because this simulation did not produce enough Add labels.
- Avoided drawdown rate for Trim/Exit: 63.46%
- False trim rate: 64.29%
- Bad hold rate: 47.12%
- Portfolio label usefulness: not enough evidence.

## Readiness Judgment

- Regular investing is ready for research and paper tracking.
- It is not ready for real-money reliance.
- Evidence is mixed: strong absolute returns and SPY/QQQ excess returns, but weaker than random and equal-weight universe baselines.
- The current mega-cap universe is concentrated and likely benefited from a strong large-cap tech regime.
- Fundamentals are not point-in-time in historical replay; OHLCV-only replay strips fundamentals/news/social/short-interest/options to avoid look-ahead.

## Calibration Pass Inputs

- Reduce false positives and invalidation hits without hiding bad results.
- Improve Add/Hold/Trim/Exit separation; Add labels need enough sample size.
- Add point-in-time fundamentals or explicitly separate price-only Core Investing from fundamentals-assisted current scans.
- Improve value-trap and broken-thesis validation because Exit / Broken Thesis did not clearly avoid upside in this run.
- Compare broader universes beyond mega-cap technology-heavy names.
- Calibrate against random and equal-weight baselines, not only SPY/QQQ.
