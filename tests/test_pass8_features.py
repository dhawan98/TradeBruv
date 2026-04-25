from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tradebruv.ai_guardrails import validate_ai_output
from tradebruv.alternative_data import build_alternative_data_signal, load_alternative_data_repository
from tradebruv.doctor import run_doctor
from tradebruv.external_sources import fmp_status, gdelt_status, sec_edgar_status
from tradebruv.models import AlternativeDataItem, SecurityData
from tradebruv.readiness import run_readiness
from tradebruv.signal_quality import compare_strategy_to_baselines, run_signal_audit


def test_env_example_contains_free_first_vars():
    content = Path(".env.example").read_text(encoding="utf-8")
    for key in ("FINANCIAL_MODELING_PREP_API_KEY", "SEC_USER_AGENT", "GDELT_ENABLED=true", "QUIVER_API_KEY", "CAPITOL_TRADES_API_KEY"):
        assert key in content


def test_provider_status_missing_and_configured(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.delenv("FINANCIAL_MODELING_PREP_API_KEY", raising=False)
    assert sec_edgar_status(live=False).status == "WARN"
    assert fmp_status(live=False).status == "WARN"
    assert gdelt_status(live=False).status == "PASS"
    monkeypatch.setenv("SEC_USER_AGENT", "TradeBruv tests test@example.com")
    monkeypatch.setenv("FINANCIAL_MODELING_PREP_API_KEY", "fmp-test-key")
    assert sec_edgar_status(live=False).status == "PASS"
    assert fmp_status(live=False).status == "PASS"


def test_alternative_data_csv_parsing_and_signals(tmp_path):
    path = tmp_path / "alternative.csv"
    path.write_text(
        "\n".join(
            [
                "ticker,source_type,source_name,source_url,timestamp,actor_name,actor_role,actor_type,transaction_type,shares,estimated_value,price,filing_date,transaction_date,disclosure_lag_days,confidence,notes",
                "NVDA,sec,SEC,https://sec.gov/a,2026-01-01,CFO One,CFO,CFO,Buy,100,500000,500,2026-01-02,2026-01-01,1,0.9,verified",
                "NVDA,sec,SEC,https://sec.gov/b,2026-01-01,Director Two,Director,Director,Buy,100,250000,500,2026-01-02,2026-01-01,1,0.9,verified",
                "NVDA,manual,Congress,https://example.com/c,2026-01-01,Rep Three,Representative,Representative,Buy,10,20000,500,2026-03-01,2026-01-01,60,0.7,delayed",
            ]
        ),
        encoding="utf-8",
    )
    repo = load_alternative_data_repository(path)
    assert len(repo.items_for("NVDA")) == 3
    security = SecurityData(ticker="NVDA", company_name="NVIDIA", sector="Technology", bars=[], alternative_data_items=repo.items_for("NVDA"))
    features = SimpleNamespace(volume_confirmation=True, breakout_confirmed=True, close_near_week_high=False, return_5d=1.0)
    signal, warnings = build_alternative_data_signal(security=security, features=features, status_label="Strong Research Candidate")
    assert signal["CEO_CFO_buy_flag"] is True
    assert signal["cluster_buying_flag"] is True
    assert signal["politician_buy_count"] == 1
    assert signal["disclosure_lag_warning"]
    assert "Politician trades can be delayed" in " ".join(warnings)


def test_heavy_selling_and_alt_data_cannot_override_avoid():
    security = SecurityData(
        ticker="RISK",
        company_name="Risk",
        sector="Unknown",
        bars=[],
        alternative_data_items=[
            AlternativeDataItem(ticker="RISK", actor_type="CEO", actor_role="CEO", transaction_type="Buy", estimated_value=100000, source_url="https://sec.gov/buy", filing_date="2026-01-02"),
            AlternativeDataItem(ticker="RISK", actor_type="Director", actor_role="Director", transaction_type="Sell", estimated_value=1000000, source_url="https://sec.gov/sell", filing_date="2026-01-02"),
        ],
    )
    features = SimpleNamespace(volume_confirmation=False, breakout_confirmed=False, close_near_week_high=False, return_5d=-1.0)
    signal, warnings = build_alternative_data_signal(security=security, features=features, status_label="Avoid")
    assert signal["heavy_insider_selling_flag"] is True
    assert any("cannot override" in warning for warning in warnings)


def test_ai_guardrail_validator_flags_bad_output():
    bad = {
        "final_recommendation_label": "Strong Buy Candidate",
        "debate_summary": "Guaranteed winner. Buy now at current price $123. https://invented.example",
        "bull_case": ["will definitely go up"],
    }
    result = validate_ai_output(bad, {"status_label": "Avoid", "current_price": "unavailable"})
    assert result["unsupported_claims_detected"] is True
    assert result["ai_guardrail_warnings"]


def test_ai_guardrail_validator_good_mock_passes():
    good = {
        "final_recommendation_label": "Hold / Watch",
        "bear_case": ["Risk remains elevated."],
        "risk_manager_view": "Invalidation is 100. Research support only.",
        "missing_data": ["No verified news source."],
        "events_to_watch": ["Invalidation: 100"],
    }
    result = validate_ai_output(good, {"status_label": "Hold / Watch", "current_price": 120})
    assert result["unsupported_claims_detected"] is False


def test_doctor_and_readiness_reports_no_secret_leakage(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-pass8-secret-value")
    doctor = run_doctor(live=False, output_dir=tmp_path / "outputs")
    readiness = run_readiness(provider="sample", universe=_copy_universe(tmp_path), output_dir=tmp_path / "outputs")
    text = json.dumps({"doctor": doctor, "readiness": readiness})
    assert "sk-pass8-secret-value" not in text
    assert doctor["available"] is True
    assert readiness["ready_for_real_money_reliance"] is False


def test_signal_audit_random_baseline_comparison(tmp_path):
    comparison = compare_strategy_to_baselines(strategy_returns=[1, 2, -1, 4], baseline_returns={"SPY": [0.5, 0.8, -0.5, 1]}, random_returns=[-1, 1, 2, 4])
    assert comparison["strategy"]["sample_size"] == 4
    assert "SPY" in comparison["baselines"]
    report = run_signal_audit(reports_dir=tmp_path / "missing", random_baseline=True, output_dir=tmp_path / "outputs")
    assert report["conclusion"] == "Not enough evidence yet."


@pytest.mark.skipif(importlib.util.find_spec("fastapi") is None, reason="FastAPI is not installed")
def test_api_doctor_readiness_signal_audit_and_alt_data(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "outputs").mkdir()
    _copy_universe(tmp_path)
    source_template = Path(__file__).resolve().parents[1] / ".env.example"
    (tmp_path / ".env.example").write_text(source_template.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "config" / "alternative_data_watchlist.csv").write_text(
        "\n".join(
            [
                "ticker,source_type,source_name,source_url,timestamp,actor_name,actor_role,actor_type,transaction_type,shares,estimated_value,price,filing_date,transaction_date,disclosure_lag_days,confidence,notes",
                "NVDA,sec,SEC,https://sec.gov/a,2026-01-01,CFO One,CFO,CFO,Buy,100,500000,500,2026-01-02,2026-01-01,1,0.9,verified",
            ]
        ),
        encoding="utf-8",
    )
    from fastapi.testclient import TestClient
    from tradebruv.api import create_app

    client = TestClient(create_app())
    sources = client.get("/api/data-sources").json()["rows"]
    assert any(row["tier"] == "No key / free" for row in sources)
    scan = client.post("/api/scan", json={"provider": "sample", "mode": "outliers", "universe_path": "config/sample_universe.txt"}).json()
    nvda = next(row for row in scan["results"] if row["ticker"] == "NVDA")
    assert nvda["CEO_CFO_buy_flag"] is True
    assert client.post("/api/doctor/run", json={"live": False}).json()["available"] is True
    assert client.post("/api/readiness/run", json={"provider": "sample"}).json()["ready_for_real_money_reliance"] is False
    assert client.post("/api/signal-audit/run", json={"random_baseline": True}).json()["available"] is True


def _copy_universe(tmp_path: Path) -> Path:
    universe = tmp_path / "config" / "sample_universe.txt"
    universe.parent.mkdir(parents=True, exist_ok=True)
    universe.write_text("NVDA\nMSFT\nLLY\nPLTR\nENPH\nRIVN\n", encoding="utf-8")
    return universe
