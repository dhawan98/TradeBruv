from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from tradebruv.ai_committee import GeminiCommitteeProvider, OpenAICompatibleCommitteeProvider, run_ai_committee
from tradebruv.app_status import build_app_status_report
from tradebruv.doctor import run_doctor
from tradebruv.external_sources import finnhub_status
from tradebruv.readiness import run_readiness
from tradebruv.validation_lab import create_prediction_record


def test_doctor_live_failures_are_redacted_and_non_crashing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-pass9-secret-value")
    monkeypatch.setenv("FINANCIAL_MODELING_PREP_API_KEY", "fmp-pass9-secret-value")

    def fail_urlopen(*args, **kwargs):
        raise urllib.error.URLError("bad key sk-pass9-secret-value")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)
    report = run_doctor(live=True, ai="openai", ticker="NVDA", output_dir=tmp_path / "outputs")
    text = json.dumps(report)
    assert report["available"] is True
    assert "sk-pass9-secret-value" not in text
    assert any(check["status"] in {"WARN", "FAIL"} for check in report["checks"])


def test_finnhub_missing_and_failure_are_clean(monkeypatch, tmp_path):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    assert finnhub_status(live=False).status == "WARN"
    monkeypatch.setenv("FINNHUB_API_KEY", "finnhub-pass9-secret")

    def fail_urlopen(*args, **kwargs):
        raise urllib.error.URLError("token=finnhub-pass9-secret")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)
    status = finnhub_status(live=True, cache_dir=tmp_path)
    assert status.status == "FAIL"
    assert "finnhub-pass9-secret" not in status.message


def test_openai_and_gemini_adapters_mocked_success(monkeypatch):
    payloads = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            if len(payloads) == 1:
                return json.dumps({"choices": [{"message": {"content": json.dumps(_ai_payload())}}]}).encode()
            return json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(_ai_payload())}]}}]}).encode()

    def fake_urlopen(request, timeout=30):
        payloads.append(request.full_url)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    scanner_row = {"ticker": "NVDA", "status_label": "Hold / Watch", "current_price": 100, "why_it_could_fail": ["Risk"], "why_it_passed": ["Setup"]}
    openai = run_ai_committee(scanner_row=scanner_row, provider=OpenAICompatibleCommitteeProvider(api_key="sk-test-secret", model="test"))
    gemini = run_ai_committee(scanner_row=scanner_row, provider=GeminiCommitteeProvider(api_key="gemini-test-secret", model="gemini-test"))
    assert openai["available"] is True
    assert gemini["available"] is True
    assert openai["unsupported_claims_detected"] is False
    assert gemini["unsupported_claims_detected"] is False


def test_readiness_and_app_status_reports_include_pass9_truths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sample_universe.txt").write_text("NVDA\nMSFT\nLLY\nPLTR\nENPH\nRIVN\n", encoding="utf-8")
    readiness = run_readiness(provider="sample", universe=Path("config/sample_universe.txt"), ai="mock", output_dir=tmp_path / "outputs")
    assert readiness["ready_for_real_money_reliance"] is False
    assert "ai_guardrails_passed" in readiness
    assert "signal_audit_has_enough_samples" in readiness
    app_status = build_app_status_report(output_dir=tmp_path / "outputs")
    assert (tmp_path / "outputs" / "app_status_report.md").exists()
    assert app_status["validation_sample_enough"] is False


def test_paper_tracking_record_includes_review_and_snapshot():
    record = create_prediction_record(
        scanner_row={"ticker": "NVDA", "current_price": 100, "status_label": "Hold / Watch", "invalidation_level": 90, "tp1": 110, "tp2": 120},
        rule_based_recommendation="Hold / Watch",
        thesis="Paper thesis",
        invalidation=91,
        tp1=111,
        tp2=121,
        expected_holding_period="10D",
        recommendation_snapshot={"deterministic": "Hold / Watch"},
        created_at="2026-04-24T00:00:00Z",
    )
    assert record["next_review_date"] == "2026-05-04"
    assert record["invalidation"] == 91
    assert "deterministic" in record["recommendation_snapshot"]


def _ai_payload() -> dict[str, object]:
    return {
        "bull_case": ["Setup is improving."],
        "bear_case": ["Risk remains elevated."],
        "risk_manager_view": "Invalidation is supplied. Research support only.",
        "catalyst_view": "No invented catalyst.",
        "debate_summary": "Hold / Watch while evidence develops. Research support only.",
        "final_recommendation_label": "Hold / Watch",
        "confidence_label": "Medium",
        "evidence_used": ["Supplied scanner row."],
        "missing_data": ["No verified external filings in payload."],
        "events_to_watch": ["Invalidation level."],
        "what_would_change_my_mind": ["Break below invalidation."],
        "portfolio_specific_action": "No portfolio action without holdings.",
        "recommended_next_step": "Deep Research",
    }
