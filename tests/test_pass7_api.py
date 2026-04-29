from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(importlib.util.find_spec("fastapi") is None, reason="FastAPI is not installed")


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "outputs").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "config" / "sample_universe.txt").write_text("NVDA\nMSFT\nLLY\nPLTR\nENPH\nRIVN\n", encoding="utf-8")
    source_template = Path(__file__).resolve().parents[1] / ".env.example"
    (tmp_path / ".env.example").write_text(source_template.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("TRADEBRUV_ALLOW_LOCAL_ENV_EDITOR", raising=False)

    from fastapi.testclient import TestClient
    from tradebruv.api import create_app

    return TestClient(create_app())


def test_api_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["primary_ui"] == "vite-react"
    assert payload["fallback_ui"] == "streamlit"


def test_data_sources_no_secret_leakage(client, monkeypatch):
    secret = "sk-test-secret-not-for-ui"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    response = client.get("/api/data-sources")
    assert response.status_code == 200
    text = response.text
    assert secret not in text
    assert "OPENAI_API_KEY" in text


def test_env_template_endpoint(client):
    response = client.get("/api/env-template")
    assert response.status_code == 200
    payload = response.json()
    assert payload["exists"] is True
    assert "OPENAI_API_KEY" in payload["keys"]
    assert "TRADEBRUV_ALLOW_LOCAL_ENV_EDITOR" in payload["content"]


def test_create_env_template_behavior(client):
    response = client.post("/api/env/create-template")
    assert response.status_code == 200
    assert response.json()["created"] is True
    second = client.post("/api/env/create-template")
    assert second.status_code == 200
    assert second.json()["created"] is False


def test_local_env_editor_disabled_by_default(client):
    response = client.post("/api/env/update-local", json={"values": {"OPENAI_API_KEY": "sk-disabled"}})
    assert response.status_code == 403


def test_local_env_editor_enabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=\nTRADEBRUV_ALLOW_LOCAL_ENV_EDITOR=false\n", encoding="utf-8")
    monkeypatch.setenv("TRADEBRUV_ALLOW_LOCAL_ENV_EDITOR", "true")
    from fastapi.testclient import TestClient
    from tradebruv.api import create_app

    client = TestClient(create_app())
    response = client.post("/api/env/update-local", json={"values": {"OPENAI_API_KEY": "sk-local-editor"}})
    assert response.status_code == 200
    assert response.json()["updated_keys"] == ["OPENAI_API_KEY"]
    assert "sk-local-editor" not in response.text
    assert "sk-local-editor" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_scan_endpoint_with_sample_provider(client):
    response = client.post(
        "/api/scan",
        json={"provider": "sample", "mode": "outliers", "universe_path": "config/sample_universe.txt", "as_of_date": "2026-04-24"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    assert payload["available"] is True
    assert payload["demo_mode"] is True
    assert payload["report_snapshot"] is False
    assert payload["data_issues"]
    assert all(row["price_validation_status"] == "FAIL" for row in payload["decisions"])
    assert (Path("outputs") / "outlier_scan_report.json").exists()


def test_daily_decision_latest_endpoint(client):
    output_path = Path("outputs/daily/decision_today.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "available": True,
                "generated_at": "2026-04-24T00:00:00Z",
                "provider": "real",
                "mode": "daily-decision",
                "data_mode": "live_daily_decision",
                "results": [],
                "summary": {},
                "decisions": [],
                "data_issues": [],
                "validation_context": {"messages": ["Fresh live prices validated."]},
                "market_regime": {"regime": "Risk On"},
                "demo_mode": False,
                "report_snapshot": False,
                "stale_data": False,
            }
        ),
        encoding="utf-8",
    )

    response = client.get("/api/daily-decision/latest")

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["mode"] == "daily-decision"


def test_chart_and_tracked_endpoints(client):
    chart = client.get("/api/chart/NVDA", params={"provider": "sample", "timeframe": "1Y"})
    assert chart.status_code == 200
    chart_payload = chart.json()
    assert chart_payload["available"] is True
    assert chart_payload["ticker"] == "NVDA"
    assert chart_payload["series"]

    before = client.get("/api/tracked")
    assert before.status_code == 200
    add = client.post("/api/tracked/add", json={"ticker": "NVDA"})
    assert add.status_code == 200
    assert "NVDA" in add.json()["tickers"]
    remove = client.post("/api/tracked/remove", json={"ticker": "NVDA"})
    assert remove.status_code == 200
    assert "NVDA" not in remove.json()["tickers"]


def test_deep_research_endpoint(client):
    response = client.post("/api/deep-research", json={"ticker": "NVDA", "provider": "sample", "as_of_date": "2026-04-24"})
    assert response.status_code == 200
    assert response.json()["ticker"] == "NVDA"


def test_portfolio_crud_and_analyze(client):
    create = client.post("/api/portfolio/positions", json={"ticker": "NVDA", "quantity": 2, "average_cost": 100, "current_price": 120})
    assert create.status_code == 200
    assert create.json()["summary"]["position_count"] == 1
    update = client.put("/api/portfolio/positions/NVDA", json={"quantity": 3, "average_cost": 100, "current_price": 120})
    assert update.status_code == 200
    analyze = client.post("/api/portfolio/analyze", json={"provider": "sample", "as_of_date": "2026-04-24"})
    assert analyze.status_code == 200
    assert analyze.json()["positions"]
    delete = client.delete("/api/portfolio/positions/NVDA")
    assert delete.status_code == 200
    assert delete.json()["removed"] is True


def test_ai_committee_mock_endpoint(client):
    scan = client.post("/api/scan", json={"provider": "sample", "mode": "outliers", "universe_path": "config/sample_universe.txt", "as_of_date": "2026-04-24"}).json()
    response = client.post("/api/ai-committee", json={"mode": "Mock AI for testing", "scanner_row": scan["results"][0]})
    assert response.status_code == 200
    assert response.json()["committee"]["available"] is True


def test_validation_alerts_reports_endpoints(client):
    scan = client.post("/api/scan", json={"provider": "sample", "mode": "outliers", "universe_path": "config/sample_universe.txt", "as_of_date": "2026-04-24"}).json()
    prediction = client.post("/api/predictions", json={"scanner_row": scan["results"][0], "rule_based_recommendation": "Strong Research Candidate"})
    assert prediction.status_code == 200
    assert client.get("/api/predictions").json()
    assert client.get("/api/predictions/summary").status_code == 200
    alerts_path = Path("outputs/daily/alerts.json")
    alerts_path.parent.mkdir(parents=True, exist_ok=True)
    alerts_path.write_text(json.dumps({"alerts": [{"ticker": "NVDA", "severity": "Watch"}]}), encoding="utf-8")
    assert client.get("/api/alerts").json()[0]["ticker"] == "NVDA"
    assert client.get("/api/reports/latest").json()["available"] is True
