import { FormEvent, useState } from 'react';
import type React from 'react';
import {
  Activity,
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
  Sparkles,
  Wallet,
} from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Line, LineChart as ReLineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import {
  api,
  AlertRow,
  DataSourceRow,
  HealthPayload,
  PortfolioPayload,
  PredictionRow,
  ProofReport,
  ReplayPayload,
  ResearchPayload,
  ScannerRow,
  UnifiedDecision,
  UniverseItem,
  UniversesPayload,
  ValidationContext,
  getApiBaseUrl,
  isApiError,
} from './api';
import { useAsync } from './hooks';

type PageKey =
  | 'Home'
  | 'Stock Picker'
  | 'Core Investing'
  | 'Velocity Scanner'
  | 'Deep Research'
  | 'Replay Lab'
  | 'Outlier Case Study'
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
  { key: 'Core Investing', icon: LineChart },
  { key: 'Velocity Scanner', icon: Activity },
  { key: 'Deep Research', icon: BookOpen },
  { key: 'Replay Lab', icon: LineChart },
  { key: 'Outlier Case Study', icon: Sparkles },
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
  'No key / free': ['No key / free'],
  'Free key': ['Free key'],
  'Paid / optional': ['Paid / optional'],
  AI: ['AI'],
  'Future brokerage': ['Future brokerage'],
};

const DEFAULT_UNIVERSES: UniverseItem[] = [
  { label: 'Active Core Investing', path: 'config/active_core_investing_universe.txt', description: 'Quality compounders and practical portfolio research names.', available: true },
  { label: 'Active Outliers', path: 'config/active_outlier_universe.txt', description: 'Current high-growth and high-momentum research names.', available: true },
  { label: 'Active Velocity', path: 'config/active_velocity_universe.txt', description: 'High-volume / velocity monitor names.', available: true },
  { label: 'Mega Cap', path: 'config/mega_cap_universe.txt', description: 'Large-cap leadership basket.', available: true },
  { label: 'Momentum', path: 'config/momentum_universe.txt', description: 'Momentum-leaning universe.', available: true },
  { label: 'Famous Case Studies', path: 'config/famous_outlier_case_studies.txt', description: 'Historical validation names only.', available: true },
];

const DEFAULT_UNIVERSE_WARNING = 'Famous Case Studies are for historical validation, not active monitoring.';

type ScanState = {
  generated_at?: string;
  results?: ScannerRow[];
  decisions?: UnifiedDecision[];
  validation_context?: ValidationContext;
};

export function App() {
  const [page, setPage] = useState<PageKey>('Home');
  const health = useAsync(api.health, []);
  const portfolio = useAsync(api.portfolio, []);
  const latest = useAsync(api.latestReport, []);

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
        <TopBar
          health={health.data}
          healthError={health.error}
          portfolio={portfolio.data}
          latest={latest.data}
          onRetryHealth={health.retry}
        />
        <section className="workspace">
          {page === 'Home' && <HomePage setPage={setPage} />}
          {page === 'Stock Picker' && <StockPicker />}
          {page === 'Core Investing' && <CoreInvesting />}
          {page === 'Velocity Scanner' && <VelocityScanner />}
          {page === 'Deep Research' && <DeepResearch />}
          {page === 'Replay Lab' && <ReplayLab />}
          {page === 'Outlier Case Study' && <OutlierCaseStudy />}
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

function TopBar({
  health,
  healthError,
  portfolio,
  latest,
  onRetryHealth,
}: {
  health: HealthPayload | null;
  healthError: Error | null;
  portfolio: PortfolioPayload | null;
  latest: { generated_at?: string; provider?: string; validation_context?: ValidationContext } | null;
  onRetryHealth: () => void;
}) {
  const backendStatus = describeBackendStatus(healthError);
  return (
    <header className="topbar">
      <div>
        <span className="eyebrow">Decision Cockpit</span>
        <strong>{health?.mode ?? 'waiting for backend'}</strong>
      </div>
      <Status label="Backend" value={backendStatus.label} tone={backendStatus.tone} />
      <Status label="API base" value={getApiBaseUrl()} />
      <Status label="Provider" value={latest?.provider ?? health?.provider ?? 'unavailable'} />
      <Status label="Last scan" value={compactDate(latest?.generated_at ?? health?.last_scan_time)} />
      <Status label="Data sources" value={`${health?.data_source_health.optional_ready ?? 0} ready`} tone="good" />
      <Status label="AI" value={health?.ai.any_configured ? 'Configured' : 'Missing'} tone={health?.ai.any_configured ? 'good' : 'warn'} />
      <Status label="Portfolio" value={money(Number(portfolio?.summary?.total_market_value ?? health?.portfolio_value ?? 0))} />
      <Status label="Alerts" value={String(health?.alert_count ?? 0)} tone={health?.alert_count ? 'warn' : 'good'} />
      {healthError && <button className="ghost topbar-retry" onClick={onRetryHealth}><RefreshCcw size={14} /> Retry backend</button>}
    </header>
  );
}

function HomePage({ setPage }: { setPage: (page: PageKey) => void }) {
  const latest = useAsync(api.latestReport, []);
  const portfolio = useAsync(api.portfolio, []);
  const sources = useAsync(api.dataSources, []);
  const universes = useAsync(api.universes, []);
  const decisions = latest.data?.decisions ?? [];
  const validation = latest.data?.validation_context;
  const buyResearch = decisions.filter((row) => row.primary_action === 'Research / Buy Candidate').slice(0, 6);
  const watch = decisions.filter((row) => row.primary_action === 'Watch').slice(0, 6);
  const holdAdd = decisions.filter((row) => ['Hold', 'Add'].includes(String(row.primary_action))).slice(0, 6);
  const trimSell = decisions.filter((row) => ['Trim', 'Sell / Exit Candidate', 'Watch Closely'].includes(String(row.primary_action))).slice(0, 6);
  const avoid = decisions.filter((row) => ['Avoid', 'Data Insufficient'].includes(String(row.primary_action))).slice(0, 6);
  const tpBoard = decisions.filter((row) => row.entry_zone && row.entry_zone !== 'unavailable').slice(0, 10);

  return (
    <Page title="Home" subtitle="One-screen daily decision cockpit for what to research, watch, hold, add to, trim, sell, and avoid.">
      {latest.error && <ApiErrorPanel error={latest.error} onRetry={latest.retry} />}
      {sources.error && <ApiErrorPanel error={sources.error} onRetry={sources.retry} compact />}
      <div className="metric-grid">
        <Metric label="Buy / Research" value={String(buyResearch.length)} sub="Highest-priority current candidates" />
        <Metric label="Watch" value={String(watch.length)} sub="Interesting, not actionable yet" />
        <Metric label="Hold / Add / Trim" value={String(holdAdd.length + trimSell.length)} sub="Portfolio-aware labels when available" />
        <Metric label="Data sources" value={`${sources.data?.summary.optional_ready ?? 0} ready`} sub="Configured optional providers" />
      </div>
      <div className="grid two">
        <Panel title="Market / Data Health">
          <DecisionCard
            label={String(latest.data?.market_regime?.regime ?? 'Unavailable')}
            status={String(latest.data?.market_regime?.provider ?? 'No market regime loaded')}
            risk={String(avoid.length ? 55 : 30)}
            details={listText((latest.data?.validation_context?.messages as string[] | undefined) ?? ['Run a fresh scan, then use Deep Research only on the top names.'])}
          />
          <div className="metric-grid compact">
            <Metric label="Last scan" value={compactDate(latest.data?.generated_at)} sub={latest.data?.provider ?? 'unavailable'} />
            <Metric label="Portfolio loaded" value={(portfolio.data?.positions?.length ?? 0) ? 'Yes' : 'No'} sub={(portfolio.data?.positions?.length ?? 0) ? 'Portfolio-aware labels active' : 'Import or add positions for hold/add/trim/sell labels'} />
            <Metric label="Universe defaults" value={String((universes.data?.home_defaults ?? []).length)} sub="Home uses active universes only" />
          </div>
          <div className="action-strip">
            <button className="primary" onClick={() => setPage('Stock Picker')}><RefreshCcw size={16} /> Run Scan</button>
            <button className="secondary" onClick={() => setPage('Deep Research')}><Search size={16} /> Deep Research</button>
            <button className="secondary" onClick={() => setPage('Validation Lab')}><FlaskConical size={16} /> Validation Context</button>
          </div>
        </Panel>
        <Panel title="Active Universes">
          <UniverseSummary payload={universes.data} />
        </Panel>
      </div>
      {decisions.length ? (
        <>
          <div className="grid two">
            <Panel title="Buy / Research Candidates">
              <DecisionList rows={buyResearch} empty="Run a fresh active-universe scan to fill this lane." />
            </Panel>
            <Panel title="Watchlist / Wait">
              <DecisionList rows={watch} empty="No watch-only names right now." />
            </Panel>
            <Panel title="Hold / Add">
              {portfolio.data?.positions?.length ? (
                <DecisionList rows={holdAdd} empty="No hold/add names right now." />
              ) : (
                <EmptyState title="No portfolio loaded" action="Open Portfolio" onAction={() => setPage('Portfolio')}>
                  Import a portfolio or add positions manually to activate Hold / Add / Trim / Sell decisions.
                </EmptyState>
              )}
            </Panel>
            <Panel title="Trim / Sell / Watch Closely">
              {portfolio.data?.positions?.length ? (
                <DecisionList rows={trimSell} empty="No trim or sell candidates right now." />
              ) : (
                <EmptyState title="Portfolio decisions need holdings" action="Open Portfolio" onAction={() => setPage('Portfolio')}>
                  Portfolio-aware actions stay empty until a portfolio is loaded.
                </EmptyState>
              )}
            </Panel>
            <Panel title="Avoid / Risk">
              <DecisionList rows={avoid} empty="No avoid candidates right now." />
            </Panel>
            <Panel title="Validation Context">
              <ValidationContextCard context={validation} />
            </Panel>
          </div>
          <Panel title="Quick TP / SL Board">
            <DecisionBoard rows={tpBoard} />
          </Panel>
        </>
      ) : (
        <EmptyState title="No scan loaded" action="Open scanner" onAction={() => setPage('Stock Picker')}>
          Home becomes the daily cockpit after you run a scan from an active universe.
        </EmptyState>
      )}
    </Page>
  );
}

function StockPicker() {
  const universes = useAsync(api.universes, []);
  const [scan, setScan] = useState<ScanState | null>(null);
  const [tab, setTab] = useState<'All Decisions' | 'Buy / Research' | 'Watch' | 'Hold / Add' | 'Trim / Sell' | 'Avoid' | 'Core Investing' | 'Outliers' | 'Velocity'>('All Decisions');
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const payload = await api.scan({
        provider: form.get('provider'),
        mode: form.get('mode'),
        universe_path: form.get('universe_path'),
        as_of_date: form.get('as_of_date'),
      });
      setScan(payload);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Scan failed'));
    } finally {
      setLoading(false);
    }
  }

  const rows = filterDecisionRows(scan?.decisions ?? [], tab);

  return (
    <Page title="Stock Picker" subtitle="Run one scan, then filter decisions by action instead of jumping across scattered tabs.">
      {universes.error && <ApiErrorPanel error={universes.error} onRetry={universes.retry} compact />}
      <form className="toolbar" onSubmit={submit}>
        <Select name="provider" label="Provider" options={['sample', 'local', 'real']} />
        <Select name="mode" label="Mode" options={['outliers', 'velocity', 'investing']} />
        <UniverseField name="universe_path" label="Universe" defaultValue="config/active_outlier_universe.txt" universes={universes.data} />
        <Field name="as_of_date" label="As of" defaultValue="2026-04-24" />
        <button className="primary" disabled={loading}>
          <RefreshCcw size={16} /> {loading ? 'Running' : 'Run Scan'}
        </button>
      </form>
      <Notice tone="neutral">{universes.data?.warning ?? DEFAULT_UNIVERSE_WARNING}</Notice>
      {error && <ApiErrorPanel error={error} onRetry={() => setError(null)} />}
      {loading && <Notice tone="neutral">Running the scanner can take a bit with the real provider. Results will appear here without changing your data.</Notice>}
      {scan?.decisions?.length ? (
        <div className="tabs">
          {(['All Decisions', 'Buy / Research', 'Watch', 'Hold / Add', 'Trim / Sell', 'Avoid', 'Core Investing', 'Outliers', 'Velocity'] as const).map((item) => (
            <button className={tab === item ? 'active' : ''} key={item} onClick={() => setTab(item)}>{item}</button>
          ))}
        </div>
      ) : null}
      {loading ? (
        <SkeletonGrid />
      ) : scan?.decisions?.length ? (
        <div className="grid">
          <Panel title={tab}>
            <DecisionList rows={rows.slice(0, 10)} empty="No names match this tab right now." />
          </Panel>
          <Panel title="Why This Lane Is Actionable">
            <DecisionSummary rows={rows} />
          </Panel>
          <Panel title="Decision Table">
            <DecisionBoard rows={rows} />
          </Panel>
          <Panel title="Raw Scanner Table">
            <ScannerTable rows={filterScannerRows(scan.results ?? [], tab)} />
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

function CoreInvesting() {
  const universes = useAsync(api.universes, []);
  const latestReplay = useAsync(api.latestInvestingReplay, []);
  const latestProof = useAsync(api.latestInvestingProofReport, []);
  const [scan, setScan] = useState<ScannerRow[]>([]);
  const [replay, setReplay] = useState<ReplayPayload | null>(null);
  const [proof, setProof] = useState<ProofReport | null>(null);
  const [loading, setLoading] = useState('');
  const [error, setError] = useState<Error | null>(null);

  async function runScan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading('scan');
    setError(null);
    try {
      const payload = await api.scan({
        provider: form.get('provider'),
        mode: 'investing',
        universe_path: form.get('universe_path'),
        as_of_date: form.get('as_of_date'),
      });
      setScan(payload.results);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Core investing scan failed'));
    } finally {
      setLoading('');
    }
  }

  async function runReplay() {
    setLoading('replay');
    setError(null);
    try {
      setReplay(await api.runInvestingReplay({
        provider: 'sample',
        universe: 'config/mega_cap_universe.txt',
        start_date: '2020-01-01',
        end_date: '2026-04-24',
        frequency: 'monthly',
        horizons: '20,60,120,252',
        random_baseline: true,
      }));
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Investing replay failed'));
    } finally {
      setLoading('');
    }
  }

  async function runProof() {
    setLoading('proof');
    setError(null);
    try {
      setProof(await api.runInvestingProofReport({
        provider: 'sample',
        universe: 'config/mega_cap_universe.txt',
        start_date: '2020-01-01',
        end_date: '2026-04-24',
        baseline: 'SPY,QQQ',
        random_baseline: true,
      }));
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Investing proof report failed'));
    } finally {
      setLoading('');
    }
  }

  const rows = scan.length ? scan : ((latestReplay.data?.replay_scans?.[0]?.top_investing_candidates as ScannerRow[] | undefined) ?? []);
  const replayReport = replay ?? latestReplay.data;
  const proofReport = proof ?? latestProof.data;
  return (
    <Page title="Core Investing" subtitle="Regular buy, watch, hold, add, trim, and avoid research separated from outlier and velocity lanes.">
      <form className="toolbar" onSubmit={runScan}>
        <Select name="provider" label="Provider" options={['sample', 'local', 'real']} />
        <UniverseField name="universe_path" label="Universe" defaultValue="config/active_core_investing_universe.txt" universes={universes.data} />
        <Field name="as_of_date" label="As of" defaultValue="2026-04-24" />
        <button className="primary" disabled={loading === 'scan'}><RefreshCcw size={16} /> {loading === 'scan' ? 'Scanning' : 'Run Core Scan'}</button>
      </form>
      {error && <ApiErrorPanel error={error} onRetry={() => setError(null)} />}
      <div className="metric-grid">
        <Metric label="Candidates" value={String(rows.filter((row) => Number(row.regular_investing_score ?? 0) >= 60).length)} sub="Regular score >= 60" />
        <Metric label="Add / Buy" value={String(rows.filter((row) => String(row.investing_action_label).includes('Add') || String(row.investing_action_label).includes('Buy')).length)} sub="Research candidates only" />
        <Metric label="Trim / Exit" value={String(rows.filter((row) => String(row.investing_action_label).includes('Trim') || String(row.investing_action_label).includes('Exit')).length)} sub="Portfolio review prompts" />
        <Metric label="Warnings" value={String(rows.filter((row) => row.value_trap_warning && row.value_trap_warning !== 'No value-trap warning.').length)} sub="Value trap / broken thesis" />
      </div>
      <div className="grid two">
        <Panel title="Long-Term Candidates">
          <CoreInvestingCards rows={rows.filter((row) => ['Long-Term Compounder', 'Profitable Growth'].includes(String(row.investing_style))).slice(0, 6)} />
        </Panel>
        <Panel title="Quality Growth">
          <CoreInvestingCards rows={rows.filter((row) => ['Quality Growth Leader', 'Profitable Growth'].includes(String(row.investing_style))).slice(0, 6)} />
        </Panel>
        <Panel title="Strong Holds">
          <CoreInvestingCards rows={rows.filter((row) => row.investing_action_label === 'Hold' || row.investing_style === 'Strong Hold').slice(0, 6)} />
        </Panel>
        <Panel title="Add Candidates">
          <CoreInvestingCards rows={rows.filter((row) => String(row.investing_action_label).includes('Add') || row.investing_action_label === 'Buy Candidate').slice(0, 6)} />
        </Panel>
        <Panel title="Trim / Exit Candidates">
          <CoreInvestingCards rows={rows.filter((row) => String(row.investing_action_label).includes('Trim') || String(row.investing_action_label).includes('Exit')).slice(0, 6)} />
        </Panel>
        <Panel title="Value Trap / Broken Thesis Warnings">
          <CoreInvestingCards rows={rows.filter((row) => row.value_trap_warning && row.value_trap_warning !== 'No value-trap warning.').slice(0, 6)} />
        </Panel>
        <Panel title="Portfolio Fit">
          <DataTable rows={rows as Record<string, unknown>[]} columns={['ticker', 'regular_investing_score', 'investing_action_label', 'investing_style', 'investing_risk', 'thesis_quality', 'investing_data_quality']} />
        </Panel>
        <Panel title="Regular Investing Replay Results">
          <div className="action-strip">
            <button className="secondary" onClick={runReplay} disabled={loading === 'replay'}>{loading === 'replay' ? 'Running' : 'Run Investing Replay'}</button>
          </div>
          <ReplaySummary report={replayReport} />
        </Panel>
        <Panel title="Investing Proof Report">
          <div className="action-strip">
            <button className="secondary" onClick={runProof} disabled={loading === 'proof'}>{loading === 'proof' ? 'Running' : 'Run Investing Evidence'}</button>
          </div>
          <ProofReportView report={proofReport} />
        </Panel>
      </div>
    </Page>
  );
}

function VelocityScanner() {
  const universes = useAsync(api.universes, []);
  const [payload, setPayload] = useState<ScannerRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading(true);
    setError(null);
    try {
      const result = await api.scan({
        provider: form.get('provider'),
        mode: 'velocity',
        universe_path: form.get('universe_path'),
        as_of_date: form.get('as_of_date'),
      });
      setPayload(result.results);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Velocity scan failed'));
    } finally {
      setLoading(false);
    }
  }

  const candidates = payload.filter((row) => row.velocity_type !== 'No High-Velocity Trigger');
  return (
    <Page title="Velocity Scanner" subtitle="High-volume and quick-moving research candidates. No day-trading, options, execution, or buy-now language.">
      <form className="toolbar" onSubmit={submit}>
        <Select name="provider" label="Provider" options={['sample', 'local', 'real']} />
        <UniverseField name="universe_path" label="Universe" defaultValue="config/active_velocity_universe.txt" universes={universes.data} />
        <Field name="as_of_date" label="As of" defaultValue="2026-04-24" />
        <button className="primary" disabled={loading}><Activity size={16} /> {loading ? 'Scanning' : 'Run Velocity Scan'}</button>
      </form>
      {error && <ApiErrorPanel error={error} onRetry={() => setError(null)} />}
      <div className="metric-grid">
        <Metric label="Velocity names" value={String(candidates.length)} sub="Triggered or watchlisted" />
        <Metric label="Avoid spikes" value={String(payload.filter((row) => String(row.velocity_type).includes('Avoid')).length)} sub="Failed spike / pump risk" />
        <Metric label="Top score" value={String(Math.max(0, ...payload.map((row) => Number(row.velocity_score ?? 0))))} sub="Deterministic velocity score" />
        <Metric label="Source" value="Python" sub="React only presents results" />
      </div>
      {loading ? <SkeletonGrid /> : (
        <div className="grid">
          <Panel title="Velocity Score Cards">
            <div className="candidate-list">
              {candidates.slice(0, 12).map((row) => <VelocityCard row={row} key={row.ticker} />)}
            </div>
          </Panel>
          <Panel title="Velocity Table">
            <DataTable rows={payload as Record<string, unknown>[]} columns={['ticker', 'velocity_score', 'velocity_type', 'velocity_risk', 'quick_trade_watch_label', 'expected_horizon', 'trigger_reason', 'chase_warning']} />
          </Panel>
        </div>
      )}
    </Page>
  );
}

function ReplayLab() {
  const latest = useAsync(() => api.latestReplay('outliers'), []);
  const [payload, setPayload] = useState<ReplayPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading(true);
    setError(null);
    try {
      const result = await api.runReplay({
        provider: form.get('provider'),
        universe: form.get('universe'),
        start_date: form.get('start_date'),
        end_date: form.get('end_date'),
        frequency: form.get('frequency'),
        mode: form.get('mode'),
        top_n: Number(form.get('top_n') || 20),
      });
      setPayload(result);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Replay failed'));
    } finally {
      setLoading(false);
    }
  }

  const report = payload ?? latest.data;
  return (
    <Page title="Replay Lab" subtitle="No-lookahead historical replay with SPY/QQQ and random baseline comparisons.">
      <form className="toolbar replay-toolbar" onSubmit={submit}>
        <Select name="provider" label="Provider" options={['sample', 'local', 'real']} />
        <Select name="mode" label="Mode" options={['outliers', 'velocity']} />
        <Select name="frequency" label="Frequency" options={['weekly', 'daily']} />
        <Field name="universe" label="Universe" defaultValue="config/famous_outlier_case_studies.txt" />
        <Field name="start_date" label="Start" defaultValue="2020-01-01" />
        <Field name="end_date" label="End" defaultValue="2026-04-24" />
        <Field name="top_n" label="Top N" defaultValue="20" />
        <button className="primary" disabled={loading}><RefreshCcw size={16} /> {loading ? 'Running' : 'Run Replay'}</button>
      </form>
      {error && <ApiErrorPanel error={error} onRetry={() => setError(null)} />}
      <ReplaySummary report={report} />
    </Page>
  );
}

function OutlierCaseStudy() {
  const [study, setStudy] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading(true);
    setError(null);
    try {
      setStudy(await api.runOutlierStudy({
        provider: form.get('provider'),
        ticker: form.get('ticker'),
        start_date: form.get('start_date'),
        end_date: form.get('end_date'),
        mode: form.get('mode'),
      }));
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Case study failed'));
    } finally {
      setLoading(false);
    }
  }
  const timeline = (study?.score_progression as Record<string, unknown>[] | undefined) ?? [];
  return (
    <Page title="Outlier Case Study" subtitle="Replay famous moves and judge caught, late, missed, or inconclusive with point-in-time limits visible.">
      <form className="toolbar" onSubmit={submit}>
        <Select name="provider" label="Provider" options={['sample', 'local', 'real']} />
        <Select name="mode" label="Mode" options={['outliers', 'velocity']} />
        <Field name="ticker" label="Ticker" defaultValue="GME" />
        <Field name="start_date" label="Start" defaultValue="2020-08-01" />
        <Field name="end_date" label="End" defaultValue="2021-02-15" />
        <button className="primary" disabled={loading}><Sparkles size={16} /> {loading ? 'Running' : 'Run Study'}</button>
      </form>
      <Notice tone="warn">{DEFAULT_UNIVERSE_WARNING}</Notice>
      {error && <ApiErrorPanel error={error} onRetry={() => setError(null)} />}
      {study && (
        <div className="grid">
          <div className="metric-grid">
            <Metric label="Verdict" value={String(study.did_it_catch_move ?? 'n/a')} sub={String(study.was_it_early_or_late ?? 'Timing unavailable')} />
            <Metric label="First trigger" value={String(study.first_trigger_date ?? 'n/a')} sub={String(study.first_trigger_type ?? '')} />
            <Metric label="Max score" value={String(study.max_outlier_score ?? 'n/a')} sub={String(study.date_of_max_score ?? '')} />
            <Metric label="Forward MFE" value={String(study.max_forward_return_after_trigger ?? 'n/a')} sub="After first trigger" />
          </div>
          <Panel title="Score And Price Progression">
            <DualLineChart data={timeline} />
          </Panel>
          <Panel title="Trigger Timeline">
            <DataTable rows={timeline.filter((row) => row.triggered) as Record<string, unknown>[]} columns={['date', 'price', 'outlier_score', 'velocity_score', 'status_label', 'outlier_type', 'velocity_type', 'relative_volume']} />
          </Panel>
          <Panel title="Narrative">
            <Notice tone="neutral">{String(study.narrative ?? study.point_in_time_limitations ?? '')}</Notice>
          </Panel>
        </div>
      )}
    </Page>
  );
}

function DeepResearch() {
  const [research, setResearch] = useState<ResearchPayload | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    setLoading(true);
    try {
      setResearch(await api.deepResearch({ ticker: form.get('ticker'), provider: form.get('provider') }));
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Deep research failed'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Page title="Deep Research" subtitle="Single-stock deterministic thesis, risks, levels, and portfolio context.">
      <form className="toolbar" onSubmit={submit}>
        <Field name="ticker" label="Ticker" defaultValue="NVDA" />
        <Select name="provider" label="Provider" options={['sample', 'local', 'real']} />
        <button className="primary" disabled={loading}><Search size={16} /> {loading ? 'Researching' : 'Research'}</button>
      </form>
      {error && <ApiErrorPanel error={error} onRetry={() => setError(null)} />}
      {loading && <SkeletonGrid />}
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
      <DataTable rows={positions} columns={['ticker', 'core_investing_decision', 'regular_investing_score', 'investing_style', 'review_priority', 'reason_to_hold', 'reason_to_add', 'reason_to_trim', 'reason_to_exit', 'concentration_warning', 'valuation_or_overextension_warning', 'broken_trend_warning', 'next_review_trigger']} />
    </Page>
  );
}

function AICommittee() {
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    setLoading(true);
    try {
      setPayload(await api.aiCommittee({ ticker: form.get('ticker'), mode: form.get('mode'), provider: form.get('provider') }));
    } catch (err) {
      setError(err instanceof Error ? err : new Error('AI committee failed'));
    } finally {
      setLoading(false);
    }
  }
  const committee = payload?.committee as Record<string, unknown> | undefined;
  const combined = payload?.combined as Record<string, unknown> | undefined;
  return (
    <Page title="AI Committee" subtitle="Rule-first committee view. AI is shown beside deterministic rules and cannot replace them.">
      <form className="toolbar" onSubmit={submit}>
        <Field name="ticker" label="Ticker" defaultValue="NVDA" />
        <Select name="provider" label="Data Provider" options={['sample', 'real', 'local']} />
        <Select name="mode" label="Mode" options={['No AI', 'Mock AI for testing', 'OpenAI only', 'Gemini only']} />
        <button className="primary" disabled={loading}><Brain size={16} /> {loading ? 'Running' : 'Run Committee'}</button>
      </form>
      {error && <ApiErrorPanel error={error} onRetry={() => setError(null)} />}
      {loading && <SkeletonLine />}
      {committee && (
        <div className="grid two">
          <Panel title="Combined Recommendation">
            <KeyValue payload={combined ?? {}} />
          </Panel>
          <Panel title="AI Guardrails">
            <div className="metric-grid compact">
              <Metric label="Output quality" value={String(committee.ai_output_quality_score ?? 'n/a')} sub="100 is cleanest" />
              <Metric label="Grounding" value={String(committee.evidence_grounding_score ?? 'n/a')} sub="Evidence discipline" />
              <Metric label="Unsupported claims" value={committee.unsupported_claims_detected ? 'Flagged' : 'Clear'} sub="Validator result" />
            </div>
            <SignalStack row={{ warnings: committee.ai_guardrail_warnings as string[] } as ScannerRow} />
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
  const signalAudit = useAsync(api.signalAuditLatest, []);
  const proof = useAsync(api.latestProofReport, []);
  const investingReplay = useAsync(api.latestInvestingReplay, []);
  const portfolioReplay = useAsync(api.latestPortfolioReplay, []);
  const investingProof = useAsync(api.latestInvestingProofReport, []);
  const [auditLoading, setAuditLoading] = useState(false);
  const [proofLoading, setProofLoading] = useState(false);
  const [investingLoading, setInvestingLoading] = useState('');
  const [updateLoading, setUpdateLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function runAudit() {
    setAuditLoading(true);
    try {
      signalAudit.setData(await api.runSignalAudit({ reports_dir: 'reports/scans', baseline: 'SPY,QQQ', random_baseline: true }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Signal audit failed'));
    } finally {
      setAuditLoading(false);
    }
  }

  async function updateOutcomes() {
    setUpdateLoading(true);
    try {
      const payload = await api.updatePredictions({ provider: 'real' });
      summary.setData(payload.summary as Record<string, unknown>);
      predictions.setData(payload.predictions as PredictionRow[]);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Prediction outcome update failed'));
    } finally {
      setUpdateLoading(false);
    }
  }

  async function runProof() {
    setProofLoading(true);
    try {
      proof.setData(await api.runProofReport({
        provider: 'sample',
        universe: 'config/active_outlier_universe.txt',
        start_date: '2020-01-01',
        end_date: '2026-04-24',
        include_famous_outliers: true,
        include_velocity: true,
        baseline: 'SPY,QQQ',
        random_baseline: true,
      }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Proof report failed'));
    } finally {
      setProofLoading(false);
    }
  }

  async function runInvestingWorkflow(kind: 'investing-replay' | 'portfolio-replay' | 'investing-proof') {
    setInvestingLoading(kind);
    try {
      if (kind === 'investing-replay') {
        investingReplay.setData(await api.runInvestingReplay({ provider: 'sample', universe: 'config/mega_cap_universe.txt', start_date: '2020-01-01', end_date: '2026-04-24', frequency: 'monthly', horizons: '20,60,120,252', random_baseline: true }));
      } else if (kind === 'portfolio-replay') {
        portfolioReplay.setData(await api.runPortfolioReplay({ provider: 'sample', universe: 'config/mega_cap_universe.txt', start_date: '2020-01-01', end_date: '2026-04-24', frequency: 'monthly' }));
      } else {
        investingProof.setData(await api.runInvestingProofReport({ provider: 'sample', universe: 'config/mega_cap_universe.txt', start_date: '2020-01-01', end_date: '2026-04-24', baseline: 'SPY,QQQ', random_baseline: true }));
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Investing validation workflow failed'));
    } finally {
      setInvestingLoading('');
    }
  }

  const due = (summary.data?.recent_predictions_needing_update as Record<string, unknown>[] | undefined) ?? [];
  const hitLevels = (summary.data?.predictions_with_hit_levels as Record<string, unknown>[] | undefined) ?? [];
  const missingOutcomes = (summary.data?.predictions_with_missing_outcome as Record<string, unknown>[] | undefined) ?? [];

  return (
    <Page title="Validation Lab" subtitle="Paper predictions, outcome updates, and famous outlier case studies.">
      {(error || summary.error || predictions.error || signalAudit.error || proof.error || investingReplay.error || portfolioReplay.error || investingProof.error) && (
        <ApiErrorPanel error={error ?? summary.error ?? predictions.error ?? signalAudit.error ?? proof.error ?? investingReplay.error ?? portfolioReplay.error ?? investingProof.error ?? new Error('Validation request failed')} onRetry={() => setError(null)} />
      )}
      <div className="metric-grid">
        <Metric label="Open" value={String((summary.data?.open_predictions as unknown[] | undefined)?.length ?? 0)} sub="Awaiting outcome" />
        <Metric label="Closed" value={String((summary.data?.closed_predictions as unknown[] | undefined)?.length ?? 0)} sub="Measured signals" />
        <Metric label="Due" value={String(due.length)} sub="Needs 1D/5D/10D/20D check" />
        <Metric label="Hit levels" value={String(hitLevels.length)} sub="TP or invalidation touched" />
      </div>
      <Panel title="Paper Tracking Queue">
        <div className="action-strip">
          <button className="secondary" onClick={updateOutcomes} disabled={updateLoading}>{updateLoading ? 'Updating' : 'Update Outcomes With Real Provider'}</button>
        </div>
        <DataTable rows={due} columns={['prediction_id', 'ticker', 'next_review_date', 'outcome_label', 'return_1d', 'return_5d', 'return_10d', 'return_20d']} />
        {missingOutcomes.length > 0 && <Notice tone="warn">{missingOutcomes.length} prediction(s) still need a clean outcome.</Notice>}
      </Panel>
      <Panel title="Signal Quality">
        <div className="metric-grid compact">
          <ValidationMetricCard label="Strategy vs baseline" value={signalAudit.data?.available ? 'Measured' : 'Not run'} />
          <ValidationMetricCard label="Random baseline" value={signalAudit.data?.available ? 'Included' : 'Pending'} />
          <ValidationMetricCard label="Evidence state" value={String(signalAudit.data?.conclusion ?? 'Not enough evidence yet')} />
        </div>
        <Notice tone="neutral">This audit measures signals against baselines and random samples. It does not prove profitability or prediction accuracy.</Notice>
        <button className="secondary" onClick={runAudit} disabled={auditLoading}>{auditLoading ? 'Running' : 'Run Signal Audit'}</button>
        <WorkflowReportView report={signalAudit.data} />
      </Panel>
      <Panel title="Proof Report">
        <div className="action-strip">
          <button className="secondary" onClick={runProof} disabled={proofLoading}>{proofLoading ? 'Running' : 'Run Evidence Report'}</button>
        </div>
        <ProofReportView report={proof.data} />
      </Panel>
      <Panel title="Core Investing Validation">
        <div className="action-strip">
          <button className="secondary" onClick={() => runInvestingWorkflow('investing-replay')} disabled={!!investingLoading}>{investingLoading === 'investing-replay' ? 'Running' : 'Investing Replay'}</button>
          <button className="secondary" onClick={() => runInvestingWorkflow('portfolio-replay')} disabled={!!investingLoading}>{investingLoading === 'portfolio-replay' ? 'Running' : 'Portfolio Replay'}</button>
          <button className="secondary" onClick={() => runInvestingWorkflow('investing-proof')} disabled={!!investingLoading}>{investingLoading === 'investing-proof' ? 'Running' : 'Investing Proof Report'}</button>
        </div>
        <Notice tone="neutral">Core Investing compares regular_investing_score against SPY, QQQ, random baseline, and equal-weight universe where available.</Notice>
        <ReplaySummary report={investingReplay.data} />
        <DataTable rows={((portfolioReplay.data?.summary?.decision_performance as Record<string, unknown>[] | undefined) ?? [])} columns={['core_investing_decision', 'sample_size', 'average', 'median', 'win_rate', 'false_positive_rate']} />
        <ProofReportView report={investingProof.data} />
      </Panel>
      <Panel title="Predictions">
        <DataTable rows={predictions.data ?? []} columns={['prediction_id', 'ticker', 'final_combined_recommendation', 'next_review_date', 'outcome_label', 'return_20d']} />
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
  const doctor = useAsync(api.doctorLatest, []);
  const readiness = useAsync(api.readinessLatest, []);
  const [message, setMessage] = useState('');
  const [error, setError] = useState<Error | null>(null);
  const [workflowLoading, setWorkflowLoading] = useState('');
  const rows = sources.data?.rows ?? [];

  async function createTemplate() {
    setError(null);
    try {
      const result = await api.createEnvTemplate();
      setMessage(result.message);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Could not create .env'));
    }
  }

  async function runWorkflow(kind: 'doctor' | 'doctor-live' | 'readiness' | 'readiness-openai' | 'readiness-gemini') {
    setWorkflowLoading(kind);
    setError(null);
    try {
      if (kind === 'doctor') {
        const report = await api.runDoctor({ live: false, ticker: 'NVDA' });
        doctor.setData(report);
      } else if (kind === 'doctor-live') {
        const report = await api.runDoctor({ live: true, ticker: 'NVDA' });
        doctor.setData(report);
      } else {
        const ai = kind === 'readiness-openai' ? 'openai' : kind === 'readiness-gemini' ? 'gemini' : 'mock';
        const report = await api.runReadiness({ provider: 'real', ai, tickers: 'NVDA,PLTR,MU,RDDT,SMCI,COIN,HOOD,ARM,CAVA,AAPL,MSFT,LLY,TSLA,AMD,AVGO' });
        readiness.setData(report);
      }
      setMessage('Workflow completed. Restart the backend only after changing .env values.');
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Workflow failed'));
    } finally {
      setWorkflowLoading('');
    }
  }

  async function updateLocalEnv(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const values: Record<string, string> = {};
    for (const [key, value] of form.entries()) {
      if (typeof value === 'string' && value.trim()) values[key] = value;
    }
    setError(null);
    try {
      const result = await api.updateLocalEnv(values);
      setMessage(result.message);
      event.currentTarget.reset();
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Could not update .env'));
    }
  }

  return (
    <Page title="Data Sources" subtitle="Provider readiness, missing keys, degraded capabilities, and local .env setup.">
      {message && <Notice tone="good">{message}</Notice>}
      {(error || sources.error || doctor.error || readiness.error) && (
        <ApiErrorPanel error={error ?? sources.error ?? doctor.error ?? readiness.error ?? new Error('Data source request failed')} onRetry={() => setError(null)} />
      )}
      <Panel title="Recommended Free-First Setup">
        <div className="setup-grid">
          <DataHealthCard ready={sources.data?.summary.optional_ready ?? 0} missing={sources.data?.summary.optional_missing ?? 0} requiredMissing={sources.data?.summary.required_missing ?? 0} />
          <div>
            <h3>Keys to add first</h3>
            <div className="pill-row">
              {['OPENAI_API_KEY', 'GEMINI_API_KEY', 'FINANCIAL_MODELING_PREP_API_KEY', 'FINNHUB_API_KEY', 'SEC_USER_AGENT'].map((key) => <ProviderBadge key={key}>{key}</ProviderBadge>)}
            </div>
            <p className="muted">yfinance, GDELT, manual catalysts, manual alternative data, and local portfolio CSV work without paid keys.</p>
          </div>
        </div>
      </Panel>
      <div className="grid two">
        <Panel title="How to Add Keys Locally">
          <ol className="steps">
            <li>Copy <code>.env.example</code> to <code>.env</code>.</li>
            <li>Fill only the providers you want, such as <code>OPENAI_API_KEY</code> or <code>GEMINI_API_KEY</code>.</li>
            <li>Restart the FastAPI backend.</li>
          </ol>
          <CommandSnippet text="python3 -m tradebruv doctor --live --ai openai --ticker NVDA" />
          <CommandSnippet text="python3 -m tradebruv readiness --universe config/active_outlier_universe.txt --provider real --tickers NVDA,PLTR,MU,RDDT,SMCI,COIN,HOOD,ARM,CAVA,AAPL,MSFT,LLY,TSLA,AMD,AVGO --ai mock" />
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
      <div className="grid two">
        <Panel title="Doctor / API Testing">
          <div className="action-strip">
            <button className="secondary" disabled={!!workflowLoading} onClick={() => runWorkflow('doctor')}>Run Doctor</button>
            <button className="secondary" disabled={!!workflowLoading} onClick={() => runWorkflow('doctor-live')}>Run Live Doctor</button>
          </div>
          {workflowLoading.startsWith('doctor') && <SkeletonLine />}
          <WorkflowReportView report={doctor.data} />
        </Panel>
        <Panel title="Readiness Workflow">
          <div className="action-strip">
            <button className="secondary" disabled={!!workflowLoading} onClick={() => runWorkflow('readiness')}>Run Readiness</button>
            <button className="secondary" disabled={!!workflowLoading} onClick={() => runWorkflow('readiness-openai')}>With OpenAI</button>
            <button className="secondary" disabled={!!workflowLoading} onClick={() => runWorkflow('readiness-gemini')}>With Gemini</button>
          </div>
          {workflowLoading.startsWith('readiness') && <SkeletonLine />}
          <WorkflowReportView report={readiness.data} />
        </Panel>
      </div>
      {Object.entries(GROUPS).map(([group, categories]) => (
        <Panel title={group} key={group}>
          <div className="provider-grid">
            {rows.filter((row) => categories.includes(row.tier ?? row.category)).sort((a, b) => (a.recommended_priority ?? 99) - (b.recommended_priority ?? 99)).map((row) => (
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
  const appStatus = useAsync(api.appStatusLatest, []);
  const [debug, setDebug] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  async function refreshStatus() {
    setStatusLoading(true);
    try {
      appStatus.setData(await api.runAppStatus());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('App status refresh failed'));
    } finally {
      setStatusLoading(false);
    }
  }
  return (
    <Page title="Reports" subtitle="Latest scan, archive index, daily summary, alerts, and optional debug payloads.">
      {(error || latest.error || archive.error || appStatus.error) && (
        <ApiErrorPanel error={error ?? latest.error ?? archive.error ?? appStatus.error ?? new Error('Report request failed')} onRetry={() => setError(null)} />
      )}
      <Panel title="App Status Report">
        <div className="action-strip">
          <button className="secondary" onClick={refreshStatus} disabled={statusLoading}>{statusLoading ? 'Writing' : 'Refresh App Status'}</button>
        </div>
        <MarkdownReport text={appStatus.data?.markdown ?? 'No app status report loaded yet.'} />
      </Panel>
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

function Status({ label, value, tone = 'neutral' }: { label: string; value: string; tone?: 'neutral' | 'good' | 'warn' | 'bad' }) {
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

function UniverseField({ name, label, defaultValue, universes }: { name: string; label: string; defaultValue: string; universes: UniversesPayload | null }) {
  const items = universes?.items ?? DEFAULT_UNIVERSES;
  return (
    <label className="field">
      <span>{label}</span>
      <input name={name} defaultValue={defaultValue} list={`${name}-options`} />
      <datalist id={`${name}-options`}>
        {items.map((item) => <option key={item.path} value={item.path}>{item.label}</option>)}
      </datalist>
    </label>
  );
}

function Notice({ tone, children }: { tone: 'good' | 'bad' | 'warn' | 'neutral'; children: React.ReactNode }) {
  return <div className={`notice ${tone}`}>{children}</div>;
}

function ApiErrorPanel({ error, onRetry, compact = false }: { error: Error; onRetry: () => void; compact?: boolean }) {
  if (!isApiError(error)) {
    return (
      <Notice tone="bad">
        {error.message}
        <button className="ghost" onClick={onRetry}>Retry</button>
      </Notice>
    );
  }
  return (
    <div className={compact ? 'api-error compact' : 'api-error'}>
      <div className="provider-title">
        <strong>{describeBackendStatus(error).label}</strong>
        <button className="ghost" onClick={onRetry}><RefreshCcw size={14} /> Retry</button>
      </div>
      <div className="kv">
        <div><span>Endpoint attempted</span><strong>{error.endpoint}</strong></div>
        <div><span>API base URL</span><strong>{error.apiBaseUrl}</strong></div>
        <div><span>Cause</span><strong>{error.causeText}</strong></div>
        <div><span>Suggested fix</span><strong>{error.suggestedFix}</strong></div>
      </div>
      {error.backendBody ? <pre className="debug-json">{JSON.stringify(error.backendBody, null, 2)}</pre> : null}
    </div>
  );
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
      <ProviderBadge>{row.tier ?? row.category}</ProviderBadge>
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
      {row.quota_notes && <p className="muted">{row.quota_notes}</p>}
      <a href={row.url} target="_blank" rel="noreferrer">Docs</a>
    </article>
  );
}

function CoreInvestingCards({ rows }: { rows: ScannerRow[] }) {
  if (!rows.length) return <p className="muted">No names in this section yet.</p>;
  return (
    <div className="candidate-list">
      {rows.map((row) => (
        <article className="candidate-card" key={row.ticker}>
          <div className="provider-title">
            <div>
              <h3>{row.ticker}</h3>
              <span>{row.investing_style ?? 'Core investing'}</span>
            </div>
            <ScoreRing value={Number(row.regular_investing_score ?? 0)} label="Core" />
          </div>
          <div className="pill-row">
            <Chip tone={String(row.investing_action_label).includes('Avoid') || String(row.investing_action_label).includes('Exit') ? 'bad' : String(row.investing_action_label).includes('Watch') ? 'warn' : 'good'}>{row.investing_action_label ?? 'Data Insufficient'}</Chip>
            <Chip tone={row.investing_risk === 'High' ? 'warn' : 'neutral'}>{row.investing_risk ?? 'Risk n/a'}</Chip>
            <Chip tone="neutral">{row.investing_time_horizon ?? 'Horizon n/a'}</Chip>
          </div>
          <p>{row.investing_reason ?? 'No regular investing reason returned.'}</p>
          <PriceSanityBadge payload={row} />
          <KeyValue payload={{
            bear_case: row.investing_bear_case,
            invalidation: row.investing_invalidation,
            events_to_watch: row.investing_events_to_watch,
            value_trap_warning: row.value_trap_warning,
            thesis_quality: row.thesis_quality,
            data_quality: row.investing_data_quality,
          }} />
        </article>
      ))}
    </div>
  );
}

function ScannerTable({ rows }: { rows: ScannerRow[] }) {
  return <DataTable rows={rows} columns={['ticker', 'status_label', 'winner_score', 'outlier_score', 'risk_score', 'price_source', 'price_timestamp', 'entry_zone']} />;
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

function filterDecisionRows(rows: UnifiedDecision[], tab: 'All Decisions' | 'Buy / Research' | 'Watch' | 'Hold / Add' | 'Trim / Sell' | 'Avoid' | 'Core Investing' | 'Outliers' | 'Velocity') {
  if (tab === 'All Decisions') return rows;
  if (tab === 'Buy / Research') return rows.filter((row) => row.primary_action === 'Research / Buy Candidate');
  if (tab === 'Watch') return rows.filter((row) => row.primary_action === 'Watch');
  if (tab === 'Hold / Add') return rows.filter((row) => ['Hold', 'Add'].includes(String(row.primary_action)));
  if (tab === 'Trim / Sell') return rows.filter((row) => ['Trim', 'Sell / Exit Candidate', 'Watch Closely'].includes(String(row.primary_action)));
  if (tab === 'Avoid') return rows.filter((row) => ['Avoid', 'Data Insufficient'].includes(String(row.primary_action)));
  return rows.filter((row) => row.action_lane === tab.replace('Outliers', 'Outlier').replace('Core Investing', 'Core Investing'));
}

function filterScannerRows(rows: ScannerRow[], tab: 'All Decisions' | 'Buy / Research' | 'Watch' | 'Hold / Add' | 'Trim / Sell' | 'Avoid' | 'Core Investing' | 'Outliers' | 'Velocity') {
  if (tab === 'Velocity') return rows.filter((row) => Number(row.velocity_score ?? 0) >= 35 && !String(row.velocity_type).includes('No High'));
  if (tab === 'Avoid') return rows.filter((row) => row.status_label === 'Avoid' || String(row.outlier_type).includes('Avoid'));
  if (tab === 'Core Investing') return rows.filter((row) => Number(row.regular_investing_score ?? 0) > 0);
  if (tab === 'Outliers') return rows.filter((row) => Number(row.outlier_score ?? 0) > 0);
  return rows;
}

function DecisionSummary({ rows }: { rows: UnifiedDecision[] }) {
  const row = rows[0];
  if (!row) return <p className="muted">No decision matched this lane yet.</p>;
  return (
    <div className="brief-grid">
      <div>
        <span className="eyebrow">Why it is here</span>
        <p>{row.reason ?? 'No decision reason returned yet.'}</p>
      </div>
      <div>
        <span className="eyebrow">What could block it</span>
        <p>{row.why_not ?? 'No counter-thesis returned yet.'}</p>
      </div>
    </div>
  );
}

function VelocityCard({ row }: { row: ScannerRow }) {
  return (
    <article className="candidate-card velocity-card">
      <div className="provider-title">
        <div>
          <h3>{row.ticker}</h3>
          <span>{row.velocity_type}</span>
        </div>
        <ScoreRing value={Number(row.velocity_score ?? 0)} label="Velocity" />
      </div>
      <div className="pill-row">
        <Chip tone={String(row.velocity_type).includes('Avoid') ? 'bad' : 'good'}>{row.quick_trade_watch_label ?? 'Watch Only'}</Chip>
        <Chip tone={row.velocity_risk === 'Extreme' || row.velocity_risk === 'High' ? 'warn' : 'neutral'}>{row.expected_horizon ?? 'n/a'}</Chip>
      </div>
      <p>{row.trigger_reason}</p>
      <Notice tone={String(row.chase_warning).includes('No special') ? 'neutral' : 'warn'}>{row.chase_warning ?? 'Use invalidation discipline.'}</Notice>
      <KeyValue payload={{ invalidation: row.velocity_invalidation, TP1: row.velocity_tp1, TP2: row.velocity_tp2 }} />
      <PriceSanityBadge payload={row} />
    </article>
  );
}

function DecisionList({ rows, empty }: { rows: UnifiedDecision[]; empty: string }) {
  if (!rows.length) return <p className="muted">{empty}</p>;
  return (
    <div className="candidate-list">
      {rows.map((row) => (
        <article className="candidate-card decision-row" key={row.ticker}>
          <div className="provider-title">
            <div>
              <h3>{row.ticker}</h3>
              <span>{row.company ?? row.action_lane ?? 'Decision'}</span>
            </div>
            <ScoreRing value={Number(row.score ?? 0)} label="Score" />
          </div>
          <div className="pill-row">
            <StatusPill status={row.primary_action} />
            <Chip tone={String(row.risk_level).includes('High') ? 'warn' : 'neutral'}>{row.risk_level ?? 'Risk n/a'}</Chip>
            <Chip tone="neutral">{row.confidence_label ?? 'Confidence n/a'}</Chip>
          </div>
          <p>{row.reason ?? 'No decision reason returned.'}</p>
          <KeyValue payload={{ entry: row.entry_zone, stop: row.stop_loss, invalidation: row.invalidation, tp1: row.tp1, tp2: row.tp2, review: row.next_review_date }} />
          <PriceSanityBadge payload={row.price_sanity} />
          {row.why_not && <Notice tone="warn">{row.why_not}</Notice>}
          {row.source_row && <PaperTrackingForm scannerRow={row.source_row} compact />}
        </article>
      ))}
    </div>
  );
}

function DecisionBoard({ rows }: { rows: UnifiedDecision[] }) {
  if (!rows.length) return <p className="muted">No actionable TP / SL rows yet.</p>;
  return (
    <DataTable
      rows={rows.map((row) => ({
        ticker: row.ticker,
        action: row.primary_action,
        entry: row.entry_zone,
        stop: row.stop_loss,
        TP1: row.tp1,
        TP2: row.tp2,
        reward_risk: row.reward_risk,
        review_date: row.next_review_date,
      }))}
      columns={['ticker', 'action', 'entry', 'stop', 'TP1', 'TP2', 'reward_risk', 'review_date']}
    />
  );
}

function UniverseSummary({ payload }: { payload: UniversesPayload | null }) {
  const items = payload?.items ?? DEFAULT_UNIVERSES;
  return (
    <div className="provider-grid">
      {items.map((item) => (
        <article className="provider-card" key={item.path}>
          <div className="provider-title">
            <strong>{item.label}</strong>
            <Chip tone={item.available ? 'good' : 'warn'}>{item.available ? 'Ready' : 'Missing'}</Chip>
          </div>
          <p>{item.description}</p>
          <code>{item.path}</code>
        </article>
      ))}
      <Notice tone="warn">{payload?.warning ?? DEFAULT_UNIVERSE_WARNING}</Notice>
    </div>
  );
}

function ValidationContextCard({ context }: { context?: ValidationContext | null }) {
  const messages = context?.messages ?? ['Not enough evidence yet.'];
  return (
    <div className="validation-context">
      <div className="metric-grid compact">
        <Metric label="Evidence" value={String(context?.evidence_strength ?? 'Not enough evidence yet')} sub="Plain-English validation context" />
        <Metric label="Real-money reliance" value={context?.real_money_reliance ? 'Yes' : 'No'} sub="Should stay No" />
      </div>
      {messages.map((message) => <Notice tone="neutral" key={message}>{message}</Notice>)}
      {context?.language_note && <p className="muted">{context.language_note}</p>}
    </div>
  );
}

function ReplaySummary({ report }: { report: ReplayPayload | null }) {
  const summary = report?.summary ?? {};
  const strategy = (summary.strategy_performance as Record<string, unknown>[] | undefined) ?? (summary.best_worst_investing_styles as Record<string, unknown>[] | undefined) ?? [];
  const returns = (summary.average_forward_return_by_horizon as Record<string, unknown> | undefined) ?? Object.fromEntries(Object.entries((summary.regular_investing_forward_returns as Record<string, Record<string, unknown>> | undefined) ?? {}).map(([horizon, metric]) => [horizon, metric.average]));
  const chartData = Object.entries(returns ?? {}).map(([horizon, value]) => ({ horizon, value: Number(value ?? 0) }));
  return (
    <div className="grid">
      <Notice tone="neutral">{report?.point_in_time_limitations ?? 'No replay loaded yet. Sample replay is safest for a quick UI check.'}</Notice>
      <div className="metric-grid">
        <Metric label="Replay dates" value={String(summary.total_replay_dates ?? 0)} sub="Historical runs" />
        <Metric label="Candidates" value={String(summary.total_candidates ?? 0)} sub="Selected rows" />
        <Metric label="False positives" value={String(summary.false_positive_rate ?? 'n/a')} sub="20D <= 0 or invalidated" />
        <Metric label="Evidence" value={String(summary.sample_size_warning ? 'Small sample' : 'Measured')} sub="Needs forward confirmation" />
      </div>
      <div className="grid two">
        <Panel title="Forward Returns">
          <MiniBarChart data={chartData} />
        </Panel>
        <Panel title="Baseline Comparison">
          <KeyValue payload={(summary.excess_return_vs_baselines as Record<string, unknown> | undefined) ?? {}} />
        </Panel>
      </div>
      <Panel title="Performance By Strategy">
        <DataTable rows={strategy} columns={['strategy_label', 'investing_style', 'sample_size', 'average', 'median', 'win_rate', 'false_positive_rate']} />
      </Panel>
      <Panel title="Recent Replay Rows">
        <DataTable rows={(report?.results ?? []).slice(0, 30)} columns={['replay_date', 'ticker', 'regular_investing_score', 'investing_action_label', 'investing_style', 'status_label', 'outlier_score', 'velocity_score', 'risk_score']} />
      </Panel>
    </div>
  );
}

function ProofReportView({ report }: { report: ProofReport | null }) {
  if (!report) return <p className="muted">No proof report loaded.</p>;
  return (
    <div className="grid">
      <div className="metric-grid compact">
        <Metric label="Evidence strength" value={String(report.evidence_strength ?? 'Not enough evidence')} sub="Historical only" />
        <Metric label="Real-money reliance" value={report.real_money_reliance ? 'Yes' : 'No'} sub="Must remain false" />
        <Metric label="Velocity" value={report.velocity_replay ? 'Included' : 'Not included'} sub="High-volume triggers" />
      </div>
      <Notice tone="neutral">{report.language_note ?? 'Use evidence language. Do not treat this as proof of future results.'}</Notice>
      <KeyValue payload={report.answers ?? {}} />
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

function MiniBarChart({ data }: { data: { horizon: string; value: number }[] }) {
  if (!data.length) return <p className="muted">No replay return data.</p>;
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data}>
          <CartesianGrid stroke="#243244" />
          <XAxis dataKey="horizon" stroke="#9fb0c4" />
          <YAxis stroke="#9fb0c4" />
          <Tooltip contentStyle={{ background: '#101722', border: '1px solid #27364a', color: '#e8eef7' }} />
          <Bar dataKey="value" fill="#75d8c7" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function DualLineChart({ data }: { data: Record<string, unknown>[] }) {
  if (!data.length) return <p className="muted">No case-study timeline.</p>;
  return (
    <div className="chart tall">
      <ResponsiveContainer width="100%" height={340}>
        <ReLineChart data={data}>
          <CartesianGrid stroke="#243244" />
          <XAxis dataKey="date" stroke="#9fb0c4" minTickGap={28} />
          <YAxis yAxisId="left" stroke="#75d8c7" />
          <YAxis yAxisId="right" orientation="right" stroke="#f1bf69" />
          <Tooltip contentStyle={{ background: '#101722', border: '1px solid #27364a', color: '#e8eef7' }} />
          <Line yAxisId="left" type="monotone" dataKey="price" stroke="#75d8c7" dot={false} strokeWidth={2} />
          <Line yAxisId="right" type="monotone" dataKey="outlier_score" stroke="#f1bf69" dot={false} strokeWidth={2} />
          <Line yAxisId="right" type="monotone" dataKey="velocity_score" stroke="#a9b8ff" dot={false} strokeWidth={2} />
        </ReLineChart>
      </ResponsiveContainer>
    </div>
  );
}

function ResearchView({ payload }: { payload: ResearchPayload }) {
  const decision = payload.decision_card as Record<string, unknown> | undefined;
  const unifiedDecision = payload.unified_decision;
  const scanner = payload.scanner_row;
  const regularView = payload.regular_investing_view as Record<string, unknown> | undefined;
  return (
    <div className="grid">
      <Panel title="Primary Decision">
        <DecisionCard
          label={String(unifiedDecision?.primary_action ?? decision?.research_recommendation ?? scanner?.status_label ?? 'Data Insufficient')}
          status={String(unifiedDecision?.reason ?? scanner?.strategy_label ?? scanner?.outlier_type ?? 'Rule-based research')}
          risk={String(scanner?.risk_score ?? 'Unknown')}
          details={String(unifiedDecision?.why_not ?? scanner?.alternative_data_summary ?? 'Deterministic scanner output remains primary.')}
        />
        <div className="metric-grid compact">
          <Metric label="Winner" value={String(scanner?.winner_score ?? payload.winner_score ?? 0)} sub="Rule score" />
          <Metric label="Outlier" value={String(scanner?.outlier_score ?? payload.outlier_score ?? 0)} sub="Outlier engine" />
          <Metric label="Risk" value={String(scanner?.risk_score ?? payload.risk_score ?? 0)} sub="Lower is better" />
          <Metric label="Confidence" value={String(unifiedDecision?.confidence_label ?? scanner?.confidence_label ?? 'Low')} sub={String(unifiedDecision?.evidence_strength ?? 'No validation context')} />
        </div>
      </Panel>
      <div className="grid two">
        <Panel title="Action Setup">
          <KeyValue payload={{ entry: unifiedDecision?.entry_zone ?? payload.entry_zone, stop: unifiedDecision?.stop_loss, invalidation: unifiedDecision?.invalidation ?? payload.invalidation, tp1: unifiedDecision?.tp1 ?? payload.tp1, tp2: unifiedDecision?.tp2 ?? payload.tp2, horizon: unifiedDecision?.holding_horizon }} />
        </Panel>
        <Panel title="Price Sanity">
          <KeyValue payload={payload.price_sanity ?? scanner ?? {}} />
          <PriceSanityBadge payload={payload.price_sanity ?? scanner} />
        </Panel>
        <Panel title="Why Not To Buy">
          <Notice tone="warn">
            {String(unifiedDecision?.why_not ?? listText(scanner?.why_it_could_fail ?? (payload.key_risks as unknown[] | undefined) ?? ['No explicit risk notes were returned. Refresh data before relying on the thesis.']))}
          </Notice>
          <KeyValue payload={{ invalidation: payload.invalidation, warnings: scanner?.warnings, missing_data: scanner?.alternative_data_warnings }} />
        </Panel>
        <Panel title="Bull Case">
          <KeyValue payload={{ bull_case: payload.bull_case ?? scanner?.why_it_passed, big_winner_case: scanner?.why_it_passed }} />
        </Panel>
        <Panel title="Bear Case">
          <KeyValue payload={{ bear_case: payload.bear_case ?? scanner?.why_it_could_fail, key_risks: payload.key_risks ?? scanner?.warnings }} />
        </Panel>
        <Panel title="Regular Investing View">
          <div className="metric-grid compact">
            <Metric label="Core score" value={String(regularView?.regular_investing_score ?? scanner?.regular_investing_score ?? 0)} sub="0-100 regular investing" />
            <Metric label="Action" value={String(regularView?.investing_action_label ?? scanner?.investing_action_label ?? 'Data Insufficient')} sub="Research label only" />
            <Metric label="Risk" value={String(regularView?.investing_risk ?? scanner?.investing_risk ?? 'Unknown')} sub="Not an order" />
          </div>
          <KeyValue payload={{
            style: regularView?.investing_style ?? scanner?.investing_style,
            horizon: regularView?.investing_time_horizon ?? scanner?.investing_time_horizon,
            bull_case: regularView?.bull_case ?? scanner?.investing_reason,
            bear_case: regularView?.bear_case ?? scanner?.investing_bear_case,
            invalidation: regularView?.invalidation ?? scanner?.investing_invalidation,
            events_to_watch: regularView?.events_to_watch ?? scanner?.investing_events_to_watch,
            value_trap_warning: regularView?.value_trap_warning ?? scanner?.value_trap_warning,
            thesis_quality: regularView?.thesis_quality ?? scanner?.thesis_quality,
            data_quality: regularView?.data_quality ?? scanner?.investing_data_quality,
          }} />
        </Panel>
        <Panel title="Validation Context">
          <ValidationContextCard context={payload.validation_context} />
        </Panel>
        <Panel title="Insider / Politician Activity">
          <div className="alt-grid">
            <InsiderActivityCard row={scanner} />
            <PoliticianActivityCard row={scanner} />
          </div>
        </Panel>
        <Panel title="Data Quality">
          <KeyValue payload={{ alternative_data_quality: scanner?.alternative_data_quality, alternative_sources: scanner?.alternative_data_source_count, disclosure_lag: scanner?.disclosure_lag_warning, data_notes: scanner?.warnings }} />
        </Panel>
        <Panel title="Portfolio Context">
          <KeyValue payload={{ portfolio_context: payload.portfolio_context, journal_history: payload.journal_history }} />
        </Panel>
        <Panel title="Historical Evidence">
          <p className="muted">Use Validation Lab to save this thesis and measure forward outcomes against SPY, QQQ, and random baselines.</p>
          {scanner && <PaperTrackingForm scannerRow={scanner} />}
        </Panel>
      </div>
    </div>
  );
}

function PaperTrackingForm({ scannerRow, compact = false }: { scannerRow: ScannerRow; compact?: boolean }) {
  const [message, setMessage] = useState('');
  const [error, setError] = useState<Error | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setMessage('');
    setError(null);
    try {
      const prediction = await api.addPrediction({
        scanner_row: scannerRow,
        rule_based_recommendation: scannerRow.status_label ?? 'Data Insufficient',
        ai_committee_recommendation: form.get('ai_committee_recommendation') || 'Data Insufficient',
        final_combined_recommendation: scannerRow.status_label ?? 'Data Insufficient',
        thesis: form.get('thesis'),
        invalidation: form.get('invalidation'),
        tp1: form.get('tp1'),
        tp2: form.get('tp2'),
        expected_holding_period: form.get('expected_holding_period'),
        events_to_watch: [form.get('events_to_watch')].filter(Boolean),
        recommendation_snapshot: {
          deterministic: scannerRow.status_label ?? 'Data Insufficient',
          ticker: scannerRow.ticker,
          winner_score: scannerRow.winner_score,
          outlier_score: scannerRow.outlier_score,
          risk_score: scannerRow.risk_score,
        },
      });
      setMessage(`Saved ${prediction.prediction_id}. Next review: ${prediction.next_review_date ?? 'pending'}.`);
      event.currentTarget.reset();
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Could not save prediction'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className={compact ? 'paper-form compact' : 'paper-form'} onSubmit={submit}>
      <strong>Start Paper Tracking</strong>
      <Select name="expected_holding_period" label="Horizon" options={['5D', '10D', '20D', '1D']} />
      <Field name="thesis" label="Thesis" defaultValue={scannerRow.why_it_passed?.[0] ?? ''} />
      <Field name="invalidation" label="Invalidation" defaultValue={String(scannerRow.invalidation_level ?? '')} />
      <Field name="tp1" label="TP1" defaultValue={String(scannerRow.tp1 ?? '')} />
      <Field name="tp2" label="TP2" defaultValue={String(scannerRow.tp2 ?? '')} />
      {!compact && <Field name="events_to_watch" label="Events to watch" defaultValue={scannerRow.why_it_could_fail?.[0] ?? ''} />}
      <input type="hidden" name="ai_committee_recommendation" value="Data Insufficient" />
      <button className="primary" disabled={saving}>{saving ? 'Saving' : 'Save Prediction'}</button>
      {message && <Notice tone="good">{message}</Notice>}
      {error && <ApiErrorPanel error={error} onRetry={() => setError(null)} compact />}
    </form>
  );
}

function DecisionCard({ label, status, risk, details }: { label: string; status: string; risk: string; details: string }) {
  const riskNumber = Number(risk);
  return (
    <div className="decision-card">
      <div>
        <span className="eyebrow">Decision</span>
        <h3>{label}</h3>
        <p>{status}</p>
      </div>
      <ScoreRing value={Number.isFinite(riskNumber) ? Math.max(0, 100 - riskNumber) : 50} label="Risk-adjusted" />
      <Notice tone={riskNumber >= 60 ? 'bad' : riskNumber >= 40 ? 'warn' : 'neutral'}>{details}</Notice>
    </div>
  );
}

function ScoreRing({ value, label }: { value: number; label: string }) {
  const degrees = Math.max(0, Math.min(100, value)) * 3.6;
  return (
    <div className="score-ring" style={{ background: `conic-gradient(#74dac7 ${degrees}deg, #1e3043 0deg)` }}>
      <div>
        <strong>{Math.round(value)}</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status?: string }) {
  const text = status ?? 'Unknown';
  const tone = text.includes('Avoid') || text.includes('Sell') ? 'bad' : text.includes('Watch') || text.includes('Forming') ? 'warn' : 'good';
  return <Chip tone={tone}>{text}</Chip>;
}

function SignalStack({ row }: { row: ScannerRow }) {
  const chips: React.ReactNode[] = [];
  if (row.CEO_CFO_buy_flag) chips.push(<AlternativeDataBadge key="ceo">CEO/CFO buy</AlternativeDataBadge>);
  if (row.cluster_buying_flag) chips.push(<AlternativeDataBadge key="cluster">Cluster buying</AlternativeDataBadge>);
  if (row.heavy_insider_selling_flag) chips.push(<Chip key="sell" tone="warn">Heavy insider selling</Chip>);
  if (row.recent_politician_activity) chips.push(<AlternativeDataBadge key="politician">Politician activity</AlternativeDataBadge>);
  if (row.alternative_data_confirmed_by_price_volume) chips.push(<Chip key="confirm" tone="good">Confirmed by price/volume</Chip>);
  (row.alternative_data_warnings ?? row.warnings ?? []).slice(0, 2).forEach((warning) => chips.push(<Chip key={warning} tone="warn">{warning}</Chip>));
  if (!chips.length) return <p className="muted">No verified alternative-data signals loaded.</p>;
  return <div className="pill-row">{chips}</div>;
}

function AlternativeDataBadge({ children }: { children: React.ReactNode }) {
  return <span className="alt-badge"><Sparkles size={13} /> {children}</span>;
}

function ProviderBadge({ children }: { children: React.ReactNode }) {
  return <span className="provider-badge">{children}</span>;
}

function DataHealthCard({ ready, missing, requiredMissing }: { ready: number; missing: number; requiredMissing: number }) {
  return (
    <div className="health-card">
      <Activity size={18} />
      <div>
        <strong>{ready} ready</strong>
        <span>{missing} optional missing · {requiredMissing} required missing</span>
      </div>
    </div>
  );
}

function ValidationMetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="validation-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function InsiderActivityCard({ row }: { row?: ScannerRow }) {
  return (
    <div className="activity-card">
      <h3>Insider Activity</h3>
      <KeyValue payload={{ buys: row?.insider_buy_count ?? 0, sells: row?.insider_sell_count ?? 0, net_value: money(Number(row?.net_insider_value ?? 0)), CEO_CFO_buy: row?.CEO_CFO_buy_flag ? 'Yes' : 'No', quality: row?.alternative_data_quality ?? 'Unavailable' }} />
    </div>
  );
}

function PoliticianActivityCard({ row }: { row?: ScannerRow }) {
  return (
    <div className="activity-card">
      <h3>Politician Activity</h3>
      <KeyValue payload={{ buys: row?.politician_buy_count ?? 0, sells: row?.politician_sell_count ?? 0, net_value: money(Number(row?.net_politician_value ?? 0)), recent: row?.recent_politician_activity ? 'Yes' : 'No', disclosure_lag: row?.disclosure_lag_warning ?? 'No warning' }} />
    </div>
  );
}

function WorkflowReportView({ report }: { report: { available?: boolean; message?: string; summary?: Record<string, number>; checks?: { name?: string; status?: string; mode?: string; message?: string }[]; conclusion?: string } | null }) {
  if (!report?.available) return <p className="muted">{report?.message ?? 'No report loaded yet.'}</p>;
  return (
    <div className="workflow-report">
      <div className="pill-row">
        {Object.entries(report.summary ?? {}).map(([key, value]) => <Chip key={key} tone={key === 'FAIL' && value ? 'bad' : key === 'WARN' && value ? 'warn' : 'neutral'}>{key}: {value}</Chip>)}
      </div>
      {report.conclusion && <p className="muted">{report.conclusion}</p>}
      <DataTable rows={(report.checks ?? []).slice(0, 8) as Record<string, unknown>[]} columns={['status', 'name', 'mode', 'message']} />
    </div>
  );
}

function CommandSnippet({ text }: { text: string }) {
  async function copy() {
    await navigator.clipboard?.writeText(text);
  }
  return (
    <div className="command-snippet">
      <code>{text}</code>
      <button className="ghost" type="button" onClick={copy}>Copy</button>
    </div>
  );
}

function MarkdownReport({ text }: { text: string }) {
  const lines = text.split('\n').filter(Boolean);
  return (
    <div className="markdown-report">
      {lines.map((line, index) => {
        if (line.startsWith('# ')) return <h3 key={index}>{line.replace(/^# /, '')}</h3>;
        if (line.startsWith('## ')) return <h4 key={index}>{line.replace(/^## /, '')}</h4>;
        if (line.startsWith('- ')) return <p key={index} className="report-bullet">{line.replace(/^- /, '')}</p>;
        return <p key={index}>{line}</p>;
      })}
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className="candidate-list">
      {[0, 1, 2].map((item) => <div className="skeleton-card" key={item}><SkeletonLine /><SkeletonLine /><SkeletonLine /></div>)}
    </div>
  );
}

function SkeletonLine() {
  return <div className="skeleton-line" />;
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

function listText(value: unknown[] | string) {
  if (Array.isArray(value)) return value.map((item) => String(item)).join(' | ');
  return String(value);
}

function cell(value: unknown): string {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === 'object' && item !== null) {
          const record = item as Record<string, unknown>;
          return String(record.label ?? record.ticker ?? record.name ?? record.summary ?? 'Structured item');
        }
        return String(item);
      })
      .join(' | ');
  }
  if (typeof value === 'object' && value !== null) return `${Object.keys(value as Record<string, unknown>).length} fields`;
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value ?? '');
}

function PriceSanityBadge({ payload }: { payload?: { price_warning?: string; price_source?: string; price_timestamp?: string; price_confidence?: string } | null }) {
  if (!payload) return null;
  return (
    <div className="pill-row">
      <Chip tone={String(payload.price_warning).includes('Sample') || String(payload.price_warning).includes('Stale') ? 'warn' : 'good'}>
        {payload.price_source ?? 'Price source unavailable'}
      </Chip>
      <Chip tone="neutral">{compactDate(payload.price_timestamp)}</Chip>
      <Chip tone="neutral">{payload.price_confidence ?? 'Confidence n/a'}</Chip>
    </div>
  );
}

function describeBackendStatus(error: Error | null) {
  if (!error) return { label: 'Connected', tone: 'good' as const };
  if (isApiError(error)) {
    if (error.kind === 'disconnected') return { label: 'Disconnected', tone: 'bad' as const };
    if (error.kind === 'wrong_api_url') return { label: 'Wrong API URL', tone: 'warn' as const };
    if (error.kind === 'backend_error') return { label: 'Backend error', tone: 'bad' as const };
    if (error.kind === 'request_timeout') return { label: 'Request timed out', tone: 'warn' as const };
  }
  return { label: 'Backend error', tone: 'bad' as const };
}
