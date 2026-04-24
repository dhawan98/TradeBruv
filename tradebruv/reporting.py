from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .models import ScannerResult


def write_json_report(results: list[ScannerResult], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "scanner": "TradeBruv deterministic scanner",
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
        "bullish_score",
        "bearish_pressure_score",
        "risk_score",
        "setup_quality_score",
        "confidence_label",
        "confidence_percent",
        "holding_period",
        "entry_zone",
        "invalidation_level",
        "stop_loss_reference",
        "tp1",
        "tp2",
        "reward_risk",
        "why_it_passed",
        "why_it_could_fail",
        "warnings",
        "signals_used",
        "data_availability_notes",
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
                    "bullish_score": row["bullish_score"],
                    "bearish_pressure_score": row["bearish_pressure_score"],
                    "risk_score": row["risk_score"],
                    "setup_quality_score": row["setup_quality_score"],
                    "confidence_label": row["confidence_label"],
                    "confidence_percent": row["confidence_percent"],
                    "holding_period": row["holding_period"],
                    "entry_zone": row["entry_zone"],
                    "invalidation_level": row["invalidation_level"],
                    "stop_loss_reference": row["stop_loss_reference"],
                    "tp1": row["tp1"],
                    "tp2": row["tp2"],
                    "reward_risk": row["reward_risk"],
                    "why_it_passed": " | ".join(row["why_it_passed"]),
                    "why_it_could_fail": " | ".join(row["why_it_could_fail"]),
                    "warnings": " | ".join(row["warnings"]),
                    "signals_used": " | ".join(row["signals_used"]),
                    "data_availability_notes": " | ".join(row["data_availability_notes"]),
                }
            )
    return output_path


def print_console_summary(results: list[ScannerResult]) -> None:
    if not results:
        print("No results to display.")
        return

    header = (
        f"{'Ticker':<8}"
        f"{'Strategy':<28}"
        f"{'Status':<25}"
        f"{'Winner':>8}"
        f"{'Risk':>8}"
        f"{'Setup':>8}"
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
            f"{result.risk_score:>8}"
            f"{result.setup_quality_score:>8}"
            f"{result.confidence_label:>10}"
        )
        print(f"  Entry: {result.trade_plan.entry_zone} | RR: {result.trade_plan.reward_risk_estimate or 'unavailable'}")
        if result.why_it_passed:
            print(f"  Why: {', '.join(result.why_it_passed[:2])}")
        if result.warnings:
            print(f"  Warnings: {', '.join(result.warnings[:2])}")

