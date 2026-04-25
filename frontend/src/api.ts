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
  configured: boolean;
  required: boolean;
  required_env_vars: string[];
  missing_env_vars_list: string[];
  capabilities: string;
  degraded_when_missing: string;
  setup: string;
  url: string;
  notes: string;
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
export type PredictionRow = { prediction_id?: string; ticker?: string; outcome_label?: string; final_combined_recommendation?: string; return_20d?: string };
export type JournalPayload = { entries: Record<string, string>[]; stats: Record<string, unknown> };
export type ArchiveReport = { path: string; name: string; modified_at: string };
