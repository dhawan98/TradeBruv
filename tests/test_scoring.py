from __future__ import annotations

import unittest

from tests.helpers import sample_results


class ScoringTests(unittest.TestCase):
    def test_leaders_score_above_weak_setups(self) -> None:
        results = sample_results()
        self.assertGreater(results["NVDA"].winner_score, results["ENPH"].winner_score)
        self.assertGreater(results["LLY"].winner_score, results["RIVN"].winner_score)

    def test_component_scores_reward_supportive_data(self) -> None:
        results = sample_results()
        self.assertGreaterEqual(results["NVDA"].component_scores["fundamental_support"], 10)
        self.assertGreaterEqual(results["NVDA"].component_scores["relative_strength"], 10)
        self.assertEqual(results["RIVN"].component_scores["fundamental_support"], 0)


if __name__ == "__main__":
    unittest.main()

