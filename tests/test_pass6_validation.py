from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from tests.helpers import ANCHOR, make_trending_bars
from tradebruv.models import SecurityData
from tradebruv.providers import SampleMarketDataProvider
from tradebruv.scanner import DeterministicScanner
from tradebruv.validation_lab import (
    add_prediction,
    create_prediction_record,
    famous_outlier_case_study,
    load_predictions,
    save_predictions,
    update_prediction_outcomes,
    validation_metrics,
)


class OneTickerProvider:
    def __init__(self, security: SecurityData) -> None:
        self.security = security

    def get_security_data(self, ticker: str) -> SecurityData:
        if ticker.upper() != self.security.ticker:
            raise KeyError(ticker)
        return self.security


def test_prediction_record_creation_update_and_metrics(tmp_path: Path) -> None:
    bars = make_trending_bars(start_price=100, count=180, drift=0.004)
    security = SecurityData(
        ticker="TEST",
        company_name="Test Inc",
        sector="Technology",
        bars=bars,
        provider_name="test",
    )
    provider = OneTickerProvider(security)
    row = DeterministicScanner(provider, analysis_date=bars[80].date).scan(["TEST"], mode="outliers")[0].to_dict()
    record = create_prediction_record(
        scanner_row={**row, "current_price": bars[80].close},
        rule_based_recommendation="Hold",
        ai_committee_recommendation="Hold / Watch",
        final_combined_recommendation="Hold",
        created_at=bars[80].date.isoformat(),
    )
    path = tmp_path / "predictions.csv"
    add_prediction(record, path)
    assert load_predictions(path)[0]["ticker"] == "TEST"

    updated = update_prediction_outcomes(records=load_predictions(path), provider=provider, as_of_date=bars[-1].date)
    save_predictions(updated, path)
    assert load_predictions(path)[0]["outcome_label"] in {"Worked", "Failed", "Mixed", "Still Open"}

    metrics = validation_metrics(load_predictions(path))
    assert metrics["by_recommendation_label"][0]["sample_size"] == 1
    assert metrics["sample_size_warning"]


def test_famous_outlier_case_study_uses_point_in_time_data() -> None:
    provider = SampleMarketDataProvider(end_date=ANCHOR)
    payload = famous_outlier_case_study(
        ticker="NVDA",
        provider=provider,
        signal_date=ANCHOR - timedelta(days=80),
        end_date=ANCHOR,
    )
    assert payload["available"] is True
    assert "point-in-time" in payload["point_in_time_note"].lower()
    assert payload["outcome"]["outcome_label"] in {"Worked", "Failed", "Mixed", "Still Open", "Data Unavailable"}
