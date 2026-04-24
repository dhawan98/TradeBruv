from __future__ import annotations

import unittest

from tests.helpers import sample_results


class TradePlanTests(unittest.TestCase):
    def test_strong_candidates_get_a_complete_trade_plan(self) -> None:
        nvda = sample_results()["NVDA"].trade_plan
        self.assertIsNotNone(nvda.entry_low)
        self.assertIsNotNone(nvda.entry_high)
        self.assertIsNotNone(nvda.invalidation_level)
        self.assertIsNotNone(nvda.tp1)
        self.assertIsNotNone(nvda.tp2)
        self.assertGreaterEqual(nvda.reward_risk_estimate or 0, 2.0)
        self.assertLess(nvda.invalidation_level or 0, nvda.current_price)
        self.assertGreater(nvda.tp2 or 0, nvda.tp1 or 0)

    def test_unclean_setups_are_marked_non_actionable(self) -> None:
        rivn = sample_results()["RIVN"]
        self.assertEqual(rivn.holding_period, "Wait / not actionable")
        self.assertLess((rivn.trade_plan.reward_risk_estimate or 0), 1.5)


if __name__ == "__main__":
    unittest.main()

