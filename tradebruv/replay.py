from __future__ import annotations

import csv
import json
import random
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from .models import PriceBar, SecurityData
from .providers import MarketDataProvider, ProviderFetchError, SECTOR_BENCHMARKS
from .scanner import DeterministicScanner


DEFAULT_HORIZONS = (1, 5, 10, 20, 60, 120)
FAMOUS_OUTLIER_WINDOWS: dict[str, tuple[date, date]] = {
    "GME": (date(2020, 8, 1), date(2021, 2, 15)),
    "CAR": (date(2021, 6, 1), date(2021, 11, 30)),
    "NVDA": (date(2023, 1, 1), date(2024, 12, 31)),
    "PLTR": (date(2023, 1, 1), date(2026, 4, 24)),
    "MU": (date(2023, 1, 1), date(2026, 4, 24)),
    "SMCI": (date(2023, 1, 1), date(2024, 6, 30)),
    "COIN": (date(2023, 1, 1), date(2024, 12, 31)),
    "HOOD": (date(2023, 1, 1), date(2024, 12, 31)),
    "ARM": (date(2023, 9, 14), date(2026, 4, 24)),
    "CAVA": (date(2023, 6, 15), date(2026, 4, 24)),
    "RDDT": (date(2024, 3, 21), date(2026, 4, 24)),
    "TSLA": (date(2020, 1, 1), date(2026, 4, 24)),
}


class PointInTimeProvider:
    def __init__(self, provider: MarketDataProvider, as_of: date, *, ohlcv_only: bool = True) -> None:
        self.provider = provider
        self.as_of = as_of
        self.ohlcv_only = ohlcv_only
        self._full_cache: dict[str, SecurityData] = {}

    def get_security_data(self, ticker: str) -> SecurityData:
        ticker = ticker.upper()
        if ticker not in self._full_cache:
            self._full_cache[ticker] = self.provider.get_security_data(ticker)
        return point_in_time_security(self._full_cache[ticker], self.as_of, ohlcv_only=self.ohlcv_only)


def point_in_time_security(security: SecurityData, as_of: date, *, ohlcv_only: bool = True) -> SecurityData:
    bars = [bar for bar in security.bars if bar.date <= as_of]
    if ohlcv_only:
        return SecurityData(
            ticker=security.ticker,
            company_name=security.company_name,
            sector=security.sector,
            industry=security.industry,
            bars=bars,
            ipo_date=security.ipo_date if security.ipo_date and security.ipo_date <= as_of else None,
            provider_name=security.provider_name,
            source_notes=security.source_notes,
            data_notes=[
                *security.data_notes,
                "Historical replay uses OHLCV-only point-in-time bars. Fundamentals/news/social/short-interest/options are omitted unless a point-in-time source is explicitly supplied.",
            ],
        )
    return replace(security, bars=bars)


def run_historical_replay(
    *,
    provider: MarketDataProvider,
    universe: Iterable[str],
    start_date: date,
    end_date: date,
    frequency: str = "weekly",
    mode: str = "outliers",
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    top_n: int = 20,
    output_dir: Path = Path("outputs/replay"),
    baselines: Iterable[str] = ("SPY", "QQQ"),
    random_baseline: bool = True,
) -> dict[str, Any]:
    tickers = sorted(dict.fromkeys(ticker.strip().upper() for ticker in universe if ticker.strip()))
    horizons = tuple(sorted({int(horizon) for horizon in horizons}))
    benchmark_symbols = sorted(dict.fromkeys([*(symbol.upper() for symbol in baselines), "SPY", "QQQ", *SECTOR_BENCHMARKS.values()]))
    cache = _prefetch(provider, [*tickers, *benchmark_symbols])
    replay_dates = _replay_dates(cache, tickers, start_date, end_date, frequency)

    rows: list[dict[str, Any]] = []
    avoid_rows: list[dict[str, Any]] = []
    random_rows: list[dict[str, Any]] = []
    false_negative_notes: list[dict[str, Any]] = []
    scans: list[dict[str, Any]] = []
    randomizer = random.Random(10)

    for replay_date in replay_dates:
        pit_provider = _CachedPointInTimeProvider(cache, replay_date)
        scanned = [result.to_dict() for result in DeterministicScanner(pit_provider, analysis_date=replay_date).scan(tickers, mode=mode)]
        selected = [row for row in scanned if row.get("status_label") != "Avoid"][:top_n]
        avoids = [row for row in scanned if row.get("status_label") == "Avoid"][: min(10, top_n)]
        scans.append(
            {
                "replay_date": replay_date.isoformat(),
                "top_candidates": selected,
                "avoid_candidates": avoids,
                "point_in_time_note": _point_in_time_note(),
            }
        )
        for row in selected:
            evaluated = _evaluate_row(row=row, cache=cache, signal_date=replay_date, horizons=horizons, baselines=baselines, use_velocity_levels=mode == "velocity")
            if evaluated.get("available"):
                rows.append(evaluated)
        for row in avoids:
            evaluated = _evaluate_row(row=row, cache=cache, signal_date=replay_date, horizons=horizons, baselines=baselines, use_velocity_levels=mode == "velocity")
            if evaluated.get("available"):
                avoid_rows.append(evaluated)
        if random_baseline and tickers and selected:
            sample_size = min(len(selected), len(tickers))
            for ticker in randomizer.sample(tickers, sample_size):
                random_eval = _evaluate_random(ticker=ticker, cache=cache, signal_date=replay_date, horizons=horizons, baselines=baselines)
                if random_eval.get("available"):
                    random_rows.append(random_eval)
        false_negative_notes.extend(_false_negative_notes(scanned, cache, replay_date, horizons))

    summary = _summary(
        rows=rows,
        avoid_rows=avoid_rows,
        random_rows=random_rows,
        replay_dates=replay_dates,
        horizons=horizons,
        baselines=baselines,
        mode=mode,
        false_negative_notes=false_negative_notes,
    )
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "mode": mode,
        "frequency": frequency,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "top_n": top_n,
        "horizons": list(horizons),
        "point_in_time_limitations": _point_in_time_note(),
        "summary": summary,
        "results": rows,
        "avoid_results": avoid_rows,
        "random_baseline_results": random_rows,
        "replay_scans": scans,
    }
    paths = write_replay_outputs(payload, output_dir=output_dir, prefix="velocity_replay" if mode == "velocity" else "replay")
    payload.update(paths)
    return payload


def run_investing_replay(
    *,
    provider: MarketDataProvider,
    universe: Iterable[str],
    start_date: date,
    end_date: date,
    frequency: str = "monthly",
    horizons: Iterable[int] = (20, 60, 120, 252),
    top_n: int = 10,
    output_dir: Path = Path("outputs/investing"),
    baselines: Iterable[str] = ("SPY", "QQQ"),
    random_baseline: bool = True,
) -> dict[str, Any]:
    tickers = sorted(dict.fromkeys(ticker.strip().upper() for ticker in universe if ticker.strip()))
    horizons = tuple(sorted({int(horizon) for horizon in horizons}))
    baseline_symbols = sorted(dict.fromkeys([*(symbol.upper() for symbol in baselines), "SPY", "QQQ", *SECTOR_BENCHMARKS.values()]))
    cache = _prefetch(provider, [*tickers, *baseline_symbols])
    replay_dates = _replay_dates(cache, tickers, start_date, end_date, frequency)
    rows: list[dict[str, Any]] = []
    winner_rows: list[dict[str, Any]] = []
    random_rows: list[dict[str, Any]] = []
    equal_weight_rows: list[dict[str, Any]] = []
    scans: list[dict[str, Any]] = []
    randomizer = random.Random(11)

    for replay_date in replay_dates:
        pit_provider = _CachedPointInTimeProvider(cache, replay_date)
        scanned = [result.to_dict() for result in DeterministicScanner(pit_provider, analysis_date=replay_date).scan(tickers, mode="investing")]
        selected = [row for row in scanned if row.get("investing_action_label") not in {"Avoid", "Data Insufficient"}][:top_n]
        winner_selected = sorted(scanned, key=lambda row: (-_to_float(row.get("winner_score")), _to_float(row.get("risk_score")), str(row.get("ticker"))))[:top_n]
        scans.append({"replay_date": replay_date.isoformat(), "top_investing_candidates": selected, "top_winner_score_candidates": winner_selected, "point_in_time_note": _point_in_time_note()})
        for row in selected:
            evaluated = _evaluate_row(row=row, cache=cache, signal_date=replay_date, horizons=horizons, baselines=baselines)
            if evaluated.get("available"):
                rows.append({**evaluated, "selection_lane": "regular_investing_score"})
        for row in winner_selected:
            evaluated = _evaluate_row(row=row, cache=cache, signal_date=replay_date, horizons=horizons, baselines=baselines)
            if evaluated.get("available"):
                winner_rows.append({**evaluated, "selection_lane": "winner_score"})
        if random_baseline and tickers and selected:
            for ticker in randomizer.sample(tickers, min(len(selected), len(tickers))):
                random_eval = _evaluate_random(ticker=ticker, cache=cache, signal_date=replay_date, horizons=horizons, baselines=baselines)
                if random_eval.get("available"):
                    random_rows.append(random_eval)
        for ticker in tickers:
            equal_eval = _evaluate_random(ticker=ticker, cache=cache, signal_date=replay_date, horizons=horizons, baselines=baselines)
            if equal_eval.get("available"):
                equal_weight_rows.append(equal_eval)

    summary = _investing_summary(
        rows=rows,
        winner_rows=winner_rows,
        random_rows=random_rows,
        equal_weight_rows=equal_weight_rows,
        replay_dates=replay_dates,
        horizons=horizons,
        baselines=baselines,
    )
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "mode": "regular_investing",
        "frequency": frequency,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "top_n": top_n,
        "horizons": list(horizons),
        "point_in_time_limitations": _point_in_time_note(),
        "fundamental_limitations": "Historical replay strips non-point-in-time fundamentals unless the provider supplies point-in-time snapshots. Current real-provider fundamentals are active snapshots and are not used in OHLCV-only replay scoring.",
        "summary": summary,
        "results": rows,
        "winner_score_baseline_results": winner_rows,
        "random_baseline_results": random_rows,
        "equal_weight_universe_results": equal_weight_rows,
        "replay_scans": scans,
    }
    paths = write_investing_replay_outputs(payload, output_dir=output_dir)
    payload.update(paths)
    return payload


def run_portfolio_replay(
    *,
    provider: MarketDataProvider,
    universe: Iterable[str],
    start_date: date,
    end_date: date,
    frequency: str = "monthly",
    horizons: Iterable[int] = (20, 60, 120, 252),
    output_dir: Path = Path("outputs/investing"),
    portfolio_size: int = 12,
) -> dict[str, Any]:
    from .analysis import build_portfolio_recommendation
    from .portfolio import PortfolioPosition

    tickers = sorted(dict.fromkeys(ticker.strip().upper() for ticker in universe if ticker.strip()))
    horizons = tuple(sorted({int(horizon) for horizon in horizons}))
    cache = _prefetch(provider, [*tickers, "SPY", "QQQ", *SECTOR_BENCHMARKS.values()])
    replay_dates = _replay_dates(cache, tickers, start_date, end_date, frequency)
    rows: list[dict[str, Any]] = []
    held: list[str] = []

    for replay_date in replay_dates:
        pit_provider = _CachedPointInTimeProvider(cache, replay_date)
        scanned = [result.to_dict() for result in DeterministicScanner(pit_provider, analysis_date=replay_date).scan(tickers, mode="investing")]
        if not held:
            held = [row["ticker"] for row in scanned[:portfolio_size]]
        candidate_pool = {row["ticker"]: row for row in scanned}
        for add_row in [row for row in scanned if row["ticker"] not in held][: max(1, portfolio_size // 4)]:
            held.append(add_row["ticker"])
        held = held[: max(portfolio_size * 2, portfolio_size)]
        simulated_positions = []
        for ticker in held:
            scanner_row = candidate_pool.get(ticker)
            if not scanner_row:
                continue
            simulated_positions.append(
                PortfolioPosition(
                    ticker=ticker,
                    company_name=str(scanner_row.get("company_name") or ticker),
                    quantity=1,
                    current_price=_to_float(scanner_row.get("current_price")),
                    market_value=_to_float(scanner_row.get("current_price")),
                    average_cost=_to_float(scanner_row.get("current_price")),
                    sector=str((scanner_row.get("data_used") or {}).get("sector") or ""),
                )
            )
        total = sum(position.market_value for position in simulated_positions) or 1
        for position in simulated_positions:
            position.position_weight_pct = (position.market_value / total) * 100
            scanner_row = candidate_pool.get(position.ticker, {})
            decision = build_portfolio_recommendation(position=position, scanner_row=scanner_row)
            evaluated = _evaluate_row(row=scanner_row, cache=cache, signal_date=replay_date, horizons=horizons, baselines=("SPY", "QQQ"))
            if evaluated.get("available"):
                rows.append({**evaluated, **{key: decision.get(key) for key in _portfolio_decision_fields()}, "portfolio_replay_date": replay_date.isoformat()})
        held = [row["ticker"] for row in rows[-len(simulated_positions) :] if row.get("core_investing_decision") not in {"Exit / Sell Candidate", "Trim"}][:portfolio_size]

    summary = _portfolio_replay_summary(rows, horizons)
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "mode": "portfolio_replay",
        "frequency": frequency,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "horizons": list(horizons),
        "summary": summary,
        "results": rows,
        "point_in_time_limitations": _point_in_time_note(),
        "safety": "Simulated portfolio validation only. No broker execution, orders, or real-money recommendation.",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "portfolio_replay_report.json"
    md_path = output_dir / "portfolio_replay_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_portfolio_replay_markdown(payload), encoding="utf-8")
    payload.update({"json_path": str(json_path), "markdown_path": str(md_path)})
    return payload


def run_investing_proof_report(
    *,
    provider: MarketDataProvider,
    universe: Iterable[str],
    start_date: date,
    end_date: date,
    baselines: Iterable[str] = ("SPY", "QQQ"),
    random_baseline: bool = True,
    output_dir: Path = Path("outputs/investing"),
) -> dict[str, Any]:
    replay = run_investing_replay(
        provider=provider,
        universe=universe,
        start_date=start_date,
        end_date=end_date,
        frequency="monthly",
        horizons=(20, 60, 120, 252),
        output_dir=output_dir,
        baselines=baselines,
        random_baseline=random_baseline,
    )
    portfolio = run_portfolio_replay(
        provider=provider,
        universe=universe,
        start_date=start_date,
        end_date=end_date,
        frequency="monthly",
        output_dir=output_dir,
    )
    summary = replay.get("summary", {})
    answers = _investing_proof_answers(summary, portfolio.get("summary", {}), baselines)
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "evidence_strength": _regular_evidence_strength(summary),
        "real_money_reliance": False,
        "language_note": "This is historical evidence for research and paper tracking, not proof of future returns or a real-money recommendation.",
        "answers": answers,
        "investing_replay": summary,
        "portfolio_replay": portfolio.get("summary", {}),
        "what_remains_unproven": [
            "Forward paper-tracked performance after Pass 11.",
            "Point-in-time fundamentals, debt, valuation, and analyst revisions.",
            "Whether Add/Hold/Trim/Exit labels remain useful across future regimes.",
        ],
        "recommended_use": "Use Core Investing for research and paper tracking. Do not rely on it as a source of truth for real-money decisions.",
        "point_in_time_limitations": replay.get("point_in_time_limitations"),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "investing_proof_report.json"
    md_path = output_dir / "investing_proof_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_investing_proof_markdown(payload), encoding="utf-8")
    payload.update({"json_path": str(json_path), "markdown_path": str(md_path)})
    return payload


def run_outlier_study(
    *,
    provider: MarketDataProvider,
    ticker: str,
    start_date: date,
    end_date: date,
    mode: str = "outliers",
    output_dir: Path = Path("outputs/case_studies"),
) -> dict[str, Any]:
    ticker = ticker.upper()
    cache = _prefetch(provider, [ticker, "SPY", "QQQ", *SECTOR_BENCHMARKS.values()])
    if ticker not in cache:
        payload = {"ticker": ticker, "available": False, "reason": "No price history available."}
        return payload
    replay_dates = _replay_dates(cache, [ticker], start_date, end_date, "daily")
    timeline: list[dict[str, Any]] = []
    trigger_rows: list[dict[str, Any]] = []
    volume_spike_dates: list[str] = []
    breakout_dates: list[str] = []
    invalidation_events: list[dict[str, Any]] = []

    for replay_date in replay_dates:
        pit_provider = _CachedPointInTimeProvider(cache, replay_date)
        try:
            security = pit_provider.get_security_data(ticker)
            row = DeterministicScanner(pit_provider, analysis_date=replay_date).scan([ticker], mode=mode)[0].to_dict()
        except ProviderFetchError:
            continue
        bars = security.bars
        latest = bars[-1]
        avg_volume20 = _avg([bar.volume for bar in bars[-21:-1]])
        rel_volume = latest.volume / avg_volume20 if avg_volume20 else 0.0
        prior_high = max((bar.high for bar in bars[-65:-5]), default=0)
        if rel_volume >= 1.75:
            volume_spike_dates.append(replay_date.isoformat())
        if prior_high and latest.close > prior_high * 1.01:
            breakout_dates.append(replay_date.isoformat())
        if _to_float(row.get("invalidation_level")) and latest.low <= _to_float(row.get("invalidation_level")):
            invalidation_events.append({"date": replay_date.isoformat(), "price": latest.close, "invalidation": row.get("invalidation_level")})
        item = {
            "date": replay_date.isoformat(),
            "price": latest.close,
            "volume": latest.volume,
            "relative_volume": round(rel_volume, 4),
            "status_label": row.get("status_label"),
            "outlier_type": row.get("outlier_type"),
            "outlier_score": row.get("outlier_score"),
            "velocity_score": row.get("velocity_score"),
            "velocity_type": row.get("velocity_type"),
            "risk_score": row.get("risk_score"),
            "triggered": _is_trigger(row, mode=mode),
        }
        timeline.append(item)
        if item["triggered"]:
            trigger_rows.append({**item, "scanner_row": row})

    first = trigger_rows[0] if trigger_rows else None
    first_date = date.fromisoformat(first["date"]) if first else None
    first_eval = _evaluate_row(row=first["scanner_row"], cache=cache, signal_date=first_date, horizons=DEFAULT_HORIZONS, baselines=("SPY", "QQQ"), use_velocity_levels=mode == "velocity") if first and first_date else {}
    peak = max(timeline, key=lambda row: float(row["price"])) if timeline else None
    days_to_peak = (date.fromisoformat(peak["date"]) - first_date).days if peak and first_date else None
    max_forward_return = first_eval.get("max_favorable_excursion", "unavailable")
    verdict = _case_verdict(first, first_eval, days_to_peak)
    payload = {
        "ticker": ticker,
        "available": True,
        "mode": mode,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "first_trigger_date": first["date"] if first else "missed",
        "first_trigger_type": (first.get("outlier_type") if mode != "velocity" else first.get("velocity_type")) if first else "missed",
        "first_outlier_score": first.get("outlier_score") if first else "unavailable",
        "max_outlier_score": max((_to_float(row.get("outlier_score")) for row in timeline), default=0),
        "date_of_max_score": _date_of_max(timeline, "outlier_score"),
        "price_at_first_trigger": first.get("price") if first else "unavailable",
        "max_forward_return_after_trigger": max_forward_return,
        "max_drawdown_after_trigger": first_eval.get("max_adverse_excursion", "unavailable"),
        "days_from_trigger_to_peak": days_to_peak if days_to_peak is not None else "unavailable",
        "did_it_catch_move": verdict["did_it_catch_move"],
        "was_it_early_or_late": verdict["was_it_early_or_late"],
        "false_positive_notes": _false_trigger_notes(trigger_rows, first_eval),
        "missing_data_notes": [_point_in_time_note()],
        "point_in_time_limitations": _point_in_time_note(),
        "volume_spike_dates": volume_spike_dates,
        "relative_strength_acceleration_dates": [row["date"] for row in timeline if _to_float(row.get("outlier_score")) >= 60],
        "breakout_dates": breakout_dates,
        "invalidation_events": invalidation_events,
        "score_progression": timeline,
        "narrative": _case_markdown_narrative(ticker, first, verdict, first_eval),
    }
    paths = write_case_study_outputs(payload, output_dir=output_dir)
    payload.update(paths)
    return payload


def run_famous_outlier_studies(
    *,
    provider: MarketDataProvider,
    output_dir: Path = Path("outputs/case_studies"),
    mode: str = "outliers",
) -> dict[str, Any]:
    studies = [
        run_outlier_study(provider=provider, ticker=ticker, start_date=window[0], end_date=window[1], mode=mode, output_dir=output_dir)
        for ticker, window in FAMOUS_OUTLIER_WINDOWS.items()
    ]
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "mode": mode,
        "studies": studies,
        "summary": {
            "total": len(studies),
            "caught": sum(1 for study in studies if study.get("did_it_catch_move") == "caught"),
            "missed": sum(1 for study in studies if study.get("did_it_catch_move") == "missed"),
            "inconclusive": sum(1 for study in studies if study.get("did_it_catch_move") == "inconclusive"),
        },
        "point_in_time_limitations": _point_in_time_note(),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = "velocity_famous_outliers" if mode == "velocity" else "famous_outliers_summary"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_famous_markdown(payload), encoding="utf-8")
    payload.update({"json_path": str(json_path), "markdown_path": str(md_path)})
    return payload


def run_proof_report(
    *,
    provider: MarketDataProvider,
    universe: Iterable[str],
    start_date: date,
    end_date: date,
    include_famous_outliers: bool = False,
    include_velocity: bool = False,
    baselines: Iterable[str] = ("SPY", "QQQ"),
    random_baseline: bool = True,
    output_dir: Path = Path("outputs/proof"),
) -> dict[str, Any]:
    replay = run_historical_replay(
        provider=provider,
        universe=universe,
        start_date=start_date,
        end_date=end_date,
        frequency="weekly",
        mode="outliers",
        baselines=baselines,
        random_baseline=random_baseline,
    )
    velocity = None
    if include_velocity:
        velocity = run_historical_replay(
            provider=provider,
            universe=universe,
            start_date=start_date,
            end_date=end_date,
            frequency="weekly",
            mode="velocity",
            baselines=baselines,
            random_baseline=random_baseline,
        )
    famous = run_famous_outlier_studies(provider=provider) if include_famous_outliers else None
    evidence = _evidence_strength(replay.get("summary", {}))
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "evidence_strength": evidence,
        "real_money_reliance": False,
        "language_note": "This is evidence, not proof of future performance or prediction accuracy.",
        "historical_replay": replay.get("summary", {}),
        "velocity_replay": velocity.get("summary", {}) if velocity else None,
        "famous_outliers": famous.get("summary", {}) if famous else None,
        "answers": _proof_answers(replay, velocity, famous, baselines),
        "what_remains_unproven": [
            "Forward live/paper performance across future regimes.",
            "Point-in-time fundamentals, news, short-interest, and social-data effects.",
            "Real-money execution quality, slippage, taxes, liquidity, and behavioral discipline.",
        ],
        "paper_track_next": [
            "Track at least 30 closed forward predictions before tuning thresholds.",
            "Separate velocity setups from long-term compounder setups.",
            "Record every Avoid and false-positive case, not only winners.",
        ],
        "point_in_time_limitations": _point_in_time_note(),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "proof_report.json"
    md_path = output_dir / "proof_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_proof_markdown(payload), encoding="utf-8")
    payload.update({"json_path": str(json_path), "markdown_path": str(md_path)})
    return payload


class _CachedPointInTimeProvider:
    def __init__(self, cache: dict[str, SecurityData], as_of: date) -> None:
        self.cache = cache
        self.as_of = as_of

    def get_security_data(self, ticker: str) -> SecurityData:
        ticker = ticker.upper()
        if ticker not in self.cache:
            raise ProviderFetchError(f"{ticker} unavailable for replay.")
        security = point_in_time_security(self.cache[ticker], self.as_of, ohlcv_only=True)
        if len(security.bars) < 30:
            raise ProviderFetchError(f"{ticker} has fewer than 30 OHLCV bars by {self.as_of}.")
        return security


def _prefetch(provider: MarketDataProvider, tickers: Iterable[str]) -> dict[str, SecurityData]:
    cache: dict[str, SecurityData] = {}
    for ticker in sorted(dict.fromkeys(ticker.upper() for ticker in tickers if ticker)):
        try:
            cache[ticker] = provider.get_security_data(ticker)
        except Exception:
            continue
    return cache


def _replay_dates(cache: dict[str, SecurityData], universe: list[str], start_date: date, end_date: date, frequency: str) -> list[date]:
    date_source = cache.get("SPY") or next((cache.get(ticker) for ticker in universe if ticker in cache), None)
    if not date_source:
        return []
    dates = [bar.date for bar in date_source.bars if start_date <= bar.date <= end_date]
    if frequency == "daily":
        return dates
    if frequency == "monthly":
        monthly: list[date] = []
        seen_months: set[tuple[int, int]] = set()
        for item in dates:
            key = (item.year, item.month)
            if key not in seen_months:
                monthly.append(item)
                seen_months.add(key)
        return monthly
    weekly: list[date] = []
    seen: set[tuple[int, int]] = set()
    for item in dates:
        key = item.isocalendar()[:2]
        if key not in seen:
            weekly.append(item)
            seen.add(key)
    return weekly


def _evaluate_row(
    *,
    row: dict[str, Any],
    cache: dict[str, SecurityData],
    signal_date: date,
    horizons: Iterable[int],
    baselines: Iterable[str],
    use_velocity_levels: bool = False,
) -> dict[str, Any]:
    evaluated = _evaluate_ticker(str(row.get("ticker", "")), cache, signal_date, horizons)
    if not evaluated.get("available"):
        return evaluated
    benchmark_returns = {
        symbol.upper(): _evaluate_ticker(symbol.upper(), cache, signal_date, horizons).get("returns", {})
        for symbol in baselines
    }
    returns = evaluated["returns"]
    excess = {}
    for symbol, payload in benchmark_returns.items():
        for horizon, value in returns.items():
            benchmark_value = payload.get(horizon)
            excess[f"excess_vs_{symbol}_{horizon}"] = _round(value - benchmark_value) if benchmark_value is not None else None
    tp1 = _to_float(row.get("velocity_tp1") if use_velocity_levels else row.get("tp1"))
    tp2 = _to_float(row.get("velocity_tp2") if use_velocity_levels else row.get("tp2"))
    invalidation = _to_float(row.get("velocity_invalidation") if use_velocity_levels else row.get("invalidation_level"))
    levels = _level_hits(cache[str(row.get("ticker")).upper()], signal_date, max(horizons), tp1=tp1, tp2=tp2, invalidation=invalidation)
    return {
        **{key: row.get(key) for key in _result_fields()},
        "sector": row.get("sector") or (row.get("data_used") or {}).get("sector"),
        "replay_date": signal_date.isoformat(),
        "available": True,
        "signal_price": evaluated["signal_price"],
        "returns": returns,
        "max_favorable_excursion": evaluated["max_favorable_excursion"],
        "max_adverse_excursion": evaluated["max_adverse_excursion"],
        **levels,
        "benchmark_returns": benchmark_returns,
        "excess_returns": excess,
    }


def _evaluate_random(ticker: str, cache: dict[str, SecurityData], signal_date: date, horizons: Iterable[int], baselines: Iterable[str]) -> dict[str, Any]:
    evaluated = _evaluate_ticker(ticker, cache, signal_date, horizons)
    if not evaluated.get("available"):
        return evaluated
    return {"ticker": ticker, "replay_date": signal_date.isoformat(), **evaluated, "baselines": list(baselines)}


def _evaluate_ticker(ticker: str, cache: dict[str, SecurityData], signal_date: date, horizons: Iterable[int]) -> dict[str, Any]:
    security = cache.get(ticker.upper())
    if not security:
        return {"ticker": ticker, "available": False, "reason": "Ticker unavailable."}
    index = _bar_index_at_or_before(security.bars, signal_date)
    if index is None:
        return {"ticker": ticker, "available": False, "reason": "No bar on or before replay date."}
    signal = security.bars[index]
    returns: dict[str, float | None] = {}
    for horizon in horizons:
        target = index + int(horizon)
        returns[f"{horizon}d"] = _round(((security.bars[target].close / signal.close) - 1.0) * 100) if target < len(security.bars) and signal.close else None
    window = security.bars[index + 1 : min(len(security.bars), index + max(horizons) + 1)]
    if not window:
        return {"ticker": ticker, "available": False, "reason": "No forward bars after replay date."}
    return {
        "ticker": ticker,
        "available": True,
        "signal_price": signal.close,
        "returns": returns,
        "max_favorable_excursion": _round(((max(bar.high for bar in window) / signal.close) - 1.0) * 100),
        "max_adverse_excursion": _round(((min(bar.low for bar in window) / signal.close) - 1.0) * 100),
    }


def _level_hits(security: SecurityData, signal_date: date, max_horizon: int, *, tp1: float, tp2: float, invalidation: float) -> dict[str, Any]:
    index = _bar_index_at_or_before(security.bars, signal_date)
    if index is None:
        return {"hit_TP1": False, "hit_TP2": False, "hit_invalidation": False}
    window = security.bars[index + 1 : min(len(security.bars), index + max_horizon + 1)]
    hit_tp1 = hit_tp2 = hit_inv = False
    days_tp1 = days_tp2 = days_inv = None
    for offset, bar in enumerate(window, start=1):
        if tp1 and not hit_tp1 and bar.high >= tp1:
            hit_tp1, days_tp1 = True, offset
        if tp2 and not hit_tp2 and bar.high >= tp2:
            hit_tp2, days_tp2 = True, offset
        if invalidation and not hit_inv and bar.low <= invalidation:
            hit_inv, days_inv = True, offset
    return {
        "hit_TP1": hit_tp1,
        "hit_TP2": hit_tp2,
        "hit_invalidation": hit_inv,
        "days_to_TP1": days_tp1,
        "days_to_TP2": days_tp2,
        "days_to_invalidation": days_inv,
    }


def _summary(
    *,
    rows: list[dict[str, Any]],
    avoid_rows: list[dict[str, Any]],
    random_rows: list[dict[str, Any]],
    replay_dates: list[date],
    horizons: Iterable[int],
    baselines: Iterable[str],
    mode: str,
    false_negative_notes: list[dict[str, Any]],
) -> dict[str, Any]:
    horizon_metrics = {f"{horizon}d": _return_metrics(rows, f"{horizon}d") for horizon in horizons}
    random_metrics = {f"{horizon}d": _return_metrics(random_rows, f"{horizon}d") for horizon in horizons}
    benchmark_excess = {}
    for symbol in baselines:
        for horizon in horizons:
            values = [_nested_float(row, "excess_returns", f"excess_vs_{symbol.upper()}_{horizon}d") for row in rows]
            values = [value for value in values if value is not None]
            benchmark_excess[f"{symbol.upper()}_{horizon}d"] = _avg_metric(values)
    return {
        "mode": mode,
        "total_replay_dates": len(replay_dates),
        "total_candidates": len(rows),
        "total_avoid_candidates": len(avoid_rows),
        "average_forward_return_by_horizon": {key: value["average"] for key, value in horizon_metrics.items()},
        "median_forward_return_by_horizon": {key: value["median"] for key, value in horizon_metrics.items()},
        "win_rate_by_horizon": {key: value["win_rate"] for key, value in horizon_metrics.items()},
        "average_MFE": _avg([_to_float(row.get("max_favorable_excursion")) for row in rows]),
        "average_MAE": _avg([_to_float(row.get("max_adverse_excursion")) for row in rows]),
        "TP1_hit_rate": _rate(row.get("hit_TP1") for row in rows),
        "TP2_hit_rate": _rate(row.get("hit_TP2") for row in rows),
        "invalidation_hit_rate": _rate(row.get("hit_invalidation") for row in rows),
        "excess_return_vs_baselines": benchmark_excess,
        "random_baseline_comparison": random_metrics,
        "strategy_performance": _bucket(rows, "strategy_label"),
        "outlier_type_performance": _bucket(rows, "outlier_type"),
        "velocity_type_performance": _bucket(rows, "velocity_type"),
        "score_bucket_performance": _bucket(_with_score_bucket(rows, "outlier_score"), "score_bucket"),
        "risk_bucket_performance": _bucket(_with_risk_bucket(rows), "risk_bucket"),
        "false_positive_rate": _false_positive_rate(rows),
        "avoid_signal_correct_rate": _avoid_correct_rate(avoid_rows),
        "false_negative_case_study_notes": false_negative_notes[:20],
        "sample_size_warning": "Small sample: treat as directional evidence only." if len(rows) < 100 else "",
        "safety": "Historical replay uses no future OHLCV before each replay date. It is evidence gathering, not guaranteed prediction accuracy.",
    }


def _investing_summary(
    *,
    rows: list[dict[str, Any]],
    winner_rows: list[dict[str, Any]],
    random_rows: list[dict[str, Any]],
    equal_weight_rows: list[dict[str, Any]],
    replay_dates: list[date],
    horizons: Iterable[int],
    baselines: Iterable[str],
) -> dict[str, Any]:
    horizon_metrics = {f"{horizon}d": _return_metrics(rows, f"{horizon}d") for horizon in horizons}
    winner_metrics = {f"{horizon}d": _return_metrics(winner_rows, f"{horizon}d") for horizon in horizons}
    random_metrics = {f"{horizon}d": _return_metrics(random_rows, f"{horizon}d") for horizon in horizons}
    equal_weight_metrics = {f"{horizon}d": _return_metrics(equal_weight_rows, f"{horizon}d") for horizon in horizons}
    benchmark_excess = {}
    random_excess = {}
    equal_weight_excess = {}
    for horizon in horizons:
        key = f"{horizon}d"
        row_avg = horizon_metrics[key]["average"]
        random_avg = random_metrics[key]["average"]
        equal_avg = equal_weight_metrics[key]["average"]
        random_excess[key] = _round(row_avg - random_avg) if row_avg is not None and random_avg is not None else None
        equal_weight_excess[key] = _round(row_avg - equal_avg) if row_avg is not None and equal_avg is not None else None
        for symbol in baselines:
            values = [_nested_float(row, "excess_returns", f"excess_vs_{symbol.upper()}_{horizon}d") for row in rows]
            values = [value for value in values if value is not None]
            benchmark_excess[f"{symbol.upper()}_{key}"] = _avg_metric(values)
    return {
        "mode": "regular_investing",
        "total_replay_dates": len(replay_dates),
        "total_candidates": len(rows),
        "regular_investing_forward_returns": horizon_metrics,
        "winner_score_forward_returns": winner_metrics,
        "random_baseline_comparison": random_metrics,
        "equal_weight_universe_baseline": equal_weight_metrics,
        "excess_return_vs_baselines": benchmark_excess,
        "excess_return_vs_random_baseline": random_excess,
        "excess_return_vs_equal_weight_universe": equal_weight_excess,
        "median_forward_return_by_horizon": {key: value["median"] for key, value in horizon_metrics.items()},
        "win_rate_by_horizon": {key: value["win_rate"] for key, value in horizon_metrics.items()},
        "average_MFE": _avg([_to_float(row.get("max_favorable_excursion")) for row in rows]),
        "average_MAE": _avg([_to_float(row.get("max_adverse_excursion")) for row in rows]),
        "hit_invalidation_rate": _rate(row.get("hit_invalidation") for row in rows),
        "false_positive_rate": _false_positive_rate(rows),
        "turnover": _turnover(rows),
        "repeated_monthly_picks": _repeated_picks(rows),
        "sector_concentration": _bucket(rows, "sector"),
        "best_worst_investing_styles": _bucket(rows, "investing_style"),
        "best_worst_action_labels": _bucket(rows, "investing_action_label"),
        "sample_size_warning": "Small sample: treat as weak evidence only." if len(rows) < 100 else "",
        "safety": "Regular investing replay is research evidence only. It can underperform SPY, QQQ, random, or equal-weight baselines.",
    }


def write_investing_replay_outputs(payload: dict[str, Any], *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "investing_replay_results.json"
    csv_path = output_dir / "investing_replay_results.csv"
    summary_json = output_dir / "investing_replay_summary.json"
    summary_md = output_dir / "investing_replay_summary.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    summary_json.write_text(json.dumps(payload["summary"], indent=2), encoding="utf-8")
    _write_investing_rows_csv(payload.get("results", []), csv_path)
    summary_md.write_text(_investing_replay_markdown(payload), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "summary_json_path": str(summary_json),
        "summary_markdown_path": str(summary_md),
    }


def write_replay_outputs(payload: dict[str, Any], *, output_dir: Path, prefix: str = "replay") -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / ("replay_results.json" if prefix == "replay" else f"{prefix}_results.json")
    csv_path = output_dir / ("replay_results.csv" if prefix == "replay" else f"{prefix}_results.csv")
    summary_json = output_dir / ("replay_summary.json" if prefix == "replay" else f"{prefix}_summary.json")
    summary_md = output_dir / ("replay_summary.md" if prefix == "replay" else f"{prefix}_summary.md")
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    summary_json.write_text(json.dumps(payload["summary"], indent=2), encoding="utf-8")
    _write_rows_csv(payload.get("results", []), csv_path)
    summary_md.write_text(_replay_markdown(payload), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "summary_json_path": str(summary_json),
        "summary_markdown_path": str(summary_md),
    }


def write_case_study_outputs(payload: dict[str, Any], *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['ticker']}_case_study"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_case_markdown(payload), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(md_path)}


def _write_rows_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "replay_date",
        "ticker",
        "status_label",
        "strategy_label",
        "outlier_type",
        "outlier_score",
        "velocity_type",
        "velocity_score",
        "risk_score",
        "signal_price",
        "return_1d",
        "return_5d",
        "return_10d",
        "return_20d",
        "return_60d",
        "return_120d",
        "max_favorable_excursion",
        "max_adverse_excursion",
        "hit_TP1",
        "hit_TP2",
        "hit_invalidation",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            flat = {field: row.get(field, "") for field in fields}
            for key, value in (row.get("returns") or {}).items():
                flat[f"return_{key}"] = value
            writer.writerow(flat)


def _write_investing_rows_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "replay_date",
        "ticker",
        "regular_investing_score",
        "investing_action_label",
        "investing_style",
        "investing_risk",
        "thesis_quality",
        "investing_data_quality",
        "winner_score",
        "risk_score",
        "signal_price",
        "return_20d",
        "return_60d",
        "return_120d",
        "return_252d",
        "max_favorable_excursion",
        "max_adverse_excursion",
        "hit_invalidation",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            flat = {field: row.get(field, "") for field in fields}
            for key, value in (row.get("returns") or {}).items():
                flat[f"return_{key}"] = value
            writer.writerow(flat)


def _result_fields() -> list[str]:
    return [
        "ticker",
        "company_name",
        "status_label",
        "strategy_label",
        "regular_investing_score",
        "investing_style",
        "investing_risk",
        "investing_time_horizon",
        "investing_action_label",
        "investing_reason",
        "investing_bear_case",
        "investing_invalidation",
        "investing_events_to_watch",
        "value_trap_warning",
        "thesis_quality",
        "investing_data_quality",
        "regular_investing_components",
        "outlier_type",
        "outlier_score",
        "outlier_risk",
        "risk_score",
        "setup_quality_score",
        "winner_score",
        "sector",
        "velocity_score",
        "velocity_type",
        "velocity_risk",
        "quick_trade_watch_label",
        "trigger_reason",
        "chase_warning",
        "expected_horizon",
        "tp1",
        "tp2",
        "invalidation_level",
        "velocity_tp1",
        "velocity_tp2",
        "velocity_invalidation",
    ]


def _return_metrics(rows: list[dict[str, Any]], horizon_key: str) -> dict[str, Any]:
    values = []
    for row in rows:
        if "returns" in row:
            value = (row.get("returns") or {}).get(horizon_key)
        else:
            value = (row.get("returns") or {}).get(horizon_key)
        if value is not None:
            values.append(float(value))
    return {
        "sample_size": len(values),
        "average": _round(sum(values) / len(values)) if values else None,
        "median": _round(median(values)) if values else None,
        "win_rate": _round(sum(1 for value in values if value > 0) / len(values)) if values else None,
    }


def _bucket(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(str(row.get(field) or "Unclassified"), []).append(row)
    output = []
    for key, bucket_rows in buckets.items():
        metrics = _return_metrics(bucket_rows, "20d")
        output.append({field: key, **metrics, "false_positive_rate": _false_positive_rate(bucket_rows)})
    return sorted(output, key=lambda row: row.get("sample_size", 0), reverse=True)


def _with_score_bucket(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        score = _to_float(row.get(field))
        bucket = "80+" if score >= 80 else "60-79" if score >= 60 else "40-59" if score >= 40 else "<40"
        output.append({**row, "score_bucket": bucket})
    return output


def _with_risk_bucket(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        risk = _to_float(row.get("risk_score"))
        bucket = "High" if risk >= 65 else "Medium" if risk >= 35 else "Low"
        output.append({**row, "risk_bucket": bucket})
    return output


def _false_positive_rate(rows: list[dict[str, Any]]) -> float | None:
    measured = [row for row in rows if (row.get("returns") or {}).get("20d") is not None]
    if not measured:
        return None
    false_count = sum(1 for row in measured if (row.get("returns") or {}).get("20d", 0) <= 0 or (row.get("hit_invalidation") and not row.get("hit_TP1")))
    return _round(false_count / len(measured))


def _avoid_correct_rate(rows: list[dict[str, Any]]) -> float | None:
    measured = [row for row in rows if (row.get("returns") or {}).get("20d") is not None]
    if not measured:
        return None
    correct = sum(1 for row in measured if (row.get("returns") or {}).get("20d", 0) <= 0 or row.get("hit_invalidation"))
    return _round(correct / len(measured))


def _false_negative_notes(scanned: list[dict[str, Any]], cache: dict[str, SecurityData], replay_date: date, horizons: Iterable[int]) -> list[dict[str, Any]]:
    selected = {row.get("ticker") for row in scanned if row.get("status_label") != "Avoid" and _to_float(row.get("outlier_score")) >= 40}
    notes = []
    for row in scanned:
        ticker = str(row.get("ticker"))
        if ticker in selected:
            continue
        evaluated = _evaluate_ticker(ticker, cache, replay_date, horizons)
        return_20d = (evaluated.get("returns") or {}).get("20d") if evaluated.get("available") else None
        if return_20d is not None and return_20d >= 20:
            notes.append(
                {
                    "replay_date": replay_date.isoformat(),
                    "ticker": ticker,
                    "return_20d": return_20d,
                    "scanner_label": row.get("status_label"),
                    "note": "Ticker made a large forward move without a strong selected signal; review for missed setup context.",
                }
            )
    return notes[:3]


def _bar_index_at_or_before(bars: list[PriceBar], item: date) -> int | None:
    index = None
    for idx, bar in enumerate(bars):
        if bar.date <= item:
            index = idx
        else:
            break
    return index


def _is_trigger(row: dict[str, Any], *, mode: str) -> bool:
    if mode == "velocity":
        return _to_float(row.get("velocity_score")) >= 45 and "Avoid" not in str(row.get("velocity_type"))
    return str(row.get("status_label")) in {"Watch Only", "Strong Research Candidate", "Active Setup", "Trade Setup Forming"} and _to_float(row.get("outlier_score")) >= 35


def _case_verdict(first: dict[str, Any] | None, first_eval: dict[str, Any], days_to_peak: int | None) -> dict[str, str]:
    if not first:
        return {"did_it_catch_move": "missed", "was_it_early_or_late": "missed"}
    mfe = _to_float(first_eval.get("max_favorable_excursion"))
    if mfe < 20:
        return {"did_it_catch_move": "inconclusive", "was_it_early_or_late": "triggered but move was not large after trigger"}
    if days_to_peak is not None and days_to_peak >= 20:
        timing = "early"
    elif days_to_peak is not None and days_to_peak <= 5:
        timing = "late/during move"
    else:
        timing = "during move"
    return {"did_it_catch_move": "caught", "was_it_early_or_late": timing}


def _false_trigger_notes(trigger_rows: list[dict[str, Any]], first_eval: dict[str, Any]) -> list[str]:
    if not trigger_rows:
        return ["No trigger occurred in the selected window."]
    notes = [f"{len(trigger_rows)} trigger day(s) occurred before or during the study window."]
    if first_eval.get("hit_invalidation") and not first_eval.get("hit_TP1"):
        notes.append("The first trigger hit invalidation before TP1, so classify carefully as a false/early trigger.")
    return notes


def _date_of_max(timeline: list[dict[str, Any]], field: str) -> str:
    if not timeline:
        return "unavailable"
    return str(max(timeline, key=lambda row: _to_float(row.get(field))).get("date"))


def _proof_answers(replay: dict[str, Any], velocity: dict[str, Any] | None, famous: dict[str, Any] | None, baselines: Iterable[str]) -> dict[str, Any]:
    summary = replay.get("summary", {})
    return {
        "beat_SPY_QQQ_historically": summary.get("excess_return_vs_baselines", {}),
        "beat_random_baseline": summary.get("random_baseline_comparison", {}),
        "which_strategies_worked": summary.get("strategy_performance", []),
        "which_strategies_were_weak": [row for row in summary.get("strategy_performance", []) if (row.get("average") or 0) <= 0],
        "famous_outlier_detection": famous.get("summary") if famous else "Not included.",
        "high_volume_triggers_worked": velocity.get("summary") if velocity else "Not included.",
        "false_positives": summary.get("false_positive_rate"),
        "avoid_signals_correct": summary.get("avoid_signal_correct_rate"),
        "minimum_evidence_threshold": "At least 30 closed forward paper predictions per major setup family; 100+ historical samples is more useful.",
        "baseline_symbols": [symbol.upper() for symbol in baselines],
    }


def _investing_proof_answers(summary: dict[str, Any], portfolio_summary: dict[str, Any], baselines: Iterable[str]) -> dict[str, Any]:
    excess = summary.get("excess_return_vs_baselines", {})
    random_excess = summary.get("excess_return_vs_random_baseline", {})
    equal_excess = summary.get("excess_return_vs_equal_weight_universe", {})
    return {
        "does_regular_investing_score_beat_SPY": _beat_baseline_text(excess, "SPY_252d"),
        "does_regular_investing_score_beat_QQQ": _beat_baseline_text(excess, "QQQ_252d"),
        "does_it_beat_random_baseline": _beat_simple_text(random_excess.get("252d")),
        "does_it_beat_equal_weight_universe": _beat_simple_text(equal_excess.get("252d")),
        "which_investing_styles_work": [row for row in summary.get("best_worst_investing_styles", []) if (row.get("average") or 0) > 0],
        "which_investing_styles_are_poor": [row for row in summary.get("best_worst_investing_styles", []) if (row.get("average") or 0) <= 0],
        "are_add_hold_trim_exit_labels_useful": portfolio_summary.get("label_usefulness", "Not enough evidence"),
        "is_system_useful_for_normal_investing": "Useful for research/paper tracking only when it beats or clearly contextualizes baselines; not for real-money reliance.",
        "what_remains_unproven": "Point-in-time fundamentals, future performance, valuation calibration, taxes, execution, and behavior.",
        "baseline_symbols": [symbol.upper() for symbol in baselines],
    }


def _beat_baseline_text(excess: dict[str, Any], key: str) -> str:
    value = excess.get(key)
    average = value.get("average") if isinstance(value, dict) else value
    return _beat_simple_text(average)


def _beat_simple_text(value: Any) -> str:
    if value is None:
        return "Not enough evidence"
    numeric = _to_float(value)
    if numeric > 0:
        return f"Yes in this replay window by {numeric:.2f} percentage points on average."
    if numeric < 0:
        return f"No in this replay window; it lagged by {abs(numeric):.2f} percentage points on average."
    return "Tied in this replay window."


def _evidence_strength(summary: dict[str, Any]) -> str:
    samples = int(summary.get("total_candidates") or 0)
    avg20 = (summary.get("average_forward_return_by_horizon") or {}).get("20d")
    if samples < 30:
        return "Not enough evidence"
    if avg20 is None or avg20 <= 0:
        return "Weak evidence"
    if samples < 100:
        return "Promising"
    return "Strong historical evidence" if avg20 >= 3 else "Needs forward confirmation"


def _regular_evidence_strength(summary: dict[str, Any]) -> str:
    samples = int(summary.get("total_candidates") or 0)
    returns = summary.get("regular_investing_forward_returns") or {}
    avg252 = (returns.get("252d") or {}).get("average")
    random_excess = (summary.get("excess_return_vs_random_baseline") or {}).get("252d")
    if samples < 30:
        return "Not enough evidence"
    if avg252 is None:
        return "Weak evidence"
    if _to_float(avg252) <= 0:
        return "Weak evidence"
    if random_excess is not None and _to_float(random_excess) <= 0:
        return "Mixed evidence"
    return "Promising historical evidence" if samples < 100 else "Strong historical evidence"


def _point_in_time_note() -> str:
    return "Replay truncates OHLCV at each replay date and strips non-point-in-time fundamentals/news/social/short-interest/options. Results are historical evidence, not proof or guaranteed prediction accuracy."


def _portfolio_decision_fields() -> list[str]:
    return [
        "core_investing_decision",
        "reason_to_hold",
        "reason_to_add",
        "reason_to_trim",
        "reason_to_exit",
        "thesis_status",
        "concentration_warning",
        "valuation_or_overextension_warning",
        "broken_trend_warning",
        "review_priority",
        "next_review_trigger",
    ]


def _portfolio_replay_summary(rows: list[dict[str, Any]], horizons: Iterable[int]) -> dict[str, Any]:
    label_metrics = _bucket(rows, "core_investing_decision")
    add_rows = [row for row in rows if str(row.get("core_investing_decision")).startswith("Add")]
    hold_rows = [row for row in rows if row.get("core_investing_decision") in {"Hold", "Strong Hold"}]
    trim_rows = [row for row in rows if row.get("core_investing_decision") == "Trim"]
    exit_rows = [row for row in rows if row.get("core_investing_decision") == "Exit / Sell Candidate"]
    horizon = f"{max(horizons)}d"
    add_avg = _return_metrics(add_rows, horizon)["average"]
    hold_avg = _return_metrics(hold_rows, horizon)["average"]
    trim_avg = _return_metrics(trim_rows, horizon)["average"]
    exit_avg = _return_metrics(exit_rows, horizon)["average"]
    useful = "Not enough evidence"
    if len(add_rows) >= 5 and len(hold_rows) >= 5 and add_avg is not None and hold_avg is not None:
        useful = "Add labels outperformed Hold labels in this replay." if add_avg > hold_avg else "Add labels did not outperform Hold labels in this replay."
    return {
        "total_decisions": len(rows),
        "decision_performance": label_metrics,
        "add_label_forward_return": add_avg,
        "hold_label_forward_return": hold_avg,
        "trim_label_forward_return": trim_avg,
        "exit_label_forward_return": exit_avg,
        "avoided_drawdown_rate": _rate((_to_float(row.get("max_adverse_excursion")) <= -10) for row in [*trim_rows, *exit_rows]),
        "false_trim_rate": _rate((_to_float((row.get("returns") or {}).get(horizon)) > 0) for row in trim_rows),
        "bad_hold_rate": _rate((_to_float(row.get("max_adverse_excursion")) <= -15) for row in hold_rows),
        "portfolio_concentration_warnings": sum(1 for row in rows if row.get("concentration_warning") not in (None, "", "No concentration warning.")),
        "sample_size_warning": "Small sample: treat portfolio label evidence as directional only." if len(rows) < 100 else "",
        "label_usefulness": useful,
    }


def _turnover(rows: list[dict[str, Any]]) -> float | None:
    by_date: dict[str, set[str]] = {}
    for row in rows:
        by_date.setdefault(str(row.get("replay_date")), set()).add(str(row.get("ticker")))
    dates = sorted(by_date)
    if len(dates) < 2:
        return None
    changes = []
    for previous, current in zip(dates, dates[1:]):
        prev_set = by_date[previous]
        curr_set = by_date[current]
        changes.append(1 - (len(prev_set & curr_set) / max(len(curr_set), 1)))
    return _round(sum(changes) / len(changes)) if changes else None


def _repeated_picks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        ticker = str(row.get("ticker"))
        counts[ticker] = counts.get(ticker, 0) + 1
    return [{"ticker": ticker, "pick_count": count} for ticker, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:20] if count > 1]


def _case_markdown(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {payload['ticker']} case study",
            "",
            f"- First trigger: {payload.get('first_trigger_date')} ({payload.get('first_trigger_type')})",
            f"- Verdict: {payload.get('did_it_catch_move')} / {payload.get('was_it_early_or_late')}",
            f"- Max forward return after trigger: {payload.get('max_forward_return_after_trigger')}",
            f"- Max drawdown after trigger: {payload.get('max_drawdown_after_trigger')}",
            f"- Point-in-time limitation: {payload.get('point_in_time_limitations')}",
            "",
            str(payload.get("narrative", "")),
        ]
    )


def _case_markdown_narrative(ticker: str, first: dict[str, Any] | None, verdict: dict[str, str], first_eval: dict[str, Any]) -> str:
    if not first:
        return f"{ticker} did not produce a qualifying trigger inside the selected window under the current deterministic rules."
    return (
        f"{ticker} first triggered on {first['date']} at {first['price']}. "
        f"The scanner verdict is {verdict['did_it_catch_move']} and timing is {verdict['was_it_early_or_late']}. "
        f"Forward MFE was {first_eval.get('max_favorable_excursion', 'unavailable')}% and MAE was {first_eval.get('max_adverse_excursion', 'unavailable')}%."
    )


def _famous_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Famous outlier summary", "", f"Mode: {payload.get('mode')}", "", "| Ticker | Verdict | First trigger | Timing |", "| --- | --- | --- | --- |"]
    for study in payload.get("studies", []):
        lines.append(f"| {study.get('ticker')} | {study.get('did_it_catch_move')} | {study.get('first_trigger_date')} | {study.get('was_it_early_or_late')} |")
    lines.extend(["", f"Point-in-time limitation: {payload.get('point_in_time_limitations')}"])
    return "\n".join(lines)


def _replay_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    lines = [
        "# Historical replay summary",
        "",
        f"- Mode: {payload.get('mode')}",
        f"- Replay dates: {summary.get('total_replay_dates')}",
        f"- Candidates: {summary.get('total_candidates')}",
        f"- False-positive rate: {summary.get('false_positive_rate')}",
        f"- TP1/TP2 hit rate: {summary.get('TP1_hit_rate')} / {summary.get('TP2_hit_rate')}",
        f"- Invalidation hit rate: {summary.get('invalidation_hit_rate')}",
        f"- Point-in-time limitation: {payload.get('point_in_time_limitations')}",
        "",
        "## Forward Returns",
    ]
    for horizon, value in (summary.get("average_forward_return_by_horizon") or {}).items():
        lines.append(f"- {horizon}: avg {value}, median {(summary.get('median_forward_return_by_horizon') or {}).get(horizon)}, win rate {(summary.get('win_rate_by_horizon') or {}).get(horizon)}")
    return "\n".join(lines)


def _investing_replay_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    returns = summary.get("regular_investing_forward_returns") or {}
    lines = [
        "# Regular investing replay summary",
        "",
        f"- Replay dates: {summary.get('total_replay_dates')}",
        f"- Candidates: {summary.get('total_candidates')}",
        f"- False-positive rate: {summary.get('false_positive_rate')}",
        f"- Invalidation hit rate: {summary.get('hit_invalidation_rate')}",
        f"- Point-in-time limitation: {payload.get('point_in_time_limitations')}",
        f"- Fundamental limitation: {payload.get('fundamental_limitations')}",
        "",
        "## Forward Returns",
    ]
    for horizon, metric in returns.items():
        lines.append(f"- {horizon}: avg {metric.get('average')}, median {metric.get('median')}, win rate {metric.get('win_rate')}, sample {metric.get('sample_size')}")
    lines.extend(["", "## Baseline Comparisons"])
    lines.append(f"- Excess vs SPY/QQQ: {summary.get('excess_return_vs_baselines')}")
    lines.append(f"- Excess vs random: {summary.get('excess_return_vs_random_baseline')}")
    lines.append(f"- Excess vs equal-weight universe: {summary.get('excess_return_vs_equal_weight_universe')}")
    lines.extend(["", "## Styles And Labels"])
    lines.append(f"- Investing styles: {summary.get('best_worst_investing_styles')}")
    lines.append(f"- Action labels: {summary.get('best_worst_action_labels')}")
    return "\n".join(lines)


def _portfolio_replay_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    return "\n".join(
        [
            "# Portfolio replay report",
            "",
            f"- Decisions: {summary.get('total_decisions')}",
            f"- Add forward return: {summary.get('add_label_forward_return')}",
            f"- Hold forward return: {summary.get('hold_label_forward_return')}",
            f"- Trim forward return: {summary.get('trim_label_forward_return')}",
            f"- Exit forward return: {summary.get('exit_label_forward_return')}",
            f"- Avoided drawdown rate: {summary.get('avoided_drawdown_rate')}",
            f"- False trim rate: {summary.get('false_trim_rate')}",
            f"- Bad hold rate: {summary.get('bad_hold_rate')}",
            f"- Label usefulness: {summary.get('label_usefulness')}",
            f"- Sample size warning: {summary.get('sample_size_warning') or 'None'}",
            "",
            str(payload.get("safety", "")),
        ]
    )


def _investing_proof_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Core investing evidence report",
        "",
        f"- Evidence strength: {payload.get('evidence_strength')}",
        f"- Real-money reliance: {payload.get('real_money_reliance')}",
        f"- Note: {payload.get('language_note')}",
        "",
        "## Answers",
    ]
    for key, value in (payload.get("answers") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## What remains unproven"])
    lines.extend(f"- {item}" for item in payload.get("what_remains_unproven", []))
    lines.extend(["", f"Recommended use: {payload.get('recommended_use')}"])
    return "\n".join(lines)


def _proof_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# TradeBruv evidence report",
        "",
        f"- Evidence strength: {payload.get('evidence_strength')}",
        f"- Real-money reliance: {payload.get('real_money_reliance')}",
        f"- Note: {payload.get('language_note')}",
        "",
        "## Answers",
    ]
    for key, value in (payload.get("answers") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## What remains unproven"])
    lines.extend(f"- {item}" for item in payload.get("what_remains_unproven", []))
    lines.extend(["", "## Paper track next"])
    lines.extend(f"- {item}" for item in payload.get("paper_track_next", []))
    return "\n".join(lines)


def _nested_float(row: dict[str, Any], key: str, subkey: str) -> float | None:
    value = (row.get(key) or {}).get(subkey)
    return float(value) if value is not None else None


def _avg_metric(values: list[float]) -> dict[str, Any]:
    return {"sample_size": len(values), "average": _round(sum(values) / len(values)) if values else None, "median": _round(median(values)) if values else None}


def _rate(values: Iterable[Any]) -> float | None:
    values = list(values)
    if not values:
        return None
    return _round(sum(1 for value in values if value is True or value == "True") / len(values))


def _avg(values: Iterable[float]) -> float | None:
    values = [float(value) for value in values if value is not None]
    return _round(sum(values) / len(values)) if values else None


def _to_float(value: Any) -> float:
    if value in (None, "", "unavailable"):
        return 0.0
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except ValueError:
        return 0.0


def _round(value: float) -> float:
    return round(float(value or 0), 4)
