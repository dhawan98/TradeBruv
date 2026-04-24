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

    def to_dict(self) -> dict[str, Any]:
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
