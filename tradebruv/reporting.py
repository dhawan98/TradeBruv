from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .models import ScannerResult


def write_json_report(results: list[ScannerResult], path: str | Path, mode: str = "standard") -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "scanner": "TradeBruv deterministic scanner",
        "mode": mode,
        "results": [result.to_dict() for result in results],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def write_csv_report(results: list[ScannerResult], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ticker",
        "company_name",
        "current_price",
        "strategy_label",
        "status_label",
        "winner_score",
        "outlier_score",
        "outlier_type",
        "outlier_risk",
        "confidence_label",
        "confidence_percent",
        "bullish_score",
        "bearish_pressure_score",
        "risk_score",
        "setup_quality_score",
        "holding_period",
        "entry_zone",
        "invalidation_level",
        "stop_loss_reference",
        "tp1",
        "tp2",
        "reward_risk",
        "outlier_reason",
        "theme_tags",
        "catalyst_tags",
        "chase_risk_warning",
        "squeeze_watch",
        "options_placeholders",
        "why_it_passed",
        "why_it_could_be_a_big_winner",
        "why_it_could_fail",
        "warnings",
        "signals_used",
        "provider_name",
        "source_notes",
        "data_availability_notes",
        "catalyst_score",
        "catalyst_quality",
        "catalyst_type",
        "catalyst_source_count",
        "catalyst_recency",
        "official_catalyst_found",
        "narrative_catalyst_found",
        "hype_catalyst_found",
        "social_attention_available",
        "social_attention_score",
        "social_attention_velocity",
        "news_attention_score",
        "news_sentiment_label",
        "source_urls",
        "source_timestamps",
        "source_provider_notes",
        "catalyst_data_available",
        "catalyst_data_missing_reason",
        "price_volume_confirms_catalyst",
        "attention_spike",
        "hype_risk",
        "pump_risk",
        "alternative_data_quality",
        "alternative_data_source_count",
        "insider_buy_count",
        "insider_sell_count",
        "net_insider_value",
        "CEO_CFO_buy_flag",
        "cluster_buying_flag",
        "heavy_insider_selling_flag",
        "politician_buy_count",
        "politician_sell_count",
        "net_politician_value",
        "recent_politician_activity",
        "disclosure_lag_warning",
        "alternative_data_confirmed_by_price_volume",
        "alternative_data_warnings",
        "alternative_data_items",
        "catalyst_items",
        "ai_explanation_available",
        "ai_explanation_provider",
        "ai_explanation",
        "velocity_score",
        "velocity_type",
        "velocity_risk",
        "trigger_reason",
        "chase_warning",
        "quick_trade_watch_label",
        "velocity_invalidation",
        "velocity_tp1",
        "velocity_tp2",
        "expected_horizon",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = result.to_dict()
            writer.writerow(
                {
                    "ticker": row["ticker"],
                    "company_name": row["company_name"],
                    "current_price": row["current_price"],
                    "strategy_label": row["strategy_label"],
                    "status_label": row["status_label"],
                    "winner_score": row["winner_score"],
                    "outlier_score": row["outlier_score"],
                    "outlier_type": row["outlier_type"],
                    "outlier_risk": row["outlier_risk"],
                    "confidence_label": row["confidence_label"],
                    "confidence_percent": row["confidence_percent"],
                    "bullish_score": row["bullish_score"],
                    "bearish_pressure_score": row["bearish_pressure_score"],
                    "risk_score": row["risk_score"],
                    "setup_quality_score": row["setup_quality_score"],
                    "holding_period": row["holding_period"],
                    "entry_zone": row["entry_zone"],
                    "invalidation_level": row["invalidation_level"],
                    "stop_loss_reference": row["stop_loss_reference"],
                    "tp1": row["tp1"],
                    "tp2": row["tp2"],
                    "reward_risk": row["reward_risk"],
                    "outlier_reason": row["outlier_reason"],
                    "theme_tags": " | ".join(row["theme_tags"]),
                    "catalyst_tags": " | ".join(row["catalyst_tags"]),
                    "chase_risk_warning": row["chase_risk_warning"],
                    "squeeze_watch": json.dumps(row["squeeze_watch"]),
                    "options_placeholders": json.dumps(row["options_placeholders"]),
                    "why_it_passed": " | ".join(row["why_it_passed"]),
                    "why_it_could_be_a_big_winner": " | ".join(row["why_it_could_be_a_big_winner"]),
                    "why_it_could_fail": " | ".join(row["why_it_could_fail"]),
                    "warnings": " | ".join(row["warnings"]),
                    "signals_used": " | ".join(row["signals_used"]),
                    "provider_name": row["provider_name"],
                    "source_notes": " | ".join(row["source_notes"]),
                    "data_availability_notes": " | ".join(row["data_availability_notes"]),
                    "catalyst_score": row["catalyst_score"],
                    "catalyst_quality": row["catalyst_quality"],
                    "catalyst_type": row["catalyst_type"],
                    "catalyst_source_count": row["catalyst_source_count"],
                    "catalyst_recency": row["catalyst_recency"],
                    "official_catalyst_found": row["official_catalyst_found"],
                    "narrative_catalyst_found": row["narrative_catalyst_found"],
                    "hype_catalyst_found": row["hype_catalyst_found"],
                    "social_attention_available": row["social_attention_available"],
                    "social_attention_score": row["social_attention_score"],
                    "social_attention_velocity": row["social_attention_velocity"],
                    "news_attention_score": row["news_attention_score"],
                    "news_sentiment_label": row["news_sentiment_label"],
                    "source_urls": " | ".join(row["source_urls"]),
                    "source_timestamps": " | ".join(row["source_timestamps"]),
                    "source_provider_notes": " | ".join(row["source_provider_notes"]),
                    "catalyst_data_available": row["catalyst_data_available"],
                    "catalyst_data_missing_reason": row["catalyst_data_missing_reason"],
                    "price_volume_confirms_catalyst": row["price_volume_confirms_catalyst"],
                    "attention_spike": row["attention_spike"],
                    "hype_risk": row["hype_risk"],
                    "pump_risk": row["pump_risk"],
                    "alternative_data_quality": row["alternative_data_quality"],
                    "alternative_data_source_count": row["alternative_data_source_count"],
                    "insider_buy_count": row["insider_buy_count"],
                    "insider_sell_count": row["insider_sell_count"],
                    "net_insider_value": row["net_insider_value"],
                    "CEO_CFO_buy_flag": row["CEO_CFO_buy_flag"],
                    "cluster_buying_flag": row["cluster_buying_flag"],
                    "heavy_insider_selling_flag": row["heavy_insider_selling_flag"],
                    "politician_buy_count": row["politician_buy_count"],
                    "politician_sell_count": row["politician_sell_count"],
                    "net_politician_value": row["net_politician_value"],
                    "recent_politician_activity": row["recent_politician_activity"],
                    "disclosure_lag_warning": row["disclosure_lag_warning"],
                    "alternative_data_confirmed_by_price_volume": row["alternative_data_confirmed_by_price_volume"],
                    "alternative_data_warnings": " | ".join(row["alternative_data_warnings"]),
                    "alternative_data_items": json.dumps(row["alternative_data_items"]),
                    "catalyst_items": json.dumps(row["catalyst_items"]),
                    "ai_explanation_available": row["ai_explanation_available"],
                    "ai_explanation_provider": row["ai_explanation_provider"],
                    "ai_explanation": json.dumps(row["ai_explanation"]),
                    "velocity_score": row["velocity_score"],
                    "velocity_type": row["velocity_type"],
                    "velocity_risk": row["velocity_risk"],
                    "trigger_reason": row["trigger_reason"],
                    "chase_warning": row["chase_warning"],
                    "quick_trade_watch_label": row["quick_trade_watch_label"],
                    "velocity_invalidation": row["velocity_invalidation"],
                    "velocity_tp1": row["velocity_tp1"],
                    "velocity_tp2": row["velocity_tp2"],
                    "expected_horizon": row["expected_horizon"],
                }
            )
    return output_path


def print_console_summary(results: list[ScannerResult], mode: str = "standard") -> None:
    if not results:
        print("No results to display.")
        return

    if mode == "velocity":
        header = (
            f"{'Ticker':<8}"
            f"{'Velocity Type':<28}"
            f"{'Velocity':>9}"
            f"{'Risk':>10}"
            f"{'Horizon':>10}"
            f"{'Status':>25}"
        )
        print(header)
        print("-" * len(header))
        for result in results:
            print(
                f"{result.ticker:<8}"
                f"{result.velocity_type[:27]:<28}"
                f"{result.velocity_score:>9}"
                f"{result.velocity_risk:>10}"
                f"{result.expected_horizon:>10}"
                f"{result.quick_trade_watch_label[:24]:>25}"
            )
            print(f"  Trigger: {result.trigger_reason}")
            if result.chase_warning and result.chase_warning != "unavailable":
                print(f"  Warning: {result.chase_warning}")
        return

    if mode == "outliers":
        header = (
            f"{'Ticker':<8}"
            f"{'Outlier Type':<26}"
            f"{'Outlier':>8}"
            f"{'Risk':>10}"
            f"{'Status':>25}"
        )
        print(header)
        print("-" * len(header))
        for result in results:
            print(
                f"{result.ticker:<8}"
                f"{result.outlier_type[:25]:<26}"
                f"{result.outlier_score:>8}"
                f"{result.outlier_risk:>10}"
                f"{result.status_label[:24]:>25}"
            )
            print(f"  Winner: {result.winner_score} | Entry: {result.trade_plan.entry_zone} | RR: {result.trade_plan.reward_risk_estimate or 'unavailable'}")
            if result.why_it_could_be_a_big_winner:
                print(f"  Outlier Why: {', '.join(result.why_it_could_be_a_big_winner[:2])}")
            if result.warnings:
                print(f"  Warnings: {', '.join(result.warnings[:2])}")
        return

    header = (
        f"{'Ticker':<8}"
        f"{'Strategy':<28}"
        f"{'Status':<25}"
        f"{'Winner':>8}"
        f"{'Outlier':>8}"
        f"{'Risk':>8}"
        f"{'Conf.':>10}"
    )
    print(header)
    print("-" * len(header))
    for result in results:
        print(
            f"{result.ticker:<8}"
            f"{result.strategy_label[:27]:<28}"
            f"{result.status_label[:24]:<25}"
            f"{result.winner_score:>8}"
            f"{result.outlier_score:>8}"
            f"{result.risk_score:>8}"
            f"{result.confidence_label:>10}"
        )
        print(f"  Entry: {result.trade_plan.entry_zone} | RR: {result.trade_plan.reward_risk_estimate or 'unavailable'}")
        if result.why_it_passed:
            print(f"  Why: {', '.join(result.why_it_passed[:2])}")
        if result.outlier_type not in {"Watch Only", "Avoid"}:
            print(f"  Outlier: {result.outlier_type} | {result.outlier_reason}")
        if result.warnings:
            print(f"  Warnings: {', '.join(result.warnings[:2])}")
