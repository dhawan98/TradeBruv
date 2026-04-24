from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tradebruv.dashboard_data import (
    build_daily_summary,
    build_market_regime,
    classify_avoid_reasons,
    extract_options_fields,
    filter_results,
    is_high_risk_outlier,
    load_dashboard_report,
    sort_results,
)

from tests.helpers import sample_outlier_results


class MissingProvider:
    def get_security_data(self, ticker: str):
        raise RuntimeError(f"{ticker} missing")


class DashboardDataTests(unittest.TestCase):
    def _rows(self):
        return [result.to_dict() for result in sample_outlier_results().values()]

    def test_filtering_and_sorting_keep_outlier_leaders_visible(self) -> None:
        rows = self._rows()
        filtered = filter_results(
            rows,
            {
                "min_outlier_score": 40,
                "exclude_avoid": True,
                "status": [],
                "strategy": [],
                "outlier_type": [],
                "risk_level": [],
            },
        )
        tickers = [row["ticker"] for row in sort_results(filtered, sort_by="outlier_score")]
        self.assertEqual(tickers[:2], ["NVDA", "LLY"])
        self.assertNotIn("ENPH", tickers)
        self.assertNotIn("RIVN", tickers)

    def test_daily_summary_aggregates_candidates_warnings_and_special_buckets(self) -> None:
        summary = build_daily_summary(self._rows())
        self.assertEqual(summary["top_outlier_candidates"][0]["ticker"], "NVDA")
        self.assertTrue(any(row["ticker"] == "ENPH" for row in summary["top_avoid_names"]))
        self.assertTrue(summary["common_theme_tags"])
        self.assertIsNotNone(summary["highest_risk_candidate"])
        self.assertIsNone(summary["best_squeeze_watch_candidate"])

    def test_report_loader_normalizes_missing_fields(self) -> None:
        payload = {
            "generated_at": "2026-04-24T00:00:00Z",
            "mode": "outliers",
            "results": [{"ticker": "abc", "winner_score": 10}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scan_report.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            report = load_dashboard_report(path)
        self.assertEqual(report.mode, "outliers")
        self.assertEqual(report.results[0]["ticker"], "ABC")
        self.assertEqual(report.results[0]["status_label"], "Watch Only")
        self.assertEqual(report.results[0]["warnings"], [])

    def test_missing_provider_data_returns_report_only_regime_warning(self) -> None:
        regime = build_market_regime(provider=MissingProvider(), results=[])
        self.assertEqual(regime["regime"], "Mixed")
        self.assertTrue(any("SPY benchmark unavailable" in warning for warning in regime["risk_warnings"]))

    def test_avoid_and_options_helpers_are_conservative(self) -> None:
        rows = {row["ticker"]: row for row in self._rows()}
        enph_reasons = classify_avoid_reasons(rows["ENPH"])
        self.assertIn("Earnings too close", enph_reasons)
        self.assertIn("Hype/pump risk", enph_reasons)
        self.assertFalse(is_high_risk_outlier(rows["NVDA"]))
        self.assertEqual(extract_options_fields(rows["NVDA"])["options_interest_available"], True)


if __name__ == "__main__":
    unittest.main()
