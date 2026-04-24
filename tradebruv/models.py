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
    options_data: OptionsSnapshot | None = None
    theme_tags: list[str] = field(default_factory=list)
    catalyst_tags: list[str] = field(default_factory=list)
    provider_name: str = "unavailable"
    source_notes: list[str] = field(default_factory=list)
    data_notes: list[str] = field(default_factory=list)


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
    ai_explanation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        catalyst_intelligence = _default_catalyst_intelligence() | self.catalyst_intelligence
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
            "ai_explanation": ai_explanation,
            "ai_explanation_available": ai_explanation["available"],
            "ai_explanation_provider": ai_explanation["provider"],
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
