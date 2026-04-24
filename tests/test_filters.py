from __future__ import annotations

import unittest

from tests.helpers import sample_results


class RejectionFilterTests(unittest.TestCase):
    def test_risky_names_are_flagged_as_avoid(self) -> None:
        results = sample_results()
        self.assertEqual(results["RIVN"].status_label, "Avoid")
        self.assertEqual(results["ENPH"].status_label, "Avoid")

    def test_dilution_and_hype_warnings_surface(self) -> None:
        results = sample_results()
        self.assertIn("Recent dilution/offering risk is present.", results["RIVN"].warnings)
        self.assertIn("Headline attention looks hype-driven.", results["ENPH"].warnings)


if __name__ == "__main__":
    unittest.main()

