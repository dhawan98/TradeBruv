import { FormEvent, useEffect, useState } from 'react';
import type React from 'react';
import {
  Activity,
  Plus,
  BookOpen,
  Brain,
  ChevronDown,
  ChevronRight,
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
  Trash2,
  Wallet,
} from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Line, LineChart as ReLineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import {
  api,
  AlertRow,
  ChartPayload,
  DataSourceRow,
  DecisionSnapshotPayload,
  PredictionRow,
  ProofReport,
  ReplayPayload,
  ResearchPayload,
  ScanJobStatus,
  ScannerRow,
  SignalTableRow,
  UnifiedDecision,
  UniverseItem,
  UniversesPayload,
  ValidationContext,
  isApiError,
} from './api';
import { useAsync } from './hooks';

type PageKey =
  | 'Decision Cockpit'
  | 'Stock Picker'
  | 'Deep Research'
  | 'Portfolio'
  | 'Data Sources'
  | 'Reports'
  | 'Core Investing'
  | 'Velocity Scanner'
  | 'Replay Lab'
  | 'Outlier Case Study'
  | 'Portfolio Analyst'
  | 'AI Committee'
  | 'Validation Lab'
  | 'Alerts'
  | 'Journal';

const PRIMARY_NAV: { key: PageKey; icon: React.ComponentType<{ size?: number }> }[] = [
  { key: 'Decision Cockpit', icon: Home },
  { key: 'Stock Picker', icon: Search },
  { key: 'Deep Research', icon: BookOpen },
  { key: 'Portfolio', icon: Wallet },
  { key: 'Data Sources', icon: Database },
  { key: 'Reports', icon: Layers },
];

const ADVANCED_NAV: { key: PageKey; icon: React.ComponentType<{ size?: number }> }[] = [
  { key: 'Core Investing', icon: LineChart },
  { key: 'Velocity Scanner', icon: Activity },
  { key: 'Replay Lab', icon: LineChart },
  { key: 'Outlier Case Study', icon: Sparkles },
  { key: 'Portfolio Analyst', icon: LineChart },
  { key: 'AI Committee', icon: Brain },
  { key: 'Validation Lab', icon: FlaskConical },
  { key: 'Alerts', icon: ShieldAlert },
  { key: 'Journal', icon: FileText },
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
  { label: 'US Broad 1000 Target', path: 'config/universe_us_broad_1000.txt', description: 'Broader static discovery starter for wide market scans.', available: true },
  { label: 'Famous Case Studies', path: 'config/famous_outlier_case_studies.txt', description: 'Historical validation names only.', available: true },
];

const DEFAULT_UNIVERSE_WARNING = 'Famous Case Studies are for historical validation, not active monitoring.';
const EMPTY_DECISIONS: UnifiedDecision[] = [];
const EMPTY_SIGNALS: SignalTableRow[] = [];

type ScanState = {
  available?: boolean;
  generated_at?: string;
  provider?: string;
  demo_mode?: boolean;
  report_snapshot?: boolean;
  stale_data?: boolean;
  results?: ScannerRow[];
  decisions?: UnifiedDecision[];
  data_issues?: UnifiedDecision[];
  validation_context?: ValidationContext;
};

export function App() {
  const [page, setPage] = useState<PageKey>('Decision Cockpit');
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const health = useAsync(api.health, []);
  const latest = useAsync(api.dailyDecisionLatest, []);

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
          {PRIMARY_NAV.map(({ key, icon: Icon }) => (
            <button className={page === key ? 'nav-item active' : 'nav-item'} key={key} onClick={() => setPage(key)}>
              <Icon size={17} />
              <span>{key}</span>
            </button>
          ))}
          <button className={advancedOpen ? 'nav-item nav-section open' : 'nav-item nav-section'} onClick={() => setAdvancedOpen((value) => !value)} type="button">
            {advancedOpen ? <ChevronDown size={17} /> : <ChevronRight size={17} />}
            <span>Advanced</span>
          </button>
          {advancedOpen ? ADVANCED_NAV.map(({ key, icon: Icon }) => (
            <button className={page === key ? 'nav-item active nav-subitem' : 'nav-item nav-subitem'} key={key} onClick={() => setPage(key)}>
              <Icon size={16} />
              <span>{key}</span>
            </button>
          )) : null}
        </nav>
      </aside>
      <main className="main">
        <TopBar
          healthError={health.error}
          latest={latest.data}
          onRetryHealth={health.retry}
        />
        <section className="workspace">
          {page === 'Decision Cockpit' && <HomePage setPage={setPage} />}
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
  healthError,
  latest,
  onRetryHealth,
}: {
  healthError: Error | null;
  latest: DecisionSnapshotPayload | null;
  onRetryHealth: () => void;
}) {
  const coverage = latest?.workspace?.coverage_status ?? latest?.data_coverage_status ?? {};
  const statusBar = latest?.workspace?.status_bar ?? {};
  const coverageHealth = coverage.provider_health as Record<string, unknown> | undefined;
  const warnings = [
    String(statusBar.provider_health ?? coverageHealth?.status ?? '') === 'rate_limited' ? 'Rate-limited' : '',
    String(statusBar.provider_health ?? coverageHealth?.status ?? '') === 'degraded' ? 'Degraded' : '',
    latest?.report_snapshot ? 'Snapshot' : '',
    latest?.stale_data ? 'Stale' : '',
    healthError ? 'Backend' : '',
  ].filter(Boolean);
  return (
    <header className="topbar terminal-topbar">
      <div className="topbar-title">
        <strong>TradeBruv</strong>
        <span>Stock decision terminal</span>
      </div>
      <div className="topbar-stream">
        <span><label>Provider</label><strong>{String(statusBar.provider ?? latest?.provider ?? 'unavailable')}</strong></span>
        <span><label>Last scan</label><strong>{compactDate(String(statusBar.last_scan ?? latest?.generated_at ?? 'unavailable'))}</strong></span>
        <span><label>Coverage</label><strong>{String(statusBar.coverage_summary ?? `${coverage.tickers_successfully_scanned ?? 0}/${coverage.tickers_attempted ?? 0} scanned`)}</strong></span>
        <span><label>Universe</label><strong>{String(statusBar.universe_label ?? coverage.universe_label ?? 'Active')}</strong></span>
        <span><label>Tracked</label><strong>{String(statusBar.tracked_count ?? coverage.tracked_tickers_count ?? 0)}</strong></span>
        <span><label>Health</label><strong>{String(statusBar.provider_health ?? coverageHealth?.status ?? 'healthy')}</strong></span>
      </div>
      {warnings.length ? (
        <div className="topbar-warnings">
          {warnings.map((warning) => (
            <span className="topbar-warning" key={warning}>{warning}</span>
          ))}
        </div>
      ) : null}
      {healthError ? <button className="ghost topbar-retry" onClick={onRetryHealth}><RefreshCcw size={14} /> Retry backend</button> : null}
    </header>
  );
}

type CockpitView = 'Top' | 'Movers' | 'Tracked' | 'Broad' | 'Watch' | 'Avoid' | 'All';

function HomePage({ setPage }: { setPage: (page: PageKey) => void }) {
  const latest = useAsync(api.dailyDecisionLatest, []);
  const tracked = useAsync(api.tracked, []);
  const [selectedTicker, setSelectedTicker] = useState('');
  const [timeframe, setTimeframe] = useState<'3M' | '6M' | '1Y' | '2Y'>('1Y');
  const [activeView, setActiveView] = useState<CockpitView>('Top');
  const [trackedInput, setTrackedInput] = useState('');
  const workspace = latest.data?.workspace;
  const canonicalRows = workspace?.canonical_rows ?? latest.data?.decisions ?? EMPTY_DECISIONS;
  const signalRows = workspace?.signal_table_rows ?? latest.data?.signal_table ?? EMPTY_SIGNALS;
  const decisionByTicker = workspace?.decision_by_ticker ?? {};
  const activeRows = filterCockpitRows(canonicalRows, activeView);
  const activeSignalRows = filterSignalRows(signalRows, activeView);
  const defaultTicker =
    workspace?.selected_ticker
    ?? workspace?.source_aware_top?.overall_top_setup?.ticker
    ?? activeRows[0]?.ticker
    ?? canonicalRows[0]?.ticker
    ?? '';

  useEffect(() => {
    if (!selectedTicker && defaultTicker) {
      setSelectedTicker(defaultTicker);
      return;
    }
    if (selectedTicker && !canonicalRows.some((row) => row.ticker === selectedTicker) && defaultTicker) {
      setSelectedTicker(defaultTicker);
    }
  }, [canonicalRows, defaultTicker, selectedTicker]);

  const selectedDecision =
    (selectedTicker ? decisionByTicker[selectedTicker] : null)
    ?? workspace?.source_aware_top?.overall_top_setup
    ?? latest.data?.top_candidate
    ?? null;
  const chart = useAsync(
    () => (
      selectedTicker
        ? api.chart(selectedTicker, latest.data?.provider ?? 'sample', timeframe)
        : Promise.resolve(emptyChartPayload())
    ),
    [selectedTicker, timeframe, latest.data?.provider],
  );
  const activeChart = chart.data?.ticker ? chart.data : (workspace?.chart_data_by_ticker?.[selectedTicker] ?? chart.data);

  async function addTrackedTicker(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!trackedInput.trim()) return;
    const payload = await api.trackedAdd(trackedInput.trim().toUpperCase());
    tracked.setData(payload);
    setTrackedInput('');
  }

  async function removeTrackedTicker(ticker: string) {
    tracked.setData(await api.trackedRemove(ticker));
  }

  async function toggleTrackedTicker(ticker: string) {
    const trackedTickers = tracked.data?.tickers ?? [];
    tracked.setData(
      trackedTickers.includes(ticker)
        ? await api.trackedRemove(ticker)
        : await api.trackedAdd(ticker),
    );
  }

  return (
    <div className="cockpit-page">
      {latest.error && <ApiErrorPanel error={latest.error} onRetry={latest.retry} />}
      {tracked.error && <ApiErrorPanel error={tracked.error} onRetry={tracked.retry} compact />}
      {latest.data?.available ? (
        <>
          <div className="cockpit-grid">
            <aside className="cockpit-rail">
              <div className="rail-header">
                <details className="rail-settings">
                  <summary><Plus size={14} /> Watchlist</summary>
                  <form className="rail-add-form" onSubmit={addTrackedTicker}>
                    <input value={trackedInput} onChange={(event) => setTrackedInput(event.target.value)} placeholder="Add ticker" aria-label="Add tracked ticker" />
                    <button className="ghost" type="submit">Add</button>
                  </form>
                  <div className="tracked-chip-strip">
                    {(tracked.data?.tickers ?? []).slice(0, 18).map((ticker) => (
                      <button className="tracked-chip subtle" key={ticker} onClick={() => removeTrackedTicker(ticker)} type="button" title={`Remove ${ticker} from tracked`}>
                        <span>{ticker}</span>
                        <Trash2 size={12} />
                      </button>
                    ))}
                  </div>
                </details>
              </div>
              <RailFilterTabs
                activeView={activeView}
                counts={(workspace?.view_counts ?? {}) as Record<string, number>}
                onChange={setActiveView}
              />
              <div className="rail-list">
                {activeRows.length ? activeRows.map((row) => (
                  <button
                    className={selectedTicker === row.ticker ? 'rail-row selected' : 'rail-row'}
                    key={`${activeView}-${row.ticker}`}
                    onClick={() => setSelectedTicker(row.ticker)}
                    type="button"
                  >
                    <div className="rail-main">
                      <strong>{row.ticker}</strong>
                      <span>{shortCompanyName(row.company ?? row.source_row?.company_name ?? '')}</span>
                    </div>
                    <div className="rail-side">
                      <span>{cell(row.source_row?.current_price ?? 'n/a')}</span>
                      <span className={pctTone(row.source_row?.price_change_1d_pct)}>{pct(row.source_row?.price_change_1d_pct)}</span>
                      <span>RV {cell(row.source_row?.relative_volume_20d ?? 'n/a')}</span>
                      <span>{row.source_row?.signal_summary ?? 'No Clean Signal'}</span>
                      <span>{shortAction(row.actionability_label ?? row.primary_action)}</span>
                    </div>
                  </button>
                )) : <p className="muted">No rows in this view right now.</p>}
              </div>
            </aside>
            <section className="cockpit-canvas">
              <MarketChartPanel
                chart={activeChart}
                decision={selectedDecision}
                timeframe={timeframe}
                onTimeframeChange={(value) => setTimeframe(value)}
              />
            </section>
            <aside className="cockpit-panel">
              {selectedDecision ? (
                <>
                  <SelectedDecisionPanel
                    row={selectedDecision}
                    trackedTickers={tracked.data?.tickers ?? []}
                    onToggleTracked={toggleTrackedTicker}
                    onDeepResearch={() => setPage('Deep Research')}
                    onAICommittee={() => setPage('AI Committee')}
                  />
                  <MarketLeadersPanel
                    gainers={latest.data?.top_gainers ?? []}
                    losers={latest.data?.top_losers ?? []}
                    unusualVolume={latest.data?.unusual_volume ?? []}
                    breakoutVolume={latest.data?.breakout_volume ?? []}
                    onSelect={setSelectedTicker}
                  />
                </>
              ) : (
                <EmptyState title="No Clean Candidate Today" action="Open Stock Picker" onAction={() => setPage('Stock Picker')}>
                  {latest.data?.no_clean_candidate_reason ?? 'No validated setup passed the actionability gate today.'}
                </EmptyState>
              )}
            </aside>
          </div>
          <section className="cockpit-table-zone">
            <SignalWorkspaceTable
              rows={activeSignalRows}
              onSelect={setSelectedTicker}
              selectedTicker={selectedTicker}
              title={`${activeView} screener`}
            />
            <details className="diagnostics cockpit-diagnostics">
              <summary>Diagnostics / Raw Data</summary>
              <div className="cockpit-diagnostics-grid">
                <div className="cockpit-diagnostics-copy">
                  <p><strong>Coverage</strong> {String(workspace?.coverage_status?.universe_label ?? 'Active')} · {String(workspace?.coverage_status?.tickers_successfully_scanned ?? 0)}/{String(workspace?.coverage_status?.tickers_attempted ?? 0)} scanned · Unique {String(workspace?.coverage_status?.unique_candidate_tickers_requested ?? 0)}</p>
                  <p><strong>Selection</strong> {String(workspace?.selected_ticker_consistency_reason ?? 'No diagnostics loaded.')}</p>
                  {workspace?.coverage_status?.universe_warning ? <p><strong>Universe note</strong> {String(workspace.coverage_status.universe_warning)}</p> : null}
                </div>
                <div>
                  <h3>Data issues</h3>
                  <DecisionList rows={(workspace?.data_issues ?? latest.data?.data_issues ?? []).slice(0, 8)} empty="No hidden data issues." />
                </div>
              </div>
            </details>
          </section>
        </>
      ) : (
        <EmptyState title="No live daily decision loaded" action="Open Stock Picker" onAction={() => setPage('Stock Picker')}>
          Build a live decision snapshot with the real provider, or use Reports to inspect historical report snapshots.
        </EmptyState>
      )}
    </div>
  );
}

function RailFilterTabs({
  activeView,
  counts,
  onChange,
}: {
  activeView: CockpitView;
  counts: Record<string, number>;
  onChange: (view: CockpitView) => void;
}) {
  const items: { key: CockpitView; countKey: string }[] = [
    { key: 'Top', countKey: 'top' },
    { key: 'Movers', countKey: 'movers' },
    { key: 'Tracked', countKey: 'tracked' },
    { key: 'Broad', countKey: 'broad' },
    { key: 'Watch', countKey: 'watch' },
    { key: 'Avoid', countKey: 'avoid' },
    { key: 'All', countKey: 'all' },
  ];
  return (
    <div className="rail-filters">
      {items.map((item) => (
        <button className={activeView === item.key ? 'rail-filter active' : 'rail-filter'} key={item.key} onClick={() => onChange(item.key)} type="button">
          <span>{item.key}</span>
          <strong>{String(counts[item.countKey] ?? 0)}</strong>
        </button>
      ))}
    </div>
  );
}

function MarketChartPanel({
  chart,
  decision,
  timeframe,
  onTimeframeChange,
}: {
  chart: ChartPayload | null;
  decision: UnifiedDecision | null;
  timeframe: '3M' | '6M' | '1Y' | '2Y';
  onTimeframeChange: (value: '3M' | '6M' | '1Y' | '2Y') => void;
}) {
  const [showEma, setShowEma] = useState(true);
  const [showVolume, setShowVolume] = useState(true);
  const series = chart?.series ?? [];
  const latestPoint = series[series.length - 1];
  const signalSummary = String(chart?.signals?.signal_summary ?? decision?.source_row?.signal_summary ?? 'No Clean Signal');
  const signalExplanation = String(chart?.signals?.signal_explanation ?? decision?.source_row?.signal_explanation ?? 'No signal explanation loaded.');
  const actionability = decision?.actionability_label ?? decision?.primary_action ?? chart?.price_source ?? 'No decision loaded';
  const sourceGroups = (decision?.source_groups ?? [decision?.source_group]).filter(Boolean).join(' + ');
  return (
    <div className="market-chart-panel">
      <div className="chart-toolbar workspace-chart-toolbar">
        <div className="chart-heading">
          <strong>{chart?.ticker ?? decision?.ticker ?? 'No symbol selected'}</strong>
          <span>{shortCompanyName(decision?.company ?? '') || sourceGroups || 'No company loaded'}</span>
        </div>
        <div className="chart-price-strip">
          <span className="chart-price">{money(Number(latestPoint?.close ?? decision?.source_row?.current_price ?? 0))}</span>
          <span className={pctTone(decision?.source_row?.price_change_1d_pct)}>{pct(decision?.source_row?.price_change_1d_pct)}</span>
          <span>{actionability}</span>
          <span>{signalSummary}</span>
        </div>
        <div className="chart-controls">
          {(['3M', '6M', '1Y', '2Y'] as const).map((option) => (
            <button className={timeframe === option ? 'secondary active-tab' : 'ghost'} key={option} onClick={() => onTimeframeChange(option)} type="button">
              {option}
            </button>
          ))}
          <button className={showEma ? 'secondary active-tab' : 'ghost'} onClick={() => setShowEma((value) => !value)} type="button">EMA</button>
          <button className={showVolume ? 'secondary active-tab' : 'ghost'} onClick={() => setShowVolume((value) => !value)} type="button">Volume</button>
        </div>
      </div>
      {!chart?.available && !series.length ? (
        <EmptyState title="Chart unavailable" action="Retry">
          {chart?.reason ?? 'No chart data is available for this symbol yet.'}
        </EmptyState>
        ) : (
        <>
          <div className="chart-header-strip workspace-chart-strip">
            <span>{sourceGroups || 'Source unavailable'}</span>
            <span>Updated {compactDate(chart?.last_market_date)}</span>
            <span>RV {cell(chart?.signals?.relative_volume_20d ?? decision?.source_row?.relative_volume_20d ?? 'n/a')}</span>
            <span>{String(chart?.signals?.ema_stack ?? decision?.source_row?.ema_stack ?? 'No EMA stack')}</span>
          </div>
          <div className="chart-dual">
            <div className="chart tall">
              <ResponsiveContainer width="100%" height={460}>
                <ReLineChart data={series}>
                  <CartesianGrid stroke="#243244" />
                  <XAxis dataKey="date" stroke="#9fb0c4" minTickGap={28} />
                  <YAxis stroke="#9fb0c4" domain={['auto', 'auto']} />
                  <Tooltip contentStyle={{ background: '#101722', border: '1px solid #27364a', color: '#e8eef7' }} />
                  <Line type="monotone" dataKey="close" stroke="#e8eef7" dot={false} strokeWidth={2} />
                  {showEma ? <Line type="monotone" dataKey="ema_21" stroke="#60d8c2" dot={false} strokeWidth={1.6} /> : null}
                  {showEma ? <Line type="monotone" dataKey="ema_50" stroke="#f4c15d" dot={false} strokeWidth={1.6} /> : null}
                  {showEma ? <Line type="monotone" dataKey="ema_150" stroke="#6fa2ff" dot={false} strokeWidth={1.4} /> : null}
                  {showEma ? <Line type="monotone" dataKey="ema_200" stroke="#c88cff" dot={false} strokeWidth={1.4} /> : null}
                </ReLineChart>
              </ResponsiveContainer>
            </div>
            {showVolume ? (
            <div className="chart volume-chart">
              <ResponsiveContainer width="100%" height={110}>
                <BarChart data={series}>
                  <CartesianGrid stroke="#243244" vertical={false} />
                  <XAxis dataKey="date" hide />
                  <YAxis stroke="#9fb0c4" hide />
                  <Tooltip contentStyle={{ background: '#101722', border: '1px solid #27364a', color: '#e8eef7' }} />
                  <Bar dataKey="volume" fill="#365978" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            ) : null}
          </div>
          <div className="chart-legend workspace-chart-legend">
            <span><i className="legend-swatch ema21" /> EMA 21: {cell(latestPoint?.ema_21 ?? 'n/a')}</span>
            <span><i className="legend-swatch ema50" /> EMA 50: {cell(latestPoint?.ema_50 ?? 'n/a')}</span>
            <span><i className="legend-swatch ema150" /> EMA 150: {cell(latestPoint?.ema_150 ?? 'n/a')}</span>
            <span><i className="legend-swatch ema200" /> EMA 200: {cell(latestPoint?.ema_200 ?? 'n/a')}</span>
            {showVolume ? <span><i className="legend-swatch volume" /> Volume</span> : null}
          </div>
          <div className="chart-meta workspace-chart-meta">
            <span>{signalSummary}</span>
            <span>Rel Vol {cell(chart?.signals?.relative_volume_20d ?? 'n/a')}</span>
            <span>vs EMA21 {pct(chart?.signals?.price_vs_ema_21_pct)}</span>
            <span>vs EMA50 {pct(chart?.signals?.price_vs_ema_50_pct)}</span>
            <span>vs EMA200 {pct(chart?.signals?.price_vs_ema_200_pct)}</span>
          </div>
          <p className="signal-strip">{signalSummary} · {signalExplanation}</p>
        </>
      )}
    </div>
  );
}

function SelectedDecisionPanel({
  row,
  trackedTickers = [],
  onToggleTracked,
  onDeepResearch,
  onAICommittee,
}: {
  row: UnifiedDecision;
  trackedTickers?: string[];
  onToggleTracked?: (ticker: string) => Promise<void> | void;
  onDeepResearch?: () => void;
  onAICommittee?: () => void;
}) {
  const tracked = trackedTickers.includes(row.ticker);
  const visibleNotices = (row.decision_notices ?? []).filter((notice) => notice.severity !== 'debug');
  return (
    <div className="selected-decision">
      <div className="decision-heading">
        <div>
          <h3>{row.ticker}</h3>
          <p>{row.actionability_label ?? row.primary_action ?? 'Decision unavailable'} · Score {Math.round(Number(row.actionability_score ?? row.score ?? 0))}</p>
        </div>
        <div className="decision-score-block">
          <span>{money(Number(row.source_row?.current_price ?? 0))}</span>
          <strong className={pctTone(row.source_row?.price_change_1d_pct)}>{pct(row.source_row?.price_change_1d_pct)}</strong>
        </div>
      </div>
      <div className="decision-inline-meta">
        <span>Signal {row.source_row?.signal_summary ?? 'n/a'}</span>
        <span>EMA {row.source_row?.ema_stack ?? 'n/a'}</span>
        <span>Rel Vol {cell(row.source_row?.relative_volume_20d ?? 'n/a')}</span>
        <span>Risk {row.risk_level ?? 'n/a'}</span>
        <span>Updated {compactDate(row.latest_market_date)}</span>
      </div>
      {visibleNotices.length ? (
        <div className="notice-stack">
          {visibleNotices.slice(0, 1).map((notice) => (
            <div className={`notice-line ${notice.severity}`} key={`${notice.severity}-${notice.message}`}>
              <span>{notice.message}</span>
            </div>
          ))}
        </div>
      ) : null}
      <div className="decision-level-grid">
        <div>
          <span className="eyebrow">{row.trigger_needed ? 'Trigger / Better Entry' : row.entry_label ?? 'Entry'}</span>
          <p>{row.trigger_needed ? (row.action_trigger ?? row.entry_zone ?? 'Wait for setup.') : (row.entry_zone ?? 'No level')}</p>
        </div>
        <div>
          <span className="eyebrow">Stop / Invalidation</span>
          <p>{cell(row.stop_loss ?? row.invalidation)}</p>
        </div>
        <div>
          <span className="eyebrow">TP1</span>
          <p>{cell(row.tp1)}</p>
        </div>
        <div>
          <span className="eyebrow">TP2</span>
          <p>{cell(row.tp2)}</p>
        </div>
      </div>
      <div className="decision-subfacts">
        <div><span>Signal</span><strong>{row.source_row?.signal_summary ?? 'n/a'}</strong></div>
        <div><span>EMA</span><strong>{row.source_row?.ema_stack ?? 'n/a'}</strong></div>
        <div><span>Fresh</span><strong>{row.data_freshness ?? compactDate(row.latest_market_date)}</strong></div>
        <div><span>Source</span><strong>{(row.source_groups ?? [row.source_group]).filter(Boolean).join(' + ') || 'n/a'}</strong></div>
      </div>
      <div className="action-strip">
        {onDeepResearch ? <button className="secondary" onClick={onDeepResearch} type="button">Deep Research</button> : null}
        {onToggleTracked ? <button className="ghost" onClick={() => onToggleTracked(row.ticker)} type="button">{tracked ? 'Untrack' : 'Track'}</button> : null}
        {row.source_row ? <TrackPredictionButton scannerRow={row.source_row} /> : null}
        {onAICommittee ? <button className="ghost" onClick={onAICommittee} type="button">Run AI Committee</button> : null}
      </div>
      <details className="decision-disclosure">
        <summary>Why</summary>
        <p>{row.actionability_reason ?? row.reason ?? 'No thesis returned.'}</p>
      </details>
      <details className="decision-disclosure">
        <summary>Risk</summary>
        <p>{row.why_not ?? 'No major counter-thesis beyond routine review discipline.'}</p>
      </details>
      <details className="decision-disclosure">
        <summary>Sources</summary>
        <p>{(row.source_groups ?? [row.source_group]).filter(Boolean).join(' + ') || 'No source tags loaded.'}</p>
      </details>
    </div>
  );
}

function MarketLeadersPanel({
  gainers,
  losers,
  unusualVolume,
  breakoutVolume,
  onSelect,
}: {
  gainers: Record<string, unknown>[];
  losers: Record<string, unknown>[];
  unusualVolume: Record<string, unknown>[];
  breakoutVolume: Record<string, unknown>[];
  onSelect: (ticker: string) => void;
}) {
  const rows = [
    { label: 'Gainer', row: gainers[0] },
    { label: 'Loser', row: losers[0] },
    { label: 'Rel Vol', row: unusualVolume[0] },
    { label: 'Breakout', row: breakoutVolume[0] ?? gainers.find((item) => String(item.signal ?? '') === 'Breakout with Volume') ?? gainers[0] },
  ].filter((item) => item.row && item.row.ticker);
  if (!rows.length) return null;
  return (
    <div className="market-leaders-panel">
      {rows.map(({ label, row }) => (
        <button className="market-leader-row" key={`${label}-${String(row?.ticker)}`} onClick={() => onSelect(String(row?.ticker))} type="button">
          <span>{label}</span>
          <strong>{String(row?.ticker)}</strong>
          <em>{pct(row?.percent_change)}</em>
          <small>RV {cell(row?.relative_volume)}</small>
        </button>
      ))}
    </div>
  );
}

function SignalWorkspaceTable({
  rows,
  onSelect,
  selectedTicker,
  title = 'Signal table',
  subtitle,
}: {
  rows: SignalTableRow[];
  onSelect: (ticker: string) => void;
  selectedTicker: string;
  title?: string;
  subtitle?: string | null;
}) {
  const [sortBy, setSortBy] = useState<'actionability' | 'relative_volume_20d' | 'price_change_1d_pct'>('actionability');
  const sorted = [...rows].sort((left, right) => {
    if (sortBy === 'actionability') {
      return Number(labelWeight(right.actionability)) - Number(labelWeight(left.actionability));
    }
    return Number(right[sortBy] ?? 0) - Number(left[sortBy] ?? 0);
  });
  if (!rows.length) return <p className="muted">No signal table rows are available yet.</p>;
  return (
    <div className="table-wrap workspace-table-wrap">
      <div className="table-head">
        <div>
          <strong>{title}</strong>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        <div className="pill-row">
        <button className={sortBy === 'actionability' ? 'secondary active-tab' : 'ghost'} onClick={() => setSortBy('actionability')} type="button">Sort: Actionability</button>
        <button className={sortBy === 'relative_volume_20d' ? 'secondary active-tab' : 'ghost'} onClick={() => setSortBy('relative_volume_20d')} type="button">Sort: Rel Vol</button>
        <button className={sortBy === 'price_change_1d_pct' ? 'secondary active-tab' : 'ghost'} onClick={() => setSortBy('price_change_1d_pct')} type="button">Sort: % Change</button>
        </div>
      </div>
      <table className="signal-table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Source</th>
            <th>Price</th>
            <th>% Change</th>
            <th>Rel Vol</th>
            <th>EMA Stack</th>
            <th>Signal</th>
            <th>Actionability</th>
            <th>Risk</th>
            <th>Entry / Trigger</th>
            <th>Stop</th>
            <th>TP1</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, index) => (
            <tr className={selectedTicker === row.ticker ? 'selected' : ''} key={`${row.ticker}-${index}`} onClick={() => row.ticker && onSelect(row.ticker)}>
              <td><strong>{row.ticker}</strong></td>
              <td>{cell(row.source)}</td>
              <td>{cell(row.price)}</td>
              <td className={pctTone(row.price_change_1d_pct)}>{pct(row.price_change_1d_pct)}</td>
              <td>{cell(row.relative_volume_20d)}</td>
              <td>{cell(row.ema_stack)}</td>
              <td><strong>{cell(row.signal)}</strong></td>
              <td>{cell(row.actionability)}</td>
              <td>{cell(row.risk)}</td>
              <td>{cell(row.entry_or_trigger)}</td>
              <td>{cell(row.stop)}</td>
              <td>{cell(row.tp1)}</td>
              <td>{compactDate(row.updated)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function emptyChartPayload(): ChartPayload {
  return {
    ticker: '',
    available: false,
    series: [],
    markers: [],
    signals: {},
    available_timeframes: ['3M', '6M', '1Y', '2Y'],
  };
}

function StockPicker() {
  const universes = useAsync(api.universes, []);
  const [scan, setScan] = useState<ScanState | null>(null);
  const [scanJob, setScanJob] = useState<ScanJobStatus | null>(null);
  const [tab, setTab] = useState<'Best Ideas' | 'Research' | 'Watch' | 'Avoid' | 'All'>('Best Ideas');
  const [selectedTicker, setSelectedTicker] = useState('');
  const [timeframe, setTimeframe] = useState<'3M' | '6M' | '1Y' | '2Y'>('6M');
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(false);
  const previewRows = (scanJob?.preview_rows ?? []) as Record<string, unknown>[];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const job = await api.startScan({
        provider: form.get('provider'),
        mode: form.get('mode'),
        universe_path: form.get('universe_path'),
        as_of_date: form.get('as_of_date'),
      });
      setScanJob(job);
      const payload = await waitForScanResult(job.job_id, setScanJob);
      setScan(payload);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Scan failed'));
    } finally {
      setLoading(false);
    }
  }

  const rows = filterDecisionRows(scan?.decisions ?? [], tab);
  const selectedDecision = rows.find((row) => row.ticker === selectedTicker) ?? rows[0] ?? null;
  useEffect(() => {
    if (!selectedTicker && rows[0]?.ticker) {
      setSelectedTicker(rows[0].ticker);
      return;
    }
    if (selectedTicker && !rows.some((row) => row.ticker === selectedTicker)) {
      setSelectedTicker(rows[0]?.ticker ?? '');
    }
  }, [rows, selectedTicker]);
  const chart = useAsync(
    () => (
      selectedDecision?.ticker
        ? api.chart(selectedDecision.ticker, scan?.provider ?? 'sample', timeframe)
        : Promise.resolve(emptyChartPayload())
    ),
    [selectedDecision?.ticker, scan?.provider, timeframe],
  );

  return (
    <Page title="Stock Picker" subtitle="Run a deterministic scan, then review the results in a dense screener instead of a card wall.">
      {universes.error && <ApiErrorPanel error={universes.error} onRetry={universes.retry} compact />}
      <form className="toolbar" onSubmit={submit}>
        <Select name="provider" label="Provider" options={['real', 'local', 'sample']} />
        <Select name="mode" label="Mode" options={['outliers', 'velocity', 'investing']} />
        <UniverseField name="universe_path" label="Universe" defaultValue="config/universe_us_broad_1000.txt" universes={universes.data} />
        <Field name="as_of_date" label="As of" defaultValue="2026-04-24" />
        <button className="primary" disabled={loading}>
          <RefreshCcw size={16} /> {loading ? 'Running' : 'Run Scan'}
        </button>
      </form>
      <Notice tone="neutral">{universes.data?.warning ?? DEFAULT_UNIVERSE_WARNING}</Notice>
      {scan?.demo_mode && <Notice tone="warn">DEMO MODE. Demo sample data — not real prices.</Notice>}
      {scan?.report_snapshot && <Notice tone="warn">Report Snapshot. Historical rows are not actionable.</Notice>}
      {error && <ApiErrorPanel error={error} onRetry={() => setError(null)} />}
      {loading && (
        <Notice tone="neutral">
          {scanJob
            ? `Scan ${scanJob.status}. Attempted ${scanJob.attempted ?? 0} · scanned ${scanJob.scanned ?? 0} · failed ${scanJob.failed ?? 0}${scanJob.current_batch ? ` · ${scanJob.current_batch}` : ''}${scanJob.provider_health?.status ? ` · ${String(scanJob.provider_health.status)}` : ''}`
            : 'Starting scan job…'}
        </Notice>
      )}
      {loading && previewRows.length ? (
        <div className="table-wrap workspace-table-wrap">
          <div className="table-head">
            <div>
              <strong>Live preview</strong>
            </div>
          </div>
          <table className="signal-table screener-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Price</th>
                <th>% Change</th>
                <th>Rel Vol</th>
                <th>Signal</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {previewRows.map((row) => (
                <tr key={String(row.ticker ?? row.current_price)}>
                  <td><strong>{cell(row.ticker)}</strong></td>
                  <td>{cell(row.current_price)}</td>
                  <td className={pctTone(row.price_change_1d_pct)}>{pct(row.price_change_1d_pct)}</td>
                  <td>{cell(row.relative_volume_20d)}</td>
                  <td>{cell(row.signal_summary)}</td>
                  <td>{cell(row.outlier_score ?? row.regular_investing_score ?? row.velocity_score)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {scan?.decisions?.length ? (
        <div className="tabs">
          {(['Best Ideas', 'Research', 'Watch', 'Avoid', 'All'] as const).map((item) => (
            <button className={tab === item ? 'active' : ''} key={item} onClick={() => setTab(item)}>{item}</button>
          ))}
        </div>
      ) : null}
      {loading ? (
        <SkeletonGrid />
      ) : scan?.decisions?.length ? (
        <div className="picker-workspace">
          <div className="picker-table-pane">
            <StockPickerScreenerTable rows={rows} selectedTicker={selectedTicker} onSelect={setSelectedTicker} />
            <details className="diagnostics">
              <summary>Diagnostics / Raw Data</summary>
              <div className="grid">
                <Panel title="Data Issues">
                  <DecisionList rows={(scan.data_issues ?? []).slice(0, 8)} empty="No price-validation issues in this scan." />
                </Panel>
                <Panel title="Raw Scanner Table">
                  <ScannerTable rows={filterScannerRows(scan.results ?? [], tab === 'All' ? 'All Decisions' : tab === 'Best Ideas' || tab === 'Research' ? 'Buy / Research' : tab)} />
                </Panel>
              </div>
            </details>
          </div>
          <aside className="picker-detail-pane">
            <MarketChartPanel
              chart={chart.data}
              decision={selectedDecision}
              timeframe={timeframe}
              onTimeframeChange={(value) => setTimeframe(value)}
            />
            {selectedDecision ? <SelectedDecisionPanel row={selectedDecision} /> : null}
          </aside>
        </div>
      ) : (
        <EmptyState title={scanJob?.status === 'running' ? 'Scan in progress' : 'Ready for a deterministic scan'} action="Run real outlier scan">
          {scanJob?.status === 'running' ? 'Broad scan is still running in the background.' : 'Sample mode is demo-only and stays non-actionable.'}
        </EmptyState>
      )}
    </Page>
  );
}

function StockPickerScreenerTable({
  rows,
  selectedTicker,
  onSelect,
}: {
  rows: UnifiedDecision[];
  selectedTicker: string;
  onSelect: (ticker: string) => void;
}) {
  const [sortBy, setSortBy] = useState<'score' | 'actionability' | 'relative_volume_20d' | 'price_change_1d_pct' | 'signal' | 'source'>('score');
  const sortedRows = [...rows].sort((left, right) => {
    if (sortBy === 'actionability') return labelWeight(right.actionability_label) - labelWeight(left.actionability_label);
    if (sortBy === 'score') return Number(right.actionability_score ?? right.score ?? 0) - Number(left.actionability_score ?? left.score ?? 0);
    if (sortBy === 'relative_volume_20d') return Number(right.source_row?.relative_volume_20d ?? 0) - Number(left.source_row?.relative_volume_20d ?? 0);
    if (sortBy === 'price_change_1d_pct') return Number(right.source_row?.price_change_1d_pct ?? 0) - Number(left.source_row?.price_change_1d_pct ?? 0);
    if (sortBy === 'signal') return String(left.source_row?.signal_summary ?? '').localeCompare(String(right.source_row?.signal_summary ?? ''));
    return String(left.best_source_group ?? left.source_group ?? '').localeCompare(String(right.best_source_group ?? right.source_group ?? ''));
  });
  if (!rows.length) return <p className="muted">No names match this tab right now.</p>;
  return (
    <div className="table-wrap workspace-table-wrap">
      <div className="table-head">
        <div>
          <strong>Stock screener</strong>
        </div>
        <div className="pill-row">
          <button className={sortBy === 'score' ? 'secondary active-tab' : 'ghost'} onClick={() => setSortBy('score')} type="button">Sort: Score</button>
          <button className={sortBy === 'actionability' ? 'secondary active-tab' : 'ghost'} onClick={() => setSortBy('actionability')} type="button">Actionability</button>
          <button className={sortBy === 'relative_volume_20d' ? 'secondary active-tab' : 'ghost'} onClick={() => setSortBy('relative_volume_20d')} type="button">Rel Vol</button>
          <button className={sortBy === 'price_change_1d_pct' ? 'secondary active-tab' : 'ghost'} onClick={() => setSortBy('price_change_1d_pct')} type="button">% Change</button>
          <button className={sortBy === 'signal' ? 'secondary active-tab' : 'ghost'} onClick={() => setSortBy('signal')} type="button">Signal</button>
          <button className={sortBy === 'source' ? 'secondary active-tab' : 'ghost'} onClick={() => setSortBy('source')} type="button">Source</button>
        </div>
      </div>
      <table className="signal-table screener-table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Company</th>
            <th>Status</th>
            <th>Actionability</th>
            <th>Score</th>
            <th>Price</th>
            <th>% Change</th>
            <th>Rel Vol</th>
            <th>EMA Stack</th>
            <th>Signal</th>
            <th>Entry / Trigger</th>
            <th>Stop</th>
            <th>TP1</th>
            <th>Risk</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => (
            <tr className={selectedTicker === row.ticker ? 'selected' : ''} key={row.ticker} onClick={() => onSelect(row.ticker)}>
                <td><strong>{row.ticker}</strong></td>
                <td>{cell(row.company)}</td>
                <td>{cell(row.primary_action)}</td>
                <td>{cell(row.actionability_label)}</td>
                <td>{Math.round(Number(row.actionability_score ?? row.score ?? 0))}</td>
                <td>{cell(row.source_row?.current_price ?? 'n/a')}</td>
                <td className={pctTone(row.source_row?.price_change_1d_pct)}>{pct(row.source_row?.price_change_1d_pct)}</td>
                <td>{cell(row.source_row?.relative_volume_20d ?? 'n/a')}</td>
                <td>{cell(row.source_row?.ema_stack ?? 'n/a')}</td>
                <td>{cell(row.source_row?.signal_summary ?? 'n/a')}</td>
                <td>{cell(row.trigger_needed ? row.action_trigger : row.entry_zone)}</td>
                <td>{cell(row.stop_loss ?? row.invalidation)}</td>
                <td>{cell(row.tp1)}</td>
                <td>{cell(row.risk_level)}</td>
                <td>{cell(row.reason)}</td>
              </tr>
          ))}
        </tbody>
      </table>
    </div>
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
        <Select name="provider" label="Provider" options={['real', 'local', 'sample']} />
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

function filterDecisionRows(
  rows: UnifiedDecision[],
  tab: 'Best Ideas' | 'Research' | 'Watch' | 'Avoid' | 'All' | 'All Decisions' | 'Buy / Research' | 'Hold / Add' | 'Trim / Sell' | 'Core Investing' | 'Outliers' | 'Velocity',
) {
  if (tab === 'All' || tab === 'All Decisions') return rows;
  if (tab === 'Best Ideas') {
    return rows.filter((row) => row.actionability_label === 'Actionable Today' || row.actionability_label === 'Research First');
  }
  if (tab === 'Research' || tab === 'Buy / Research') {
    return rows.filter((row) => row.primary_action === 'Research / Buy Candidate' && row.actionability_label === 'Research First');
  }
  if (tab === 'Watch') return rows.filter((row) => ['Watch', 'Watch Closely', 'Hold'].includes(String(row.primary_action)) && !!row.trigger_needed);
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
              <span>{row.company ?? row.action_lane ?? 'Decision'}{row.action_lane ? ` • ${row.action_lane}` : ''}</span>
            </div>
            <div className="score-stack compact">
              <strong>{Math.round(Number(row.actionability_score ?? row.score ?? 0))}</strong>
              <span>Actionability</span>
            </div>
          </div>
          <div className="pill-row">
            <StatusPill status={row.actionability_label ?? row.primary_action} />
            {row.primary_action && row.actionability_label !== row.primary_action ? <Chip tone="neutral">{row.primary_action}</Chip> : null}
            <Chip tone={String(row.risk_level).includes('High') ? 'warn' : 'neutral'}>{row.risk_level ?? 'Risk n/a'}</Chip>
            <Chip tone="neutral">Evidence: {row.evidence_pill ?? 'Not enough evidence'}</Chip>
          </div>
          <p>{row.actionability_reason ?? row.reason ?? 'No decision reason returned.'}</p>
          <p className="muted">{row.price_source ?? 'Price source unavailable'} • {compactDate(row.latest_market_date)} • {row.data_freshness ?? 'Freshness n/a'}</p>
          <div className="brief-grid">
            <div>
              <span className="eyebrow">Why not</span>
              <p>{row.why_not ?? 'No major counter-thesis beyond routine review discipline.'}</p>
            </div>
            <div>
              <span className="eyebrow">{row.trigger_needed ? 'Trigger / Better Entry' : (row.entry_label ?? 'Entry')}</span>
              <p>{row.trigger_needed ? (row.action_trigger ?? row.entry_zone ?? 'Wait for refreshed setup.') : (row.entry_zone ?? 'No level')}</p>
            </div>
          </div>
          <LevelPreview row={row} />
          <div className="action-strip">
            <Chip tone={row.level_status === 'Actionable' ? 'good' : row.level_status === 'Hidden' ? 'bad' : 'warn'}>{row.level_status ?? 'Hidden'}</Chip>
            {row.source_row && row.price_validation_status === 'PASS' ? <TrackPredictionButton scannerRow={row.source_row} /> : null}
          </div>
        </article>
      ))}
    </div>
  );
}

function ValidationContextCard({ context }: { context?: ValidationContext | null }) {
  const messages = context?.messages ?? ['Not enough evidence yet.'];
  return (
    <div className="validation-context">
      <div className="metric-grid compact">
        <Metric label="Evidence" value={String(context?.evidence_strength ?? 'Not enough evidence yet')} sub="Compact evidence pill summary" />
        <Metric label="Use for" value={context?.real_money_reliance ? 'Real money' : 'Paper-track only'} sub="Actionability still comes from the live setup" />
      </div>
      <div className="brief-grid">
        {messages.slice(0, 2).map((message) => (
          <div key={message}>
            <span className="eyebrow">Evidence note</span>
            <p>{message}</p>
          </div>
        ))}
      </div>
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

function LevelPreview({ row }: { row: UnifiedDecision }) {
  if (row.level_status === 'Hidden' || row.actionability_label === 'Data Insufficient') {
    return <Notice tone="warn">{row.levels_explanation ?? 'Levels hidden.'}</Notice>;
  }

  if (row.level_status === 'Conditional') {
    return (
      <div className="brief-grid">
        <div>
          <span className="eyebrow">{row.entry_label ?? 'Trigger / Better Entry'}</span>
          <p>{row.action_trigger ?? row.entry_zone ?? 'Wait for the trigger.'}</p>
        </div>
        <div>
          <span className="eyebrow">Conditional levels</span>
          <p>Invalidation {cell(row.stop_loss ?? row.invalidation)} • TP1 {cell(row.tp1)} • TP2 {cell(row.tp2)}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="brief-grid">
      <div>
        <span className="eyebrow">{row.entry_label ?? 'Entry'}</span>
        <p>{row.entry_zone ?? 'unavailable'}</p>
      </div>
      <div>
        <span className="eyebrow">{row.level_status === 'Preliminary' ? 'Preliminary levels' : 'Levels'}</span>
        <p>Stop {cell(row.stop_loss ?? row.invalidation)} • TP1 {cell(row.tp1)} • TP2 {cell(row.tp2)}</p>
      </div>
    </div>
  );
}

function ResearchView({ payload }: { payload: ResearchPayload }) {
  const decision = payload.decision_card as Record<string, unknown> | undefined;
  const unifiedDecision = payload.unified_decision;
  const scanner = payload.scanner_row;
  const regularView = payload.regular_investing_view as Record<string, unknown> | undefined;
  const fallbackDecision: UnifiedDecision = {
    ticker: String(payload.ticker ?? 'Unknown'),
    actionability_label: 'Data Insufficient',
    level_status: 'Hidden',
  };
  return (
    <div className="grid">
      <Panel title="Decision Synthesis">
        <div className="provider-title">
          <div>
            <span className="eyebrow">Final decision</span>
            <h3>{String(unifiedDecision?.ticker ?? payload.ticker ?? 'Unknown')}</h3>
            <p>{String(unifiedDecision?.actionability_label ?? unifiedDecision?.primary_action ?? decision?.research_recommendation ?? scanner?.status_label ?? 'Data Insufficient')}</p>
          </div>
          <div className="score-stack compact">
            <strong>{Math.round(Number(unifiedDecision?.actionability_score ?? unifiedDecision?.score ?? 0))}</strong>
            <span>Actionability</span>
          </div>
        </div>
        <div className="pill-row">
          <StatusPill status={unifiedDecision?.actionability_label ?? unifiedDecision?.primary_action} />
          <Chip tone={String(unifiedDecision?.risk_level).includes('High') ? 'warn' : 'neutral'}>{unifiedDecision?.risk_level ?? 'Risk n/a'}</Chip>
          <Chip tone="neutral">State: {unifiedDecision?.current_setup_state ?? 'Unknown'}</Chip>
          <Chip tone="neutral">Evidence: {unifiedDecision?.evidence_pill ?? 'Not enough evidence'}</Chip>
        </div>
        <p>{String(decision?.why_this_recommendation ?? unifiedDecision?.actionability_reason ?? unifiedDecision?.reason ?? 'Deterministic scanner output remains primary.')}</p>
        <div className="brief-grid">
          <div>
            <span className="eyebrow">Why now</span>
            <p>{unifiedDecision?.actionability_reason ?? unifiedDecision?.reason ?? 'No current setup explanation returned.'}</p>
          </div>
          <div>
            <span className="eyebrow">Why not</span>
            <p>{unifiedDecision?.why_not ?? 'No major counter-thesis beyond routine review discipline.'}</p>
          </div>
        </div>
        <LevelPreview row={unifiedDecision ?? fallbackDecision} />
        <KeyValue payload={{
          trigger_or_entry: unifiedDecision?.trigger_needed ? unifiedDecision?.action_trigger : unifiedDecision?.entry_zone,
          stop_or_invalidation: unifiedDecision?.stop_loss ?? unifiedDecision?.invalidation ?? payload.invalidation,
          tp1: unifiedDecision?.level_status === 'Actionable' ? unifiedDecision?.tp1 : undefined,
          tp2: unifiedDecision?.level_status === 'Actionable' ? unifiedDecision?.tp2 : undefined,
          events_to_watch: unifiedDecision?.events_to_watch ?? payload.events_to_watch,
          data_quality: payload.price_sanity?.price_validation_status === 'PASS' ? 'Validated live price' : payload.price_sanity?.price_validation_reason,
        }} />
        {scanner && scanner.price_validation_status === 'PASS' ? <TrackPredictionButton scannerRow={scanner} /> : null}
      </Panel>
      <Panel title="Chart And EMA / Volume Signals">
        <MarketChartPanel
          chart={payload.chart ?? emptyChartPayload()}
          decision={unifiedDecision ?? fallbackDecision}
          timeframe={(payload.chart?.selected_timeframe as '3M' | '6M' | '1Y' | '2Y' | undefined) ?? '1Y'}
          onTimeframeChange={() => undefined}
        />
      </Panel>
      <div className="grid two">
        <Panel title="Price Validation">
          <KeyValue payload={{
            live_quote: payload.price_sanity?.quote_price_if_available,
            latest_close: payload.price_sanity?.latest_available_close,
            displayed_price: payload.price_sanity?.displayed_price,
            mismatch_pct: payload.price_sanity?.price_mismatch_pct,
            source: payload.price_sanity?.validated_price_source ?? payload.price_sanity?.price_source,
            latest_market_date: payload.price_sanity?.last_market_date,
            validation_status: payload.price_sanity?.price_validation_status,
          }} />
          {payload.price_sanity?.price_validation_status !== 'PASS' && <Notice tone="bad">Do not use TP/SL levels. Price validation failed.</Notice>}
        </Panel>
        <Panel title="Core Investing">
          <KeyValue payload={{
            score: regularView?.regular_investing_score ?? scanner?.regular_investing_score,
            action: regularView?.investing_action_label ?? scanner?.investing_action_label,
            style: regularView?.investing_style ?? scanner?.investing_style,
            risk: regularView?.investing_risk ?? scanner?.investing_risk,
            horizon: regularView?.investing_time_horizon ?? scanner?.investing_time_horizon,
            thesis_quality: regularView?.thesis_quality ?? scanner?.thesis_quality,
          }} />
        </Panel>
        <Panel title="Outlier">
          <KeyValue payload={{
            outlier_score: scanner?.outlier_score ?? payload.outlier_score,
            setup_quality: scanner?.setup_quality_score ?? payload.setup_quality,
            bull_case: payload.bull_case ?? scanner?.why_it_passed,
            bear_case: payload.bear_case ?? scanner?.why_it_could_fail,
            catalyst: payload.catalyst_news_social_summary,
          }} />
        </Panel>
        <Panel title="Velocity">
          <KeyValue payload={{
            velocity_score: scanner?.velocity_score,
            velocity_type: scanner?.velocity_type,
            trigger_reason: scanner?.trigger_reason,
            chase_warning: scanner?.chase_warning,
          }} />
        </Panel>
        <Panel title="Portfolio">
          <KeyValue payload={{ portfolio_context: payload.portfolio_context, journal_history: payload.journal_history }} />
        </Panel>
        <Panel title="AI">
          <KeyValue payload={{
            recommended_next_step: decision?.next_review_trigger,
            what_would_change: decision?.what_would_change_the_recommendation,
            safety: decision?.safety,
          }} />
        </Panel>
        <Panel title="Evidence">
          <ValidationContextCard context={payload.validation_context} />
        </Panel>
        <Panel title="Events To Watch">
          <KeyValue payload={{
            events_to_watch: unifiedDecision?.events_to_watch ?? payload.events_to_watch,
            key_risks: payload.key_risks ?? scanner?.warnings,
            alt_data_quality: scanner?.alternative_data_quality,
          }} />
        </Panel>
        <Panel title="Alt Data">
          <div className="alt-grid">
            <InsiderActivityCard row={scanner} />
            <PoliticianActivityCard row={scanner} />
          </div>
        </Panel>
      </div>
    </div>
  );
}

function TrackPredictionButton({ scannerRow }: { scannerRow: ScannerRow }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="secondary" onClick={() => setOpen(true)} type="button">Track</button>
      {open ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="modal-card">
            <div className="provider-title">
              <div>
                <strong>Track {scannerRow.ticker}</strong>
                <span>Save one paper-tracking record without the inline form clutter.</span>
              </div>
              <button className="ghost" onClick={() => setOpen(false)} type="button">Close</button>
            </div>
            <PaperTrackingForm scannerRow={scannerRow} onSaved={() => setOpen(false)} />
          </div>
        </div>
      ) : null}
    </>
  );
}

function PaperTrackingForm({ scannerRow, compact = false, onSaved }: { scannerRow: ScannerRow; compact?: boolean; onSaved?: () => void }) {
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
      onSaved?.();
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Could not save prediction'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className={compact ? 'paper-form compact' : 'paper-form'} onSubmit={submit}>
      <strong>Track this idea</strong>
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

function filterCockpitRows(rows: UnifiedDecision[], view: CockpitView) {
  const actionable = rows.filter((row) => row.actionability_label === 'Actionable Today' || row.actionability_label === 'Research First');
  if (view === 'Top') return actionable.slice(0, 24);
  if (view === 'Movers') return rows.filter((row) => (row.source_groups ?? [row.source_group]).includes('Movers'));
  if (view === 'Tracked') return rows.filter((row) => (row.source_groups ?? [row.source_group]).includes('Tracked'));
  if (view === 'Broad') return rows.filter((row) => (row.source_groups ?? [row.source_group]).includes('Broad') && !(row.source_groups ?? [row.source_group]).includes('Tracked'));
  if (view === 'Watch') return rows.filter((row) => row.actionability_label === 'Wait for Better Entry' || row.actionability_label === 'Watch for Trigger');
  if (view === 'Avoid') return rows.filter((row) => row.actionability_label === 'Avoid / Do Not Chase');
  return rows;
}

function filterSignalRows(rows: SignalTableRow[], view: CockpitView) {
  if (view === 'All') return rows;
  if (view === 'Top') return rows.filter((row) => ['Actionable Today', 'Research First'].includes(String(row.actionability)));
  if (view === 'Watch') return rows.filter((row) => ['Wait for Better Entry', 'Watch for Trigger'].includes(String(row.actionability)));
  if (view === 'Avoid') return rows.filter((row) => String(row.actionability) === 'Avoid / Do Not Chase');
  if (view === 'Movers') return rows.filter((row) => String(row.source).includes('Movers'));
  if (view === 'Tracked') return rows.filter((row) => String(row.source).includes('Tracked'));
  if (view === 'Broad') return rows.filter((row) => String(row.source).includes('Broad'));
  return rows;
}

async function waitForScanResult(jobId: string, onStatus: (status: ScanJobStatus) => void): Promise<ScanState> {
  for (let attempt = 0; attempt < 180; attempt += 1) {
    const status = await api.scanStatus(jobId);
    onStatus(status);
    if (status.status === 'completed') {
      return api.scanResult(jobId) as Promise<ScanState>;
    }
    if (status.status === 'failed') {
      throw new Error(status.error || 'Background scan failed.');
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
  throw new Error('Background scan timed out before results were ready.');
}

function shortCompanyName(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return '';
  return trimmed
    .replace(/\b(Inc\.?|Corporation|Corp\.?|Holdings?|Group|Company|Co\.?|Technologies|Technology|International|Systems|Limited|Ltd\.?)\b/gi, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function compactDate(value?: string) {
  if (!value || value === 'unavailable') return 'Unavailable';
  return value.replace('T', ' ').replace('Z', '').slice(0, 16);
}

function shortAction(value: unknown) {
  const text = String(value ?? '');
  if (text.includes('Actionable')) return 'Actionable';
  if (text.includes('Research')) return 'Research';
  if (text.includes('Wait')) return 'Wait';
  if (text.includes('Avoid')) return 'Avoid';
  if (text.includes('Data')) return 'Data';
  return text || 'n/a';
}

function money(value: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value || 0);
}

function pct(value: unknown) {
  if (value === null || value === undefined || value === '' || value === 'unavailable') return 'n/a';
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return `${numeric >= 0 ? '+' : ''}${numeric.toFixed(2)}%`;
}

function pctTone(value: unknown) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return '';
  return numeric > 0 ? 'positive' : numeric < 0 ? 'negative' : '';
}

function labelWeight(value: unknown) {
  return {
    'Actionable Today': 5,
    'Research First': 4,
    'Wait for Better Entry': 3,
    'Watch for Trigger': 2,
    'Avoid / Do Not Chase': 1,
    'Data Insufficient': 0,
  }[String(value ?? '')] ?? 0;
}

function labelize(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase());
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

function PriceSanityBadge({ payload }: { payload?: { price_warning?: string; price_source?: string; price_timestamp?: string; price_confidence?: string; validated_price_source?: string; price_validation_status?: string } | null }) {
  if (!payload) return null;
  const tone = payload.price_validation_status === 'PASS'
    ? 'good'
    : payload.price_validation_status === 'WARN'
      ? 'warn'
      : String(payload.price_warning).includes('Sample') || String(payload.price_warning).includes('Stale')
        ? 'warn'
        : 'bad';
  return (
    <div className="pill-row">
      <Chip tone={tone}>
        {payload.validated_price_source ?? payload.price_source ?? 'Price source unavailable'}
      </Chip>
      <Chip tone="neutral">{compactDate(payload.price_timestamp)}</Chip>
      <Chip tone="neutral">{payload.price_validation_status ?? payload.price_confidence ?? 'Confidence n/a'}</Chip>
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
