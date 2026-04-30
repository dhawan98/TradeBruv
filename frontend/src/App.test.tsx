import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.stubGlobal('ResizeObserver', ResizeObserverMock);

vi.stubGlobal(
  'fetch',
  vi.fn((url: string) => {
    const payloads: Record<string, unknown> = {
      '/api/health': {
        ok: true,
        provider: 'sample',
        mode: 'outliers',
        last_scan_time: '2026-04-24T00:00:00Z',
        data_source_health: { providers: 2, required_missing: 0, optional_ready: 1, optional_missing: 1 },
        ai: { any_configured: false, configured: [] },
        portfolio_value: 0,
        alert_count: 0,
        local_env_editor_enabled: false,
      },
      '/api/portfolio': { positions: [], summary: { total_market_value: 0 } },
      '/api/daily-decision/latest': {
        available: true,
        generated_at: '2026-04-24T00:00:00Z',
        provider: 'real',
        mode: 'daily-decision',
        demo_mode: false,
        report_snapshot: false,
        stale_data: false,
        market_regime: { regime: 'Risk On', provider: 'real' },
        summary: {},
        validation_context: { messages: ['Fresh live prices validated.'] },
        decisions: [
          {
            ticker: 'NVDA',
            company: 'NVIDIA',
            primary_action: 'Research / Buy Candidate',
            action_lane: 'Outlier',
            source_group: 'Tracked',
            score: 82,
            actionability_score: 84,
            actionability_label: 'Actionable Today',
            actionability_reason: 'Validated price, acceptable risk/reward, and current setup all line up.',
            action_trigger: 'Already in range near 95 - 100.',
            current_setup_state: 'In Entry Zone',
            level_status: 'Actionable',
            entry_label: 'Entry',
            evidence_pill: 'Mixed',
            confidence_label: 'Medium',
            evidence_strength: 'Not enough evidence yet',
            risk_level: 'Low',
            entry_zone: '95 - 100',
            stop_loss: 90,
            invalidation: 90,
            tp1: 110,
            tp2: 120,
            reward_risk: 2,
            holding_horizon: '12+ months',
            reason: 'Quality long-term candidate.',
            why_not: 'Valuation can reset.',
            decision_notices: [
              { severity: 'debug', message: 'Adjusted price series may include split-adjusted closes.' },
              { severity: 'info', message: 'No fresh catalyst loaded.' },
            ],
            next_review_date: '2026-04-30',
            price_source: 'live quote',
            latest_market_date: '2026-04-24',
            price_validation_status: 'PASS',
            price_validation_reason: 'Validated live price.',
            data_freshness: 'Fresh enough',
            source_row: {
              ticker: 'NVDA',
              current_price: 100,
              price_change_1d_pct: 2.4,
              relative_volume_20d: 1.8,
              ema_stack: 'Bullish Stack',
              signal_summary: 'Breakout with Volume',
              status_label: 'Hold / Watch',
              winner_score: 70,
              outlier_score: 65,
              risk_score: 35,
              price_validation_status: 'PASS',
            },
          },
        ],
        data_issues: [
          {
            ticker: 'PLTR',
            company: 'Palantir',
            source_group: 'Tracked',
            primary_action: 'Data Insufficient',
            action_lane: 'Outlier',
            score: 55,
            actionability_score: 0,
            actionability_label: 'Data Insufficient',
            actionability_reason: 'Critical live-price validation failed, so this cannot become a daily pick.',
            action_trigger: 'Wait for data refresh.',
            current_setup_state: 'Data Insufficient',
            level_status: 'Hidden',
            entry_label: 'Hidden',
            evidence_pill: 'Not enough evidence',
            confidence_label: 'Low',
            evidence_strength: 'Not enough evidence yet',
            risk_level: 'Medium',
            entry_zone: 'unavailable',
            stop_loss: 'unavailable',
            invalidation: 'unavailable',
            tp1: 'unavailable',
            tp2: 'unavailable',
            reward_risk: 'unavailable',
            holding_horizon: 'unavailable',
            reason: 'No validated live price. Levels hidden.',
            why_not: 'Displayed price mismatches validated price by 12.3%.',
            next_review_date: '2026-04-24',
            price_source: 'latest close',
            latest_market_date: '2026-04-21',
            price_validation_status: 'FAIL',
            price_validation_reason: 'Displayed price mismatches validated price by 12.3%.',
          },
        ],
        top_candidate: {
          ticker: 'NVDA',
          company: 'NVIDIA',
          primary_action: 'Research / Buy Candidate',
          action_lane: 'Outlier',
          score: 82,
          actionability_score: 84,
          actionability_label: 'Actionable Today',
          actionability_reason: 'Validated price, acceptable risk/reward, and current setup all line up.',
          action_trigger: 'Already in range near 95 - 100.',
          current_setup_state: 'In Entry Zone',
          level_status: 'Actionable',
          entry_label: 'Entry',
          evidence_pill: 'Mixed',
          confidence_label: 'Medium',
          evidence_strength: 'Not enough evidence yet',
          risk_level: 'Low',
          entry_zone: '95 - 100',
          stop_loss: 90,
          invalidation: 90,
          tp1: 110,
          tp2: 120,
          reward_risk: 2,
          holding_horizon: '12+ months',
          reason: 'Quality long-term candidate.',
          why_not: 'Valuation can reset.',
          next_review_date: '2026-04-30',
          price_source: 'live quote',
          latest_market_date: '2026-04-24',
          price_validation_status: 'PASS',
          price_validation_reason: 'Validated live price.',
          data_freshness: 'Fresh enough',
          source_row: {
            ticker: 'NVDA',
            status_label: 'Hold / Watch',
            winner_score: 70,
            outlier_score: 65,
            risk_score: 35,
            price_validation_status: 'PASS',
          },
        },
        research_candidates: [],
        watch_candidates: [],
        avoid_candidates: [],
        portfolio_actions: [],
        best_tracked_setup: {
          ticker: 'NVDA',
          actionability_label: 'Actionable Today',
          actionability_score: 84,
        },
        best_broad_setup: null,
        signal_table: [
          {
            ticker: 'NVDA',
            source: 'Tracked',
            price: 100,
            price_change_1d_pct: 2.4,
            relative_volume_20d: 1.8,
            ema_stack: 'Bullish Stack',
            signal: 'Breakout with Volume',
            signal_explanation: 'Breakout with Volume: price cleared recent highs with relative volume around 1.80.',
            actionability: 'Actionable Today',
            risk: 'Low',
            entry_or_trigger: '95 - 100',
            stop: 90,
            tp1: 110,
            updated: '2026-04-24',
          },
        ],
        top_gainers: [{ ticker: 'SBUX', percent_change: 9.3, relative_volume: 2.85, signal: 'Breakout with Volume' }],
        top_losers: [{ ticker: 'NVDA', percent_change: -1.8, relative_volume: 0.79, signal: 'Bullish Trend Stack' }],
        unusual_volume: [{ ticker: 'SBUX', percent_change: 9.3, relative_volume: 2.85, signal: 'Breakout with Volume' }],
        data_coverage_status: {
          universe_label: 'Large Cap Starter',
          universe_row_count: 120,
          coverage_percent: 24,
          tickers_attempted: 2,
          tickers_successfully_scanned: 1,
          tickers_failed: 1,
          tracked_tickers_count: 2,
          portfolio_tickers_count: 0,
          provider: 'real',
          cache_age_ttl_minutes: 60,
          cache_hits: 1,
          cache_misses: 1,
          scan_groups: [{ source_group: 'Tracked', universe: 'config/tracked_tickers.txt', result_count: 2 }],
        },
        compact_board: [
          {
            ticker: 'NVDA',
            primary_action: 'Research / Buy Candidate',
            actionability_label: 'Actionable Today',
            level_status: 'Actionable',
            entry_label: 'Entry',
            action_trigger: 'Already in range near 95 - 100.',
            entry_zone: '95 - 100',
            stop_loss: 90,
            tp1: 110,
            tp2: 120,
            reward_risk: 2,
            latest_market_date: '2026-04-24',
            trigger_needed: false,
          },
        ],
        no_clean_candidate_reason: '',
        workspace: {
          selected_ticker: 'NVDA',
          canonical_rows: [
            {
              ticker: 'NVDA',
              company: 'NVIDIA',
              primary_action: 'Research / Buy Candidate',
              action_lane: 'Outlier',
              source_group: 'Tracked',
              source_groups: ['Tracked', 'Broad'],
              actionability_score: 84,
              actionability_label: 'Actionable Today',
              reason: 'Quality long-term candidate.',
              why_not: 'Valuation can reset.',
              decision_notices: [
                { severity: 'debug', message: 'Adjusted price series may include split-adjusted closes.' },
                { severity: 'info', message: 'No fresh catalyst loaded.' },
              ],
              entry_zone: '95 - 100',
              stop_loss: 90,
              tp1: 110,
              source_row: {
                ticker: 'NVDA',
                current_price: 100,
                price_change_1d_pct: 2.4,
                relative_volume_20d: 1.8,
                ema_stack: 'Bullish Stack',
                signal_summary: 'Breakout with Volume',
                signal_explanation: 'Breakout with Volume: price cleared recent highs with relative volume around 1.80.',
              },
            },
          ],
          top_candidates: [
            {
              ticker: 'NVDA',
              company: 'NVIDIA',
              primary_action: 'Research / Buy Candidate',
              action_lane: 'Outlier',
              source_group: 'Tracked',
              source_groups: ['Tracked', 'Broad'],
              actionability_score: 84,
              actionability_label: 'Actionable Today',
              reason: 'Quality long-term candidate.',
              why_not: 'Valuation can reset.',
              decision_notices: [
                { severity: 'debug', message: 'Adjusted price series may include split-adjusted closes.' },
                { severity: 'info', message: 'No fresh catalyst loaded.' },
              ],
              entry_zone: '95 - 100',
              stop_loss: 90,
              tp1: 110,
              source_row: {
                ticker: 'NVDA',
                current_price: 100,
                price_change_1d_pct: 2.4,
                relative_volume_20d: 1.8,
                ema_stack: 'Bullish Stack',
                signal_summary: 'Breakout with Volume',
                signal_explanation: 'Breakout with Volume: price cleared recent highs with relative volume around 1.80.',
              },
            },
          ],
          tracked_rows: [
            {
              ticker: 'NVDA',
              company: 'NVIDIA',
              primary_action: 'Research / Buy Candidate',
              action_lane: 'Outlier',
              source_group: 'Tracked',
              source_groups: ['Tracked', 'Broad'],
              actionability_score: 84,
              actionability_label: 'Actionable Today',
              reason: 'Quality long-term candidate.',
              why_not: 'Valuation can reset.',
              decision_notices: [
                { severity: 'debug', message: 'Adjusted price series may include split-adjusted closes.' },
                { severity: 'info', message: 'No fresh catalyst loaded.' },
              ],
              entry_zone: '95 - 100',
              stop_loss: 90,
              tp1: 110,
              source_row: {
                ticker: 'NVDA',
                current_price: 100,
                price_change_1d_pct: 2.4,
                relative_volume_20d: 1.8,
                ema_stack: 'Bullish Stack',
                signal_summary: 'Breakout with Volume',
                signal_explanation: 'Breakout with Volume: price cleared recent highs with relative volume around 1.80.',
              },
            },
          ],
          broad_rows: [],
          watch_rows: [],
          avoid_rows: [],
          signal_table_rows: [
            {
              ticker: 'NVDA',
              source: 'Tracked + Broad',
              price: 100,
              price_change_1d_pct: 2.4,
              relative_volume_20d: 1.8,
              ema_stack: 'Bullish Stack',
              signal: 'Breakout with Volume',
              signal_explanation: 'Breakout with Volume: price cleared recent highs with relative volume around 1.80.',
              actionability: 'Actionable Today',
              risk: 'Low',
              entry_or_trigger: '95 - 100',
              stop: 90,
              tp1: 110,
              updated: '2026-04-24',
            },
          ],
          decision_by_ticker: {
            NVDA: {
              ticker: 'NVDA',
              company: 'NVIDIA',
              primary_action: 'Research / Buy Candidate',
              action_lane: 'Outlier',
              source_group: 'Tracked',
              source_groups: ['Tracked', 'Broad'],
              actionability_score: 84,
              actionability_label: 'Actionable Today',
              reason: 'Quality long-term candidate.',
              why_not: 'Valuation can reset.',
              entry_zone: '95 - 100',
              stop_loss: 90,
              tp1: 110,
              source_row: {
                ticker: 'NVDA',
                current_price: 100,
                price_change_1d_pct: 2.4,
                relative_volume_20d: 1.8,
                ema_stack: 'Bullish Stack',
                signal_summary: 'Breakout with Volume',
                signal_explanation: 'Breakout with Volume: price cleared recent highs with relative volume around 1.80.',
              },
            },
          },
          chart_data_by_ticker: {},
          coverage_status: {
            universe_label: 'Large Cap Starter',
            tickers_attempted: 2,
            tickers_successfully_scanned: 1,
            tickers_failed: 1,
            tracked_tickers_count: 2,
            portfolio_tickers_count: 0,
            provider: 'real',
            cache_age_ttl_minutes: 60,
            cache_hits: 1,
            cache_misses: 1,
            scan_groups: [{ source_group: 'Tracked', universe: 'config/tracked_tickers.txt', result_count: 2 }],
          },
          data_issues: [],
          source_aware_top: {
            overall_top_setup: { ticker: 'NVDA', source_groups: ['Tracked', 'Broad'], actionability_label: 'Actionable Today', actionability_score: 84 },
            best_tracked_setup: { ticker: 'NVDA', actionability_label: 'Actionable Today', actionability_score: 84 },
            best_broad_setup: null,
          },
          selected_ticker_consistency_status: 'PASS',
          selected_ticker_consistency_reason: 'Selected ticker uses the canonical validated row across the chart, summary panel, and signal table.',
        },
      },
      '/api/reports/latest': { available: false, results: [], market_regime: {}, summary: {}, decisions: [], validation_context: { messages: ['Not enough evidence yet.'] } },
      '/api/tracked': {
        path: 'config/tracked_tickers.txt',
        tickers: ['NVDA', 'PLTR'],
        count: 2,
        message: 'Tracked tickers are monitored every daily run and can become top candidates if setup is strong.',
      },
      '/api/chart/NVDA': {
        available: true,
        ticker: 'NVDA',
        price_source: 'live quote',
        last_market_date: '2026-04-24',
        selected_timeframe: '1Y',
        series: [
          { date: '2026-04-22', close: 98, volume: 1000, ema_21: 96, ema_50: 94, ema_150: 90, ema_200: 88 },
          { date: '2026-04-23', close: 99, volume: 1200, ema_21: 97, ema_50: 95, ema_150: 90.5, ema_200: 88.5 },
          { date: '2026-04-24', close: 100, volume: 1500, ema_21: 98, ema_50: 96, ema_150: 91, ema_200: 89 },
        ],
        markers: [{ date: '2026-04-24', label: 'Breakout', tone: 'good' }],
        signals: { ema_stack: 'Bullish Stack', signal_summary: 'Breakout with Volume', relative_volume_20d: 1.8, signal_explanation: 'Breakout with Volume: price cleared recent highs with relative volume around 1.80.' },
      },
      '/api/universes': {
        items: [
          { label: 'Active Core Investing', path: 'config/active_core_investing_universe.txt', description: 'Core names.', available: true },
          { label: 'Active Outliers', path: 'config/active_outlier_universe.txt', description: 'Outlier names.', available: true },
          { label: 'Active Velocity', path: 'config/active_velocity_universe.txt', description: 'Velocity names.', available: true },
          { label: 'Mega Cap', path: 'config/mega_cap_universe.txt', description: 'Mega cap names.', available: true },
          { label: 'Momentum', path: 'config/momentum_universe.txt', description: 'Momentum names.', available: true },
          { label: 'Famous Case Studies', path: 'config/famous_outlier_case_studies.txt', description: 'Historical only.', available: true },
        ],
        warning: 'Famous Case Studies are for historical validation, not active monitoring.',
        home_defaults: ['config/active_core_investing_universe.txt', 'config/active_outlier_universe.txt'],
      },
      '/api/alerts': [],
      '/api/data-sources': {
        rows: [
          {
            name: 'OpenAI',
            category: 'AI providers',
            tier: 'AI',
            recommended_priority: 1,
            configured: false,
            required: false,
            required_env_vars: ['OPENAI_API_KEY', 'OPENAI_MODEL'],
            missing_env_vars_list: ['OPENAI_API_KEY'],
            capabilities: 'AI explanations',
            degraded_when_missing: 'OpenAI AI analysis is unavailable.',
            setup: 'Set OPENAI_API_KEY.',
            url: 'https://platform.openai.com/docs',
            notes: '',
            quota_notes: '',
            last_checked: 'not configured',
          },
          {
            name: 'SEC EDGAR',
            category: 'No key / free',
            tier: 'No key / free',
            recommended_priority: 5,
            configured: false,
            required: false,
            required_env_vars: ['SEC_USER_AGENT'],
            missing_env_vars_list: ['SEC_USER_AGENT'],
            capabilities: 'Company filings; Form 4 discovery',
            degraded_when_missing: 'SEC discovery unavailable.',
            setup: 'Set SEC_USER_AGENT.',
            url: 'https://www.sec.gov/',
            notes: '',
            quota_notes: 'Use gentle request rates.',
            last_checked: 'not configured',
          },
        ],
        summary: { providers: 1, required_missing: 0, optional_ready: 0, optional_missing: 1, degraded_capabilities: [] },
        local_env_editor_enabled: false,
        local_env_warning: 'local only',
      },
      '/api/doctor/latest': { available: false, message: 'Doctor has not run yet.' },
      '/api/readiness/latest': { available: false, message: 'Readiness has not run yet.' },
      '/api/signal-audit/latest': { available: false, message: 'Signal audit has not run yet.' },
      '/api/predictions': [],
      '/api/predictions/summary': {},
      '/api/app-status/latest': { available: true, markdown: '# TradeBruv App Status Report\n- OpenAI works: false' },
      '/api/replay/latest': {
        available: true,
        mode: 'outliers',
        summary: { total_replay_dates: 2, total_candidates: 2, false_positive_rate: 0.5, average_forward_return_by_horizon: { '20d': 4.2 }, strategy_performance: [] },
        results: [],
        point_in_time_limitations: 'OHLCV-only replay.',
      },
      '/api/investing-replay/latest': {
        available: true,
        mode: 'regular_investing',
        summary: {
          total_replay_dates: 2,
          total_candidates: 2,
          false_positive_rate: 0,
          regular_investing_forward_returns: { '20d': { average: 3.1, median: 2.4, win_rate: 1, sample_size: 2 } },
          best_worst_investing_styles: [{ investing_style: 'Quality Growth Leader', sample_size: 2, average: 3.1, median: 2.4, win_rate: 1 }],
        },
        replay_scans: [{
          top_investing_candidates: [{
            ticker: 'MSFT',
            company_name: 'Microsoft',
            regular_investing_score: 82,
            investing_action_label: 'Buy Candidate',
            investing_style: 'Quality Growth Leader',
            investing_risk: 'Low',
            investing_time_horizon: '12+ months',
            investing_reason: 'Quality long-term candidate.',
            investing_bear_case: 'Valuation can reset.',
            investing_invalidation: '200D trend fails.',
            investing_events_to_watch: ['Earnings'],
            value_trap_warning: 'No value-trap warning.',
            thesis_quality: 'High',
            investing_data_quality: 'Strong',
          }],
        }],
        results: [],
        point_in_time_limitations: 'OHLCV-only investing replay.',
      },
      '/api/portfolio-replay/latest': {
        available: true,
        summary: {
          total_decisions: 2,
          decision_performance: [{ core_investing_decision: 'Add on Strength', sample_size: 1, average: 4, median: 4, win_rate: 1 }],
        },
        results: [],
      },
      '/api/proof-report/latest': {
        available: true,
        evidence_strength: 'Not enough evidence',
        real_money_reliance: false,
        language_note: 'Evidence only.',
        answers: {},
      },
      '/api/investing-proof-report/latest': {
        available: true,
        evidence_strength: 'Promising historical evidence',
        real_money_reliance: false,
        language_note: 'Evidence only.',
        answers: { does_regular_investing_score_beat_SPY: 'Yes in this replay window.' },
      },
      '/api/scan': {
        generated_at: '2026-04-24T00:00:00Z',
        provider: 'real',
        mode: 'outliers',
        demo_mode: false,
        report_snapshot: false,
        stale_data: false,
        data_issues: [],
        results: [
          {
            ticker: 'NVDA',
            company_name: 'NVIDIA',
            status_label: 'Hold / Watch',
            winner_score: 70,
            outlier_score: 65,
            risk_score: 35,
            why_it_passed: ['Strong setup'],
            why_it_could_fail: ['Invalidation risk'],
            invalidation_level: 90,
            tp1: 110,
            tp2: 120,
            velocity_score: 72,
            velocity_type: 'Relative Volume Explosion',
            velocity_risk: 'High',
            quick_trade_watch_label: 'Quick trade watch',
            trigger_reason: 'Relative volume is high.',
            chase_warning: 'No special chase warning beyond normal invalidation discipline.',
            expected_horizon: '5D',
            regular_investing_score: 82,
            investing_action_label: 'Buy Candidate',
            investing_style: 'Quality Growth Leader',
            investing_risk: 'Low',
            investing_time_horizon: '12+ months',
            investing_reason: 'Quality long-term candidate.',
            investing_bear_case: 'Valuation can reset.',
            investing_invalidation: '200D trend fails.',
            investing_events_to_watch: ['Earnings'],
            value_trap_warning: 'No value-trap warning.',
            thesis_quality: 'High',
            investing_data_quality: 'Strong',
            provider: 'real',
            provider_name: 'real',
            price_source: 'latest quote',
            price_timestamp: '2026-04-24T00:00:00Z',
            price_confidence: 'High',
            price_warning: 'No price sanity warning.',
            latest_available_close: 100,
            quote_price_if_available: 101,
            last_market_date: '2026-04-24',
            validated_price: 101,
            validated_price_source: 'live quote',
            displayed_price: 101,
            price_mismatch_pct: 0,
            price_validation_status: 'PASS',
            price_validation_reason: 'Validated live price.',
          },
        ],
        market_regime: {},
        summary: {},
        decisions: [
          {
            ticker: 'NVDA',
            company: 'NVIDIA',
            primary_action: 'Research / Buy Candidate',
            action_lane: 'Core Investing',
            score: 82,
            actionability_score: 72,
            actionability_label: 'Research First',
            actionability_reason: 'Price is valid and the thesis is interesting, but confirmation is not clean enough for a same-day entry.',
            action_trigger: 'Research around 95 - 100, then reassess catalyst, risk, and execution discipline.',
            trigger_needed: true,
            current_setup_state: 'In Entry Zone',
            level_status: 'Preliminary',
            entry_label: 'Research Zone',
            evidence_pill: 'Mixed',
            confidence_label: 'Medium',
            evidence_strength: 'Not enough evidence yet',
            risk_level: 'Low',
            entry_zone: '95 - 100',
            stop_loss: 90,
            invalidation: 90,
            tp1: 110,
            tp2: 120,
            reward_risk: 2,
            holding_horizon: '12+ months',
            reason: 'Quality long-term candidate.',
            why_not: 'Valuation can reset.',
            next_review_date: '2026-04-30',
            price_sanity: {
              price_source: 'latest quote',
              price_timestamp: '2026-04-24T00:00:00Z',
              price_confidence: 'High',
              price_warning: 'No price sanity warning.',
              latest_available_close: 100,
              quote_price_if_available: 101,
              validated_price: 101,
              validated_price_source: 'live quote',
              displayed_price: 101,
              price_mismatch_pct: 0,
              price_validation_status: 'PASS',
              price_validation_reason: 'Validated live price.',
            },
            price_source: 'live quote',
            latest_market_date: '2026-04-24',
            price_validation_status: 'PASS',
            price_validation_reason: 'Validated live price.',
            source_row: {
              ticker: 'NVDA',
              status_label: 'Hold / Watch',
              winner_score: 70,
              outlier_score: 65,
              risk_score: 35,
              price_validation_status: 'PASS',
            },
          },
        ],
        validation_context: { messages: ['Not enough evidence yet.'] },
      },
      '/api/outlier-study/run': {
        ticker: 'GME',
        available: true,
        did_it_catch_move: 'caught',
        was_it_early_or_late: 'early',
        first_trigger_date: '2021-01-04',
        first_trigger_type: 'Explosive Momentum',
        max_outlier_score: 80,
        date_of_max_score: '2021-01-11',
        max_forward_return_after_trigger: 120,
        score_progression: [{ date: '2021-01-04', price: 20, outlier_score: 70, velocity_score: 75, triggered: true }],
        narrative: 'Mock case study narrative.',
      },
      '/api/deep-research': {
        ticker: 'NVDA',
        current_price: 100,
        decision_card: { research_recommendation: 'Buy Candidate' },
        unified_decision: {
          ticker: 'NVDA',
          primary_action: 'Research / Buy Candidate',
          actionability_label: 'Research First',
          actionability_score: 72,
          actionability_reason: 'Price is valid and the thesis is interesting, but confirmation is not clean enough for a same-day entry.',
          current_setup_state: 'In Entry Zone',
          action_trigger: 'Research around 95 - 100, then reassess catalyst, risk, and execution discipline.',
          trigger_needed: true,
          level_status: 'Preliminary',
          entry_label: 'Research Zone',
          entry_zone: '95 - 100',
          stop_loss: 90,
          tp1: 110,
          tp2: 120,
          evidence_pill: 'Mixed',
          reason: 'Quality long-term candidate.',
          why_not: 'Valuation can reset.',
          confidence_label: 'Medium',
          evidence_strength: 'Not enough evidence yet',
          events_to_watch: ['Earnings'],
        },
        price_sanity: {
          price_source: 'sample latest close',
          price_timestamp: '2026-04-24T00:00:00Z',
          price_confidence: 'Low',
          price_warning: 'Sample data — not real price.',
        },
        validation_context: { messages: ['Not enough evidence yet.'] },
        regular_investing_view: {
          regular_investing_score: 82,
          investing_action_label: 'Buy Candidate',
          investing_style: 'Quality Growth Leader',
          investing_risk: 'Low',
          bull_case: 'Quality long-term candidate.',
          bear_case: 'Valuation can reset.',
          invalidation: '200D trend fails.',
          events_to_watch: ['Earnings'],
          value_trap_warning: 'No value-trap warning.',
          thesis_quality: 'High',
          data_quality: 'Strong',
        },
        scanner_row: {
          ticker: 'NVDA',
          winner_score: 70,
          outlier_score: 65,
          risk_score: 35,
          regular_investing_score: 82,
          investing_action_label: 'Buy Candidate',
          investing_style: 'Quality Growth Leader',
          investing_risk: 'Low',
          investing_reason: 'Quality long-term candidate.',
          investing_bear_case: 'Valuation can reset.',
          investing_invalidation: '200D trend fails.',
          investing_events_to_watch: ['Earnings'],
          value_trap_warning: 'No value-trap warning.',
          thesis_quality: 'High',
          investing_data_quality: 'Strong',
          price_source: 'sample latest close',
          price_timestamp: '2026-04-24T00:00:00Z',
          price_confidence: 'Low',
          price_warning: 'Sample data — not real price.',
        },
      },
      '/api/portfolio/analyze': {
        positions: [{
          ticker: 'NVDA',
          core_investing_decision: 'Strong Hold',
          regular_investing_score: 82,
          investing_style: 'Quality Growth Leader',
          review_priority: 'Normal',
          reason_to_hold: 'Trend intact.',
          reason_to_add: 'Quality long-term candidate.',
          reason_to_trim: 'No trim reason confirmed.',
          reason_to_exit: 'Exit case is not confirmed.',
          concentration_warning: 'No concentration warning.',
          valuation_or_overextension_warning: 'No valuation or overextension warning.',
          broken_trend_warning: 'No broken-trend warning.',
          next_review_trigger: 'Review on earnings.',
        }],
      },
    };
    const pathname = new URL(url, 'http://localhost:8000').pathname;
    if (pathname === '/api/scan/start') {
      return Promise.resolve(new Response(JSON.stringify({ job_id: 'job-1', status: 'queued' }), { status: 200 }));
    }
    if (pathname === '/api/scan/status/job-1') {
      return Promise.resolve(new Response(JSON.stringify({ job_id: 'job-1', status: 'completed', attempted: 1, scanned: 1, failed: 0, provider_health: { status: 'healthy' }, preview_rows: [{ ticker: 'NVDA', current_price: 100, price_change_1d_pct: 2.4, relative_volume_20d: 1.8, signal_summary: 'Breakout with Volume', outlier_score: 82 }] }), { status: 200 }));
    }
    if (pathname === '/api/scan/result/job-1') {
      return Promise.resolve(new Response(JSON.stringify(payloads['/api/scan']), { status: 200 }));
    }
    const key = Object.keys(payloads).find((path) => pathname === path);
    return Promise.resolve(new Response(JSON.stringify(payloads[key ?? '/api/alerts']), { status: 200 }));
  }),
);

describe('App', () => {
  afterEach(() => cleanup());

  it('renders the shell navigation', async () => {
    render(<App />);
    expect((await screen.findAllByText('TradeBruv')).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /Stock Picker/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Data Sources/i })).toBeInTheDocument();
  });

  it('renders the chart-first decision cockpit workspace on the home screen', async () => {
    render(<App />);
    expect((await screen.findAllByText(/Decision Cockpit/i)).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /Movers/i })).toBeInTheDocument();
    expect(screen.getByText(/Top screener/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Large Cap Starter/i).length).toBeGreaterThan(0);
    expect((await screen.findAllByText((_, element) => element?.textContent?.includes('EMA 21:') ?? false)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Adjusted price series may include split-adjusted closes\./i)).not.toBeInTheDocument();
    expect(screen.getByText('Gainer')).toBeInTheDocument();
    expect(screen.getByText('Why')).toBeInTheDocument();
    expect(screen.queryByText(/Validated price, acceptable risk\/reward, and current setup all line up\./i)).not.toBeInTheDocument();
    expect(screen.getAllByText('NVDA').length).toBeGreaterThan(0);
    expect(screen.getAllByText('PLTR')).toHaveLength(1);
    expect(screen.queryByText('This strategy beat SPY/QQQ but did not beat random baseline.')).not.toBeInTheDocument();
    expect(screen.queryByText('No live daily decision loaded')).not.toBeInTheDocument();
  });

  it('renders data-source setup and workflow panels', async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /Data Sources/i }));
    expect(await screen.findByText('Recommended Free-First Setup')).toBeInTheDocument();
    expect(screen.getAllByText('SEC_USER_AGENT').length).toBeGreaterThan(0);
    expect(screen.getByText('Doctor / API Testing')).toBeInTheDocument();
    expect(screen.getByText('Run Readiness')).toBeInTheDocument();
  });

  it('hides repeated paper tracking forms and opens tracking in a modal', async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /Stock Picker/i }));
    fireEvent.click(await screen.findByRole('button', { name: /Run Scan/i }));
    expect(await screen.findByRole('columnheader', { name: /Company/i })).toBeInTheDocument();
    fireEvent.click((await screen.findAllByText('NVDA'))[0]);
    expect(await screen.findByRole('button', { name: /^Track$/i })).toBeInTheDocument();
    expect(screen.queryByText('Start Paper Tracking')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^Track$/i }));
    expect(await screen.findByText('Track this idea')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Save Prediction/i })).toBeInTheDocument();
  });

  it('renders the app status report', async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /Reports/i }));
    expect(await screen.findByText('App Status Report')).toBeInTheDocument();
    expect(screen.getByText(/OpenAI works/i)).toBeInTheDocument();
  });

  it('renders Replay Lab, Velocity Scanner, and Outlier Case Study', async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /Advanced/i }));
    fireEvent.click(await screen.findByRole('button', { name: /Replay Lab/i }));
    expect(await screen.findByRole('heading', { name: /Replay Lab/i })).toBeInTheDocument();
    expect(screen.getByText('OHLCV-only replay.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Velocity Scanner/i }));
    fireEvent.click(await screen.findByRole('button', { name: /Run Velocity Scan/i }));
    expect(await screen.findByText('Velocity Score Cards')).toBeInTheDocument();
    expect(screen.getAllByText('Relative Volume Explosion').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /Outlier Case Study/i }));
    fireEvent.click(await screen.findByRole('button', { name: /Run Study/i }));
    expect(await screen.findByText('Trigger Timeline')).toBeInTheDocument();
    expect(screen.getByText('Mock case study narrative.')).toBeInTheDocument();
  });

  it('renders Core Investing, Deep Research regular view, portfolio decision, and validation workflows', async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /Advanced/i }));
    fireEvent.click(await screen.findByRole('button', { name: /Core Investing/i }));
    expect(await screen.findByRole('heading', { name: /Core Investing/i })).toBeInTheDocument();
    expect(screen.getByText('Long-Term Candidates')).toBeInTheDocument();
    expect(screen.getAllByText('Quality Growth Leader').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /Deep Research/i }));
    fireEvent.click(await screen.findByRole('button', { name: /^Research$/i }));
    expect(await screen.findByText('Decision Synthesis')).toBeInTheDocument();
    expect(screen.getAllByText('Quality Growth Leader').length).toBeGreaterThan(0);
    expect(screen.getByText(/Evidence: Mixed/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Portfolio Analyst/i }));
    expect(await screen.findByText('Strong Hold')).toBeInTheDocument();
    expect(screen.getByText('Core Investing Decision')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Validation Lab/i }));
    expect(await screen.findByText('Core Investing Validation')).toBeInTheDocument();
    expect(screen.getByText('Investing Replay')).toBeInTheDocument();
    expect(screen.getByText('Investing Proof Report')).toBeInTheDocument();
  });
});
