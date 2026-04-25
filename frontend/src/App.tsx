import { FormEvent, useState } from 'react';
import type React from 'react';
import {
  AlertTriangle,
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
import { api, AlertRow, DataSourceRow, HealthPayload, PortfolioPayload, PredictionRow, ProofReport, ReplayPayload, ScannerRow } from './api';
import { useAsync } from './hooks';

type PageKey =
  | 'Home'
  | 'Stock Picker'
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
  const predictions = useAsync(api.predictions, []);
  const rows = latest.data?.results ?? [];
  const top = rows.filter((row) => row.status_label !== 'Avoid').slice(0, 5);
  const openPredictions = (predictions.data ?? []).filter((row) => !row.outcome_label || ['Open', 'Still Open', 'Data Unavailable'].includes(row.outcome_label));
  const duePredictions = openPredictions.filter((row) => !row.next_review_date || row.next_review_date <= new Date().toISOString().slice(0, 10));

  return (
    <Page title="Home" subtitle="Daily brief, open risks, and the next useful research action.">
      <div className="metric-grid">
        <Metric label="Candidates" value={String(top.length)} sub="Non-avoid names in latest scan" />
        <Metric label="Open alerts" value={String(alerts.data?.length ?? 0)} sub="Daily workflow prompts" />
        <Metric label="Due reviews" value={String(duePredictions.length)} sub="Paper predictions needing update" />
        <Metric label="Data sources" value={`${sources.data?.summary.optional_ready ?? 0} ready`} sub="Configured optional providers" />
      </div>
      <div className="grid two">
        <Panel title="Market Regime">
          <DecisionCard
            label={String(latest.data?.market_regime?.regime ?? 'Unavailable')}
            status={latest.data?.available ? 'Latest scan loaded' : 'Run a scan to populate regime'}
            risk={String(latest.data?.market_regime?.risk_level ?? 'Unknown')}
            details={String(latest.data?.market_regime?.summary ?? 'Regime comes from Python scan outputs.')}
          />
        </Panel>
        <Panel title="Quick Actions">
          <div className="action-strip">
            <button className="primary" onClick={() => setPage('Stock Picker')}><RefreshCcw size={16} /> Run Scan</button>
            <button className="secondary" onClick={() => setPage('Deep Research')}><Search size={16} /> Deep Research Ticker</button>
            <button className="secondary" onClick={() => setPage('Validation Lab')}><FlaskConical size={16} /> Review Predictions</button>
          </div>
          <WatchlistChangeCard label="Predictions needing review" value={String(duePredictions.length)} note="Forward tracking is the honest scorekeeper." />
        </Panel>
      </div>
      {top.length ? (
        <div className="grid two">
          <Panel title="Top Research Candidates">
            <CandidateList rows={top} />
          </Panel>
          <Panel title="Open Alerts">
            <AlertList rows={(alerts.data ?? []).slice(0, 6)} />
          </Panel>
          <Panel title="Data Health">
            <DataHealthCard ready={sources.data?.summary.optional_ready ?? 0} missing={sources.data?.summary.optional_missing ?? 0} requiredMissing={sources.data?.summary.required_missing ?? 0} />
          </Panel>
          <Panel title="Portfolio Review Prompts">
            <p className="muted">Use Portfolio Analyst after each real scan to compare current holdings against refreshed deterministic signals.</p>
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
  const [tab, setTab] = useState<'Outliers' | 'Velocity' | 'Long-Term' | 'Avoid'>('Outliers');
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
        <Select name="mode" label="Mode" options={['outliers', 'velocity', 'standard']} />
        <Field name="universe_path" label="Universe" defaultValue="config/outlier_watchlist.txt" />
        <Field name="as_of_date" label="As of" defaultValue="2026-04-24" />
        <button className="primary" disabled={loading}>
          <RefreshCcw size={16} /> {loading ? 'Running' : 'Run Scan'}
        </button>
      </form>
      {error && <Notice tone="bad">{error}</Notice>}
      {loading && <Notice tone="neutral">Running the scanner can take a bit with the real provider. Results will appear here without changing your data.</Notice>}
      {scan.length > 0 && (
        <div className="tabs">
          {(['Outliers', 'Velocity', 'Long-Term', 'Avoid'] as const).map((item) => (
            <button className={tab === item ? 'active' : ''} key={item} onClick={() => setTab(item)}>{item}</button>
          ))}
        </div>
      )}
      {loading ? (
        <SkeletonGrid />
      ) : scan.length ? (
        <div className="grid">
          <Panel title={`${tab} Candidates`}>
            <CandidateList rows={filterStockRows(scan, tab).slice(0, 8)} />
          </Panel>
          <Panel title="Why This Is Actionable">
            <SignalBrief rows={filterStockRows(scan, tab)} />
          </Panel>
          <Panel title="Scanner Table">
            <ScannerTable rows={filterStockRows(scan, tab)} />
          </Panel>
          <Panel title="What Invalidates This Fast">
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

function VelocityScanner() {
  const [payload, setPayload] = useState<ScannerRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading(true);
    setError('');
    try {
      const result = await api.scan({
        provider: form.get('provider'),
        mode: 'velocity',
        universe_path: form.get('universe_path'),
        as_of_date: form.get('as_of_date'),
      });
      setPayload(result.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Velocity scan failed');
    } finally {
      setLoading(false);
    }
  }

  const candidates = payload.filter((row) => row.velocity_type !== 'No High-Velocity Trigger');
  return (
    <Page title="Velocity Scanner" subtitle="High-volume and quick-moving research candidates. No day-trading, options, execution, or buy-now language.">
      <form className="toolbar" onSubmit={submit}>
        <Select name="provider" label="Provider" options={['sample', 'local', 'real']} />
        <Field name="universe_path" label="Universe" defaultValue="config/outlier_watchlist.txt" />
        <Field name="as_of_date" label="As of" defaultValue="2026-04-24" />
        <button className="primary" disabled={loading}><Activity size={16} /> {loading ? 'Scanning' : 'Run Velocity Scan'}</button>
      </form>
      {error && <Notice tone="bad">{error}</Notice>}
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
  const [error, setError] = useState('');

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading(true);
    setError('');
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
      setError(err instanceof Error ? err.message : 'Replay failed');
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
        <Field name="universe" label="Universe" defaultValue="config/outlier_watchlist.txt" />
        <Field name="start_date" label="Start" defaultValue="2020-01-01" />
        <Field name="end_date" label="End" defaultValue="2026-04-24" />
        <Field name="top_n" label="Top N" defaultValue="20" />
        <button className="primary" disabled={loading}><RefreshCcw size={16} /> {loading ? 'Running' : 'Run Replay'}</button>
      </form>
      {error && <Notice tone="bad">{error}</Notice>}
      <ReplaySummary report={report} />
    </Page>
  );
}

function OutlierCaseStudy() {
  const [study, setStudy] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading(true);
    setError('');
    try {
      setStudy(await api.runOutlierStudy({
        provider: form.get('provider'),
        ticker: form.get('ticker'),
        start_date: form.get('start_date'),
        end_date: form.get('end_date'),
        mode: form.get('mode'),
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Case study failed');
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
      {error && <Notice tone="bad">{error}</Notice>}
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
  const [research, setResearch] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError('');
    setLoading(true);
    try {
      setResearch(await api.deepResearch({ ticker: form.get('ticker'), provider: form.get('provider') }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Deep research failed');
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
      {error && <Notice tone="bad">{error}</Notice>}
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
      <DataTable rows={positions} columns={['ticker', 'recommendation_label', 'action_urgency', 'reason_to_hold', 'reason_to_add', 'invalidation_level']} />
    </Page>
  );
}

function AICommittee() {
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError('');
    setLoading(true);
    try {
      setPayload(await api.aiCommittee({ ticker: form.get('ticker'), mode: form.get('mode'), provider: form.get('provider') }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI committee failed');
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
      {error && <Notice tone="bad">{error}</Notice>}
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
  const [auditLoading, setAuditLoading] = useState(false);
  const [proofLoading, setProofLoading] = useState(false);
  const [updateLoading, setUpdateLoading] = useState(false);

  async function runAudit() {
    setAuditLoading(true);
    try {
      signalAudit.setData(await api.runSignalAudit({ reports_dir: 'reports/scans', baseline: 'SPY,QQQ', random_baseline: true }));
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
    } finally {
      setUpdateLoading(false);
    }
  }

  async function runProof() {
    setProofLoading(true);
    try {
      proof.setData(await api.runProofReport({
        provider: 'sample',
        universe: 'config/outlier_watchlist.txt',
        start_date: '2020-01-01',
        end_date: '2026-04-24',
        include_famous_outliers: true,
        include_velocity: true,
        baseline: 'SPY,QQQ',
        random_baseline: true,
      }));
    } finally {
      setProofLoading(false);
    }
  }

  const due = (summary.data?.recent_predictions_needing_update as Record<string, unknown>[] | undefined) ?? [];
  const hitLevels = (summary.data?.predictions_with_hit_levels as Record<string, unknown>[] | undefined) ?? [];
  const missingOutcomes = (summary.data?.predictions_with_missing_outcome as Record<string, unknown>[] | undefined) ?? [];

  return (
    <Page title="Validation Lab" subtitle="Paper predictions, outcome updates, and famous outlier case studies.">
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
  const [error, setError] = useState('');
  const [workflowLoading, setWorkflowLoading] = useState('');
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

  async function runWorkflow(kind: 'doctor' | 'doctor-live' | 'readiness' | 'readiness-openai' | 'readiness-gemini') {
    setWorkflowLoading(kind);
    setError('');
    try {
      if (kind === 'doctor') {
        const report = await api.runDoctor({ live: false, ticker: 'NVDA' });
        doctor.setData(report);
      } else if (kind === 'doctor-live') {
        const report = await api.runDoctor({ live: true, ticker: 'NVDA' });
        doctor.setData(report);
      } else {
        const ai = kind === 'readiness-openai' ? 'openai' : kind === 'readiness-gemini' ? 'gemini' : 'mock';
        const report = await api.runReadiness({ provider: 'real', ai, tickers: 'NVDA,PLTR,MU,RDDT,GME,CAR,SMCI,COIN,HOOD,ARM,CAVA,AAPL,MSFT,LLY,TSLA' });
        readiness.setData(report);
      }
      setMessage('Workflow completed. Restart the backend only after changing .env values.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Workflow failed');
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
          <CommandSnippet text="python3 -m tradebruv readiness --universe config/outlier_watchlist.txt --provider real --tickers NVDA,PLTR,MU,RDDT,GME,CAR,SMCI,COIN,HOOD,ARM,CAVA,AAPL,MSFT,LLY,TSLA --ai mock" />
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
  async function refreshStatus() {
    setStatusLoading(true);
    try {
      appStatus.setData(await api.runAppStatus());
    } finally {
      setStatusLoading(false);
    }
  }
  return (
    <Page title="Reports" subtitle="Latest scan, archive index, daily summary, alerts, and optional debug payloads.">
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
            <ScoreBar label="Winner" value={Number(row.winner_score ?? 0)} />
            <RiskBadge score={Number(row.risk_score ?? 0)} />
          </div>
          <p><StatusPill status={row.status_label} /> {row.outlier_type}</p>
          <SignalStack row={row} />
          {(row.warnings ?? []).slice(0, 2).map((warning) => <small className="risk" key={warning}><AlertTriangle size={13} /> {warning}</small>)}
          <PaperTrackingForm scannerRow={row} compact />
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

function filterStockRows(rows: ScannerRow[], tab: 'Outliers' | 'Velocity' | 'Long-Term' | 'Avoid') {
  if (tab === 'Avoid') return rows.filter((row) => row.status_label === 'Avoid' || String(row.outlier_type).includes('Avoid'));
  if (tab === 'Velocity') return rows.filter((row) => Number(row.velocity_score ?? 0) >= 35 && !String(row.velocity_type).includes('No High'));
  if (tab === 'Long-Term') return rows.filter((row) => row.strategy_label === 'Long-Term Leader' || row.outlier_type === 'Long-Term Monster');
  return rows.filter((row) => row.status_label !== 'Avoid');
}

function SignalBrief({ rows }: { rows: ScannerRow[] }) {
  const row = rows[0];
  if (!row) return <p className="muted">No row selected for this mode.</p>;
  return (
    <div className="brief-grid">
      <div>
        <span className="eyebrow">Actionable because</span>
        <p>{row.why_it_passed?.[0] ?? row.trigger_reason ?? row.outlier_reason ?? 'The deterministic scanner has not produced a clean reason yet.'}</p>
      </div>
      <div>
        <span className="eyebrow">Invalidates fast</span>
        <p>{row.why_it_could_fail?.[0] ?? row.chase_warning ?? `Invalidation: ${row.invalidation_level ?? row.velocity_invalidation ?? 'unavailable'}`}</p>
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
    </article>
  );
}

function ReplaySummary({ report }: { report: ReplayPayload | null }) {
  const summary = report?.summary ?? {};
  const strategy = (summary.strategy_performance as Record<string, unknown>[] | undefined) ?? [];
  const returns = summary.average_forward_return_by_horizon as Record<string, unknown> | undefined;
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
        <DataTable rows={strategy} columns={['strategy_label', 'sample_size', 'average', 'median', 'win_rate', 'false_positive_rate']} />
      </Panel>
      <Panel title="Recent Replay Rows">
        <DataTable rows={(report?.results ?? []).slice(0, 30)} columns={['replay_date', 'ticker', 'status_label', 'outlier_type', 'outlier_score', 'velocity_type', 'velocity_score', 'risk_score']} />
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

function ResearchView({ payload }: { payload: Record<string, unknown> }) {
  const decision = payload.decision_card as Record<string, unknown> | undefined;
  const scanner = payload.scanner_row as ScannerRow | undefined;
  return (
    <div className="grid">
      <Panel title="Hero Decision">
        <DecisionCard
          label={String(decision?.recommendation_label ?? scanner?.status_label ?? 'Data Insufficient')}
          status={String(scanner?.strategy_label ?? scanner?.outlier_type ?? 'Rule-based research')}
          risk={String(scanner?.risk_score ?? 'Unknown')}
          details={String(decision?.rationale ?? scanner?.alternative_data_summary ?? 'Deterministic scanner output remains primary.')}
        />
        <div className="metric-grid compact">
          <Metric label="Winner" value={String(scanner?.winner_score ?? payload.winner_score ?? 0)} sub="Rule score" />
          <Metric label="Outlier" value={String(scanner?.outlier_score ?? payload.outlier_score ?? 0)} sub="Outlier engine" />
          <Metric label="Risk" value={String(scanner?.risk_score ?? payload.risk_score ?? 0)} sub="Lower is better" />
        </div>
      </Panel>
      <div className="grid two">
        <Panel title="Rule-Based Levels">
          <KeyValue payload={{ entry: payload.entry_zone, invalidation: payload.invalidation, tp1: payload.tp1, tp2: payload.tp2 }} />
        </Panel>
        <Panel title="Why NOT to Buy">
          <Notice tone="warn">
            {listText(scanner?.why_it_could_fail ?? (payload.key_risks as unknown[] | undefined) ?? ['No explicit risk notes were returned. Refresh data before relying on the thesis.'])}
          </Notice>
          <KeyValue payload={{ invalidation: payload.invalidation, warnings: scanner?.warnings, missing_data: scanner?.alternative_data_warnings }} />
        </Panel>
        <Panel title="Bull Case">
          <KeyValue payload={{ bull_case: payload.bull_case ?? scanner?.why_it_passed, big_winner_case: scanner?.why_it_passed }} />
        </Panel>
        <Panel title="Bear Case">
          <KeyValue payload={{ bear_case: payload.bear_case ?? scanner?.why_it_could_fail, key_risks: payload.key_risks ?? scanner?.warnings }} />
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
        <Panel title="Validation History">
          <p className="muted">Use Validation Lab to save this thesis and measure forward outcomes against SPY, QQQ, and random baselines.</p>
          {scanner && <PaperTrackingForm scannerRow={scanner} />}
        </Panel>
      </div>
    </div>
  );
}

function PaperTrackingForm({ scannerRow, compact = false }: { scannerRow: ScannerRow; compact?: boolean }) {
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setMessage('');
    setError('');
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
      setError(err instanceof Error ? err.message : 'Could not save prediction');
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
      {error && <Notice tone="bad">{error}</Notice>}
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

function ScoreBar({ label, value }: { label: string; value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="score-bar">
      <span>{label}</span>
      <div><i style={{ width: `${clamped}%` }} /></div>
      <strong>{Math.round(clamped)}</strong>
    </div>
  );
}

function RiskBadge({ score }: { score: number }) {
  return <Chip tone={score >= 70 ? 'bad' : score >= 45 ? 'warn' : 'good'}>Risk {Math.round(score)}</Chip>;
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

function WatchlistChangeCard({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="watch-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{note}</p>
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
