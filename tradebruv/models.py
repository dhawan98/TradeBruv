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


@dataclass(frozen=True)
class CatalystSnapshot:
    has_catalyst: bool | None = None
    description: str | None = None
    price_reaction_positive: bool | None = None
    volume_confirmation: bool | None = None
    holds_gains: bool | None = None
    hype_risk: bool | None = None


@dataclass
class SecurityData:
    ticker: str
    company_name: str | None
    sector: str | None
    bars: list[PriceBar]
    fundamentals: FundamentalsSnapshot | None = None
    catalyst: CatalystSnapshot | None = None
    next_earnings_date: date | None = None
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
            "why_it_passed": self.why_it_passed,
            "why_it_could_fail": self.why_it_could_fail,
            "warnings": self.warnings,
            "signals_used": self.signals_used,
            "data_availability_notes": self.data_availability_notes,
            "component_scores": self.component_scores,
            "strategy_alignment": self.strategy_alignment,
            "data_used": self.data_used,
        }


def _format_number(value: float | None) -> float | str:
    if value is None:
        return "unavailable"
    return round(value, 2)

