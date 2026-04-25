import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';

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
    };
    const key = Object.keys(payloads).find((path) => url.endsWith(path));
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
});
