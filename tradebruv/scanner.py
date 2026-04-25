from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .alternative_data import build_alternative_data_signal
from .catalysts import build_catalyst_intelligence
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
    return_1d: float | None
    return_5d: float | None
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
    close_near_week_high: bool
    above_50: bool
    above_200: bool
    ma_stack_bullish: bool
    sma50_rising: bool
    sma200_rising: bool
    near_high: bool
    price_near_multi_month_high: bool
    higher_highs_lows: bool
    volume_confirmation: bool
    breakout_volume_confirmation: bool
    relative_volume_ratio: float | None
    unusual_volume: bool
    breakout_confirmed: bool
    breakout_retest: bool
    close_holds_breakout: bool
    weak_breakout_close: bool
    clean_base: bool
    gap_and_fade: bool
    failed_breakout: bool
    overextended: bool
    extreme_overextension: bool
    accumulation_days: int
    distribution_days: int
    lower_volume_pullbacks: bool
    support_holds: bool
    prior_uptrend: bool
    correction_depth: float | None
    reclaimed_sma50: bool
    rs_1d: float | None
    rs_5d: float | None
    rs_1m: float | None
    rs_3m: float | None
    rs_6m: float | None
    rs_vs_sector_3m: float | None
    rs_improving: bool
    rs_line_rising: bool
    holding_up_when_market_weak: bool
    higher_lows_while_market_weak: bool
    sector_support: bool | None
    strong_multitimeframe_trend: bool
    low_liquidity: bool
    falling_knife: bool
    broken_downtrend: bool
    recent_ipo: bool
    pump_risk: bool


class DeterministicScanner:
    def __init__(self, provider: MarketDataProvider, analysis_date: date | None = None) -> None:
        self.provider = provider
        self.analysis_date = analysis_date or date.today()
        self._cache: dict[str, SecurityData] = {}

    def scan(self, tickers: Iterable[str], mode: str = "standard") -> list[ScannerResult]:
        results: list[ScannerResult] = []
        for raw_ticker in tickers:
            ticker = raw_ticker.strip().upper()
            if not ticker:
                continue
            try:
                security = self._get_data(ticker)
                results.append(self._scan_security(security))
            except Exception as exc:
                results.append(self._failure_result(ticker, exc))

        if mode == "outliers":
            results.sort(key=lambda result: (-result.outlier_score, result.risk_score, result.ticker))
        else:
            results.sort(key=lambda result: (-result.winner_score, result.risk_score, -result.outlier_score, result.ticker))
        return results

    def _get_data(self, ticker: str) -> SecurityData:
        if ticker not in self._cache:
            self._cache[ticker] = self.provider.get_security_data(ticker)
        return self._cache[ticker]

    def _scan_security(self, security: SecurityData) -> ScannerResult:
        notes = list(security.data_notes)
        self._append_availability_notes(notes, security)

        spy = self._safe_get("SPY", notes, "SPY benchmark unavailable.")
        qqq = self._safe_get("QQQ", notes, "QQQ benchmark unavailable.")
        sector_symbol = SECTOR_BENCHMARKS.get(security.sector or "")
        sector = self._safe_get(sector_symbol, notes, f"{security.sector} sector benchmark unavailable.") if sector_symbol else None

        features = self._build_features(security, spy, qqq, sector)

        component_scores = {
            "price_leadership": self._score_price_leadership(features),
            "relative_strength": self._score_relative_strength(features),
            "volume_accumulation": self._score_volume(features),
            "fundamental_support": self._score_fundamentals(security),
            "catalyst_attention": self._score_catalyst(security, features),
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
                    + (best_strategy_score * 0.35)
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
        catalyst_intelligence, catalyst_warnings = build_catalyst_intelligence(
            security=security,
            features=features,
            analysis_date=self.analysis_date,
        )
        for warning in catalyst_warnings:
            if warning not in warnings:
                warnings.append(warning)
        if (
            status_label != "Avoid"
            and catalyst_intelligence["catalyst_quality"] in {"Social Attention Only", "Hype Risk"}
            and not catalyst_intelligence["official_catalyst_found"]
            and not catalyst_intelligence["narrative_catalyst_found"]
            and not catalyst_intelligence["price_volume_confirms_catalyst"]
        ):
            status_label = "Watch Only"

        outlier_components = {
            "explosive_price_strength": self._score_outlier_price_strength(features),
            "relative_strength_acceleration": self._score_outlier_relative_strength(features),
            "volume_attention_expansion": self._score_outlier_volume_attention(features, security),
            "catalyst_repricing_support": self._score_outlier_catalyst(security, features),
            "float_short_or_institutional_demand": self._score_outlier_demand(security, features),
            "setup_cleanliness_risk_reward": self._score_outlier_setup(features, trade_plan),
        }
        outlier_score = int(sum(outlier_components.values()))
        outlier_type, outlier_reason, big_winner_reasons = self._outlier_classification(
            security=security,
            features=features,
            trade_plan=trade_plan,
            outlier_score=outlier_score,
            risk_score=risk_score,
            status_label=status_label,
        )
        outlier_risk = self._outlier_risk_label(
            outlier_type=outlier_type,
            risk_score=risk_score,
            features=features,
            security=security,
        )
        chase_risk_warning = self._chase_risk_warning(features, security)
        if chase_risk_warning and chase_risk_warning not in warnings:
            warnings.append(chase_risk_warning)
        alternative_data, alternative_warnings = build_alternative_data_signal(
            security=security,
            features=features,
            status_label=status_label,
        )
        for warning in alternative_warnings:
            if warning not in warnings:
                warnings.append(warning)

        why_it_passed = bullish_signals[:6]
        why_it_could_fail = bearish_signals[:6]
        signals_used = why_it_passed + [
            "Fundamental support is used only as a secondary confirmation layer.",
            "Catalysts require price and volume confirmation to matter.",
            "Outlier ranking is deterministic and does not predict probability of profit.",
        ]
        data_used = {
            "bars": len(security.bars),
            "provider": security.provider_name,
            "sector_benchmark": sector_symbol or "unavailable",
            "fundamentals_available": security.fundamentals is not None,
            "catalyst_available": security.catalyst is not None,
            "earnings_available": security.next_earnings_date is not None,
            "market_cap_available": security.market_cap is not None,
            "short_interest_available": security.short_interest is not None,
            "social_attention_available": security.social_attention is not None,
            "options_placeholder_available": security.options_data is not None,
            "catalyst_data_available": catalyst_intelligence["catalyst_data_available"],
            "manual_catalyst_source_count": catalyst_intelligence["catalyst_source_count"],
            "alternative_data_available": bool(alternative_data["alternative_data_source_count"]),
            "alternative_data_source_count": alternative_data["alternative_data_source_count"],
            "outlier_components": outlier_components,
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
            strategy_alignment={
                **strategy_alignment,
                "No Clean Strategy": 100 - best_strategy_score if strategy_label == "No Clean Strategy" else 0,
            },
            trade_plan=trade_plan,
            why_it_passed=why_it_passed,
            why_it_could_fail=why_it_could_fail,
            warnings=warnings,
            signals_used=signals_used,
            data_availability_notes=notes,
            outlier_score=outlier_score,
            outlier_type=outlier_type,
            outlier_risk=outlier_risk,
            outlier_reason=outlier_reason,
            why_it_could_be_a_big_winner=big_winner_reasons[:6],
            chase_risk_warning=chase_risk_warning,
            theme_tags=security.theme_tags,
            catalyst_tags=security.catalyst_tags,
            squeeze_watch=self._squeeze_watch_payload(security),
            options_placeholders=self._options_payload(security),
            provider_name=security.provider_name,
            source_notes=security.source_notes,
            data_used=data_used,
            catalyst_intelligence=catalyst_intelligence,
            alternative_data=alternative_data,
        )

    def _failure_result(self, ticker: str, error: Exception) -> ScannerResult:
        failure_plan = TradePlan(
            current_price=0.0,
            entry_low=None,
            entry_high=None,
            invalidation_level=None,
            stop_loss_reference=None,
            tp1=None,
            tp2=None,
            reward_risk_estimate=None,
            holding_period_estimate="unavailable",
        )
        message = str(error)
        return ScannerResult(
            ticker=ticker,
            company_name="unavailable",
            current_price=0.0,
            strategy_label="No Clean Strategy",
            status_label="Avoid",
            winner_score=0,
            bullish_score=0,
            bearish_pressure_score=100,
            risk_score=100,
            setup_quality_score=0,
            confidence_label="Very Low",
            confidence_percent=0,
            holding_period="unavailable",
            component_scores={},
            strategy_alignment={"No Clean Strategy": 100},
            trade_plan=failure_plan,
            why_it_passed=[],
            why_it_could_fail=[f"Ticker data could not be loaded: {message}"],
            warnings=[f"Data fetch failed for {ticker}: {message}"],
            signals_used=["No deterministic scan was run because data loading failed."],
            data_availability_notes=[f"Provider failure: {message}"],
            outlier_score=0,
            outlier_type="Avoid",
            outlier_risk="Extreme",
            outlier_reason="Data could not be loaded, so no outlier judgment was made.",
            why_it_could_be_a_big_winner=[],
            chase_risk_warning="Data unavailable.",
            theme_tags=[],
            catalyst_tags=[],
            squeeze_watch=self._unavailable_squeeze_payload(),
            options_placeholders=self._unavailable_options_payload(),
            provider_name="unavailable",
            source_notes=[],
            data_used={"provider_error": message},
        )

    def _append_availability_notes(self, notes: list[str], security: SecurityData) -> None:
        if not security.fundamentals:
            notes.append("Fundamental support data unavailable.")
        if not security.catalyst:
            notes.append("Catalyst confirmation data unavailable.")
        if not security.next_earnings_date:
            notes.append("Next earnings date unavailable.")
        if security.market_cap is None:
            notes.append("Market cap unavailable.")
        if not security.industry:
            notes.append("Industry data unavailable.")
        if not security.short_interest:
            notes.append("Short interest data unavailable.")
        if not security.social_attention:
            notes.append("Social/news attention data unavailable.")
        if not security.alternative_data_items:
            notes.append("Insider/politician alternative data unavailable.")
        if not security.options_data:
            notes.append("Options placeholder data unavailable.")
        if not security.ipo_date:
            notes.append("IPO date unavailable.")

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
        avg_dollar_volume20 = average(bar.close * bar.volume for bar in bars[-20:])
        high_52w = max(highs[-252:]) if len(highs) >= 252 else max(highs)
        low_3m = min(lows[-63:]) if len(lows) >= 63 else min(lows)
        resistance_level = max(highs[-60:-5]) if len(highs) >= 65 else max(highs[:-5]) if len(highs) > 5 else None
        base_low = min(lows[-60:-5]) if len(lows) >= 65 else min(lows[:-5]) if len(lows) > 5 else None
        tight_window = closes[-30:-5] if len(closes) >= 35 else closes[:-5]
        base_tightness = None
        if tight_window:
            tight_stddev = sample_stddev(tight_window)
            avg_close = average(tight_window)
            if tight_stddev is not None and avg_close:
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
        relative_volume_ratio = (volumes[-1] / avg_volume50) if avg_volume50 else None
        volume_confirmation = bool(avg_volume20 and volumes[-1] >= avg_volume20 * 1.15)
        breakout_volume_confirmation = bool(avg_volume50 and volumes[-1] >= avg_volume50 * 1.35)
        unusual_volume = bool(relative_volume_ratio and relative_volume_ratio >= 1.75)
        breakout_confirmed = bool(resistance_level and current > resistance_level * 1.01 and breakout_volume_confirmation)
        close_holds_breakout = bool(breakout_confirmed and current >= resistance_level * 1.005)
        breakout_retest = bool(
            resistance_level
            and close_holds_breakout
            and len(lows) >= 5
            and min(lows[-5:]) <= resistance_level * 1.03
            and current >= resistance_level
        )
        weak_breakout_close = bool(breakout_confirmed and close_location(bars[-1]) < 0.55)
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
        overextended = bool((sma50 and current > sma50 * 1.14) or (resistance_level and current > resistance_level * 1.09))
        extreme_overextension = bool(
            (sma20 and current > sma20 * 1.12)
            or (sma50 and current > sma50 * 1.20)
            or (pct_change(closes, 21) is not None and pct_change(closes, 21) > 0.35 and not breakout_retest)
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
        close_near_week_high = bool(len(highs) >= 5 and current >= max(highs[-5:]) * 0.985)
        price_near_multi_month_high = bool(len(highs) >= 126 and current >= max(highs[-126:]) * 0.98)

        benchmark_rs = self._relative_strength(closes, spy.bars if spy else None, qqq.bars if qqq else None, periods=(1, 5, 21, 63, 126))
        sector_rs = self._relative_strength(closes, sector.bars if sector else None, periods=(21, 63, 126))
        rs_improving = bool(
            benchmark_rs[2] is not None
            and benchmark_rs[3] is not None
            and benchmark_rs[2] >= benchmark_rs[3] - 0.01
            and benchmark_rs[2] > 0
        )
        rs_line_rising = self._rs_line_rising(closes, spy, qqq)
        holding_up_when_market_weak = self._holding_up_when_market_weak(closes, spy, qqq)
        higher_lows_while_market_weak = self._higher_lows_while_market_weak(closes, lows, spy, qqq)
        sector_support = None
        if sector_rs[1] is not None:
            sector_support = sector_rs[1] >= 0

        support_candidates = [
            value
            for value in (
                sma50,
                base_low,
                min(lows[-20:]) if len(lows) >= 20 else None,
            )
            if value is not None
        ]
        support_floor = max(support_candidates) if support_candidates else None
        support_holds = bool(support_floor and current >= support_floor * 1.02)
        lower_volume_pullbacks = bool(up_day_volumes and down_day_volumes and average(down_day_volumes) < average(up_day_volumes))
        falling_knife = bool(
            sma50
            and sma50_prior
            and current < sma50
            and sma50 < sma50_prior
            and pct_change(closes, 21) is not None
            and pct_change(closes, 21) <= -0.12
            and current <= low_3m * 1.05
        )
        broken_downtrend = bool(sma50 and sma200 and current < sma50 and sma50 < sma200 and not higher_highs_lows)
        low_liquidity = bool(
            (avg_dollar_volume20 is not None and avg_dollar_volume20 < 10_000_000)
            or (avg_volume20 is not None and avg_volume20 < 300_000)
            or current < 5
        )
        strong_multitimeframe_trend = bool(
            sma20
            and sma50
            and sma200
            and current > sma20 > sma50 > sma200
            and all(
                value is not None and value > 0
                for value in (
                    pct_change(closes, 5),
                    pct_change(closes, 21),
                    pct_change(closes, 63),
                )
            )
        )
        recent_ipo = bool(
            security.ipo_date
            and (self.analysis_date - security.ipo_date).days <= 540
        ) or bool(len(bars) < 252)
        pump_risk = bool(
            unusual_volume
            and gap_and_fade
            and security.social_attention
            and security.social_attention.attention_velocity is not None
            and security.social_attention.attention_velocity >= 1.2
        )

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
            return_1d=pct_change(closes, 1),
            return_5d=pct_change(closes, 5),
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
            close_near_week_high=close_near_week_high,
            above_50=bool(sma50 and current > sma50),
            above_200=bool(sma200 and current > sma200),
            ma_stack_bullish=bool(sma50 and sma200 and current > sma50 > sma200),
            sma50_rising=bool(sma50 and sma50_prior and sma50 > sma50_prior),
            sma200_rising=bool(sma200 and sma200_prior and sma200 > sma200_prior),
            near_high=bool(high_52w and current >= high_52w * 0.95),
            price_near_multi_month_high=price_near_multi_month_high,
            higher_highs_lows=higher_highs_lows,
            volume_confirmation=volume_confirmation,
            breakout_volume_confirmation=breakout_volume_confirmation,
            relative_volume_ratio=relative_volume_ratio,
            unusual_volume=unusual_volume,
            breakout_confirmed=breakout_confirmed,
            breakout_retest=breakout_retest,
            close_holds_breakout=close_holds_breakout,
            weak_breakout_close=weak_breakout_close,
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
            extreme_overextension=extreme_overextension,
            accumulation_days=accumulation_days,
            distribution_days=distribution_days,
            lower_volume_pullbacks=lower_volume_pullbacks,
            support_holds=support_holds,
            prior_uptrend=prior_uptrend,
            correction_depth=correction_depth,
            reclaimed_sma50=reclaimed_sma50,
            rs_1d=benchmark_rs[0],
            rs_5d=benchmark_rs[1],
            rs_1m=benchmark_rs[2],
            rs_3m=benchmark_rs[3],
            rs_6m=benchmark_rs[4],
            rs_vs_sector_3m=sector_rs[1],
            rs_improving=rs_improving,
            rs_line_rising=rs_line_rising,
            holding_up_when_market_weak=holding_up_when_market_weak,
            higher_lows_while_market_weak=higher_lows_while_market_weak,
            sector_support=sector_support,
            strong_multitimeframe_trend=strong_multitimeframe_trend,
            low_liquidity=low_liquidity,
            falling_knife=falling_knife,
            broken_downtrend=broken_downtrend,
            recent_ipo=recent_ipo,
            pump_risk=pump_risk,
        )

    def _relative_strength(
        self,
        closes: list[float],
        benchmark_a: list | None = None,
        benchmark_b: list | None = None,
        periods: tuple[int, ...] = (21, 63, 126),
    ) -> tuple[float | None, ...]:
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
        return tuple(results)

    def _rs_line_rising(self, closes: list[float], spy: SecurityData | None, qqq: SecurityData | None) -> bool:
        comparisons: list[float] = []
        if spy and len(spy.bars) >= 21:
            comparisons.append([bar.close for bar in spy.bars][-21])
        if qqq and len(qqq.bars) >= 21:
            comparisons.append([bar.close for bar in qqq.bars][-21])
        benchmark_closes = []
        for benchmark in (spy, qqq):
            if benchmark:
                benchmark_closes.append([bar.close for bar in benchmark.bars])
        if not benchmark_closes or len(closes) < 21:
            return False
        current_ratio = []
        previous_ratio = []
        for benchmark in benchmark_closes:
            if len(benchmark) < 21:
                continue
            current_ratio.append(closes[-1] / benchmark[-1])
            previous_ratio.append(closes[-21] / benchmark[-21])
        if not current_ratio or not previous_ratio:
            return False
        return (sum(current_ratio) / len(current_ratio)) > (sum(previous_ratio) / len(previous_ratio)) * 1.02

    def _holding_up_when_market_weak(self, closes: list[float], spy: SecurityData | None, qqq: SecurityData | None) -> bool:
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

    def _higher_lows_while_market_weak(
        self,
        closes: list[float],
        lows: list[float],
        spy: SecurityData | None,
        qqq: SecurityData | None,
    ) -> bool:
        if len(lows) < 40:
            return False
        stock_higher_low = min(lows[-20:]) > min(lows[-40:-20])
        if not stock_higher_low:
            return False
        benchmark_returns = []
        for benchmark in (spy, qqq):
            if benchmark:
                benchmark_return = pct_change([bar.close for bar in benchmark.bars], 20)
                if benchmark_return is not None:
                    benchmark_returns.append(benchmark_return)
        return bool(benchmark_returns and min(benchmark_returns) < 0)

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
        if ((fundamentals.margin_change is not None and fundamentals.margin_change >= 0) or fundamentals.profitability_positive):
            score += 3
        if fundamentals.free_cash_flow_growth is not None and fundamentals.free_cash_flow_growth >= 0:
            score += 2
        if fundamentals.analyst_revision_score is not None and fundamentals.analyst_revision_score > 0:
            score += 1
        if fundamentals.guidance_improvement:
            score += 1
        return min(score, 15)

    def _score_catalyst(self, security: SecurityData, features: FeatureSnapshot) -> int:
        catalyst = security.catalyst
        if not catalyst or not catalyst.has_catalyst:
            return 0
        score = 0
        if catalyst.price_reaction_positive:
            score += 5
        if catalyst.volume_confirmation or features.unusual_volume:
            score += 4
        if catalyst.holds_gains or features.close_near_week_high:
            score += 4
        if not catalyst.hype_risk:
            score += 2
        return min(score, 15)

    def _score_setup_quality(self, features: FeatureSnapshot, trade_plan: TradePlan) -> int:
        score = 0
        if features.clean_base or features.higher_highs_lows:
            score += 3
        if features.breakout_confirmed or features.reclaimed_sma50 or features.breakout_retest:
            score += 3
        if trade_plan.reward_risk_estimate is not None and trade_plan.reward_risk_estimate >= 2:
            score += 4
        if not any((features.overextended, features.failed_breakout, features.falling_knife, features.weak_breakout_close)):
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
                    not features.weak_breakout_close,
                    features.breakout_retest if features.breakout_retest else None,
                ]
            ),
            "Relative Strength Leader": self._condition_ratio(
                [
                    features.rs_1m is not None and features.rs_1m > 0,
                    features.rs_3m is not None and features.rs_3m > 0,
                    features.rs_6m is not None and features.rs_6m > 0,
                    features.rs_vs_sector_3m >= 0 if features.rs_vs_sector_3m is not None else None,
                    features.holding_up_when_market_weak,
                    features.higher_lows_while_market_weak,
                    features.rs_line_rising,
                    features.strong_multitimeframe_trend,
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
                    not (security.fundamentals and security.fundamentals.recent_dilution),
                    catalyst_confirmed if security.catalyst else None,
                    security.fundamentals.institutional_support if security.fundamentals else None,
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
            ("Catalyst is confirmed by price and volume.", 3, self._score_catalyst(security, features) >= 10),
        ]
        return self._weighted_score(rules)

    def _bearish_score(self, features: FeatureSnapshot, security: SecurityData, trade_plan: TradePlan) -> tuple[int, list[str]]:
        earnings_too_close = bool(security.next_earnings_date and (security.next_earnings_date - self.analysis_date).days <= 7)
        poor_rr = trade_plan.reward_risk_estimate is None or trade_plan.reward_risk_estimate < 1.75
        rules = [
            ("Price is below a declining 50-day moving average.", 10, not features.above_50 and features.sma50_rising is False),
            ("Price is below a declining 200-day moving average.", 10, not features.above_200 and features.sma200_rising is False),
            ("Heavy-volume selling is showing up in the tape.", 12, features.distribution_days >= 4),
            ("The breakout structure has failed.", 12, features.failed_breakout),
            ("The current move is overextended from support.", 9, features.overextended),
            ("The move is extremely extended without consolidation.", 10, features.extreme_overextension),
            ("A gap-and-fade pattern weakens the setup.", 8, features.gap_and_fade),
            ("The breakout closed weakly.", 8, features.weak_breakout_close),
            ("The stock is acting like a falling knife.", 14, features.falling_knife),
            ("Reward/risk is poor or unclear.", 10, poor_rr),
            ("Liquidity is too low for a clean setup.", 8, features.low_liquidity),
            ("An earnings report is too close for a clean setup.", 7, earnings_too_close),
            ("Recent dilution risk is present.", 5, bool(security.fundamentals and security.fundamentals.recent_dilution)),
            ("Sector relative strength is weak.", 5, features.sector_support is False),
            ("Headline attention is not confirmed by price action.", 8, bool(security.catalyst and security.catalyst.hype_risk)),
            ("Price/volume action looks pump-like.", 8, features.pump_risk),
        ]
        return self._weighted_score(rules)

    def _risk_score(self, features: FeatureSnapshot, security: SecurityData, trade_plan: TradePlan) -> tuple[int, list[str]]:
        warnings: list[str] = []
        score = 0

        def flag(condition: bool, weight: int, warning: str) -> None:
            nonlocal score
            if condition:
                score += weight
                warnings.append(warning)

        earnings_too_close = bool(security.next_earnings_date and (security.next_earnings_date - self.analysis_date).days <= 7)
        poor_rr = trade_plan.reward_risk_estimate is None or trade_plan.reward_risk_estimate < 1.75
        flag(features.falling_knife, 20, "Falling knife behavior is present.")
        flag(features.failed_breakout, 16, "Recent breakout attempt failed.")
        flag(features.overextended, 12, "Move is extended away from the 50-day average.")
        flag(features.extreme_overextension, 16, "Move is extremely extended and vulnerable to chase risk.")
        flag(features.low_liquidity, 14, "Liquidity is too low for a clean research candidate.")
        flag(features.distribution_days >= 4, 10, "Heavy-volume selling is active.")
        flag(earnings_too_close, 10, "Earnings are too close to the setup.")
        flag(bool(security.catalyst and security.catalyst.hype_risk), 8, "Headline attention looks hype-driven.")
        flag(features.pump_risk, 12, "Price/volume behavior looks pump-like.")
        flag(bool(security.fundamentals and security.fundamentals.recent_dilution), 12, "Recent dilution/offering risk is present.")
        flag(features.sector_support is False, 6, "Sector backdrop is weak.")
        flag(trade_plan.invalidation_level is None, 8, "No clear invalidation level was found.")
        flag(poor_rr, 12, "Reward/risk is not attractive enough.")
        flag(features.weak_breakout_close, 8, "Breakout day close was weak.")
        return int(clamp(score, 0, 100)), warnings

    def _weighted_score(self, rules: list[tuple[str, int, bool]]) -> tuple[int, list[str]]:
        total_possible = sum(weight for _, weight, _ in rules)
        triggered = [description for description, _, condition in rules if condition]
        total = sum(weight for _, weight, condition in rules if condition)
        if total_possible == 0:
            return 0, triggered
        return int(round((total / total_possible) * 100)), triggered

    def _confidence(self, *, bullish_signals: list[str], bearish_signals: list[str], notes: list[str]) -> tuple[int, str]:
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
                features.broken_downtrend,
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
        if nearest_resistance is not None and (strategy_label == "No Clean Strategy" or features.broken_downtrend or features.falling_knife):
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

    def _score_outlier_price_strength(self, features: FeatureSnapshot) -> int:
        score = 0
        if features.return_1d is not None and features.return_1d > 0.02:
            score += 3
        if features.return_5d is not None and features.return_5d > 0.06:
            score += 5
        if features.return_1m is not None and features.return_1m > 0.12:
            score += 4
        if features.return_3m is not None and features.return_3m > 0.25:
            score += 4
        if features.return_6m is not None and features.return_6m > 0.40:
            score += 2
        if features.near_high or features.breakout_confirmed or features.price_near_multi_month_high:
            score += 2
        return min(score, 20)

    def _score_outlier_relative_strength(self, features: FeatureSnapshot) -> int:
        score = 0
        if features.rs_1d is not None and features.rs_1d > 0:
            score += 3
        if features.rs_5d is not None and features.rs_5d > 0:
            score += 4
        if features.rs_1m is not None and features.rs_1m > 0:
            score += 4
        if features.rs_3m is not None and features.rs_3m > 0:
            score += 4
        if features.rs_6m is not None and features.rs_6m > 0:
            score += 2
        if features.rs_line_rising:
            score += 2
        if features.holding_up_when_market_weak or features.higher_lows_while_market_weak:
            score += 1
        return min(score, 20)

    def _score_outlier_volume_attention(self, features: FeatureSnapshot, security: SecurityData) -> int:
        score = 0
        if features.unusual_volume:
            score += 6
        elif features.volume_confirmation:
            score += 3
        if features.close_location >= 0.7:
            score += 3
        if features.close_near_week_high:
            score += 3
        if features.accumulation_days >= 3:
            score += 3
        if security.social_attention:
            if security.social_attention.news_headline_count is not None and security.social_attention.news_headline_count >= 8:
                score += 3
            if security.social_attention.attention_velocity is not None and security.social_attention.attention_velocity >= 0.6:
                score += 2
        return min(score, 20)

    def _score_outlier_catalyst(self, security: SecurityData, features: FeatureSnapshot) -> int:
        catalyst = security.catalyst
        if not catalyst:
            return 0
        score = 0
        if catalyst.has_catalyst:
            score += 4
        if catalyst.price_reaction_positive or (features.return_5d is not None and features.return_5d > 0.05):
            score += 4
        if catalyst.volume_confirmation or features.unusual_volume:
            score += 3
        if catalyst.holds_gains or features.close_holds_breakout:
            score += 2
        if not catalyst.hype_risk:
            score += 2
        return min(score, 15)

    def _score_outlier_demand(self, security: SecurityData, features: FeatureSnapshot) -> int:
        score = 0
        short_interest = security.short_interest
        if short_interest:
            if short_interest.short_interest_percent_float is not None and short_interest.short_interest_percent_float >= 0.15:
                score += 4
            if short_interest.days_to_cover is not None and short_interest.days_to_cover >= 4:
                score += 2
            if short_interest.institutional_activity_positive:
                score += 2
        if security.fundamentals and security.fundamentals.institutional_support:
            score += 2
        elif features.accumulation_days >= 3:
            score += 2
        return min(score, 10)

    def _score_outlier_setup(self, features: FeatureSnapshot, trade_plan: TradePlan) -> int:
        score = 0
        if features.breakout_confirmed or features.breakout_retest:
            score += 4
        if features.clean_base or features.strong_multitimeframe_trend:
            score += 3
        if trade_plan.reward_risk_estimate is not None and trade_plan.reward_risk_estimate >= 2:
            score += 4
        if not any((features.falling_knife, features.failed_breakout, features.weak_breakout_close, features.extreme_overextension)):
            score += 2
        if trade_plan.invalidation_level is not None:
            score += 2
        return min(score, 15)

    def _outlier_classification(
        self,
        *,
        security: SecurityData,
        features: FeatureSnapshot,
        trade_plan: TradePlan,
        outlier_score: int,
        risk_score: int,
        status_label: str,
    ) -> tuple[str, str, list[str]]:
        alignments = {
            "Explosive Momentum": self._condition_ratio(
                [
                    features.return_5d is not None and features.return_5d > 0.06,
                    features.return_1m is not None and features.return_1m > 0.12,
                    features.return_3m is not None and features.return_3m > 0.25,
                    features.near_high or features.breakout_confirmed,
                    features.unusual_volume,
                    features.close_location >= 0.7,
                    not features.extreme_overextension,
                ]
            ),
            "Breakout Repricing": self._condition_ratio(
                [
                    features.clean_base,
                    features.breakout_confirmed,
                    features.breakout_volume_confirmation,
                    features.close_holds_breakout,
                    features.breakout_retest if features.breakout_retest else None,
                    not features.gap_and_fade,
                    not features.weak_breakout_close,
                ]
            ),
            "Short Squeeze Watch": self._condition_ratio(
                [
                    security.short_interest.short_interest_percent_float >= 0.15 if security.short_interest and security.short_interest.short_interest_percent_float is not None else None,
                    security.short_interest.days_to_cover >= 4 if security.short_interest and security.short_interest.days_to_cover is not None else None,
                    features.unusual_volume,
                    features.breakout_confirmed or features.near_high,
                    features.return_5d is not None and features.return_5d > 0.08,
                    bool(security.social_attention and security.social_attention.attention_velocity is not None and security.social_attention.attention_velocity >= 0.8),
                ]
            ),
            "IPO Leader": self._condition_ratio(
                [
                    features.recent_ipo,
                    features.clean_base,
                    features.breakout_confirmed or features.price_near_multi_month_high,
                    security.fundamentals.revenue_growth > 0 if security.fundamentals and security.fundamentals.revenue_growth is not None else None,
                    bool(security.theme_tags),
                    not features.broken_downtrend,
                ]
            ),
            "Long-Term Monster": self._condition_ratio(
                [
                    features.return_6m is not None and features.return_6m > 0.25,
                    features.return_12m is not None and features.return_12m > 0.45,
                    features.strong_multitimeframe_trend,
                    self._score_fundamentals(security) >= 8,
                    bool(security.theme_tags),
                    features.price_near_multi_month_high or features.near_high,
                    features.accumulation_days >= 3 or (security.fundamentals.institutional_support if security.fundamentals else False),
                    not features.broken_downtrend,
                ]
            ),
            "Theme/Narrative Leader": self._condition_ratio(
                [
                    bool(security.theme_tags),
                    features.rs_1m is not None and features.rs_1m > 0,
                    features.rs_3m is not None and features.rs_3m > 0,
                    bool(security.catalyst_tags),
                    features.volume_confirmation,
                    features.close_near_week_high,
                ]
            ),
            "Institutional Accumulation": self._condition_ratio(
                [
                    features.accumulation_days >= 3,
                    features.lower_volume_pullbacks,
                    features.support_holds,
                    features.close_location >= 0.65,
                    features.distribution_days <= 2,
                    security.fundamentals.institutional_support if security.fundamentals else None,
                ]
            ),
        }

        if status_label == "Avoid" or outlier_score < 35:
            return "Avoid", "The setup lacks enough confirmed outlier characteristics.", self._outlier_positive_reasons(features, security)
        squeeze_bias = bool(
            security.short_interest
            and (
                (security.short_interest.short_interest_percent_float is not None and security.short_interest.short_interest_percent_float >= 0.15)
                or (security.short_interest.days_to_cover is not None and security.short_interest.days_to_cover >= 4)
            )
            and ("Short squeeze" in security.theme_tags or "Short squeeze conditions" in security.catalyst_tags)
        )
        if (alignments["Short Squeeze Watch"] >= 60 or squeeze_bias) and outlier_score >= 60:
            return "Short Squeeze Watch", "Crowded short interest and volume expansion are creating a high-risk repricing setup.", self._outlier_positive_reasons(features, security)
        if alignments["IPO Leader"] >= 70 and outlier_score >= 60:
            return "IPO Leader", "A recent-public-name base is breaking higher with growth and narrative support.", self._outlier_positive_reasons(features, security)
        if alignments["Long-Term Monster"] >= 70 and outlier_score >= 50:
            return "Long-Term Monster", "Multi-quarter price leadership and fundamental support point to a potential compounder-style repricing.", self._outlier_positive_reasons(features, security)
        if alignments["Breakout Repricing"] >= 70 and outlier_score >= 65:
            return "Breakout Repricing", "A clean breakout with expansion volume and hold-above-pivot behavior is in force.", self._outlier_positive_reasons(features, security)
        if alignments["Theme/Narrative Leader"] >= 70 and outlier_score >= 50:
            return "Theme/Narrative Leader", "The stock is aligning with a live theme while price and volume confirm the narrative.", self._outlier_positive_reasons(features, security)
        if alignments["Institutional Accumulation"] >= 70 and outlier_score >= 60:
            return "Institutional Accumulation", "Repeated demand days and support holds suggest large-money sponsorship.", self._outlier_positive_reasons(features, security)
        if alignments["Explosive Momentum"] >= 60 and outlier_score >= 60:
            return "Explosive Momentum", "Unusual price strength and relative-strength acceleration are already visible in the tape.", self._outlier_positive_reasons(features, security)
        return "Watch Only", "The stock shows some outlier ingredients, but confirmation is incomplete.", self._outlier_positive_reasons(features, security)

    def _outlier_positive_reasons(self, features: FeatureSnapshot, security: SecurityData) -> list[str]:
        reasons: list[str] = []
        if features.return_5d is not None and features.return_5d > 0.06:
            reasons.append("5-day performance is unusually strong.")
        if features.rs_1m is not None and features.rs_1m > 0 and features.rs_3m is not None and features.rs_3m > 0:
            reasons.append("The stock is outperforming SPY/QQQ across multiple windows.")
        if features.breakout_confirmed:
            reasons.append("Price has pushed through resistance with confirmation.")
        if features.breakout_retest:
            reasons.append("A breakout retest is holding above the pivot.")
        if features.unusual_volume:
            reasons.append("Relative volume is meaningfully above normal.")
        if features.close_location >= 0.7 and features.close_near_week_high:
            reasons.append("Closes are staying near the high of the day/week.")
        if security.catalyst and security.catalyst.has_catalyst:
            reasons.append("A catalyst exists and price/volume are validating it.")
        if security.short_interest and security.short_interest.short_interest_percent_float is not None and security.short_interest.short_interest_percent_float >= 0.15:
            reasons.append("High short interest creates squeeze/repricing fuel.")
        if security.fundamentals and self._score_fundamentals(security) >= 8:
            reasons.append("Fundamental support is constructive enough to back the move.")
        if security.theme_tags:
            reasons.append(f"Theme support is present: {', '.join(security.theme_tags[:3])}.")
        return reasons

    def _outlier_risk_label(self, *, outlier_type: str, risk_score: int, features: FeatureSnapshot, security: SecurityData) -> str:
        if outlier_type == "Short Squeeze Watch":
            if features.extreme_overextension or features.pump_risk or bool(security.catalyst and security.catalyst.hype_risk):
                return "Extreme"
            return "High"
        if risk_score >= 65 or features.falling_knife:
            return "Extreme"
        if risk_score >= 40 or features.extreme_overextension or features.gap_and_fade:
            return "High"
        if risk_score >= 20:
            return "Medium"
        return "Low"

    def _chase_risk_warning(self, features: FeatureSnapshot, security: SecurityData) -> str | None:
        if features.extreme_overextension:
            return "Chase risk is elevated because price is far extended from support."
        if features.overextended and not features.breakout_retest:
            return "Chase risk is elevated because the move has not consolidated yet."
        if security.social_attention and security.social_attention.attention_velocity is not None and security.social_attention.attention_velocity >= 1.2 and features.unusual_volume:
            return "Attention is spiking quickly, so chasing a headline move carries extra risk."
        return None

    def _squeeze_watch_payload(self, security: SecurityData) -> dict[str, object]:
        if not security.short_interest:
            return self._unavailable_squeeze_payload()
        snapshot = security.short_interest
        return {
            "short_interest_percent_float": snapshot.short_interest_percent_float,
            "days_to_cover": snapshot.days_to_cover,
            "float_shares": snapshot.float_shares,
            "borrow_cost": snapshot.borrow_cost,
            "institutional_activity_positive": snapshot.institutional_activity_positive,
            "insider_activity_positive": snapshot.insider_activity_positive,
        }

    def _options_payload(self, security: SecurityData) -> dict[str, object]:
        if not security.options_data:
            return self._unavailable_options_payload()
        snapshot = security.options_data
        return {
            "options_interest_available": snapshot.options_interest_available,
            "unusual_options_activity": snapshot.unusual_options_activity,
            "options_daytrade_candidate": snapshot.options_daytrade_candidate,
            "implied_volatility_warning": snapshot.implied_volatility_warning,
            "earnings_iv_risk": snapshot.earnings_iv_risk,
        }

    @staticmethod
    def _unavailable_squeeze_payload() -> dict[str, object]:
        return {
            "short_interest_percent_float": None,
            "days_to_cover": None,
            "float_shares": None,
            "borrow_cost": None,
            "institutional_activity_positive": None,
            "insider_activity_positive": None,
        }

    @staticmethod
    def _unavailable_options_payload() -> dict[str, object]:
        return {
            "options_interest_available": None,
            "unusual_options_activity": None,
            "options_daytrade_candidate": None,
            "implied_volatility_warning": None,
            "earnings_iv_risk": None,
        }
