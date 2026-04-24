from __future__ import annotations

import unittest

from tests.helpers import sample_results


class StatusClassificationTests(unittest.TestCase):
    def test_status_buckets_match_setup_quality(self) -> None:
        results = sample_results()
        self.assertEqual(results["NVDA"].status_label, "Strong Research Candidate")
        self.assertEqual(results["MSFT"].status_label, "Trade Setup Forming")
        self.assertEqual(results["RIVN"].status_label, "Avoid")

    def test_unclean_charts_do_not_get_a_real_strategy_badge(self) -> None:
        results = sample_results()
        self.assertEqual(results["RIVN"].strategy_label, "No Clean Strategy")


if __name__ == "__main__":
    unittest.main()

