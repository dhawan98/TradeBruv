from __future__ import annotations

import csv
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tradebruv.ai_explanations import MockExplanationProvider, UnavailableExplanationProvider, apply_ai_explanations
from tradebruv.catalysts import CatalystOverlayProvider, load_catalyst_items, load_catalyst_repository
from tradebruv.providers import SampleMarketDataProvider
from tradebruv.reporting import write_csv_report, write_json_report
from tradebruv.scanner import DeterministicScanner

from tests.helpers import ANCHOR, StaticProvider, make_trending_bars


class CatalystIngestionTests(unittest.TestCase):
    def test_missing_catalyst_file_does_not_crash(self) -> None:
        repo = load_catalyst_repository(Path("missing-catalysts.csv"))
        self.assertEqual(repo.items_by_ticker, {})
        self.assertIn("Catalyst file missing", repo.warnings[0])

    def test_csv_parsing_skips_bad_rows_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalysts.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "ticker",
                        "source_type",
                        "source_name",
                        "source_url",
                        "timestamp",
                        "headline",
                        "summary",
                        "sentiment",
                        "catalyst_type",
                        "attention_count",
                        "attention_velocity",
                        "official_source",
                        "confidence",
                        "notes",
                    ],
                )
                writer.writeheader()
                row = {
                    "ticker": "MU",
                    "source_type": "news",
                    "source_name": "manual",
                    "source_url": "https://example.test/mu",
                    "timestamp": "2026-04-24T13:00:00Z",
                    "headline": "Memory cycle catalyst",
                    "summary": "Manual verified row",
                    "sentiment": "positive",
                    "catalyst_type": "Semiconductor narrative",
                    "attention_count": "125",
                    "attention_velocity": "0.8",
                    "official_source": "false",
                    "confidence": "0.7",
                    "notes": "test",
                }
                writer.writerow(row)
                writer.writerow(row)
                writer.writerow({"ticker": "", "source_type": "news"})
            result = load_catalyst_items(path)
        self.assertEqual(len(result.items_by_ticker["MU"]), 1)
        self.assertTrue(any("duplicate" in warning for warning in result.warnings))
        self.assertTrue(any("ticker is required" in warning for warning in result.warnings))


class CatalystScannerTests(unittest.TestCase):
    def test_official_catalyst_classification(self) -> None:
        result = self._scan_with_rows(
            [
                {
                    "ticker": "NVDA",
                    "source_type": "earnings",
                    "source_name": "company",
                    "timestamp": "2026-04-23T12:00:00Z",
                    "headline": "Guidance raised",
                    "sentiment": "positive",
                    "catalyst_type": "Guidance raise",
                    "official_source": "true",
                }
            ],
            "NVDA",
        )
        row = result.to_dict()
        self.assertTrue(row["official_catalyst_found"])
        self.assertEqual(row["catalyst_type"], "Guidance raise")
        self.assertGreater(row["catalyst_score"], 0)

    def test_narrative_catalyst_classification(self) -> None:
        result = self._scan_with_rows(
            [
                {
                    "ticker": "PLTR",
                    "source_type": "news",
                    "source_name": "manual",
                    "timestamp": "2026-04-23T12:00:00Z",
                    "headline": "AI defense narrative",
                    "sentiment": "positive",
                    "catalyst_type": "Defense/geopolitical narrative",
                }
            ],
            "PLTR",
        )
        row = result.to_dict()
        self.assertTrue(row["narrative_catalyst_found"])
        self.assertEqual(row["catalyst_type"], "Defense/geopolitical narrative")

    def test_social_only_hype_is_flagged(self) -> None:
        result = self._scan_with_rows(
            [
                {
                    "ticker": "RIVN",
                    "source_type": "reddit",
                    "source_name": "manual",
                    "timestamp": "2026-04-24T12:00:00Z",
                    "headline": "Attention spike",
                    "catalyst_type": "Social hype only",
                    "attention_count": "2000",
                    "attention_velocity": "1.8",
                    "official_source": "false",
                }
            ],
            "RIVN",
        )
        row = result.to_dict()
        self.assertTrue(row["hype_catalyst_found"])
        self.assertIn("Social-only hype risk is present.", row["warnings"])

    def test_attention_without_price_confirmation_stays_watch_only(self) -> None:
        sample = SampleMarketDataProvider(end_date=ANCHOR)
        security = replace(
            sample.get_security_data("NVDA"),
            ticker="SOCL",
            catalyst=None,
            social_attention=None,
            catalyst_tags=[],
            bars=make_trending_bars(drift=0.002, boost_every=None),
        )
        provider = StaticProvider(
            {
                "SOCL": security,
                "SPY": sample.get_security_data("SPY"),
                "QQQ": sample.get_security_data("QQQ"),
                "XLK": sample.get_security_data("XLK"),
            }
        )
        repo = self._repo_from_rows(
            [
                {
                    "ticker": "SOCL",
                    "source_type": "reddit",
                    "source_name": "manual",
                    "timestamp": "2026-04-24T12:00:00Z",
                    "headline": "Social chatter only",
                    "catalyst_type": "Social hype only",
                    "attention_count": "900",
                    "attention_velocity": "0.6",
                    "official_source": "false",
                }
            ]
        )
        result = DeterministicScanner(CatalystOverlayProvider(provider, repo), analysis_date=ANCHOR).scan(["SOCL"])[0]
        self.assertEqual(result.status_label, "Watch Only")
        self.assertIn("Social/news attention is not confirmed by price and volume.", result.warnings)

    def test_mock_ai_and_unavailable_ai_do_not_change_scores(self) -> None:
        result = self._scan_with_rows([], "NVDA")
        original = (result.winner_score, result.outlier_score, result.status_label)
        apply_ai_explanations([result], UnavailableExplanationProvider("disabled"))
        self.assertEqual((result.winner_score, result.outlier_score, result.status_label), original)
        self.assertFalse(result.to_dict()["ai_explanation_available"])
        apply_ai_explanations([result], MockExplanationProvider())
        row = result.to_dict()
        self.assertTrue(row["ai_explanation_available"])
        self.assertIn("NVDA", row["ai_explanation"]["summary"])
        self.assertNotIn("guaranteed", row["ai_explanation"]["summary"].lower())

    def test_reports_include_catalyst_and_ai_fields(self) -> None:
        result = self._scan_with_rows([], "NVDA")
        apply_ai_explanations([result], MockExplanationProvider())
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = write_json_report([result], Path(temp_dir) / "scan_report.json")
            csv_path = write_csv_report([result], Path(temp_dir) / "scan_report.csv")
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            csv_header = csv_path.read_text(encoding="utf-8").splitlines()[0]
        row = payload["results"][0]
        self.assertIn("catalyst_score", row)
        self.assertIn("catalyst_items", row)
        self.assertIn("ai_explanation", row)
        self.assertIn("catalyst_score", csv_header)
        self.assertIn("ai_explanation", csv_header)

    def _scan_with_rows(self, rows: list[dict[str, str]], ticker: str):
        sample = SampleMarketDataProvider(end_date=ANCHOR)
        provider = CatalystOverlayProvider(sample, self._repo_from_rows(rows))
        return DeterministicScanner(provider=provider, analysis_date=ANCHOR).scan([ticker], mode="outliers")[0]

    def _repo_from_rows(self, rows: list[dict[str, str]]):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalysts.csv"
            fieldnames = [
                "ticker",
                "source_type",
                "source_name",
                "source_url",
                "timestamp",
                "headline",
                "summary",
                "sentiment",
                "catalyst_type",
                "attention_count",
                "attention_velocity",
                "official_source",
                "confidence",
                "notes",
            ]
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
            return load_catalyst_repository(path)


if __name__ == "__main__":
    unittest.main()
