const API_URL = import.meta.env.VITE_TRADEBRUV_API_URL ?? 'http://localhost:8000';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      message = payload.detail ?? message;
    } catch {
      // Keep status text when the backend returns non-JSON errors.
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthPayload>('/api/health'),
  dataSources: () => request<DataSourcesPayload>('/api/data-sources'),
  createEnvTemplate: () => request<EnvCreatePayload>('/api/env/create-template', { method: 'POST', body: '{}' }),
  updateLocalEnv: (values: Record<string, string>) =>
    request<EnvUpdatePayload>('/api/env/update-local', { method: 'POST', body: JSON.stringify({ values }) }),
  latestReport: () => request<LatestReport>('/api/reports/latest'),
  reportsArchive: () => request<{ reports: ArchiveReport[] }>('/api/reports/archive'),
  dailySummary: () => request<Record<string, unknown>>('/api/daily-summary'),
  alerts: () => request<AlertRow[]>('/api/alerts'),
  portfolio: () => request<PortfolioPayload>('/api/portfolio'),
  scan: (payload: Record<string, unknown>) => request<ScanPayload>('/api/scan', { method: 'POST', body: JSON.stringify(payload) }),
  deepResearch: (payload: Record<string, unknown>) =>
    request<ResearchPayload>('/api/deep-research', { method: 'POST', body: JSON.stringify(payload) }),
  portfolioAnalyze: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/portfolio/analyze', { method: 'POST', body: JSON.stringify(payload) }),
  aiCommittee: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/ai-committee', { method: 'POST', body: JSON.stringify(payload) }),
  predictions: () => request<PredictionRow[]>('/api/predictions'),
  predictionsSummary: () => request<Record<string, unknown>>('/api/predictions/summary'),
  addPrediction: (payload: Record<string, unknown>) =>
    request<PredictionRow>('/api/predictions', { method: 'POST', body: JSON.stringify(payload) }),
  updatePredictions: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/predictions/update', { method: 'POST', body: JSON.stringify(payload) }),
  caseStudy: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/case-study', { method: 'POST', body: JSON.stringify(payload) }),
  runReplay: (payload: Record<string, unknown>) =>
    request<ReplayPayload>('/api/replay/run', { method: 'POST', body: JSON.stringify(payload) }),
  latestReplay: (mode = 'outliers') => request<ReplayPayload>(`/api/replay/latest?mode=${encodeURIComponent(mode)}`),
  runInvestingReplay: (payload: Record<string, unknown>) =>
    request<ReplayPayload>('/api/investing-replay/run', { method: 'POST', body: JSON.stringify(payload) }),
  latestInvestingReplay: () => request<ReplayPayload>('/api/investing-replay/latest'),
  runPortfolioReplay: (payload: Record<string, unknown>) =>
    request<ReplayPayload>('/api/portfolio-replay/run', { method: 'POST', body: JSON.stringify(payload) }),
  latestPortfolioReplay: () => request<ReplayPayload>('/api/portfolio-replay/latest'),
  runOutlierStudy: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/outlier-study/run', { method: 'POST', body: JSON.stringify(payload) }),
  runProofReport: (payload: Record<string, unknown>) =>
    request<ProofReport>('/api/proof-report/run', { method: 'POST', body: JSON.stringify(payload) }),
  latestProofReport: () => request<ProofReport>('/api/proof-report/latest'),
  runInvestingProofReport: (payload: Record<string, unknown>) =>
    request<ProofReport>('/api/investing-proof-report/run', { method: 'POST', body: JSON.stringify(payload) }),
  latestInvestingProofReport: () => request<ProofReport>('/api/investing-proof-report/latest'),
  doctorLatest: () => request<WorkflowReport>('/api/doctor/latest'),
  runDoctor: (payload: Record<string, unknown>) =>
    request<WorkflowReport>('/api/doctor/run', { method: 'POST', body: JSON.stringify(payload) }),
  readinessLatest: () => request<WorkflowReport>('/api/readiness/latest'),
  runReadiness: (payload: Record<string, unknown>) =>
    request<WorkflowReport>('/api/readiness/run', { method: 'POST', body: JSON.stringify(payload) }),
  appStatusLatest: () => request<AppStatusReport>('/api/app-status/latest'),
  runAppStatus: () => request<AppStatusReport>('/api/app-status/run', { method: 'POST', body: '{}' }),
  signalAuditLatest: () => request<WorkflowReport>('/api/signal-audit/latest'),
  runSignalAudit: (payload: Record<string, unknown>) =>
    request<WorkflowReport>('/api/signal-audit/run', { method: 'POST', body: JSON.stringify(payload) }),
  journal: () => request<JournalPayload>('/api/journal'),
  addJournal: (payload: Record<string, unknown>) =>
    request<JournalPayload>('/api/journal', { method: 'POST', body: JSON.stringify(payload) }),
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

export type DataSourcesPayload = {
  rows: DataSourceRow[];
  summary: HealthPayload['data_source_health'] & { degraded_capabilities: string[] };
  local_env_editor_enabled: boolean;
  local_env_warning: string;
};

export type EnvCreatePayload = { created: boolean; exists: boolean; message: string; path: string };
export type EnvUpdatePayload = { updated: boolean; updated_keys: string[]; message: string };

export type ScannerRow = {
  ticker: string;
  company_name?: string;
  current_price?: number;
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
  generated_at: string;
  provider: string;
  mode: string;
  results: ScannerRow[];
  summary: Record<string, unknown>;
  market_regime: Record<string, unknown>;
};

export type LatestReport = ScanPayload & { available: boolean; path?: string };
export type ResearchPayload = Record<string, unknown> & { scanner_row?: ScannerRow; decision_card?: Record<string, unknown> };
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
