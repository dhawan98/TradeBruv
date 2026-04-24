from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tradebruv.dashboard_data import (
    build_process_quality_summary,
    build_review_summary,
    build_strategy_performance_highlights,
    filter_review_results,
)
from tradebruv.journal import (
    add_journal_entry,
    export_journal,
    journal_stats,
    read_journal,
    update_journal_entry,
)
from tradebruv.models import PriceBar, SecurityData
from tradebruv.performance import aggregate_strategy_performance
from tradebruv.review import (
    LoadedScanReport,
    calculate_forward_metrics,
    load_reports_from_dir,
    load_scan_report,
    review_report,
    review_reports,
)


class StaticProvider:
    def __init__(self, bars_by_ticker):
        self.bars_by_ticker = bars_by_ticker

    def get_security_data(self, ticker: str) -> SecurityData:
        bars = self.bars_by_ticker[ticker.upper()]
        return SecurityData(
            ticker=ticker.upper(),
            company_name=ticker.upper(),
            sector=None,
            bars=bars,
            provider_name="test",
        )


class MissingProvider:
    def get_security_data(self, ticker: str) -> SecurityData:
        raise RuntimeError(f"{ticker} missing")


def bars() -> list[PriceBar]:
    return [
        PriceBar(date(2026, 1, 1), 99, 101, 98, 100, 1000),
        PriceBar(date(2026, 1, 2), 100, 106, 99, 104, 1100),
        PriceBar(date(2026, 1, 5), 104, 113, 103, 111, 1200),
        PriceBar(date(2026, 1, 6), 111, 112, 95, 98, 1300),
        PriceBar(date(2026, 1, 7), 98, 109, 97, 108, 1400),
    ]


def report_row(ticker: str = "NVDA") -> dict:
    return {
        "ticker": ticker,
        "company_name": "Nvidia",
        "current_price": 100,
        "strategy_label": "Breakout",
        "outlier_type": "Long-Term Monster",
        "status_label": "Active Setup",
        "winner_score": 85,
        "outlier_score": 92,
        "setup_quality_score": 84,
        "risk_score": 30,
        "outlier_risk": "Low",
        "confidence_label": "High",
        "entry_zone": "99 - 101",
        "invalidation_level": 96,
        "stop_loss_reference": 95,
        "tp1": 105,
        "tp2": 112,
        "reward_risk": 2,
        "catalyst_quality": "Price Confirmed",
        "catalyst_type": "AI/data center narrative",
        "theme_tags": ["AI", "Semiconductors"],
        "warnings": ["Overextended chase risk"],
        "provider_name": "sample",
    }


class Pass4FeedbackTests(unittest.TestCase):
    def test_forward_metrics_return_mfe_mae_targets_and_invalidation(self) -> None:
        metrics = calculate_forward_metrics(
            bars=bars(),
            signal_date=date(2026, 1, 1),
            signal_close=100,
            tp1=105,
            tp2=112,
            invalidation_level=96,
            stop_reference=95,
            horizon_days=3,
        )
        self.assertTrue(metrics["available"])
        self.assertEqual(metrics["forward_return_pct"], -2.0)
        self.assertEqual(metrics["max_favorable_excursion_pct"], 13.0)
        self.assertEqual(metrics["max_adverse_excursion_pct"], -5.0)
        self.assertTrue(metrics["hit_tp1"])
        self.assertTrue(metrics["hit_tp2"])
        self.assertTrue(metrics["hit_stop_or_invalidation"])
        self.assertEqual(metrics["days_to_tp1"], 1)
        self.assertEqual(metrics["days_to_tp2"], 2)
        self.assertEqual(metrics["days_to_invalidation"], 3)
        self.assertEqual(metrics["best_close_after_signal"], 111)
        self.assertEqual(metrics["worst_close_after_signal"], 98)
        self.assertEqual(metrics["final_close_at_horizon"], 98)

    def test_missing_historical_data_marks_unavailable_without_crashing(self) -> None:
        report = LoadedScanReport(Path("scan_report.json"), "2026-01-01T00:00:00Z", "outliers", "sample", [report_row()])
        payload = review_report(report=report, provider=MissingProvider(), horizons=[5])
        self.assertFalse(payload["results"][0]["available"])
        self.assertIn("Historical data unavailable", payload["results"][0]["unavailable_reason"])

    def test_batch_review_loads_reports_and_reviews_each_saved_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index, ticker in enumerate(["NVDA", "MSFT"]):
                path = root / f"scan_{index}.json"
                path.write_text(
                    json.dumps(
                        {
                            "generated_at": "2026-01-01T00:00:00Z",
                            "mode": "outliers",
                            "results": [report_row(ticker)],
                        }
                    ),
                    encoding="utf-8",
                )
            reports = load_reports_from_dir(root)
            payload = review_reports(
                reports=reports,
                provider=StaticProvider({"NVDA": bars(), "MSFT": bars()}),
                horizons=[1, 2],
            )
        self.assertEqual(len(reports), 2)
        self.assertEqual(len(payload["results"]), 4)
        self.assertTrue(all(row["available"] for row in payload["results"]))

    def test_strategy_aggregation_calculates_expectancy_and_small_sample_warning(self) -> None:
        rows = review_reports(
            reports=[
                LoadedScanReport(Path("one.json"), "2026-01-01T00:00:00Z", "outliers", "sample", [report_row("NVDA")])
            ],
            provider=StaticProvider({"NVDA": bars()}),
            horizons=[2],
        )["results"]
        performance = aggregate_strategy_performance(rows)
        strategy = next(row for row in performance if row["dimension"] == "strategy_label" and row["bucket"] == "Breakout")
        self.assertEqual(strategy["sample_size"], 1)
        self.assertTrue(strategy["small_sample_warning"])
        self.assertEqual(strategy["average_forward_return"], 11.0)
        self.assertEqual(strategy["hit_tp1_rate"], 100.0)
        self.assertEqual(strategy["hit_tp2_rate"], 100.0)
        self.assertEqual(strategy["invalidation_rate"], 0.0)

    def test_journal_add_update_export_and_stats(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "scan_report.json"
            journal_path = root / "journal.csv"
            export_path = root / "journal_export.csv"
            report_path.write_text(
                json.dumps({"generated_at": "2026-01-01T00:00:00Z", "results": [report_row()]}),
                encoding="utf-8",
            )
            entry = add_journal_entry(
                journal_path=journal_path,
                from_report=report_path,
                ticker="NVDA",
                updates={"decision": "Paper Trade"},
            )
            updated = update_journal_entry(
                entry_id=entry["id"],
                journal_path=journal_path,
                updates={
                    "actual_entry_price": "100",
                    "actual_exit_price": "108",
                    "result_pct": "8",
                    "followed_rules": "true",
                    "mistake_category": "Good process / bad outcome",
                },
            )
            exported = export_journal(output_path=export_path, journal_path=journal_path)
            rows = read_journal(journal_path)
            stats = journal_stats(rows)
            self.assertEqual(updated["ticker"], "NVDA")
            self.assertTrue(exported.exists())
            self.assertEqual(stats["total_entries"], 1)
            self.assertEqual(stats["closed_entries"], 1)
            self.assertEqual(stats["rules_followed_pct"], 100.0)
            self.assertEqual(stats["average_result_pct"], 8.0)

    def test_dashboard_transformations_for_review_performance_and_process(self) -> None:
        rows = review_reports(
            reports=[
                LoadedScanReport(Path("one.json"), "2026-01-01T00:00:00Z", "outliers", "sample", [report_row("NVDA")])
            ],
            provider=StaticProvider({"NVDA": bars()}),
            horizons=[2],
        )["results"]
        summary = build_review_summary(rows)
        filtered = filter_review_results(rows, {"strategy": ["Breakout"], "only_available": True})
        highlights = build_strategy_performance_highlights(aggregate_strategy_performance(rows))
        process = build_process_quality_summary(
            [{"decision": "Took Trade", "result_pct": "5", "followed_rules": "false", "mistake_category": "Ignored invalidation"}]
        )
        self.assertEqual(summary["available_rows"], 1)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(highlights["best_strategy_by_expectancy"]["bucket"], "Breakout")
        self.assertEqual(process["stop_invalidation_violations"], 1)


if __name__ == "__main__":
    unittest.main()
