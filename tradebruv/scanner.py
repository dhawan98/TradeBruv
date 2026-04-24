from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .indicators import atr, average, clamp, close_location, pct_change, sample_stddev, sma
from .models import ScannerResult, SecurityData, TradePlan
from .providers import MarketDataProvider, SECTOR_BENCHMARKS


STRATEGIES = (
    "Momentum Winner",
    "Breakout Winner",
    "Relative Strength Leader",
    "Long-Term Leader",
    "Confirmed Strength Reset",
    "Institutional Accumulation",
)


@dataclass
class FeatureSnapshot:
    current_price: float
    latest_volume: float
    sma20: float | None
    sma50: float | None
    sma200: float | None
    sma50_prior: float | None
    sma200_prior: float | None
    atr14: float | None
    avg_volume20: float | None
    avg_volume50: float | None
    avg_dollar_volume20: float | None
    return_10d: float | None
    return_1m: float | None
    return_3m: float | None
    return_6m: float | None
    return_12m: float | None
    high_52w: float | None
    low_3m: float | None
    recent_swing_high: float | None
    recent_swing_low: float | None
    resistance_level: float | None
    base_low: float | None
    base_tightness: float | None
    close_location: float
    above_50: bool
    above_200: bool
    ma_stack_bullish: bool
    sma50_rising: bool
    sma200_rising: bool
    near_high: bool
    higher_highs_lows: bool
    volume_confirmation: bool
    breakout_volume_confirmation: bool
    breakout_confirmed: bool
    close_holds_breakout: bool
    clean_base: bool
    gap_and_fade: bool
    failed_breakout: bool
    overextended: bool
    accumulation_days: int
    distribution_days: int
    lower_volume_pullbacks: bool
    support_holds: bool
    prior_uptrend: bool
    correction_depth: float | None
    reclaimed_sma50: bool
    rs_1m: float | None
    rs_3m: float | None
    rs_6m: float | None
    rs_vs_sector_3m: float | None
    rs_improving: bool
    holding_up_when_market_weak: bool
    sector_support: bool | None
    low_liquidity: bool
    falling_knife: bool
    broken_downtrend: bool


class DeterministicScanner:
    def __init__(self, provider: MarketDataProvider, analysis_date: date | None = None) -> None:
        self.provider = provider
        self.analysis_date = analysis_date or date.today()
        self._cache: dict[str, SecurityData] = {}

    def scan(self, tickers: Iterable[str]) -> list[ScannerResult]:
        results: list[ScannerResult] = []
        for ticker in tickers:
            ticker = ticker.strip().upper()
            if not ticker:
                continue
            security = self._get_data(ticker)
            results.append(self._scan_security(security))
        results.sort(key=lambda result: (-result.winner_score, result.risk_score, result.ticker))
        return results

    def _get_data(self, ticker: str) -> SecurityData:
        if ticker not in self._cache:
            self._cache[ticker] = self.provider.get_security_data(ticker)
        return self._cache[ticker]

    def _scan_security(self, security: SecurityData) -> ScannerResult:
        notes = list(security.data_notes)
        spy = self._safe_get("SPY", notes, "SPY benchmark unavailable.")
        qqq = self._safe_get("QQQ", notes, "QQQ benchmark unavailable.")
        sector_symbol = SECTOR_BENCHMARKS.get(security.sector or "")
        sector = self._safe_get(sector_symbol, notes, f"{security.sector} sector benchmark unavailable.") if sector_symbol else None
        if not security.fundamentals:
            notes.append("Fundamental support data unavailable.")
        if not security.catalyst:
            notes.append("Catalyst confirmation data unavailable.")
        if not security.next_earnings_date:
            notes.append("Next earnings date unavailable.")

        features = self._build_features(security, spy, qqq, sector)

        component_scores = {
            "price_leadership": self._score_price_leadership(features),
            "relative_strength": self._score_relative_strength(features),
            "volume_accumulation": self._score_volume(features),
            "fundamental_support": self._score_fundamentals(security),
            "catalyst_attention": self._score_catalyst(security),
        }

        strategy_alignment = self._strategy_alignment(features, security)
        best_strategy_label = max(strategy_alignment, key=strategy_alignment.get)
        best_strategy_score = strategy_alignment[best_strategy_label]
        strategy_label = best_strategy_label if best_strategy_score >= 50 else "No Clean Strategy"

        trade_plan = self._build_trade_plan(features, strategy_label)
        component_scores["risk_reward_setup"] = self._score_setup_quality(features, trade_plan)
        winner_score = int(sum(component_scores.values()))

        bullish_score, bullish_signals = self._bullish_score(features, security)
        bearish_score, bearish_signals = self._bearish_score(features, security, trade_plan)
        risk_score, warnings = self._risk_score(features, security, trade_plan)
        setup_quality_score = int(
            round(
                clamp(
                    (winner_score * 0.45)
                    + (max(strategy_alignment.values()) * 0.35)
                    + ((100 - risk_score) * 0.20),
                    0,
                    100,
                )
            )
        )
        confidence_percent, confidence_label = self._confidence(
            bullish_signals=bullish_signals,
            bearish_signals=bearish_signals,
            notes=notes,
        )
        status_label = self._status_label(
            winner_score=winner_score,
            risk_score=risk_score,
            bearish_score=bearish_score,
            setup_quality_score=setup_quality_score,
            strategy_alignment=best_strategy_score,
            features=features,
            trade_plan=trade_plan,
        )

        why_it_passed = bullish_signals[:5]
        why_it_could_fail = bearish_signals[:5]
        signals_used = why_it_passed + [
            "Fundamental support applied as a secondary filter only.",
            "Catalyst confirmation requires price and volume agreement.",
        ]
        data_used = {
            "bars": len(security.bars),
            "sector_benchmark": sector_symbol or "unavailable",
            "fundamentals_available": security.fundamentals is not None,
            "catalyst_available": security.catalyst is not None,
            "earnings_available": security.next_earnings_date is not None,
        }

        return ScannerResult(
            ticker=security.ticker,
            company_name=security.company_name,
            current_price=features.current_price,
            strategy_label=strategy_label,
            status_label=status_label,
            winner_score=winner_score,
            bullish_score=bullish_score,
            bearish_pressure_score=bearish_score,
            risk_score=risk_score,
            setup_quality_score=setup_quality_score,
            confidence_label=confidence_label,
            confidence_percent=confidence_percent,
            holding_period=trade_plan.holding_period_estimate,
            component_scores=component_scores,
            strategy_alignment={**strategy_alignment, "No Clean Strategy": 100 - best_strategy_score if strategy_label == "No Clean Strategy" else 0},
            trade_plan=trade_plan,
            why_it_passed=why_it_passed,
            why_it_could_fail=why_it_could_fail,
            warnings=warnings,
            signals_used=signals_used,
            data_availability_notes=notes,
            data_used=data_used,
        )

    def _safe_get(self, ticker: str | None, notes: list[str], note: str) -> SecurityData | None:
        if not ticker:
            return None
        try:
            return self._get_data(ticker)
        except Exception:
            notes.append(note)
            return None

    def _build_features(
        self,
        security: SecurityData,
        spy: SecurityData | None,
        qqq: SecurityData | None,
        sector: SecurityData | None,
    ) -> FeatureSnapshot:
        bars = security.bars
        closes = [bar.close for bar in bars]
        highs = [bar.high for bar in bars]
        lows = [bar.low for bar in bars]
        volumes = [bar.volume for bar in bars]
        current = closes[-1]
        sma20 = sma(closes, 20)
        sma50 = sma(closes, 50)
        sma200 = sma(closes, 200)
        sma50_prior = sma(closes[:-20], 50) if len(closes) >= 70 else None
        sma200_prior = sma(closes[:-20], 200) if len(closes) >= 220 else None
        avg_volume20 = average(volumes[-20:])
        avg_volume50 = average(volumes[-50:])
        avg_dollar_volume20 = average(
            bar.close * bar.volume for bar in bars[-20:]
        )
        high_52w = max(highs[-252:]) if len(highs) >= 252 else max(highs)
        low_3m = min(lows[-63:]) if len(lows) >= 63 else min(lows)
        resistance_level = max(highs[-40:-5]) if len(highs) >= 45 else None
        base_low = min(lows[-40:-5]) if len(lows) >= 45 else None
        tight_window = closes[-30:-5] if len(closes) >= 35 else closes[:-5]
        base_tightness = None
        if tight_window:
            tight_stddev = sample_stddev(tight_window)
            avg_close = average(tight_window)
            if tight_stddev and avg_close:
                base_tightness = tight_stddev / avg_close

        accumulation_days = 0
        distribution_days = 0
        up_day_volumes: list[float] = []
        down_day_volumes: list[float] = []
        for previous, current_bar in zip(bars[-21:-1], bars[-20:]):
            day_volume_ratio = current_bar.volume / avg_volume20 if avg_volume20 else 1.0
            if (
                current_bar.close > previous.close
                and current_bar.close > current_bar.open
                and day_volume_ratio >= 1.15
                and close_location(current_bar) >= 0.65
            ):
                accumulation_days += 1
                up_day_volumes.append(current_bar.volume)
            if (
                current_bar.close < previous.close
                and current_bar.close < current_bar.open
                and day_volume_ratio >= 1.1
                and close_location(current_bar) <= 0.35
            ):
                distribution_days += 1
                down_day_volumes.append(current_bar.volume)

        higher_highs_lows = bool(
            len(highs) >= 40
            and max(highs[-20:]) > max(highs[-40:-20])
            and min(lows[-20:]) > min(lows[-40:-20])
        )
        volume_confirmation = bool(avg_volume20 and volumes[-1] >= avg_volume20 * 1.15)
        breakout_volume_confirmation = bool(avg_volume50 and volumes[-1] >= avg_volume50 * 1.3)
        breakout_confirmed = bool(
            resistance_level
            and current > resistance_level * 1.01
            and breakout_volume_confirmation
        )
        close_holds_breakout = bool(
            breakout_confirmed and current >= resistance_level * 1.005
        )
        gap_and_fade = bool(
            len(bars) >= 2
            and bars[-1].open > bars[-2].close * 1.06
            and bars[-1].close < bars[-1].open
        )
        failed_breakout = bool(
            resistance_level
            and len(highs) >= 6
            and max(highs[-6:-1]) > resistance_level * 1.01
            and current < resistance_level
        )
        overextended = bool(
            (sma50 and current > sma50 * 1.14)
            or (resistance_level and current > resistance_level * 1.09)
        )
        correction_depth = None
        if len(highs) >= 63:
            prior_high = max(highs[-63:])
            if prior_high:
                correction_depth = 1.0 - (current / prior_high)
        prior_uptrend = bool(
            pct_change(closes, 126) is not None
            and pct_change(closes, 126) > 0.18
            and sma50 is not None
            and sma200 is not None
            and sma50 > sma200
        )
        reclaimed_sma50 = bool(
            sma50
            and len(closes) >= 12
            and min(closes[-12:-2]) < sma50
            and current > sma50 * 1.01
            and volume_confirmation
        )

        benchmark_rs = self._relative_strength(closes, spy.bars if spy else None, qqq.bars if qqq else None)
        sector_rs = self._relative_strength(closes, sector.bars if sector else None)
        rs_improving = bool(
            benchmark_rs[0] is not None
            and benchmark_rs[1] is not None
            and benchmark_rs[0] >= benchmark_rs[1] - 0.02
            and benchmark_rs[0] > 0
        )
        holding_up_when_market_weak = self._holding_up_when_market_weak(closes, spy, qqq)
        sector_support = None
        if sector_rs[1] is not None:
            sector_support = sector_rs[1] >= 0

        support_floor = max(
            value for value in (sma50, base_low, min(lows[-20:]) if len(lows) >= 20 else None) if value is not None
        )
        support_holds = current >= support_floor * 1.02 if support_floor else False
        lower_volume_pullbacks = bool(
            up_day_volumes
            and down_day_volumes
            and average(down_day_volumes) < average(up_day_volumes)
        )
        falling_knife = bool(
            sma50
            and sma50_prior
            and current < sma50
            and sma50 < sma50_prior
            and pct_change(closes, 21) is not None
            and pct_change(closes, 21) <= -0.12
            and current <= low_3m * 1.05
        )
        broken_downtrend = bool(
            sma50
            and sma200
            and current < sma50
            and sma50 < sma200
            and not higher_highs_lows
        )
        low_liquidity = bool(
            avg_dollar_volume20 is not None and avg_dollar_volume20 < 10_000_000
        ) or bool(avg_volume20 is not None and avg_volume20 < 300_000) or current < 5

        return FeatureSnapshot(
            current_price=current,
            latest_volume=volumes[-1],
            sma20=sma20,
            sma50=sma50,
            sma200=sma200,
            sma50_prior=sma50_prior,
            sma200_prior=sma200_prior,
            atr14=atr(bars, 14),
            avg_volume20=avg_volume20,
            avg_volume50=avg_volume50,
            avg_dollar_volume20=avg_dollar_volume20,
            return_10d=pct_change(closes, 10),
            return_1m=pct_change(closes, 21),
            return_3m=pct_change(closes, 63),
            return_6m=pct_change(closes, 126),
            return_12m=pct_change(closes, 252),
            high_52w=high_52w,
            low_3m=low_3m,
            recent_swing_high=max(highs[-20:]) if len(highs) >= 20 else max(highs),
            recent_swing_low=min(lows[-20:]) if len(lows) >= 20 else min(lows),
            resistance_level=resistance_level,
            base_low=base_low,
            base_tightness=base_tightness,
            close_location=close_location(bars[-1]),
            above_50=bool(sma50 and current > sma50),
            above_200=bool(sma200 and current > sma200),
            ma_stack_bullish=bool(sma50 and sma200 and current > sma50 > sma200),
            sma50_rising=bool(sma50 and sma50_prior and sma50 > sma50_prior),
            sma200_rising=bool(sma200 and sma200_prior and sma200 > sma200_prior),
            near_high=bool(high_52w and current >= high_52w * 0.95),
            higher_highs_lows=higher_highs_lows,
            volume_confirmation=volume_confirmation,
            breakout_volume_confirmation=breakout_volume_confirmation,
            breakout_confirmed=breakout_confirmed,
            close_holds_breakout=close_holds_breakout,
            clean_base=bool(
                resistance_level
                and base_low
                and (resistance_level - base_low) / resistance_level <= 0.22
                and base_tightness is not None
                and base_tightness <= 0.04
            ),
            gap_and_fade=gap_and_fade,
            failed_breakout=failed_breakout,
            overextended=overextended,
            accumulation_days=accumulation_days,
            distribution_days=distribution_days,
            lower_volume_pullbacks=lower_volume_pullbacks,
            support_holds=support_holds,
            prior_uptrend=prior_uptrend,
            correction_depth=correction_depth,
            reclaimed_sma50=reclaimed_sma50,
            rs_1m=benchmark_rs[0],
            rs_3m=benchmark_rs[1],
            rs_6m=benchmark_rs[2],
            rs_vs_sector_3m=sector_rs[1],
            rs_improving=rs_improving,
            holding_up_when_market_weak=holding_up_when_market_weak,
            sector_support=sector_support,
            low_liquidity=low_liquidity,
            falling_knife=falling_knife,
            broken_downtrend=broken_downtrend,
        )

    def _relative_strength(
        self,
        closes: list[float],
        benchmark_a: list | None = None,
        benchmark_b: list | None = None,
    ) -> tuple[float | None, float | None, float | None]:
        periods = (21, 63, 126)
        results: list[float | None] = []
        for period in periods:
            stock_return = pct_change(closes, period)
            if stock_return is None:
                results.append(None)
                continue

            benchmark_returns: list[float] = []
            for benchmark in (benchmark_a, benchmark_b):
                if benchmark:
                    benchmark_return = pct_change([bar.close for bar in benchmark], period)
                    if benchmark_return is not None:
                        benchmark_returns.append(benchmark_return)
            if not benchmark_returns:
                results.append(None)
                continue
            results.append(stock_return - (sum(benchmark_returns) / len(benchmark_returns)))
        return tuple(results)  # type: ignore[return-value]

    def _holding_up_when_market_weak(
        self,
        closes: list[float],
        spy: SecurityData | None,
        qqq: SecurityData | None,
    ) -> bool:
        stock_return = pct_change(closes, 10)
        if stock_return is None:
            return False
        benchmark_returns = []
        for benchmark in (spy, qqq):
            if benchmark:
                benchmark_return = pct_change([bar.close for bar in benchmark.bars], 10)
                if benchmark_return is not None:
                    benchmark_returns.append(benchmark_return)
        if not benchmark_returns:
            return False
        return min(benchmark_returns) < 0 and stock_return >= max(benchmark_returns) + 0.02

    def _score_price_leadership(self, features: FeatureSnapshot) -> int:
        score = 0
        if features.above_50:
            score += 4
        if features.above_200:
            score += 4
        if features.ma_stack_bullish:
            score += 3
        if features.sma50_rising and features.sma200_rising:
            score += 2
        if features.near_high:
            score += 3
        if features.higher_highs_lows:
            score += 2
        if not features.overextended:
            score += 2
        return min(score, 20)

    def _score_relative_strength(self, features: FeatureSnapshot) -> int:
        score = 0
        if features.rs_1m is not None and features.rs_1m > 0:
            score += 6
        if features.rs_3m is not None and features.rs_3m > 0:
            score += 7
        if features.rs_6m is not None and features.rs_6m > 0:
            score += 5
        if features.holding_up_when_market_weak or features.sector_support:
            score += 2
        return min(score, 20)

    def _score_volume(self, features: FeatureSnapshot) -> int:
        score = 0
        if features.volume_confirmation:
            score += 4
        if features.accumulation_days >= 3:
            score += 4
        if features.distribution_days <= 2:
            score += 2
        if features.lower_volume_pullbacks:
            score += 2
        if features.support_holds:
            score += 3
        return min(score, 15)

    def _score_fundamentals(self, security: SecurityData) -> int:
        fundamentals = security.fundamentals
        if not fundamentals:
            return 0
        score = 0
        if fundamentals.revenue_growth is not None and fundamentals.revenue_growth >= 0.10:
            score += 4
        if fundamentals.eps_growth is not None and fundamentals.eps_growth >= 0.10:
            score += 4
        if (
            fundamentals.margin_change is not None
            and fundamentals.margin_change >= 0
        ) or fundamentals.profitability_positive:
            score += 3
        if fundamentals.free_cash_flow_growth is not None and fundamentals.free_cash_flow_growth >= 0:
            score += 2
        if fundamentals.analyst_revision_score is not None and fundamentals.analyst_revision_score > 0:
            score += 1
        if fundamentals.guidance_improvement:
            score += 1
        return min(score, 15)

    def _score_catalyst(self, security: SecurityData) -> int:
        catalyst = security.catalyst
        if not catalyst or not catalyst.has_catalyst:
            return 0
        score = 0
        if catalyst.price_reaction_positive:
            score += 5
        if catalyst.volume_confirmation:
            score += 4
        if catalyst.holds_gains:
            score += 4
        if not catalyst.hype_risk:
            score += 2
        return min(score, 15)

    def _score_setup_quality(self, features: FeatureSnapshot, trade_plan: TradePlan) -> int:
        score = 0
        if features.clean_base or features.higher_highs_lows:
            score += 3
        if features.breakout_confirmed or features.reclaimed_sma50:
            score += 3
        if trade_plan.reward_risk_estimate is not None and trade_plan.reward_risk_estimate >= 2:
            score += 4
        if not any((features.overextended, features.failed_breakout, features.falling_knife)):
            score += 3
        if trade_plan.invalidation_level is not None:
            score += 2
        return min(score, 15)

    def _strategy_alignment(self, features: FeatureSnapshot, security: SecurityData) -> dict[str, int]:
        fundamental_positive = self._score_fundamentals(security) >= 8
        analyst_support = None
        if security.fundamentals and security.fundamentals.analyst_revision_score is not None:
            analyst_support = security.fundamentals.analyst_revision_score > 0
        fundamental_deterioration = None
        if security.fundamentals:
            fundamental_deterioration = any(
                metric is not None and metric < 0
                for metric in (
                    security.fundamentals.eps_growth,
                    security.fundamentals.margin_change,
                    security.fundamentals.free_cash_flow_growth,
                )
            )

        catalyst_confirmed = bool(
            security.catalyst
            and security.catalyst.has_catalyst
            and security.catalyst.price_reaction_positive
            and security.catalyst.volume_confirmation
            and security.catalyst.holds_gains
            and not security.catalyst.hype_risk
        )

        return {
            "Momentum Winner": self._condition_ratio(
                [
                    features.above_50,
                    features.above_200,
                    features.rs_1m is not None and features.rs_1m > 0,
                    features.rs_3m is not None and features.rs_3m > 0,
                    features.rs_6m is not None and features.rs_6m > 0,
                    features.near_high,
                    features.higher_highs_lows,
                    features.volume_confirmation,
                    not features.overextended,
                ]
            ),
            "Breakout Winner": self._condition_ratio(
                [
                    features.clean_base,
                    features.breakout_confirmed,
                    features.breakout_volume_confirmation,
                    features.close_holds_breakout,
                    not features.failed_breakout,
                    not features.gap_and_fade,
                ]
            ),
            "Relative Strength Leader": self._condition_ratio(
                [
                    features.rs_1m is not None and features.rs_1m > 0,
                    features.rs_3m is not None and features.rs_3m > 0,
                    features.rs_6m is not None and features.rs_6m > 0,
                    features.rs_vs_sector_3m >= 0 if features.rs_vs_sector_3m is not None else None,
                    features.holding_up_when_market_weak,
                    features.rs_improving,
                ]
            ),
            "Long-Term Leader": self._condition_ratio(
                [
                    features.return_6m is not None and features.return_6m > 0.18,
                    features.return_12m is not None and features.return_12m > 0.25,
                    features.above_50,
                    features.above_200,
                    fundamental_positive,
                    analyst_support,
                    features.sector_support,
                    not features.broken_downtrend,
                ]
            ),
            "Confirmed Strength Reset": self._condition_ratio(
                [
                    features.prior_uptrend,
                    features.correction_depth is not None and 0.05 <= features.correction_depth <= 0.25,
                    features.clean_base,
                    features.reclaimed_sma50,
                    features.rs_improving,
                    features.volume_confirmation,
                    not fundamental_deterioration if fundamental_deterioration is not None else None,
                ]
            ),
            "Institutional Accumulation": self._condition_ratio(
                [
                    features.accumulation_days >= 3,
                    features.lower_volume_pullbacks,
                    features.close_location >= 0.65,
                    features.support_holds,
                    features.distribution_days <= 2,
                    not (
                        security.fundamentals
                        and security.fundamentals.recent_dilution
                    ),
                    catalyst_confirmed if security.catalyst else None,
                ]
            ),
        }

    def _condition_ratio(self, conditions: list[bool | None]) -> int:
        available = [condition for condition in conditions if condition is not None]
        if not available:
            return 0
        return int(round((sum(bool(condition) for condition in available) / len(available)) * 100))

    def _bullish_score(self, features: FeatureSnapshot, security: SecurityData) -> tuple[int, list[str]]:
        rules = [
            ("Price is above the 50-day moving average.", 6, features.above_50),
            ("Price is above the 200-day moving average.", 6, features.above_200),
            ("1-month relative strength beats major benchmarks.", 5, features.rs_1m is not None and features.rs_1m > 0),
            ("3-month relative strength beats major benchmarks.", 7, features.rs_3m is not None and features.rs_3m > 0),
            ("6-month relative strength beats major benchmarks.", 7, features.rs_6m is not None and features.rs_6m > 0),
            ("Price is trading near 52-week highs.", 4, features.near_high),
            ("Trend structure shows higher highs and higher lows.", 4, features.higher_highs_lows),
            ("Recent volume confirms demand.", 4, features.volume_confirmation),
            ("Accumulation days outweigh distribution pressure.", 4, features.accumulation_days >= 3 and features.distribution_days <= 2),
            ("Support has held repeatedly during recent pullbacks.", 3, features.support_holds),
            ("Base or consolidation is reasonably clean.", 3, features.clean_base),
            ("The stock reclaimed the 50-day moving average with confirmation.", 3, features.reclaimed_sma50),
            ("Fundamental support is constructive.", 4, self._score_fundamentals(security) >= 8),
            ("Catalyst is confirmed by price and volume.", 3, self._score_catalyst(security) >= 10),
        ]
        return self._weighted_score(rules)

    def _bearish_score(
        self,
        features: FeatureSnapshot,
        security: SecurityData,
        trade_plan: TradePlan,
    ) -> tuple[int, list[str]]:
        earnings_too_close = bool(
            security.next_earnings_date
            and (security.next_earnings_date - self.analysis_date).days <= 7
        )
        poor_rr = trade_plan.reward_risk_estimate is None or trade_plan.reward_risk_estimate < 1.75
        rules = [
            ("Price is below a declining 50-day moving average.", 10, not features.above_50 and features.sma50_rising is False),
            ("Price is below a declining 200-day moving average.", 10, not features.above_200 and features.sma200_rising is False),
            ("Heavy-volume selling is showing up in the tape.", 12, features.distribution_days >= 4),
            ("The breakout structure has failed.", 12, features.failed_breakout),
            ("The current move is overextended from support.", 9, features.overextended),
            ("A gap-and-fade pattern weakens the setup.", 8, features.gap_and_fade),
            ("The stock is acting like a falling knife.", 14, features.falling_knife),
            ("Reward/risk is poor or unclear.", 10, poor_rr),
            ("Liquidity is too low for a clean setup.", 8, features.low_liquidity),
            ("An earnings report is too close for a clean setup.", 7, earnings_too_close),
            ("Recent dilution risk is present.", 5, bool(security.fundamentals and security.fundamentals.recent_dilution)),
            ("Sector relative strength is weak.", 5, features.sector_support is False),
            ("Headline attention is not confirmed by price action.", 8, bool(security.catalyst and security.catalyst.hype_risk)),
        ]
        return self._weighted_score(rules)

    def _risk_score(
        self,
        features: FeatureSnapshot,
        security: SecurityData,
        trade_plan: TradePlan,
    ) -> tuple[int, list[str]]:
        warnings: list[str] = []
        score = 0

        def flag(condition: bool, weight: int, warning: str) -> None:
            nonlocal score
            if condition:
                score += weight
                warnings.append(warning)

        earnings_too_close = bool(
            security.next_earnings_date
            and (security.next_earnings_date - self.analysis_date).days <= 7
        )
        poor_rr = trade_plan.reward_risk_estimate is None or trade_plan.reward_risk_estimate < 1.75
        flag(features.falling_knife, 20, "Falling knife behavior is present.")
        flag(features.failed_breakout, 16, "Recent breakout attempt failed.")
        flag(features.overextended, 12, "Move is extended away from the 50-day average.")
        flag(features.low_liquidity, 14, "Liquidity is too low for a clean research candidate.")
        flag(features.distribution_days >= 4, 10, "Heavy-volume selling is active.")
        flag(earnings_too_close, 10, "Earnings are too close to the setup.")
        flag(bool(security.catalyst and security.catalyst.hype_risk), 8, "Headline attention looks hype-driven.")
        flag(bool(security.fundamentals and security.fundamentals.recent_dilution), 12, "Recent dilution/offering risk is present.")
        flag(features.sector_support is False, 6, "Sector backdrop is weak.")
        flag(trade_plan.invalidation_level is None, 8, "No clear invalidation level was found.")
        flag(poor_rr, 12, "Reward/risk is not attractive enough.")
        return int(clamp(score, 0, 100)), warnings

    def _weighted_score(self, rules: list[tuple[str, int, bool]]) -> tuple[int, list[str]]:
        total_possible = sum(weight for _, weight, _ in rules)
        triggered = [description for description, _, condition in rules if condition]
        total = sum(weight for _, weight, condition in rules if condition)
        if total_possible == 0:
            return 0, triggered
        return int(round((total / total_possible) * 100)), triggered

    def _confidence(
        self,
        *,
        bullish_signals: list[str],
        bearish_signals: list[str],
        notes: list[str],
    ) -> tuple[int, str]:
        positive = len(bullish_signals)
        negative = len(bearish_signals)
        if positive + negative == 0:
            percent = 0
        else:
            percent = int(round((positive / (positive + negative)) * 100))
        completeness_penalty = min(len(notes) * 2, 12)
        percent = int(clamp(percent - completeness_penalty, 0, 100))
        if percent >= 85:
            label = "Very High"
        elif percent >= 70:
            label = "High"
        elif percent >= 55:
            label = "Moderate"
        elif percent >= 40:
            label = "Low"
        else:
            label = "Very Low"
        return percent, label

    def _status_label(
        self,
        *,
        winner_score: int,
        risk_score: int,
        bearish_score: int,
        setup_quality_score: int,
        strategy_alignment: int,
        features: FeatureSnapshot,
        trade_plan: TradePlan,
    ) -> str:
        in_entry_zone = (
            trade_plan.entry_low is not None
            and trade_plan.entry_high is not None
            and trade_plan.entry_low <= features.current_price <= trade_plan.entry_high * 1.02
        )
        if any(
            (
                features.falling_knife,
                features.failed_breakout,
                risk_score >= 70,
                bearish_score >= 65,
                winner_score < 25 and bearish_score >= 35,
                winner_score < 25 and risk_score >= 30,
            )
        ):
            return "Avoid"
        if winner_score >= 80 and risk_score <= 35 and setup_quality_score >= 72:
            return "Strong Research Candidate"
        if winner_score >= 70 and setup_quality_score >= 65 and strategy_alignment >= 65 and in_entry_zone:
            return "Active Setup"
        if winner_score >= 58 and setup_quality_score >= 55 and strategy_alignment >= 50:
            return "Trade Setup Forming"
        return "Watch Only"

    def _build_trade_plan(self, features: FeatureSnapshot, strategy_label: str) -> TradePlan:
        current = features.current_price
        atr_value = features.atr14 or max(current * 0.03, 0.5)
        support_candidates = sorted(
            value
            for value in (
                features.sma20,
                features.sma50,
                features.base_low,
                features.recent_swing_low,
            )
            if value is not None and value < current
        )
        nearest_support = support_candidates[-1] if support_candidates else current - (1.5 * atr_value)
        deeper_support = support_candidates[0] if support_candidates else current - (2.0 * atr_value)

        if strategy_label == "Breakout Winner":
            pivot = features.resistance_level or current - atr_value * 0.4
            entry_low = pivot
            entry_high = min(current, pivot + (0.5 * atr_value))
            invalidation = min(pivot - (0.75 * atr_value), deeper_support)
            holding_period = "1-6 weeks"
        elif strategy_label == "Confirmed Strength Reset":
            reclaim = max(value for value in (features.sma50, features.sma20, nearest_support) if value is not None)
            entry_low = reclaim
            entry_high = min(current, reclaim + (0.75 * atr_value))
            invalidation = min(deeper_support, reclaim - atr_value)
            holding_period = "2-8 weeks"
        elif strategy_label == "Long-Term Leader":
            entry_low = nearest_support
            entry_high = min(current, (features.sma20 or current))
            invalidation = min(deeper_support, (features.sma200 or (current - 2.5 * atr_value)))
            holding_period = "8-26 weeks"
        elif strategy_label == "Institutional Accumulation":
            entry_low = nearest_support
            entry_high = min(current, nearest_support + (0.6 * atr_value))
            invalidation = min(deeper_support, nearest_support - atr_value)
            holding_period = "2-6 weeks"
        elif strategy_label == "No Clean Strategy":
            entry_low = nearest_support
            entry_high = min(current, nearest_support + (0.4 * atr_value))
            invalidation = min(deeper_support, nearest_support - atr_value)
            holding_period = "Wait / not actionable"
        else:
            entry_low = max(nearest_support, current - (0.5 * atr_value))
            entry_high = current
            invalidation = min(deeper_support, nearest_support - (0.8 * atr_value))
            holding_period = "2-10 weeks"

        entry_low, entry_high = sorted((round(entry_low, 2), round(entry_high, 2)))
        entry_mid = (entry_low + entry_high) / 2
        if invalidation >= entry_mid:
            invalidation = entry_mid - max(atr_value, current * 0.03)
        stop = round(invalidation, 2)
        risk_per_share = entry_mid - stop
        if risk_per_share <= 0:
            return TradePlan(
                current_price=current,
                entry_low=entry_low,
                entry_high=entry_high,
                invalidation_level=None,
                stop_loss_reference=None,
                tp1=None,
                tp2=None,
                reward_risk_estimate=None,
                holding_period_estimate=holding_period,
            )

        resistance_candidates = sorted(
            value
            for value in (
                features.resistance_level,
                features.recent_swing_high,
                features.high_52w,
            )
            if value is not None and value > entry_mid
        )
        nearest_resistance = resistance_candidates[0] if resistance_candidates else None
        conservative_target = entry_mid + (2.0 * risk_per_share)
        if nearest_resistance is not None and (
            strategy_label == "No Clean Strategy" or features.broken_downtrend or features.falling_knife
        ):
            conservative_target = min(conservative_target, nearest_resistance)
        elif nearest_resistance is not None:
            conservative_target = max(conservative_target, nearest_resistance)
        tp1 = round(max(conservative_target, entry_mid + (1.25 * risk_per_share)), 2)
        tp2 = round(max(tp1 + risk_per_share, entry_mid + (3.0 * risk_per_share)), 2)
        reward_risk = round((tp1 - entry_mid) / risk_per_share, 2)

        return TradePlan(
            current_price=current,
            entry_low=entry_low,
            entry_high=entry_high,
            invalidation_level=round(invalidation, 2),
            stop_loss_reference=stop,
            tp1=tp1,
            tp2=tp2,
            reward_risk_estimate=reward_risk,
            holding_period_estimate=holding_period,
        )
