from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .data_sources import build_data_source_status
from .doctor import load_latest_doctor
from .readiness import load_latest_readiness
from .signal_quality import load_latest_signal_quality
from .validation_lab import DEFAULT_PREDICTIONS_PATH, load_predictions, validation_metrics


DEFAULT_APP_STATUS_MD = Path("outputs/app_status_report.md")
DEFAULT_APP_STATUS_JSON = Path("outputs/app_status_report.json")


def build_app_status_report(*, output_dir: Path = Path("outputs")) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    doctor = load_latest_doctor(output_dir / "doctor_report.json")
    readiness = load_latest_readiness(output_dir / "readiness_report.json")
    signal_audit = load_latest_signal_quality(output_dir / "signal_quality_report.json")
    sources = build_data_source_status()
    predictions = load_predictions(DEFAULT_PREDICTIONS_PATH)
    metrics = validation_metrics(predictions)
    openai = _source(sources, "OpenAI")
    gemini = _source(sources, "Google Gemini")
    provider_names = ["SEC EDGAR", "GDELT", "Financial Modeling Prep", "Finnhub"]
    live_tested = _live_tested_provider_names(doctor, provider_names)

    report = {
        "available": True,
        "kind": "app_status",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "working_features": _working_features(doctor, readiness, signal_audit, predictions),
        "degraded_or_missing_features": _degraded_features(doctor, readiness, sources, metrics),
        "live_tested_providers": live_tested,
        "mock_only_providers": _mock_only_providers(readiness),
        "openai_works": _ai_works(doctor, readiness, "OpenAI"),
        "gemini_works": _ai_works(doctor, readiness, "Gemini"),
        "provider_status": {name: _provider_status(doctor, name) for name in provider_names},
        "frontend_actions_work": _frontend_status(doctor),
        "validation_sample_enough": not bool(metrics.get("sample_size_warning")),
        "recommended_next_actions": _next_actions(readiness, metrics, openai, gemini),
    }
    json_path = output_dir / "app_status_report.json"
    md_path = output_dir / "app_status_report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["markdown_path"] = str(md_path)
    report["markdown"] = md_path.read_text(encoding="utf-8")
    return report


def load_latest_app_status(path: Path = DEFAULT_APP_STATUS_MD) -> dict[str, Any]:
    json_path = path.with_suffix(".json")
    if json_path.exists():
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        payload["available"] = True
        payload["markdown"] = path.read_text(encoding="utf-8") if path.exists() else _markdown(payload)
        return payload
    if path.exists():
        return {"available": True, "kind": "app_status", "markdown": path.read_text(encoding="utf-8")}
    return build_app_status_report(output_dir=path.parent)


def _source(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next((row for row in rows if row.get("name") == name), {})


def _working_features(doctor: dict[str, Any], readiness: dict[str, Any], signal_audit: dict[str, Any], predictions: list[dict[str, Any]]) -> list[str]:
    features = ["Deterministic scanner", "Data-source readiness inventory", "Local paper-prediction storage"]
    if doctor.get("available"):
        features.append("Doctor report generation")
    if readiness.get("ready_for_manual_research_use"):
        features.append("Manual research workflow")
    if readiness.get("ready_for_paper_tracking"):
        features.append("Paper tracking workflow")
    if signal_audit.get("available"):
        features.append("Signal quality audit report")
    if predictions:
        features.append("Validation records exist")
    return features


def _degraded_features(
    doctor: dict[str, Any],
    readiness: dict[str, Any],
    sources: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> list[str]:
    degraded = []
    if not doctor.get("available"):
        degraded.append("Doctor has not run yet.")
    degraded.extend(str(item) for item in readiness.get("data_missing", []))
    degraded.extend(str(row["degraded_when_missing"]) for row in sources if not row.get("configured") and row.get("degraded_when_missing") != "none")
    if metrics.get("sample_size_warning"):
        degraded.append(str(metrics["sample_size_warning"]))
    return sorted(dict.fromkeys(degraded))[:25]


def _live_tested_provider_names(doctor: dict[str, Any], names: list[str]) -> list[str]:
    checks = doctor.get("checks") or []
    return [
        name
        for name in names
        if any(name in str(check.get("name")) and check.get("mode") == "live" and check.get("status") == "PASS" for check in checks)
    ]


def _mock_only_providers(readiness: dict[str, Any]) -> list[str]:
    providers = list(readiness.get("providers_mock_or_config_only") or [])
    if readiness.get("requested_ai") == "mock":
        providers.append("AI Committee mock")
    return sorted(dict.fromkeys(str(item) for item in providers))


def _ai_works(doctor: dict[str, Any], readiness: dict[str, Any], name: str) -> bool:
    checks = [*(doctor.get("checks") or []), *(readiness.get("checks") or [])]
    return any(name in str(check.get("name")) and check.get("status") == "PASS" for check in checks)


def _provider_status(doctor: dict[str, Any], name: str) -> str:
    checks = doctor.get("checks") or []
    match = next((check for check in checks if name in str(check.get("name"))), None)
    if not match:
        return "not tested"
    return f"{match.get('status')} - {match.get('message')}"


def _frontend_status(doctor: dict[str, Any]) -> str:
    checks = doctor.get("checks") or []
    frontend = next((check for check in checks if check.get("name") == "Frontend"), None)
    backend = next((check for check in checks if check.get("name") == "Backend API"), None)
    if frontend and frontend.get("status") == "PASS" and backend and backend.get("status") == "PASS":
        return "backend and frontend health endpoints passed; React action flows are covered by API/browser smoke tests."
    if frontend:
        return f"frontend health {frontend.get('status')}: {frontend.get('message')}"
    return "frontend health not tested yet."


def _next_actions(readiness: dict[str, Any], metrics: dict[str, Any], openai: dict[str, Any], gemini: dict[str, Any]) -> list[str]:
    actions = ["Continue paper tracking before trusting recommendations with real money."]
    if not openai.get("configured"):
        actions.append("Add OPENAI_API_KEY if OpenAI committee output is desired.")
    if not gemini.get("configured"):
        actions.append("Add GEMINI_API_KEY if Gemini committee output is desired.")
    if readiness.get("data_missing"):
        actions.append("Work through readiness missing-data rows from top to bottom.")
    if metrics.get("sample_size_warning"):
        actions.append("Collect at least 30 closed forward paper predictions before tuning rules.")
    return actions


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# TradeBruv App Status Report",
        "",
        f"- Generated: {report.get('generated_at', 'unknown')}",
        f"- OpenAI works: {report.get('openai_works')}",
        f"- Gemini works: {report.get('gemini_works')}",
        f"- Validation sample enough: {report.get('validation_sample_enough')}",
        f"- Frontend actions: {report.get('frontend_actions_work')}",
        "",
        "## Working Features",
        "",
        *[f"- {item}" for item in report.get("working_features", [])],
        "",
        "## Degraded Or Missing Features",
        "",
        *[f"- {item}" for item in report.get("degraded_or_missing_features", [])],
        "",
        "## Live-Tested Providers",
        "",
        *[f"- {item}" for item in report.get("live_tested_providers", [])],
        "" if report.get("live_tested_providers") else "- None confirmed live yet.",
        "",
        "## Mock / Config-Only Providers",
        "",
        *[f"- {item}" for item in report.get("mock_only_providers", [])],
        "" if report.get("mock_only_providers") else "- None reported.",
        "",
        "## Provider Status",
        "",
    ]
    for name, status in (report.get("provider_status") or {}).items():
        lines.append(f"- {name}: {status}")
    lines.extend(["", "## Recommended Next Actions", ""])
    lines.extend(f"- {item}" for item in report.get("recommended_next_actions", []))
    lines.extend(["", "Research support only. This report does not validate profitability or prediction accuracy.", ""])
    return "\n".join(lines)
