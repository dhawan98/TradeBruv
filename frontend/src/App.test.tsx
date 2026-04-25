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
      '/api/reports/latest': { available: false, results: [], market_regime: {}, summary: {} },
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
      '/api/proof-report/latest': {
        available: true,
        evidence_strength: 'Not enough evidence',
        real_money_reliance: false,
        language_note: 'Evidence only.',
        answers: {},
      },
      '/api/scan': {
        generated_at: '2026-04-24T00:00:00Z',
        provider: 'sample',
        mode: 'outliers',
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
          },
        ],
        market_regime: {},
        summary: {},
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
    };
    const pathname = new URL(url, 'http://localhost:8000').pathname;
    const key = Object.keys(payloads).find((path) => pathname === path);
    return Promise.resolve(new Response(JSON.stringify(payloads[key ?? '/api/alerts']), { status: 200 }));
  }),
);

describe('App', () => {
  afterEach(() => cleanup());

  it('renders the shell navigation', async () => {
    render(<App />);
    expect(await screen.findByText('TradeBruv')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Stock Picker/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Data Sources/i })).toBeInTheDocument();
  });

  it('renders the stock picker empty state on the home screen', async () => {
    render(<App />);
    expect(await screen.findByText('No scan loaded')).toBeInTheDocument();
  });

  it('renders data-source setup and workflow panels', async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /Data Sources/i }));
    expect(await screen.findByText('Recommended Free-First Setup')).toBeInTheDocument();
    expect(screen.getAllByText('SEC_USER_AGENT').length).toBeGreaterThan(0);
    expect(screen.getByText('Doctor / API Testing')).toBeInTheDocument();
    expect(screen.getByText('Run Readiness')).toBeInTheDocument();
  });

  it('shows paper tracking workflow after a scan', async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /Stock Picker/i }));
    fireEvent.click(await screen.findByRole('button', { name: /Run Scan/i }));
    expect(await screen.findByText('Start Paper Tracking')).toBeInTheDocument();
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
});
