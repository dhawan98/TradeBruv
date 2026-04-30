const EXPLICIT_API_BASE_URL = (import.meta.env.VITE_TRADEBRUV_API_URL ?? '').trim().replace(/\/$/, '');

const DEFAULT_TIMEOUT_MS = 15_000;
const LONG_TIMEOUT_MS = 90_000;

export type ApiErrorKind =
  | 'disconnected'
  | 'wrong_api_url'
  | 'backend_error'
  | 'request_timeout'
  | 'http_error';

export class ApiError extends Error {
  status: number;
  kind: ApiErrorKind;
  endpoint: string;
  apiBaseUrl: string;
  causeText: string;
  suggestedFix: string;
  backendBody?: unknown;

  constructor({
    status,
    kind,
    endpoint,
    apiBaseUrl,
    causeText,
    suggestedFix,
    backendBody,
  }: {
    status: number;
    kind: ApiErrorKind;
    endpoint: string;
    apiBaseUrl: string;
    causeText: string;
    suggestedFix: string;
    backendBody?: unknown;
  }) {
    super(causeText);
    this.status = status;
    this.kind = kind;
    this.endpoint = endpoint;
    this.apiBaseUrl = apiBaseUrl;
    this.causeText = causeText;
    this.suggestedFix = suggestedFix;
    this.backendBody = backendBody;
  }
}

type RequestOptions = {
  timeoutMs?: number;
};

function resolveApiUrl(path: string) {
  return EXPLICIT_API_BASE_URL ? `${EXPLICIT_API_BASE_URL}${path}` : path;
}

export function getApiBaseUrl() {
  if (EXPLICIT_API_BASE_URL) return EXPLICIT_API_BASE_URL;
  if (typeof window !== 'undefined') return `${window.location.origin} (same-origin /api proxy)`;
  return 'same-origin /api proxy';
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export async function request<T>(path: string, init?: RequestInit, options?: RequestOptions): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = options?.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const endpoint = path;
  const apiBaseUrl = getApiBaseUrl();

  try {
    const response = await fetch(resolveApiUrl(path), {
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
      ...init,
      signal: controller.signal,
    });

    if (!response.ok) {
      const parsedBody = await parseErrorBody(response);
      const causeText = parsedBody.message || response.statusText || 'Backend request failed.';
      const kind = response.status >= 500 ? 'backend_error' : response.status === 404 && path === '/api/health' ? 'wrong_api_url' : 'http_error';
      throw new ApiError({
        status: response.status,
        kind,
        endpoint,
        apiBaseUrl,
        causeText,
        suggestedFix: suggestionFor(kind, response.status),
        backendBody: parsedBody.raw,
      });
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError({
        status: 0,
        kind: 'request_timeout',
        endpoint,
        apiBaseUrl,
        causeText: `Request timed out after ${Math.round(timeoutMs / 1000)}s.`,
        suggestedFix: 'Retry the request. If it keeps timing out, confirm the backend is running and the selected provider is not hanging.',
      });
    }

    const kind: ApiErrorKind = EXPLICIT_API_BASE_URL ? 'wrong_api_url' : 'disconnected';
    throw new ApiError({
      status: 0,
      kind,
      endpoint,
      apiBaseUrl,
      causeText: EXPLICIT_API_BASE_URL
        ? 'Browser could not reach the configured API base URL.'
        : 'Browser could not reach the TradeBruv backend.',
      suggestedFix: EXPLICIT_API_BASE_URL
        ? 'Check VITE_TRADEBRUV_API_URL, the backend host/port, and any local CORS mismatch.'
        : 'Start the backend on port 8000, or verify the Vite proxy is forwarding /api requests.',
      backendBody: String(error),
    });
  } finally {
    clearTimeout(timeout);
  }
}

async function parseErrorBody(response: Response): Promise<{ message: string; raw: unknown }> {
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    try {
      const payload = (await response.json()) as { detail?: string; message?: string; error?: string };
      return {
        message: payload.detail ?? payload.message ?? payload.error ?? response.statusText,
        raw: payload,
      };
    } catch {
      return { message: response.statusText || 'Backend returned invalid JSON.', raw: null };
    }
  }

  try {
    const text = await response.text();
    return { message: text || response.statusText || 'Backend returned an empty error body.', raw: text };
  } catch {
    return { message: response.statusText || 'Backend request failed.', raw: null };
  }
}

function suggestionFor(kind: ApiErrorKind, status: number) {
  if (kind === 'backend_error') return 'Inspect the backend logs for the failing endpoint, then retry after fixing the root cause.';
  if (kind === 'wrong_api_url') return 'Check the API base URL and confirm it points at the FastAPI server, not the Vite frontend.';
  if (kind === 'request_timeout') return 'Retry the request. If it still times out, try a smaller universe or confirm the provider is healthy.';
  if (status === 404) return 'Check that the backend exposes this endpoint and that the API base URL is correct.';
  return 'Retry after checking backend health and local port configuration.';
}

export const api = {
  health: () => request<HealthPayload>('/api/health'),
  universes: () => request<UniversesPayload>('/api/universes'),
  dataSources: () => request<DataSourcesPayload>('/api/data-sources'),
  createEnvTemplate: () => request<EnvCreatePayload>('/api/env/create-template', { method: 'POST', body: '{}' }),
  updateLocalEnv: (values: Record<string, string>) =>
    request<EnvUpdatePayload>('/api/env/update-local', { method: 'POST', body: JSON.stringify({ values }) }),
  dailyDecisionLatest: () => request<DecisionSnapshotPayload>('/api/daily-decision/latest'),
  chart: (ticker: string, provider = 'sample', timeframe = '1Y') =>
    request<ChartPayload>(`/api/chart/${encodeURIComponent(ticker)}?provider=${encodeURIComponent(provider)}&timeframe=${encodeURIComponent(timeframe)}`),
  tracked: () => request<TrackedPayload>('/api/tracked'),
  trackedAdd: (ticker: string) =>
    request<TrackedPayload>('/api/tracked/add', { method: 'POST', body: JSON.stringify({ ticker }) }),
  trackedRemove: (ticker: string) =>
    request<TrackedPayload>('/api/tracked/remove', { method: 'POST', body: JSON.stringify({ ticker }) }),
  latestReport: () => request<LatestReport>('/api/reports/latest'),
  reportsArchive: () => request<{ reports: ArchiveReport[] }>('/api/reports/archive'),
  dailySummary: () => request<Record<string, unknown>>('/api/daily-summary'),
  alerts: () => request<AlertRow[]>('/api/alerts'),
  portfolio: () => request<PortfolioPayload>('/api/portfolio'),
  scan: (payload: Record<string, unknown>) =>
    request<ScanPayload>('/api/scan', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  startScan: (payload: Record<string, unknown>) =>
    request<ScanJobStatus>('/api/scan/start', { method: 'POST', body: JSON.stringify(payload) }),
  scanStatus: (jobId: string) =>
    request<ScanJobStatus>(`/api/scan/status/${encodeURIComponent(jobId)}`),
  scanResult: (jobId: string) =>
    request<ScanPayload>(`/api/scan/result/${encodeURIComponent(jobId)}`, undefined, { timeoutMs: LONG_TIMEOUT_MS }),
  deepResearch: (payload: Record<string, unknown>) =>
    request<ResearchPayload>('/api/deep-research', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  portfolioAnalyze: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/portfolio/analyze', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  aiCommittee: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/ai-committee', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  predictions: () => request<PredictionRow[]>('/api/predictions'),
  predictionsSummary: () => request<Record<string, unknown>>('/api/predictions/summary'),
  addPrediction: (payload: Record<string, unknown>) =>
    request<PredictionRow>('/api/predictions', { method: 'POST', body: JSON.stringify(payload) }),
  updatePredictions: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/predictions/update', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  caseStudy: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/case-study', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  runReplay: (payload: Record<string, unknown>) =>
    request<ReplayPayload>('/api/replay/run', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  latestReplay: (mode = 'outliers') => request<ReplayPayload>(`/api/replay/latest?mode=${encodeURIComponent(mode)}`),
  runInvestingReplay: (payload: Record<string, unknown>) =>
    request<ReplayPayload>('/api/investing-replay/run', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  latestInvestingReplay: () => request<ReplayPayload>('/api/investing-replay/latest'),
  runPortfolioReplay: (payload: Record<string, unknown>) =>
    request<ReplayPayload>('/api/portfolio-replay/run', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  latestPortfolioReplay: () => request<ReplayPayload>('/api/portfolio-replay/latest'),
  runOutlierStudy: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/outlier-study/run', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  runProofReport: (payload: Record<string, unknown>) =>
    request<ProofReport>('/api/proof-report/run', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  latestProofReport: () => request<ProofReport>('/api/proof-report/latest'),
  runInvestingProofReport: (payload: Record<string, unknown>) =>
    request<ProofReport>('/api/investing-proof-report/run', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  latestInvestingProofReport: () => request<ProofReport>('/api/investing-proof-report/latest'),
  doctorLatest: () => request<WorkflowReport>('/api/doctor/latest'),
  runDoctor: (payload: Record<string, unknown>) =>
    request<WorkflowReport>('/api/doctor/run', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  readinessLatest: () => request<WorkflowReport>('/api/readiness/latest'),
  runReadiness: (payload: Record<string, unknown>) =>
    request<WorkflowReport>('/api/readiness/run', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  appStatusLatest: () => request<AppStatusReport>('/api/app-status/latest'),
  runAppStatus: () => request<AppStatusReport>('/api/app-status/run', { method: 'POST', body: '{}' }, { timeoutMs: LONG_TIMEOUT_MS }),
  signalAuditLatest: () => request<WorkflowReport>('/api/signal-audit/latest'),
  runSignalAudit: (payload: Record<string, unknown>) =>
    request<WorkflowReport>('/api/signal-audit/run', { method: 'POST', body: JSON.stringify(payload) }, { timeoutMs: LONG_TIMEOUT_MS }),
  journal: () => request<JournalPayload>('/api/journal'),
  addJournal: (payload: Record<string, unknown>) =>
    request<JournalPayload>('/api/journal', { method: 'POST', body: JSON.stringify(payload) }),
};

export type PriceSanity = {
  data_mode?: string;
  price_source?: string;
  price_timestamp?: string;
  provider?: string;
  provider_is_live_capable?: boolean;
  is_sample_data?: boolean;
  is_adjusted_price?: boolean;
  is_stale_price?: boolean;
  is_replay?: boolean;
  is_case_study?: boolean;
  is_report_only?: boolean;
  is_stale?: boolean;
  last_market_date?: string;
  latest_available_close?: number | string;
  quote_price_if_available?: number | string;
  validated_price?: number | string;
  validated_price_source?: string;
  displayed_price?: number | string;
  price_mismatch_pct?: number | string;
  possible_split_adjustment_mismatch?: boolean;
  price_validation_status?: 'PASS' | 'WARN' | 'FAIL' | string;
  price_validation_reason?: string;
  has_validated_live_price?: boolean;
  levels_allowed?: boolean;
  price_warning?: string;
  price_confidence?: string;
  scan_is_stale?: boolean;
};

export type UnifiedDecision = {
  ticker: string;
  company?: string;
  primary_action?: string;
  action_lane?: string;
  source_group?: string;
  source_groups?: string[];
  best_source_group?: string;
  valid_source_groups?: string[];
  failed_source_groups?: string[];
  merge_warnings?: string[];
  has_conflicting_source_rows?: boolean;
  score?: number;
  actionability_score?: number;
  actionability_label?: string;
  actionability_reason?: string;
  actionability_blockers?: string[];
  action_trigger?: string;
  trigger_needed?: boolean;
  current_setup_state?: string;
  level_status?: 'Actionable' | 'Preliminary' | 'Conditional' | 'Hidden' | string;
  entry_label?: string;
  levels_explanation?: string;
  evidence_pill?: string;
  confidence_label?: string;
  evidence_strength?: string;
  risk_level?: string;
  entry_zone?: string;
  stop_loss?: number | string;
  invalidation?: number | string;
  tp1?: number | string;
  tp2?: number | string;
  reward_risk?: number | string;
  holding_horizon?: string;
  reason?: string;
  why_not?: string;
  events_to_watch?: string[];
  data_quality?: unknown;
  data_freshness?: string;
  price_source?: string;
  latest_market_date?: string;
  price_validation_status?: string;
  price_validation_reason?: string;
  is_actionable?: boolean;
  is_conditional?: boolean;
  is_preliminary?: boolean;
  price_sanity?: PriceSanity;
  next_review_date?: string;
  portfolio_context?: Record<string, unknown> | null;
  validation_context?: ValidationContext;
  source_row?: ScannerRow;
  decision_notices?: DecisionNotice[];
};

export type DecisionNotice = {
  severity: 'critical' | 'warning' | 'info' | 'debug' | string;
  message: string;
};

export type ValidationContext = {
  evidence_strength?: string;
  real_money_reliance?: boolean;
  language_note?: string;
  messages?: string[];
  proof_report_path?: string | null;
  signal_quality_path?: string | null;
};

export type HealthPayload = {
  ok: boolean;
  provider: string;
  mode: string;
  last_scan_time: string;
  data_source_health: { providers: number; required_missing: number; optional_ready: number; optional_missing: number };
  ai: { any_configured: boolean; configured: string[] };
  portfolio_value: number;
  alert_count: number;
  local_env_editor_enabled: boolean;
};

export type DataSourceRow = {
  name: string;
  category: string;
  tier?: string;
  recommended_priority?: number;
  configured: boolean;
  required: boolean;
  required_env_vars: string[];
  missing_env_vars_list: string[];
  capabilities: string;
  degraded_when_missing: string;
  setup: string;
  url: string;
  notes: string;
  quota_notes?: string;
  last_checked: string;
};

export type UniverseItem = { label: string; path: string; description: string; available: boolean };
export type UniversesPayload = { items: UniverseItem[]; warning: string; home_defaults: string[] };

export type DataSourcesPayload = {
  rows: DataSourceRow[];
  summary: HealthPayload['data_source_health'] & { degraded_capabilities: string[] };
  local_env_editor_enabled: boolean;
  local_env_warning: string;
};

export type EnvCreatePayload = { created: boolean; exists: boolean; message: string; path: string };
export type EnvUpdatePayload = { updated: boolean; updated_keys: string[]; message: string };

export type ScannerRow = PriceSanity & {
  ticker: string;
  company_name?: string;
  current_price?: number;
  price_change_1d_pct?: number | string;
  price_change_5d_pct?: number | string;
  ema_21?: number | string;
  ema_50?: number | string;
  ema_150?: number | string;
  ema_200?: number | string;
  ema_stack?: string;
  relative_volume_20d?: number | string;
  relative_volume_50d?: number | string;
  volume_signal?: string;
  trend_signal?: string;
  pullback_signal?: string;
  breakout_signal?: string;
  distribution_signal?: string;
  signal_summary?: string;
  signal_grade?: string;
  signal_explanation?: string;
  winner_score?: number;
  outlier_score?: number;
  risk_score?: number;
  setup_quality_score?: number;
  status_label?: string;
  outlier_type?: string;
  outlier_risk?: string;
  outlier_reason?: string;
  strategy_label?: string;
  confidence_label?: string;
  entry_zone?: string;
  invalidation_level?: number | string;
  stop_loss_reference?: number | string;
  tp1?: number | string;
  tp2?: number | string;
  reward_risk?: number | string;
  warnings?: string[];
  why_it_passed?: string[];
  why_it_could_fail?: string[];
  alternative_data_summary?: string;
  alternative_data_quality?: string;
  alternative_data_source_count?: number;
  insider_buy_count?: number;
  insider_sell_count?: number;
  net_insider_value?: number;
  CEO_CFO_buy_flag?: boolean;
  cluster_buying_flag?: boolean;
  heavy_insider_selling_flag?: boolean;
  politician_buy_count?: number;
  politician_sell_count?: number;
  net_politician_value?: number;
  recent_politician_activity?: boolean;
  disclosure_lag_warning?: string;
  alternative_data_confirmed_by_price_volume?: boolean;
  alternative_data_warnings?: string[];
  velocity_score?: number;
  velocity_type?: string;
  velocity_risk?: string;
  trigger_reason?: string;
  chase_warning?: string;
  quick_trade_watch_label?: string;
  velocity_invalidation?: number | string;
  velocity_tp1?: number | string;
  velocity_tp2?: number | string;
  expected_horizon?: string;
  regular_investing_score?: number;
  investing_style?: string;
  investing_risk?: string;
  investing_time_horizon?: string;
  investing_action_label?: string;
  investing_reason?: string;
  investing_bear_case?: string;
  investing_invalidation?: string;
  investing_events_to_watch?: string[];
  value_trap_warning?: string;
  thesis_quality?: string;
  investing_data_quality?: string;
};

export type ScanPayload = {
  available?: boolean;
  generated_at: string;
  provider: string;
  mode: string;
  data_mode?: string;
  demo_mode?: boolean;
  report_snapshot?: boolean;
  stale_data?: boolean;
  results: ScannerRow[];
  summary: Record<string, unknown>;
  market_regime: Record<string, unknown>;
  decisions?: UnifiedDecision[];
  data_issues?: UnifiedDecision[];
  validation_context?: ValidationContext;
  scan_failures?: { ticker?: string; reason?: string; category?: string }[];
  provider_health?: Record<string, unknown>;
  scan_health?: Record<string, unknown>;
  cache_stats?: Record<string, unknown>;
};

export type ScanJobStatus = {
  available?: boolean;
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'missing' | string;
  attempted?: number;
  scanned?: number;
  failed?: number;
  provider_health?: Record<string, unknown>;
  current_batch?: string;
  error?: string;
};

export type LatestReport = ScanPayload & { available: boolean; path?: string };
export type DecisionSnapshotPayload = ScanPayload & {
  available: boolean;
  path?: string;
  json_path?: string;
  markdown_path?: string;
  quality_review_path?: string;
  top_candidate?: UnifiedDecision | null;
  overall_top_candidate?: UnifiedDecision | null;
  best_tracked_setup?: UnifiedDecision | null;
  best_broad_setup?: UnifiedDecision | null;
  best_mover_setup?: UnifiedDecision | null;
  research_candidates?: UnifiedDecision[];
  watch_candidates?: UnifiedDecision[];
  avoid_candidates?: UnifiedDecision[];
  portfolio_actions?: UnifiedDecision[];
  compact_board?: UnifiedDecision[];
  tracked_watchlist_table?: SignalTableRow[];
  broad_scan_top_table?: SignalTableRow[];
  movers_table?: SignalTableRow[];
  signal_table?: SignalTableRow[];
  no_clean_candidate_reason?: string;
  data_coverage_status?: Record<string, unknown>;
  workspace?: WorkspacePayload;
};
export type ResearchPayload = Record<string, unknown> & {
  scanner_row?: ScannerRow;
  decision_card?: Record<string, unknown>;
  price_sanity?: PriceSanity;
  unified_decision?: UnifiedDecision;
  validation_context?: ValidationContext;
  chart?: ChartPayload;
};
export type SignalTableRow = {
  ticker?: string;
  source?: string;
  price?: number | string;
  price_change_1d_pct?: number | string;
  price_change_5d_pct?: number | string;
  relative_volume_20d?: number | string;
  ema_stack?: string;
  signal?: string;
  signal_explanation?: string;
  actionability?: string;
  risk?: string;
  entry_or_trigger?: string;
  stop?: number | string;
  tp1?: number | string;
  updated?: string;
};
export type ChartPoint = {
  date: string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
  ema_21?: number | null;
  ema_50?: number | null;
  ema_150?: number | null;
  ema_200?: number | null;
};
export type ChartPayload = {
  available?: boolean;
  ticker: string;
  provider?: string;
  last_market_date?: string;
  quote_timestamp?: string;
  price_source?: string;
  selected_timeframe?: string;
  available_timeframes?: string[];
  series: ChartPoint[];
  markers?: { date: string; label: string; tone: string }[];
  signals?: Record<string, unknown>;
  demo_mode?: boolean;
  cache?: Record<string, unknown>;
  reason?: string;
};
export type WorkspacePayload = {
  selected_ticker?: string;
  canonical_rows?: UnifiedDecision[];
  top_candidates?: UnifiedDecision[];
  tracked_rows?: UnifiedDecision[];
  broad_rows?: UnifiedDecision[];
  mover_rows?: UnifiedDecision[];
  watch_rows?: UnifiedDecision[];
  avoid_rows?: UnifiedDecision[];
  signal_table_rows?: SignalTableRow[];
  decision_by_ticker?: Record<string, UnifiedDecision>;
  chart_data_by_ticker?: Record<string, ChartPayload>;
  coverage_status?: Record<string, unknown>;
  data_issues?: UnifiedDecision[];
  view_counts?: Record<string, number>;
  status_bar?: Record<string, unknown>;
  source_aware_top?: {
    overall_top_setup?: UnifiedDecision | null;
    best_tracked_setup?: UnifiedDecision | null;
    best_broad_setup?: UnifiedDecision | null;
    best_mover_setup?: UnifiedDecision | null;
  };
  selected_ticker_consistency_status?: 'PASS' | 'FAIL' | string;
  selected_ticker_consistency_reason?: string;
};
export type TrackedPayload = {
  path: string;
  tickers: string[];
  count: number;
  message: string;
};
export type AlertRow = { ticker?: string; severity?: string; alert_type?: string; explanation?: string; recommended_action_label?: string };
export type PositionRow = { ticker: string; company_name?: string; market_value?: number; position_weight_pct?: number; unrealized_gain_loss_pct?: number; decision_status?: string };
export type PortfolioPayload = { positions: PositionRow[]; summary: Record<string, number | string | unknown[]> };
export type PredictionRow = {
  prediction_id?: string;
  ticker?: string;
  outcome_label?: string;
  final_combined_recommendation?: string;
  return_20d?: string;
  next_review_date?: string;
  hit_TP1?: string;
  hit_TP2?: string;
  hit_invalidation?: string;
};
export type JournalPayload = { entries: Record<string, string>[]; stats: Record<string, unknown> };
export type ArchiveReport = { path: string; name: string; modified_at: string };
export type WorkflowCheck = { name?: string; status?: string; mode?: string; message?: string };
export type WorkflowReport = {
  available?: boolean;
  kind?: string;
  generated_at?: string;
  status?: string;
  message?: string;
  summary?: Record<string, number>;
  checks?: WorkflowCheck[];
  conclusion?: string;
  ready_for_paper_tracking?: boolean;
  ready_for_manual_research_use?: boolean;
  ready_for_real_money_reliance?: boolean;
};
export type AppStatusReport = {
  available?: boolean;
  markdown?: string;
  working_features?: string[];
  degraded_or_missing_features?: string[];
  live_tested_providers?: string[];
  mock_only_providers?: string[];
  openai_works?: boolean;
  gemini_works?: boolean;
  validation_sample_enough?: boolean;
};
export type ReplayPayload = {
  available?: boolean;
  mode?: string;
  summary?: Record<string, unknown>;
  results?: Record<string, unknown>[];
  replay_scans?: Record<string, unknown>[];
  point_in_time_limitations?: string;
  json_path?: string;
  summary_markdown_path?: string;
};
export type ProofReport = {
  available?: boolean;
  evidence_strength?: string;
  real_money_reliance?: boolean;
  language_note?: string;
  answers?: Record<string, unknown>;
  historical_replay?: Record<string, unknown>;
  velocity_replay?: Record<string, unknown> | null;
  famous_outliers?: Record<string, unknown> | null;
};
