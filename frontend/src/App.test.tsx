import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
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
            configured: false,
            required: false,
            required_env_vars: ['OPENAI_API_KEY', 'OPENAI_MODEL'],
            missing_env_vars_list: ['OPENAI_API_KEY'],
            capabilities: 'AI explanations',
            degraded_when_missing: 'OpenAI AI analysis is unavailable.',
            setup: 'Set OPENAI_API_KEY.',
            url: 'https://platform.openai.com/docs',
            notes: '',
            last_checked: 'not configured',
          },
        ],
        summary: { providers: 1, required_missing: 0, optional_ready: 0, optional_missing: 1, degraded_capabilities: [] },
        local_env_editor_enabled: false,
        local_env_warning: 'local only',
      },
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
});
