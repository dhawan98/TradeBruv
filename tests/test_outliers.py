from __future__ import annotations

import unittest
from dataclasses import replace

from tradebruv.models import OptionsSnapshot
from tradebruv.providers import SampleMarketDataProvider
from tradebruv.scanner import DeterministicScanner

from tests.helpers import ANCHOR, StaticProvider, sample_outlier_results, squeeze_security, with_options_override


class OutlierEngineTests(unittest.TestCase):
    def test_outlier_scores_rank_leaders_above_weak_names(self) -> None:
        results = sample_outlier_results()
        self.assertGreater(results["NVDA"].outlier_score, results["ENPH"].outlier_score)
        self.assertGreater(results["LLY"].outlier_score, results["RIVN"].outlier_score)

    def test_long_term_monster_detection_surfaces_for_nvda(self) -> None:
        results = sample_outlier_results()
        self.assertEqual(results["NVDA"].outlier_type, "Long-Term Monster")
        self.assertGreaterEqual(results["NVDA"].outlier_score, 50)

    def test_short_squeeze_watch_classification_with_mocked_data(self) -> None:
        sample_provider = SampleMarketDataProvider(end_date=ANCHOR)
        provider = StaticProvider(
            {
                "MOCK": squeeze_security(),
                "SPY": sample_provider.get_security_data("SPY"),
                "QQQ": sample_provider.get_security_data("QQQ"),
                "XLY": sample_provider.get_security_data("XLY"),
            }
        )
        scanner = DeterministicScanner(provider=provider, analysis_date=ANCHOR)
        result = scanner.scan(["MOCK"], mode="outliers")[0]
        self.assertEqual(result.outlier_type, "Short Squeeze Watch")
        self.assertIn(result.outlier_risk, {"High", "Extreme"})
        self.assertGreaterEqual(result.outlier_score, 60)

    def test_social_news_unavailable_is_reported_without_hallucination(self) -> None:
        sample_provider = SampleMarketDataProvider(end_date=ANCHOR)
        base = sample_provider.get_security_data("NVDA")
        stripped = replace(base, social_attention=None)
        provider = StaticProvider(
            {
                "NVDA": stripped,
                "SPY": sample_provider.get_security_data("SPY"),
                "QQQ": sample_provider.get_security_data("QQQ"),
                "XLK": sample_provider.get_security_data("XLK"),
            }
        )
        scanner = DeterministicScanner(provider=provider, analysis_date=ANCHOR)
        result = scanner.scan(["NVDA"], mode="outliers")[0]
        self.assertIn("Social/news attention data unavailable.", result.data_availability_notes)
        self.assertEqual(result.data_used["social_attention_available"], False)

    def test_options_placeholder_does_not_change_stock_scoring(self) -> None:
        sample_provider = SampleMarketDataProvider(end_date=ANCHOR)
        base = sample_provider.get_security_data("NVDA")
        without_unusual = with_options_override(base, unusual_options_activity=False)
        with_unusual = with_options_override(base, unusual_options_activity=True)

        provider_a = StaticProvider(
            {
                "NVDA": without_unusual,
                "SPY": sample_provider.get_security_data("SPY"),
                "QQQ": sample_provider.get_security_data("QQQ"),
                "XLK": sample_provider.get_security_data("XLK"),
            }
        )
        provider_b = StaticProvider(
            {
                "NVDA": with_unusual,
                "SPY": sample_provider.get_security_data("SPY"),
                "QQQ": sample_provider.get_security_data("QQQ"),
                "XLK": sample_provider.get_security_data("XLK"),
            }
        )

        result_a = DeterministicScanner(provider=provider_a, analysis_date=ANCHOR).scan(["NVDA"], mode="outliers")[0]
        result_b = DeterministicScanner(provider=provider_b, analysis_date=ANCHOR).scan(["NVDA"], mode="outliers")[0]
        self.assertEqual(result_a.winner_score, result_b.winner_score)
        self.assertEqual(result_a.outlier_score, result_b.outlier_score)
        self.assertNotEqual(
            result_a.options_placeholders["unusual_options_activity"],
            result_b.options_placeholders["unusual_options_activity"],
        )


if __name__ == "__main__":
    unittest.main()
