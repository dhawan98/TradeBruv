import { FormEvent, useState } from 'react';
import type React from 'react';
import {
  AlertTriangle,
  BookOpen,
  Brain,
  Database,
  FileText,
  FlaskConical,
  Gauge,
  Home,
  Layers,
  LineChart,
  RefreshCcw,
  Search,
  ShieldAlert,
  Wallet,
} from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, AlertRow, DataSourceRow, HealthPayload, PortfolioPayload, ScannerRow } from './api';
import { useAsync } from './hooks';

type PageKey =
  | 'Home'
  | 'Stock Picker'
  | 'Deep Research'
  | 'Portfolio'
  | 'Portfolio Analyst'
  | 'AI Committee'
  | 'Validation Lab'
  | 'Alerts'
  | 'Journal'
  | 'Data Sources'
  | 'Reports';

const NAV: { key: PageKey; icon: React.ComponentType<{ size?: number }> }[] = [
  { key: 'Home', icon: Home },
  { key: 'Stock Picker', icon: Search },
  { key: 'Deep Research', icon: BookOpen },
  { key: 'Portfolio', icon: Wallet },
  { key: 'Portfolio Analyst', icon: LineChart },
  { key: 'AI Committee', icon: Brain },
  { key: 'Validation Lab', icon: FlaskConical },
  { key: 'Alerts', icon: ShieldAlert },
  { key: 'Journal', icon: FileText },
  { key: 'Data Sources', icon: Database },
  { key: 'Reports', icon: Layers },
];

const GROUPS: Record<string, string[]> = {
  'Market Data': ['Market data', 'Market data / News', 'Market data / Fundamentals'],
  'News / Events': ['News/events'],
  'Social / Attention': ['Social/attention'],
  'AI Providers': ['AI providers'],
  'Portfolio / Brokerage': ['Portfolio/brokerage'],
};

export function App() {
  const [page, setPage] = useState<PageKey>('Home');
  const health = useAsync(api.health, []);
  const portfolio = useAsync(api.portfolio, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">TB</div>
          <div>
            <strong>TradeBruv</strong>
            <span>Stock decision cockpit</span>
          </div>
        </div>
        <nav className="nav-list">
          {NAV.map(({ key, icon: Icon }) => (
            <button className={page === key ? 'nav-item active' : 'nav-item'} key={key} onClick={() => setPage(key)}>
              <Icon size={17} />
              <span>{key}</span>
            </button>
          ))}
        </nav>
      </aside>
      <main className="main">
        <TopBar health={health.data} portfolio={portfolio.data} />
        <section className="workspace">
          {page === 'Home' && <HomePage setPage={setPage} />}
          {page === 'Stock Picker' && <StockPicker />}
          {page === 'Deep Research' && <DeepResearch />}
          {page === 'Portfolio' && <Portfolio />}
          {page === 'Portfolio Analyst' && <PortfolioAnalyst />}
          {page === 'AI Committee' && <AICommittee />}
          {page === 'Validation Lab' && <ValidationLab />}
          {page === 'Alerts' && <Alerts />}
          {page === 'Journal' && <Journal />}
          {page === 'Data Sources' && <DataSources />}
          {page === 'Reports' && <Reports />}
        </section>
      </main>
    </div>
  );
}

function TopBar({ health, portfolio }: { health: HealthPayload | null; portfolio: PortfolioPayload | null }) {
  return (
    <header className="topbar">
      <div>
        <span className="eyebrow">Mode</span>
        <strong>{health?.mode ?? 'outliers'}</strong>
      </div>
      <Status label="Provider" value={health?.provider ?? 'sample'} />
      <Status label="Last scan" value={compactDate(health?.last_scan_time)} />
      <Status label="Data sources" value={`${health?.data_source_health.optional_ready ?? 0} ready`} tone="good" />
      <Status label="AI" value={health?.ai.any_configured ? 'Configured' : 'Missing'} tone={health?.ai.any_configured ? 'good' : 'warn'} />
      <Status label="Portfolio" value={money(Number(portfolio?.summary?.total_market_value ?? health?.portfolio_value ?? 0))} />
      <Status label="Alerts" value={String(health?.alert_count ?? 0)} tone={health?.alert_count ? 'warn' : 'good'} />
    </header>
  );
}

function HomePage({ setPage }: { setPage: (page: PageKey) => void }) {
  const latest = useAsync(api.latestReport, []);
  const alerts = useAsync(api.alerts, []);
  const sources = useAsync(api.dataSources, []);
  const rows = latest.data?.results ?? [];
  const top = rows.filter((row) => row.status_label !== 'Avoid').slice(0, 5);

  return (
    <Page title="Home" subtitle="Daily brief, open risks, and the next useful research action.">
      <div className="metric-grid">
        <Metric label="Candidates" value={String(top.length)} sub="Non-avoid names in latest scan" />
        <Metric label="Open alerts" value={String(alerts.data?.length ?? 0)} sub="Daily workflow prompts" />
        <Metric label="Data sources" value={`${sources.data?.summary.optional_ready ?? 0} ready`} sub="Configured optional providers" />
        <Metric label="Regime" value={String(latest.data?.market_regime?.regime ?? 'Unavailable')} sub="From latest deterministic scan" />
      </div>
      {top.length ? (
        <div className="grid two">
          <Panel title="Top Research Candidates">
            <CandidateList rows={top} />
          </Panel>
          <Panel title="Open Alerts">
            <AlertList rows={(alerts.data ?? []).slice(0, 6)} />
          </Panel>
        </div>
      ) : (
        <EmptyState title="No scan loaded" action="Run Scan" onAction={() => setPage('Stock Picker')}>
          Run a deterministic sample scan to populate candidates, risk warnings, and the daily cockpit.
        </EmptyState>
      )}
    </Page>
  );
}

function StockPicker() {
  const [scan, setScan] = useState<ScannerRow[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError('');
    const form = new FormData(event.currentTarget);
    try {
      const payload = await api.scan({
        provider: form.get('provider'),
        mode: form.get('mode'),
        universe_path: form.get('universe_path'),
        as_of_date: form.get('as_of_date'),
      });
      setScan(payload.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scan failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Page title="Stock Picker" subtitle="Run the Python scanner and review candidates without duplicating scoring in React.">
      <form className="toolbar" onSubmit={submit}>
        <Select name="provider" label="Provider" options={['sample', 'local', 'real']} />
        <Select name="mode" label="Mode" options={['outliers', 'standard']} />
        <Field name="universe_path" label="Universe" defaultValue="config/sample_universe.txt" />
        <Field name="as_of_date" label="As of" defaultValue="2026-04-24" />
        <button className="primary" disabled={loading}>
          <RefreshCcw size={16} /> {loading ? 'Running' : 'Run Scan'}
        </button>
      </form>
      {error && <Notice tone="bad">{error}</Notice>}
      {scan.length ? (
        <div className="grid">
          <Panel title="Candidates">
            <CandidateList rows={scan.filter((row) => row.status_label !== 'Avoid').slice(0, 8)} />
          </Panel>
          <Panel title="Scanner Table">
            <ScannerTable rows={scan} />
          </Panel>
          <Panel title="Avoid Panel">
            <ScannerTable rows={scan.filter((row) => row.status_label === 'Avoid')} />
          </Panel>
        </div>
      ) : (
        <EmptyState title="Ready for a deterministic scan" action="Run sample outlier scan">
          Sample mode does not need external keys and is safe for local UI checks.
        </EmptyState>
      )}
    </Page>
  );
}

function DeepResearch() {
  const [research, setResearch] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError('');
    try {
      setResearch(await api.deepResearch({ ticker: form.get('ticker'), provider: form.get('provider') }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Deep research failed');
    }
  }

  return (
    <Page title="Deep Research" subtitle="Single-stock deterministic thesis, risks, levels, and portfolio context.">
      <form className="toolbar" onSubmit={submit}>
        <Field name="ticker" label="Ticker" defaultValue="NVDA" />
        <Select name="provider" label="Provider" options={['sample', 'local', 'real']} />
        <button className="primary"><Search size={16} /> Research</button>
      </form>
      {error && <Notice tone="bad">{error}</Notice>}
      {research && <ResearchView payload={research} />}
    </Page>
  );
}

function Portfolio() {
  const portfolio = useAsync(api.portfolio, []);
  const positions = portfolio.data?.positions ?? [];
  const chart = positions.map((row) => ({ ticker: row.ticker, weight: Number(row.position_weight_pct ?? 0) }));

  return (
    <Page title="Portfolio" subtitle="Local holdings, allocation, P/L, and concentration checks.">
      <div className="metric-grid">
        <Metric label="Value" value={money(Number(portfolio.data?.summary?.total_market_value ?? 0))} sub="Local portfolio file" />
        <Metric label="Positions" value={String(positions.length)} sub="Manual or CSV import" />
        <Metric label="Unrealized P/L" value={money(Number(portfolio.data?.summary?.total_unrealized_gain_loss ?? 0))} sub="From local marks" />
      </div>
      <div className="grid two">
        <Panel title="Holdings">
          <DataTable rows={positions} columns={['ticker', 'company_name', 'market_value', 'position_weight_pct', 'unrealized_gain_loss_pct', 'decision_status']} />
        </Panel>
        <Panel title="Allocation">
          <Chart data={chart} />
        </Panel>
      </div>
    </Page>
  );
}

function PortfolioAnalyst() {
  const analyst = useAsync(() => api.portfolioAnalyze({ provider: 'sample' }), []);
  const positions = (analyst.data?.positions as Record<string, unknown>[] | undefined) ?? [];
  return (
    <Page title="Portfolio Analyst" subtitle="Hold, add, trim, exit, and watch labels generated by the Python analyst.">
      <DataTable rows={positions} columns={['ticker', 'recommendation_label', 'action_urgency', 'reason_to_hold', 'reason_to_add', 'invalidation_level']} />
    </Page>
  );
}

function AICommittee() {
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError('');
    try {
      setPayload(await api.aiCommittee({ ticker: form.get('ticker'), mode: form.get('mode'), provider: 'sample' }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI committee failed');
    }
  }
  const committee = payload?.committee as Record<string, unknown> | undefined;
  const combined = payload?.combined as Record<string, unknown> | undefined;
  return (
    <Page title="AI Committee" subtitle="Rule-first committee view. Mock mode works offline; live providers are not tested in this pass.">
      <form className="toolbar" onSubmit={submit}>
        <Field name="ticker" label="Ticker" defaultValue="NVDA" />
        <Select name="mode" label="Mode" options={['No AI', 'Mock AI for testing', 'OpenAI only', 'Gemini only']} />
        <button className="primary"><Brain size={16} /> Run Committee</button>
      </form>
      {error && <Notice tone="bad">{error}</Notice>}
      {committee && (
        <div className="grid two">
          <Panel title="Combined Recommendation">
            <KeyValue payload={combined ?? {}} />
          </Panel>
          <Panel title="Analyst Views">
            <KeyValue payload={committee} />
          </Panel>
        </div>
      )}
    </Page>
  );
}

function ValidationLab() {
  const summary = useAsync(api.predictionsSummary, []);
  const predictions = useAsync(api.predictions, []);
  return (
    <Page title="Validation Lab" subtitle="Paper predictions, outcome updates, and famous outlier case studies.">
      <div className="metric-grid">
        <Metric label="Open" value={String((summary.data?.open_predictions as unknown[] | undefined)?.length ?? 0)} sub="Awaiting outcome" />
        <Metric label="Closed" value={String((summary.data?.closed_predictions as unknown[] | undefined)?.length ?? 0)} sub="Measured signals" />
      </div>
      <Panel title="Predictions">
        <DataTable rows={predictions.data ?? []} columns={['prediction_id', 'ticker', 'final_combined_recommendation', 'outcome_label', 'return_20d']} />
      </Panel>
    </Page>
  );
}

function Alerts() {
  const alerts = useAsync(api.alerts, []);
  return (
    <Page title="Alerts" subtitle="Deterministic workflow prompts from the daily scan outputs.">
      <AlertList rows={alerts.data ?? []} />
    </Page>
  );
}

function Journal() {
  const journal = useAsync(api.journal, []);
  return (
    <Page title="Journal" subtitle="Local process journal and review statistics.">
      <div className="metric-grid">
        <Metric label="Entries" value={String(journal.data?.stats.total_entries ?? 0)} sub="Local CSV journal" />
        <Metric label="Rules followed" value={`${journal.data?.stats.rules_followed_pct ?? 0}%`} sub="Process quality" />
      </div>
      <DataTable rows={journal.data?.entries ?? []} columns={['created_at', 'ticker', 'decision', 'result_pct', 'followed_rules', 'mistake_category', 'notes']} />
    </Page>
  );
}

function DataSources() {
  const sources = useAsync(api.dataSources, []);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const rows = sources.data?.rows ?? [];

  async function createTemplate() {
    setError('');
    try {
      const result = await api.createEnvTemplate();
      setMessage(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create .env');
    }
  }

  async function updateLocalEnv(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const values: Record<string, string> = {};
    for (const [key, value] of form.entries()) {
      if (typeof value === 'string' && value.trim()) values[key] = value;
    }
    setError('');
    try {
      const result = await api.updateLocalEnv(values);
      setMessage(result.message);
      event.currentTarget.reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update .env');
    }
  }

  return (
    <Page title="Data Sources" subtitle="Provider readiness, missing keys, degraded capabilities, and local .env setup.">
      {message && <Notice tone="good">{message}</Notice>}
      {error && <Notice tone="bad">{error}</Notice>}
      <div className="grid two">
        <Panel title="How to Add Keys Locally">
          <ol className="steps">
            <li>Copy <code>.env.example</code> to <code>.env</code>.</li>
            <li>Fill only the providers you want, such as <code>OPENAI_API_KEY</code> or <code>GEMINI_API_KEY</code>.</li>
            <li>Restart the FastAPI backend.</li>
          </ol>
          <button className="secondary" onClick={createTemplate}>Create .env from template</button>
        </Panel>
        <Panel title="Safe Local .env Editor">
          <Notice tone={sources.data?.local_env_editor_enabled ? 'warn' : 'neutral'}>
            {sources.data?.local_env_editor_enabled
              ? sources.data.local_env_warning
              : 'Disabled by default. Set TRADEBRUV_ALLOW_LOCAL_ENV_EDITOR=true only on a private local machine.'}
          </Notice>
          {sources.data?.local_env_editor_enabled ? (
            <form className="env-form" onSubmit={updateLocalEnv}>
              {missingEnvVars(rows).map((key) => (
                <label key={key}>
                  <span>{key}</span>
                  <input name={key} type="password" autoComplete="off" />
                </label>
              ))}
              <button className="primary">Save missing keys locally</button>
            </form>
          ) : (
            <p className="muted">Input fields are hidden while the editor is disabled, so no secrets are sent to the frontend.</p>
          )}
        </Panel>
      </div>
      {Object.entries(GROUPS).map(([group, categories]) => (
        <Panel title={group} key={group}>
          <div className="provider-grid">
            {rows.filter((row) => categories.includes(row.category)).map((row) => (
              <ProviderCard row={row} key={row.name} />
            ))}
          </div>
        </Panel>
      ))}
      <div className="grid two">
        <Panel title="Configured Capabilities">
          <ul className="plain-list">{rows.filter((row) => row.configured).map((row) => <li key={row.name}>{row.name}: {row.capabilities}</li>)}</ul>
        </Panel>
        <Panel title="Degraded Capabilities">
          <ul className="plain-list">{rows.filter((row) => !row.configured).slice(0, 12).map((row) => <li key={row.name}>{row.degraded_when_missing}</li>)}</ul>
        </Panel>
      </div>
    </Page>
  );
}

function Reports() {
  const latest = useAsync(api.latestReport, []);
  const archive = useAsync(api.reportsArchive, []);
  const [debug, setDebug] = useState(false);
  return (
    <Page title="Reports" subtitle="Latest scan, archive index, daily summary, alerts, and optional debug payloads.">
      <div className="grid two">
        <Panel title="Latest Scan">
          <ScannerTable rows={latest.data?.results ?? []} />
        </Panel>
        <Panel title="Archive">
          <DataTable rows={archive.data?.reports ?? []} columns={['modified_at', 'name', 'path']} />
        </Panel>
      </div>
      <button className="secondary" onClick={() => setDebug((value) => !value)}>Toggle debug JSON</button>
      {debug && <pre className="debug-json">{JSON.stringify(latest.data, null, 2)}</pre>}
    </Page>
  );
}

function Page({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <>
      <div className="page-head">
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {children}
    </>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function Status({ label, value, tone = 'neutral' }: { label: string; value: string; tone?: 'neutral' | 'good' | 'warn' }) {
  return (
    <div className={`status ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}

function Field({ name, label, defaultValue = '' }: { name: string; label: string; defaultValue?: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input name={name} defaultValue={defaultValue} />
    </label>
  );
}

function Select({ name, label, options }: { name: string; label: string; options: string[] }) {
  return (
    <label className="field">
      <span>{label}</span>
      <select name={name}>
        {options.map((option) => <option key={option}>{option}</option>)}
      </select>
    </label>
  );
}

function Notice({ tone, children }: { tone: 'good' | 'bad' | 'warn' | 'neutral'; children: React.ReactNode }) {
  return <div className={`notice ${tone}`}>{children}</div>;
}

function EmptyState({ title, action, onAction, children }: { title: string; action: string; onAction?: () => void; children: React.ReactNode }) {
  return (
    <div className="empty-state">
      <Gauge size={30} />
      <h2>{title}</h2>
      <p>{children}</p>
      {onAction && <button className="primary" onClick={onAction}>{action}</button>}
    </div>
  );
}

function ProviderCard({ row }: { row: DataSourceRow }) {
  return (
    <article className="provider-card">
      <div className="provider-title">
        <strong>{row.name}</strong>
        <Chip tone={row.configured ? 'good' : 'bad'}>{row.configured ? 'Configured' : 'Missing'}</Chip>
      </div>
      <p>{row.capabilities}</p>
      <dl>
        <dt>Required env vars</dt>
        <dd>{row.required_env_vars.length ? row.required_env_vars.join(', ') : 'None'}</dd>
        <dt>Missing env vars</dt>
        <dd>{row.missing_env_vars_list.length ? row.missing_env_vars_list.join(', ') : 'None'}</dd>
        <dt>Degraded if missing</dt>
        <dd>{row.degraded_when_missing}</dd>
        <dt>Last checked</dt>
        <dd>{row.last_checked}</dd>
      </dl>
      <p className="setup">{row.setup}</p>
      <a href={row.url} target="_blank" rel="noreferrer">Docs</a>
    </article>
  );
}

function CandidateList({ rows }: { rows: ScannerRow[] }) {
  return (
    <div className="candidate-list">
      {rows.map((row) => (
        <article className="candidate-card" key={row.ticker}>
          <div>
            <h3>{row.ticker}</h3>
            <span>{row.company_name ?? row.outlier_type ?? 'Research candidate'}</span>
          </div>
          <div className="score-stack">
            <Chip tone="good">W {row.winner_score ?? 0}</Chip>
            <Chip tone={(row.risk_score ?? 0) >= 60 ? 'bad' : 'neutral'}>R {row.risk_score ?? 0}</Chip>
          </div>
          <p>{row.status_label} · {row.outlier_type}</p>
          {(row.warnings ?? []).slice(0, 2).map((warning) => <small className="risk" key={warning}><AlertTriangle size={13} /> {warning}</small>)}
          <div className="actions">
            <button className="ghost">Deep Research</button>
            <button className="ghost">Journal</button>
            <button className="ghost">Prediction</button>
          </div>
        </article>
      ))}
    </div>
  );
}

function ScannerTable({ rows }: { rows: ScannerRow[] }) {
  return <DataTable rows={rows} columns={['ticker', 'status_label', 'winner_score', 'outlier_score', 'risk_score', 'setup_quality_score', 'outlier_type', 'entry_zone']} />;
}

function AlertList({ rows }: { rows: AlertRow[] }) {
  if (!rows.length) return <p className="muted">No alerts loaded.</p>;
  return (
    <div className="alert-list">
      {rows.map((row, index) => (
        <article className="alert-row" key={`${row.ticker}-${row.alert_type}-${index}`}>
          <Chip tone={row.severity === 'Critical' ? 'bad' : row.severity === 'Important' ? 'warn' : 'neutral'}>{row.severity ?? 'Info'}</Chip>
          <strong>{row.ticker ?? 'Portfolio'}</strong>
          <span>{row.alert_type}</span>
          <p>{row.explanation}</p>
        </article>
      ))}
    </div>
  );
}

function DataTable({ rows, columns }: { rows: Record<string, unknown>[]; columns: string[] }) {
  if (!rows.length) return <p className="muted">No rows available.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column}>{labelize(column)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={String(row.id ?? row.ticker ?? row.prediction_id ?? index)}>
              {columns.map((column) => <td key={column}>{cell(row[column])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Chart({ data }: { data: { ticker: string; weight: number }[] }) {
  if (!data.length) return <p className="muted">No allocation data.</p>;
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data}>
          <CartesianGrid stroke="#243244" />
          <XAxis dataKey="ticker" stroke="#9fb0c4" />
          <YAxis stroke="#9fb0c4" />
          <Tooltip contentStyle={{ background: '#101722', border: '1px solid #27364a', color: '#e8eef7' }} />
          <Bar dataKey="weight" fill="#4fb3a3" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function ResearchView({ payload }: { payload: Record<string, unknown> }) {
  const decision = payload.decision_card as Record<string, unknown> | undefined;
  const scanner = payload.scanner_row as ScannerRow | undefined;
  return (
    <div className="grid two">
      <Panel title="Decision Card">
        <KeyValue payload={decision ?? {}} />
      </Panel>
      <Panel title="Scores">
        <div className="metric-grid compact">
          <Metric label="Winner" value={String(scanner?.winner_score ?? payload.winner_score ?? 0)} sub="Rule score" />
          <Metric label="Outlier" value={String(scanner?.outlier_score ?? payload.outlier_score ?? 0)} sub="Outlier engine" />
          <Metric label="Risk" value={String(scanner?.risk_score ?? payload.risk_score ?? 0)} sub="Lower is better" />
        </div>
        <KeyValue payload={{ entry: payload.entry_zone, invalidation: payload.invalidation, tp1: payload.tp1, tp2: payload.tp2 }} />
      </Panel>
      <Panel title="Bull / Bear / Risks">
        <KeyValue payload={{ bull_case: payload.bull_case, bear_case: payload.bear_case, key_risks: payload.key_risks }} />
      </Panel>
      <Panel title="Portfolio Context">
        <KeyValue payload={{ portfolio_context: payload.portfolio_context, journal_history: payload.journal_history }} />
      </Panel>
    </div>
  );
}

function KeyValue({ payload }: { payload: Record<string, unknown> }) {
  return (
    <div className="kv">
      {Object.entries(payload).map(([key, value]) => (
        <div key={key}>
          <span>{labelize(key)}</span>
          <strong>{cell(value)}</strong>
        </div>
      ))}
    </div>
  );
}

function Chip({ tone, children }: { tone: 'good' | 'bad' | 'warn' | 'neutral'; children: React.ReactNode }) {
  return <span className={`chip ${tone}`}>{children}</span>;
}

function missingEnvVars(rows: DataSourceRow[]) {
  return Array.from(new Set(rows.flatMap((row) => row.missing_env_vars_list))).sort();
}

function compactDate(value?: string) {
  if (!value || value === 'unavailable') return 'Unavailable';
  return value.replace('T', ' ').replace('Z', '').slice(0, 16);
}

function money(value: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value || 0);
}

function labelize(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function cell(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => (typeof item === 'object' ? JSON.stringify(item) : String(item))).join(' | ');
  if (typeof value === 'object' && value !== null) return JSON.stringify(value);
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value ?? '');
}
