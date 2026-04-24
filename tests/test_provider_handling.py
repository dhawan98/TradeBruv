from __future__ import annotations

import unittest

from tradebruv.cli import build_provider
from tradebruv.providers import ProviderConfigurationError
from tradebruv.scanner import DeterministicScanner

from tests.helpers import ANCHOR


class AlwaysFailProvider:
    def get_security_data(self, ticker: str):
        raise RuntimeError(f"boom for {ticker}")


class Namespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class ProviderHandlingTests(unittest.TestCase):
    def test_provider_failure_returns_non_hallucinated_result(self) -> None:
        scanner = DeterministicScanner(provider=AlwaysFailProvider(), analysis_date=ANCHOR)
        result = scanner.scan(["FAIL"], mode="outliers")[0]
        self.assertEqual(result.status_label, "Avoid")
        self.assertEqual(result.winner_score, 0)
        self.assertEqual(result.outlier_score, 0)
        self.assertIn("Provider failure:", result.data_availability_notes[0])
        self.assertIn("Data fetch failed", result.warnings[0])

    def test_real_provider_requires_dependency_or_initializes_cleanly(self) -> None:
        args = Namespace(provider="real", data_dir=None, history_period="3y")
        try:
            provider = build_provider(args=args, analysis_date=ANCHOR)
        except ProviderConfigurationError as exc:
            self.assertIn("yfinance", str(exc))
        else:
            self.assertIsNotNone(provider)


if __name__ == "__main__":
    unittest.main()
