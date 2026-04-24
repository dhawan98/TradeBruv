from __future__ import annotations

from datetime import date
from pathlib import Path

from tradebruv.analysis import build_portfolio_recommendation, deep_research
from tradebruv.dashboard_data import (
    build_dashboard_data_source_status,
    build_dashboard_portfolio_summary,
    run_dashboard_ai_committee,
    run_dashboard_deep_research,
    run_dashboard_portfolio_analysis,
)
from tradebruv.data_sources import build_data_source_status, secret_values_present_in_text
from tradebruv.portfolio import (
    DEFAULT_PORTFOLIO_PATH,
    broker_execution_supported,
    concentration_risk,
    delete_position,
    import_portfolio_csv,
    load_portfolio,
    refresh_portfolio_prices,
    save_portfolio,
    upsert_position,
)
from tradebruv.providers import SampleMarketDataProvider


ANCHOR = date(2026, 4, 24)


def test_portfolio_csv_import_manual_update_delete_and_export(tmp_path: Path) -> None:
    source = tmp_path / "fidelity.csv"
    source.write_text(
        "Account Name,Symbol,Description,Quantity,Average Cost,Last Price,Sector\n"
        "Brokerage,NVDA,NVIDIA Corp,2,100,150,Technology\n",
        encoding="utf-8",
    )
    portfolio_path = tmp_path / "portfolio.csv"

    rows = import_portfolio_csv(source, portfolio_path)
    assert rows[0].ticker == "NVDA"
    assert rows[0].market_value == 300

    upsert_position(
        position={"account_name": "Brokerage", "ticker": "PLTR", "quantity": 10, "average_cost": 20, "current_price": 25},
        portfolio_path=portfolio_path,
    )
    loaded = load_portfolio(portfolio_path)
    assert {row.ticker for row in loaded} == {"NVDA", "PLTR"}
    assert delete_position(ticker="PLTR", portfolio_path=portfolio_path)
    assert [row.ticker for row in load_portfolio(portfolio_path)] == ["NVDA"]

    export_path = tmp_path / "export.csv"
    save_portfolio(load_portfolio(portfolio_path), export_path)
    assert "NVDA" in export_path.read_text(encoding="utf-8")


def test_price_refresh_summary_and_concentration_with_mocked_provider(tmp_path: Path) -> None:
    provider = SampleMarketDataProvider(end_date=ANCHOR)
    positions = [
        {"ticker": "NVDA", "quantity": 10, "average_cost": 100, "theme_tags": "AI"},
        {"ticker": "MSFT", "quantity": 1, "average_cost": 100, "theme_tags": "Cloud"},
    ]

    refreshed = refresh_portfolio_prices(positions=positions, provider=provider)
    summary = build_dashboard_portfolio_summary([row.to_dict() for row in refreshed])

    assert summary["total_market_value"] > 0
    assert summary["concentration_risk"]["risk_label"] == "High"
    assert concentration_risk(refreshed)["max_position_weight_pct"] > 50


def test_portfolio_recommendation_labels_and_deep_research_context() -> None:
    provider = SampleMarketDataProvider(end_date=ANCHOR)
    portfolio = [{"ticker": "NVDA", "quantity": 1, "average_cost": 900, "current_price": 1000, "thesis": "AI leader"}]
    analysis = run_dashboard_portfolio_analysis(rows=portfolio, provider=provider, analysis_date=ANCHOR)

    nvda = analysis["positions"][0]
    assert nvda["recommendation_label"] in {"Strong Hold", "Hold", "Add on Strength", "Add on Pullback / Better Entry"}
    assert nvda["reason_to_hold"]
    assert nvda["data_quality"] in {"Good", "Partial"}

    research = run_dashboard_deep_research(
        ticker="NVDA",
        provider=provider,
        portfolio_rows=portfolio,
        journal_rows=[{"ticker": "NVDA", "decision": "Research"}],
        analysis_date=ANCHOR,
    )
    assert research["decision_card"]["research_recommendation"] in {
        "Strong Buy Candidate",
        "Buy Candidate",
        "Hold / Watch",
        "Wait for Better Entry",
    }
    assert isinstance(research["portfolio_context"], dict)
    assert research["journal_history"]


def test_ai_committee_mock_and_missing_key_handling(monkeypatch) -> None:
    provider = SampleMarketDataProvider(end_date=ANCHOR)
    research = deep_research(ticker="NVDA", provider=provider, analysis_date=ANCHOR)
    scanner_row = research["scanner_row"]

    mock_output = run_dashboard_ai_committee(scanner_row=scanner_row, mode="Mock AI for testing")
    assert mock_output["available"] is True
    assert mock_output["evidence_used"]
    assert mock_output["final_recommendation_label"] != ""

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TRADEBRUV_LLM_API_KEY", raising=False)
    unavailable = run_dashboard_ai_committee(scanner_row=scanner_row, mode="OpenAI only")
    assert unavailable["available"] is False
    assert unavailable["final_recommendation_label"] == "Data Insufficient"


def test_provider_key_status_detection_and_secret_leak_guard(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-value")
    rows = build_data_source_status(env={"OPENAI_API_KEY": "sk-test-secret-value"})
    openai = next(row for row in rows if row["name"] == "OpenAI")
    polygon = next(row for row in rows if row["name"] == "Polygon.io")
    assert openai["configured"]
    assert not polygon["configured"]
    assert "POLYGON_API_KEY" in polygon["missing_env_vars"]

    dashboard_payload = build_dashboard_data_source_status()
    assert "rows" in dashboard_payload and "summary" in dashboard_payload
    assert secret_values_present_in_text("hello sk-test-secret-value", env={"OPENAI_API_KEY": "sk-test-secret-value"}) == ["OPENAI_API_KEY"]


def test_no_broker_execution_path() -> None:
    assert broker_execution_supported() is False
