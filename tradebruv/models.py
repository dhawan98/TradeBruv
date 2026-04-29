from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class PriceBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class FundamentalsSnapshot:
    revenue_growth: float | None = None
    eps_growth: float | None = None
    margin_change: float | None = None
    free_cash_flow_growth: float | None = None
    analyst_revision_score: float | None = None
    guidance_improvement: bool | None = None
    profitability_positive: bool | None = None
    recent_dilution: bool | None = None
    earnings_beat: bool | None = None
    estimate_revision_trend: float | None = None
    institutional_support: bool | None = None


@dataclass(frozen=True)
class CatalystSnapshot:
    has_catalyst: bool | None = None
    description: str | None = None
    price_reaction_positive: bool | None = None
    volume_confirmation: bool | None = None
    holds_gains: bool | None = None
    hype_risk: bool | None = None
    catalyst_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalystItem:
    ticker: str
    source_type: str
    source_name: str | None = None
    source_url: str | None = None
    timestamp: str | None = None
    headline: str | None = None
    summary: str | None = None
    sentiment: str | None = None
    catalyst_type: str = "Unknown/unconfirmed"
    attention_count: int | None = None
    attention_velocity: float | None = None
    official_source: bool | None = None
    confidence: float | None = None
    notes: str | None = None
    source_platform: str | None = None
    official_or_verified: bool | None = None
    attention_spike: bool | None = None
    hype_risk: bool | None = None
    pump_risk: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "source_type": self.source_type,
            "source_name": self.source_name or "unavailable",
            "source_url": self.source_url or "unavailable",
            "timestamp": self.timestamp or "unavailable",
            "headline": self.headline or "unavailable",
            "summary": self.summary or "unavailable",
            "sentiment": self.sentiment or "unavailable",
            "catalyst_type": self.catalyst_type,
            "attention_count": _format_number(self.attention_count),
            "attention_velocity": _format_number(self.attention_velocity),
            "official_source": _format_bool(self.official_source),
            "confidence": _format_number(self.confidence),
            "notes": self.notes or "unavailable",
            "source_platform": self.source_platform or "unavailable",
            "official_or_verified": _format_bool(self.official_or_verified),
            "attention_spike": _format_bool(self.attention_spike),
            "hype_risk": _format_bool(self.hype_risk),
            "pump_risk": _format_bool(self.pump_risk),
        }


@dataclass(frozen=True)
class AlternativeDataItem:
    ticker: str
    source_type: str = "manual"
    source_name: str | None = None
    source_url: str | None = None
    timestamp: str | None = None
    actor_name: str | None = None
    actor_role: str = "Unknown"
    actor_type: str = "Unknown"
    transaction_type: str = "Unknown"
    shares: float | None = None
    estimated_value: float | None = None
    price: float | None = None
    filing_date: str | None = None
    transaction_date: str | None = None
    disclosure_lag_days: int | None = None
    confidence: float | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "source_type": self.source_type,
            "source_name": self.source_name or "unavailable",
            "source_url": self.source_url or "unavailable",
            "timestamp": self.timestamp or "unavailable",
            "actor_name": self.actor_name or "unavailable",
            "actor_role": self.actor_role,
            "actor_type": self.actor_type,
            "transaction_type": self.transaction_type,
            "shares": _format_number(self.shares),
            "estimated_value": _format_number(self.estimated_value),
            "price": _format_number(self.price),
            "filing_date": self.filing_date or "unavailable",
            "transaction_date": self.transaction_date or "unavailable",
            "disclosure_lag_days": self.disclosure_lag_days if self.disclosure_lag_days is not None else "unavailable",
            "confidence": _format_number(self.confidence),
            "notes": self.notes or "unavailable",
        }


@dataclass(frozen=True)
class ShortInterestSnapshot:
    short_interest_percent_float: float | None = None
    days_to_cover: float | None = None
    float_shares: float | None = None
    borrow_cost: float | None = None
    institutional_activity_positive: bool | None = None
    insider_activity_positive: bool | None = None


@dataclass(frozen=True)
class SocialAttentionSnapshot:
    reddit_mention_count: int | None = None
    twitter_mention_count: int | None = None
    truth_social_mention_flag: bool | None = None
    news_headline_count: int | None = None
    news_sentiment: float | None = None
    catalyst_source: str | None = None
    attention_velocity: float | None = None


@dataclass(frozen=True)
class OptionsSnapshot:
    options_interest_available: bool | None = None
    unusual_options_activity: bool | None = None
    options_daytrade_candidate: bool | None = None
    implied_volatility_warning: bool | None = None
    earnings_iv_risk: bool | None = None


@dataclass
class SecurityData:
    ticker: str
    company_name: str | None
    sector: str | None
    bars: list[PriceBar]
    industry: str | None = None
    market_cap: float | None = None
    ipo_date: date | None = None
    fundamentals: FundamentalsSnapshot | None = None
    catalyst: CatalystSnapshot | None = None
    next_earnings_date: date | None = None
    short_interest: ShortInterestSnapshot | None = None
    social_attention: SocialAttentionSnapshot | None = None
    catalyst_items: list[CatalystItem] = field(default_factory=list)
    alternative_data_items: list[AlternativeDataItem] = field(default_factory=list)
    options_data: OptionsSnapshot | None = None
    theme_tags: list[str] = field(default_factory=list)
    catalyst_tags: list[str] = field(default_factory=list)
    provider_name: str = "unavailable"
    source_notes: list[str] = field(default_factory=list)
    data_notes: list[str] = field(default_factory=list)
    quote_price_if_available: float | None = None
    quote_timestamp: str | None = None
    latest_available_close: float | None = None
    last_market_date: date | None = None
    is_adjusted_price: bool = False


@dataclass(frozen=True)
class TradePlan:
    current_price: float
    entry_low: float | None
    entry_high: float | None
    invalidation_level: float | None
    stop_loss_reference: float | None
    tp1: float | None
    tp2: float | None
    reward_risk_estimate: float | None
    holding_period_estimate: str

    @property
    def entry_zone(self) -> str:
        if self.entry_low is None or self.entry_high is None:
            return "unavailable"
        return f"{self.entry_low:.2f} - {self.entry_high:.2f}"


@dataclass
class ScannerResult:
    ticker: str
    company_name: str | None
    current_price: float
    strategy_label: str
    status_label: str
    winner_score: int
    bullish_score: int
    bearish_pressure_score: int
    risk_score: int
    setup_quality_score: int
    confidence_label: str
    confidence_percent: int
    holding_period: str
    component_scores: dict[str, int]
    strategy_alignment: dict[str, int]
    trade_plan: TradePlan
    why_it_passed: list[str]
    why_it_could_fail: list[str]
    warnings: list[str]
    signals_used: list[str]
    data_availability_notes: list[str]
    outlier_score: int = 0
    outlier_type: str = "Watch Only"
    outlier_risk: str = "High"
    outlier_reason: str = "No outlier case was confirmed."
    why_it_could_be_a_big_winner: list[str] = field(default_factory=list)
    chase_risk_warning: str | None = None
    theme_tags: list[str] = field(default_factory=list)
    catalyst_tags: list[str] = field(default_factory=list)
    squeeze_watch: dict[str, Any] = field(default_factory=dict)
    options_placeholders: dict[str, Any] = field(default_factory=dict)
    provider_name: str = "unavailable"
    source_notes: list[str] = field(default_factory=list)
    data_used: dict[str, Any] = field(default_factory=dict)
    catalyst_intelligence: dict[str, Any] = field(default_factory=dict)
    alternative_data: dict[str, Any] = field(default_factory=dict)
    ai_explanation: dict[str, Any] = field(default_factory=dict)
    velocity_score: int = 0
    velocity_type: str = "Not Velocity Setup"
    velocity_risk: str = "Medium"
    trigger_reason: str = "No high-velocity trigger confirmed."
    chase_warning: str = "unavailable"
    quick_trade_watch_label: str = "No quick-watch label"
    velocity_invalidation: float | None = None
    velocity_tp1: float | None = None
    velocity_tp2: float | None = None
    expected_horizon: str = "unavailable"
    regular_investing_score: int = 0
    investing_style: str = "Data Insufficient"
    investing_risk: str = "High"
    investing_time_horizon: str = "unavailable"
    investing_action_label: str = "Data Insufficient"
    investing_reason: str = "Regular investing data was unavailable."
    investing_bear_case: str = "Missing data can weaken any long-term thesis."
    investing_invalidation: str = "unavailable"
    investing_events_to_watch: list[str] = field(default_factory=list)
    value_trap_warning: str = "unavailable"
    thesis_quality: str = "Data Insufficient"
    investing_data_quality: str = "Weak"
    regular_investing_components: dict[str, int] = field(default_factory=dict)
    regular_investing_fundamental_snapshot: dict[str, Any] = field(default_factory=dict)
    price_source: str = "unavailable"
    price_timestamp: str = "unavailable"
    provider: str = "unavailable"
    is_sample_data: bool = False
    is_adjusted_price: bool = False
    is_stale_price: bool = False
    last_market_date: str = "unavailable"
    latest_available_close: float | None = None
    quote_price_if_available: float | None = None
    price_warning: str = "No price sanity warning."
    price_confidence: str = "Low"
    ema_21: float | None = None
    ema_50: float | None = None
    ema_150: float | None = None
    ema_200: float | None = None
    ema_stack: str = "Mixed Stack"
    price_vs_ema_21_pct: float | None = None
    price_vs_ema_50_pct: float | None = None
    price_vs_ema_150_pct: float | None = None
    price_vs_ema_200_pct: float | None = None
    relative_volume_20d: float | None = None
    relative_volume_50d: float | None = None
    volume_signal: str = "No Clean Signal"
    trend_signal: str = "No Clean Signal"
    pullback_signal: str = "No Clean Signal"
    breakout_signal: str = "No Clean Signal"
    distribution_signal: str = "No Clean Signal"
    signal_summary: str = "No Clean Signal"
    signal_grade: str = "F"
    signal_explanation: str = "Signal data unavailable."
    price_change_1d_pct: float | None = None
    price_change_5d_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        catalyst_intelligence = _default_catalyst_intelligence() | self.catalyst_intelligence
        alternative_data = _default_alternative_data() | self.alternative_data
        ai_explanation = _default_ai_explanation() | self.ai_explanation
        return {
            "ticker": self.ticker,
            "company_name": self.company_name or "unavailable",
            "current_price": round(self.current_price, 2),
            "strategy_label": self.strategy_label,
            "status_label": self.status_label,
            "winner_score": self.winner_score,
            "bullish_score": self.bullish_score,
            "bearish_pressure_score": self.bearish_pressure_score,
            "risk_score": self.risk_score,
            "setup_quality_score": self.setup_quality_score,
            "confidence_label": self.confidence_label,
            "confidence_percent": self.confidence_percent,
            "holding_period": self.holding_period,
            "entry_zone": self.trade_plan.entry_zone,
            "invalidation_level": _format_number(self.trade_plan.invalidation_level),
            "stop_loss_reference": _format_number(self.trade_plan.stop_loss_reference),
            "tp1": _format_number(self.trade_plan.tp1),
            "tp2": _format_number(self.trade_plan.tp2),
            "reward_risk": _format_number(self.trade_plan.reward_risk_estimate),
            "outlier_score": self.outlier_score,
            "outlier_type": self.outlier_type,
            "outlier_risk": self.outlier_risk,
            "outlier_reason": self.outlier_reason,
            "why_it_could_be_a_big_winner": self.why_it_could_be_a_big_winner,
            "chase_risk_warning": self.chase_risk_warning or "unavailable",
            "theme_tags": self.theme_tags,
            "catalyst_tags": self.catalyst_tags,
            "squeeze_watch": _format_nested(self.squeeze_watch),
            "options_placeholders": _format_nested(self.options_placeholders),
            "why_it_passed": self.why_it_passed,
            "why_it_could_fail": self.why_it_could_fail,
            "warnings": self.warnings,
            "signals_used": self.signals_used,
            "data_availability_notes": self.data_availability_notes,
            "provider_name": self.provider_name,
            "source_notes": self.source_notes,
            "component_scores": self.component_scores,
            "strategy_alignment": self.strategy_alignment,
            "data_used": self.data_used,
            "catalyst_items": catalyst_intelligence["catalyst_items"],
            "catalyst_score": catalyst_intelligence["catalyst_score"],
            "catalyst_quality": catalyst_intelligence["catalyst_quality"],
            "catalyst_type": catalyst_intelligence["catalyst_type"],
            "catalyst_source_count": catalyst_intelligence["catalyst_source_count"],
            "catalyst_recency": catalyst_intelligence["catalyst_recency"],
            "official_catalyst_found": catalyst_intelligence["official_catalyst_found"],
            "narrative_catalyst_found": catalyst_intelligence["narrative_catalyst_found"],
            "hype_catalyst_found": catalyst_intelligence["hype_catalyst_found"],
            "social_attention_available": catalyst_intelligence["social_attention_available"],
            "social_attention_score": catalyst_intelligence["social_attention_score"],
            "social_attention_velocity": catalyst_intelligence["social_attention_velocity"],
            "news_attention_score": catalyst_intelligence["news_attention_score"],
            "news_sentiment_label": catalyst_intelligence["news_sentiment_label"],
            "source_urls": catalyst_intelligence["source_urls"],
            "source_timestamps": catalyst_intelligence["source_timestamps"],
            "source_provider_notes": catalyst_intelligence["source_provider_notes"],
            "catalyst_data_available": catalyst_intelligence["catalyst_data_available"],
            "catalyst_data_missing_reason": catalyst_intelligence["catalyst_data_missing_reason"],
            "price_volume_confirms_catalyst": catalyst_intelligence["price_volume_confirms_catalyst"],
            "attention_spike": catalyst_intelligence["attention_spike"],
            "hype_risk": catalyst_intelligence["hype_risk"],
            "pump_risk": catalyst_intelligence["pump_risk"],
            "alternative_data_items": alternative_data["items"],
            "alternative_data_summary": alternative_data["summary"],
            "alternative_data_quality": alternative_data["alternative_data_quality"],
            "alternative_data_source_count": alternative_data["alternative_data_source_count"],
            "insider_buy_count": alternative_data["insider_buy_count"],
            "insider_sell_count": alternative_data["insider_sell_count"],
            "net_insider_value": alternative_data["net_insider_value"],
            "CEO_CFO_buy_flag": alternative_data["CEO_CFO_buy_flag"],
            "cluster_buying_flag": alternative_data["cluster_buying_flag"],
            "heavy_insider_selling_flag": alternative_data["heavy_insider_selling_flag"],
            "politician_buy_count": alternative_data["politician_buy_count"],
            "politician_sell_count": alternative_data["politician_sell_count"],
            "net_politician_value": alternative_data["net_politician_value"],
            "recent_politician_activity": alternative_data["recent_politician_activity"],
            "disclosure_lag_warning": alternative_data["disclosure_lag_warning"],
            "alternative_data_confirmed_by_price_volume": alternative_data["alternative_data_confirmed_by_price_volume"],
            "alternative_data_warnings": alternative_data["warnings"],
            "ai_explanation": ai_explanation,
            "ai_explanation_available": ai_explanation["available"],
            "ai_explanation_provider": ai_explanation["provider"],
            "velocity_score": self.velocity_score,
            "velocity_type": self.velocity_type,
            "velocity_risk": self.velocity_risk,
            "trigger_reason": self.trigger_reason,
            "chase_warning": self.chase_warning,
            "quick_trade_watch_label": self.quick_trade_watch_label,
            "velocity_invalidation": _format_number(self.velocity_invalidation),
            "velocity_tp1": _format_number(self.velocity_tp1),
            "velocity_tp2": _format_number(self.velocity_tp2),
            "expected_horizon": self.expected_horizon,
            "regular_investing_score": self.regular_investing_score,
            "investing_style": self.investing_style,
            "investing_risk": self.investing_risk,
            "investing_time_horizon": self.investing_time_horizon,
            "investing_action_label": self.investing_action_label,
            "investing_reason": self.investing_reason,
            "investing_bear_case": self.investing_bear_case,
            "investing_invalidation": self.investing_invalidation,
            "investing_events_to_watch": self.investing_events_to_watch,
            "value_trap_warning": self.value_trap_warning,
            "thesis_quality": self.thesis_quality,
            "investing_data_quality": self.investing_data_quality,
            "regular_investing_components": self.regular_investing_components,
            "regular_investing_fundamental_snapshot": self.regular_investing_fundamental_snapshot,
            "price_source": self.price_source,
            "price_timestamp": self.price_timestamp,
            "provider": self.provider,
            "is_sample_data": self.is_sample_data,
            "is_adjusted_price": self.is_adjusted_price,
            "is_stale_price": self.is_stale_price,
            "last_market_date": self.last_market_date,
            "latest_available_close": _format_number(self.latest_available_close),
            "quote_price_if_available": _format_number(self.quote_price_if_available),
            "price_warning": self.price_warning,
            "price_confidence": self.price_confidence,
            "ema_21": _format_number(self.ema_21),
            "ema_50": _format_number(self.ema_50),
            "ema_150": _format_number(self.ema_150),
            "ema_200": _format_number(self.ema_200),
            "ema_stack": self.ema_stack,
            "price_vs_ema_21_pct": _format_number(self.price_vs_ema_21_pct),
            "price_vs_ema_50_pct": _format_number(self.price_vs_ema_50_pct),
            "price_vs_ema_150_pct": _format_number(self.price_vs_ema_150_pct),
            "price_vs_ema_200_pct": _format_number(self.price_vs_ema_200_pct),
            "relative_volume_20d": _format_number(self.relative_volume_20d),
            "relative_volume_50d": _format_number(self.relative_volume_50d),
            "volume_signal": self.volume_signal,
            "trend_signal": self.trend_signal,
            "pullback_signal": self.pullback_signal,
            "breakout_signal": self.breakout_signal,
            "distribution_signal": self.distribution_signal,
            "signal_summary": self.signal_summary,
            "signal_grade": self.signal_grade,
            "signal_explanation": self.signal_explanation,
            "price_change_1d_pct": _format_number(self.price_change_1d_pct),
            "price_change_5d_pct": _format_number(self.price_change_5d_pct),
        }


def _format_nested(payload: dict[str, Any]) -> dict[str, Any]:
    formatted: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, bool):
            formatted[key] = value
        elif isinstance(value, (int, float)) or value is None:
            formatted[key] = _format_number(value)
        else:
            formatted[key] = value
    return formatted


def _format_number(value: float | int | None) -> float | int | str:
    if value is None:
        return "unavailable"
    if isinstance(value, int):
        return value
    return round(value, 2)


def _format_bool(value: bool | None) -> bool | str:
    if value is None:
        return "unavailable"
    return bool(value)


def _default_catalyst_intelligence() -> dict[str, Any]:
    return {
        "catalyst_items": [],
        "catalyst_score": 0,
        "catalyst_quality": "Unavailable",
        "catalyst_type": "Unknown/unconfirmed",
        "catalyst_source_count": 0,
        "catalyst_recency": "unavailable",
        "official_catalyst_found": False,
        "narrative_catalyst_found": False,
        "hype_catalyst_found": False,
        "social_attention_available": False,
        "social_attention_score": 0,
        "social_attention_velocity": "unavailable",
        "news_attention_score": 0,
        "news_sentiment_label": "unavailable",
        "source_urls": [],
        "source_timestamps": [],
        "source_provider_notes": [],
        "catalyst_data_available": False,
        "catalyst_data_missing_reason": "Catalyst data unavailable.",
        "price_volume_confirms_catalyst": False,
        "attention_spike": False,
        "hype_risk": False,
        "pump_risk": False,
    }


def _default_alternative_data() -> dict[str, Any]:
    return {
        "items": [],
        "summary": "No insider, politician, or alternative-data evidence loaded.",
        "alternative_data_quality": "Unavailable",
        "alternative_data_source_count": 0,
        "insider_buy_count": 0,
        "insider_sell_count": 0,
        "net_insider_value": 0,
        "CEO_CFO_buy_flag": False,
        "cluster_buying_flag": False,
        "heavy_insider_selling_flag": False,
        "politician_buy_count": 0,
        "politician_sell_count": 0,
        "net_politician_value": 0,
        "recent_politician_activity": False,
        "disclosure_lag_warning": "",
        "alternative_data_confirmed_by_price_volume": False,
        "warnings": [],
    }


def _default_ai_explanation() -> dict[str, Any]:
    return {
        "available": False,
        "provider": "unavailable",
        "generated": False,
        "summary": "AI explanation unavailable.",
        "bull_case": [],
        "bear_case": [],
        "why_not_to_buy": [],
        "catalyst_summary": "unavailable",
        "social_attention_summary": "unavailable",
        "setup_invalidation": "unavailable",
        "research_checklist": [],
        "source_item_refs": [],
        "safety_notes": [
            "AI is optional and is not part of deterministic scoring.",
            "AI must not create buy/sell signals or invent missing evidence.",
        ],
    }
