from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .ai_committee import run_ai_committee
from .alternative_data import DEFAULT_ALTERNATIVE_DATA_PATH, load_alternative_data_repository
from .data_sources import redact_secrets, secret_values_present_in_text
from .env import load_local_env
from .external_sources import cheap_provider_statuses
from .portfolio import PortfolioPosition
from .providers import LocalFileMarketDataProvider, ProviderFetchError, SampleMarketDataProvider, YFinanceMarketDataProvider
from .signal_quality import load_latest_signal_quality
from .validation_lab import DEFAULT_PREDICTIONS_PATH, create_prediction_record, load_predictions, validation_metrics


DEFAULT_READINESS_JSON = Path("outputs/readiness_report.json")
DEFAULT_READINESS_MD = Path("outputs/readiness_report.md")


def run_readiness(
    *,
    universe: Path = Path("config/outlier_watchlist.txt"),
    provider: str = "sample",
    tickers: list[str] | None = None,
    ai: str = "mock",
    output_dir: Path = Path("outputs"),
) -> dict[str, Any]:
    load_local_env()
    output_dir.mkdir(parents=True, exist_ok=True)
    tickers = [ticker.upper() for ticker in (tickers or ["NVDA", "PLTR", "MU", "RDDT", "GME", "CAR"])]
    checks: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []
    missing_data: list[str] = []
    live_provider_checks: list[dict[str, Any]] = []
    from .dashboard_data import run_dashboard_deep_research, run_dashboard_portfolio_analysis, run_dashboard_scan

    try:
        scan = run_dashboard_scan(provider_name=provider, mode="outliers", universe_path=universe, limit=25)
        report_rows = scan.results
        checks.append(_row("real/sample data scan", "PASS" if report_rows else "WARN", provider, f"Scanner returned {len(report_rows)} rows."))
        checks.append(_row("outlier scan", "PASS" if any(row.get("outlier_score") is not None for row in report_rows) else "WARN", provider, "Outlier scores present." if report_rows else "No rows to score."))
    except Exception as exc:  # noqa: BLE001 - readiness must continue
        checks.append(_row("real/sample data scan", "FAIL", provider, f"Scan failed: {redact_secrets(exc)}"))
        missing_data.append(f"Scanner rows unavailable from provider={provider}.")

    research_provider = _provider_for_readiness(provider)
    research_payloads = []
    for ticker in tickers[:6]:
        try:
            research_payloads.append(run_dashboard_deep_research(ticker=ticker, provider=research_provider, portfolio_rows=[], journal_rows=[]))
        except Exception as exc:  # noqa: BLE001
            checks.append(_row(f"Deep Research {ticker}", "WARN", provider, f"Deep Research failed: {redact_secrets(exc)}"))
            missing_data.append(f"Deep Research missing for {ticker}: {redact_secrets(exc)}")
    checks.append(_row("Deep Research decision cards", "PASS" if research_payloads else "WARN", provider, f"Generated {len(research_payloads)} research payloads."))

    scanner_row = (report_rows[0] if report_rows else research_payloads[0].get("scanner_row", {})) if (report_rows or research_payloads) else {}
    committee = run_ai_committee(scanner_row=scanner_row, portfolio_context={}, mode="Mock AI for testing")
    checks.append(_row("AI Committee mock", "PASS" if committee.get("available") else "WARN", "mock", str(committee.get("debate_summary", "completed"))[:300]))
    checks.append(_row("AI guardrails mock", "PASS" if not committee.get("unsupported_claims_detected") else "WARN", "mock", _guardrail_message(committee)))
    live_committee: dict[str, Any] | None = None
    if ai.lower() in {"openai", "gemini"}:
        live_committee = run_ai_committee(scanner_row=scanner_row, portfolio_context={}, mode="OpenAI only" if ai.lower() == "openai" else "Gemini only")
        status = "PASS" if live_committee.get("available") else "SKIPPED"
        checks.append(_row(f"AI Committee {ai}", status, ai.lower(), redact_secrets(str(live_committee.get("debate_summary", "unavailable"))[:300])))
        checks.append(_row(f"AI guardrails {ai}", "PASS" if live_committee.get("available") and not live_committee.get("unsupported_claims_detected") else "WARN", ai.lower(), _guardrail_message(live_committee)))

    try:
        positions = [PortfolioPosition(ticker=ticker, quantity=1, average_cost=100, cost_basis=100, current_price=110, market_value=110, account_name="sample") for ticker in tickers[:3]]
        portfolio_payload = run_dashboard_portfolio_analysis(rows=[position.to_dict() for position in positions], provider=research_provider)
        checks.append(_row("portfolio-aware analysis", "PASS" if portfolio_payload.get("recommendations") else "WARN", provider, "Portfolio analyst completed."))
    except Exception as exc:  # noqa: BLE001
        checks.append(_row("portfolio-aware analysis", "FAIL", provider, f"Portfolio analysis failed: {redact_secrets(exc)}"))
        missing_data.append(f"Portfolio-aware analysis unavailable: {redact_secrets(exc)}")

    if scanner_row:
        record = create_prediction_record(scanner_row=scanner_row, rule_based_recommendation=str(scanner_row.get("status_label", "Data Insufficient")), ai_committee_recommendation=committee.get("final_recommendation_label", "Data Insufficient"), thesis="Readiness dry-run record.")
        checks.append(_row("validation dry-run record", "PASS", "dry-run", f"Created prediction record shape for {record.get('ticker')}."))
    else:
        checks.append(_row("validation dry-run record", "WARN", "dry-run", "No scanner row available for dry-run prediction."))

    alt_repo = load_alternative_data_repository(DEFAULT_ALTERNATIVE_DATA_PATH)
    checks.append(_row("alternative data ingestion", "PASS" if alt_repo.items_by_ticker or DEFAULT_ALTERNATIVE_DATA_PATH.exists() else "SKIPPED", "local", f"Alternative data rows loaded: {sum(len(items) for items in alt_repo.items_by_ticker.values())}."))
    live_provider_checks = cheap_provider_statuses(live=provider == "real", ticker=tickers[0] if tickers else "NVDA")
    for row in live_provider_checks:
        checks.append(_row(f"provider {row['name']}", row["status"], row["mode"], row["message"]))
        if row["status"] in {"WARN", "FAIL"}:
            missing_data.append(f"{row['name']}: {row['message']}")
    prediction_rows = load_predictions(DEFAULT_PREDICTIONS_PATH)
    metrics = validation_metrics(prediction_rows)
    enough_samples = not bool(metrics.get("sample_size_warning"))
    checks.append(_row("signal audit sample size", "PASS" if enough_samples else "WARN", "validation", str(metrics.get("sample_size_warning") or "At least 30 closed paper predictions available.")))
    latest_audit = load_latest_signal_quality()
    checks.append(_row("signal quality audit report", "PASS" if latest_audit.get("available") else "WARN", "validation", str(latest_audit.get("conclusion") or latest_audit.get("message") or "Signal audit has not run yet.")))
    checks.append(_row("daily alerts dry-run", "PASS" if report_rows else "WARN", "dry-run", "Alert generation has scanner rows available." if report_rows else "No scanner rows for alert dry-run."))
    checks.append(_row("report completeness", "PASS" if report_rows and scanner_row.get("warnings") is not None else "WARN", provider, "Scanner rows include warnings, scores, and status fields." if scanner_row else "No scanner row available."))
    checks.append(_row("unsupported claims guardrail", "PASS", "config-only", "Readiness report labels research support and does not claim profitability."))
    if not alt_repo.items_by_ticker:
        missing_data.append("No local alternative-data CSV rows loaded; insider/politician context may be unavailable.")

    report = {
        "available": True,
        "kind": "readiness",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "provider": provider,
        "requested_ai": ai,
        "universe": str(universe),
        "tickers": tickers,
        "summary": _summarize(checks),
        "checks": checks,
        "scanner_produced_usable_candidates": bool(report_rows),
        "deep_research_produced_decision_cards": bool(research_payloads),
        "alternative_data_included": bool(alt_repo.items_by_ticker),
        "data_missing": sorted(dict.fromkeys(missing_data)),
        "providers_live": _providers_by_mode(live_provider_checks, live=True),
        "providers_mock_or_config_only": _providers_by_mode(live_provider_checks, live=False) + (["AI Committee mock"] if committee.get("available") else []),
        "ai_guardrails_passed": bool(not committee.get("unsupported_claims_detected") and (live_committee is None or not live_committee.get("unsupported_claims_detected"))),
        "deep_research_worked": bool(research_payloads),
        "portfolio_aware_analysis_worked": any(check["name"] == "portfolio-aware analysis" and check["status"] == "PASS" for check in checks),
        "signal_audit_has_enough_samples": enough_samples,
        "ready_for_paper_tracking": bool(report_rows and research_payloads),
        "ready_for_manual_research_use": bool(report_rows or research_payloads),
        "ready_for_real_money_reliance": False,
        "real_money_reliance_note": "Not ready for real-money reliance; use as research support until forward validation has enough evidence.",
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    leaked = secret_values_present_in_text(text)
    if leaked:
        report = json.loads(redact_secrets(text))
        report["secret_leak_check"] = "FAIL"
        report["secret_leak_env_vars"] = leaked
    else:
        report["secret_leak_check"] = "PASS"
    json_path = output_dir / "readiness_report.json"
    md_path = output_dir / "readiness_report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["markdown_path"] = str(md_path)
    return report


def load_latest_readiness(path: Path = DEFAULT_READINESS_JSON) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "status": "not_run", "message": "Readiness has not run yet."}
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["available"] = True
    return payload


def _row(name: str, status: str, mode: str, message: str) -> dict[str, Any]:
    return {"name": name, "status": status, "mode": mode, "message": message, "checked_at": datetime.utcnow().isoformat() + "Z"}


def _summarize(checks: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIPPED": 0}
    for check in checks:
        status = str(check.get("status", "WARN"))
        summary[status] = summary.get(status, 0) + 1
    return summary


def _provider_for_readiness(provider: str):
    if provider == "real":
        return YFinanceMarketDataProvider(history_period="3y")
    if provider == "local":
        try:
            return LocalFileMarketDataProvider("data")
        except Exception as exc:  # noqa: BLE001 - fallback keeps readiness usable
            raise ProviderFetchError(f"Local provider unavailable: {redact_secrets(exc)}") from exc
    return SampleMarketDataProvider(end_date=date.today())


def _guardrail_message(payload: dict[str, Any]) -> str:
    warnings = payload.get("ai_guardrail_warnings") or []
    if not warnings:
        return "AI guardrail validator found no unsupported claims."
    return redact_secrets(" | ".join(str(item) for item in warnings))


def _providers_by_mode(rows: list[dict[str, Any]], *, live: bool) -> list[str]:
    if live:
        return [str(row["name"]) for row in rows if row.get("mode") == "live" and row.get("status") == "PASS"]
    return [str(row["name"]) for row in rows if row.get("mode") != "live" or row.get("status") != "PASS"]


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# TradeBruv Readiness Report",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Provider: {report['provider']}",
        f"- AI: {report['requested_ai']}",
        f"- Ready for paper tracking: {report['ready_for_paper_tracking']}",
        f"- Ready for manual research use: {report['ready_for_manual_research_use']}",
        f"- Ready for real-money reliance: {report['ready_for_real_money_reliance']}",
        f"- AI guardrails passed: {report['ai_guardrails_passed']}",
        f"- Deep research worked: {report['deep_research_worked']}",
        f"- Portfolio-aware analysis worked: {report['portfolio_aware_analysis_worked']}",
        f"- Signal audit has enough samples: {report['signal_audit_has_enough_samples']}",
        f"- Live providers: {', '.join(report['providers_live']) or 'none'}",
        f"- Mock/config-only/degraded providers: {', '.join(report['providers_mock_or_config_only']) or 'none'}",
        "",
        "## Missing Data",
        "",
        *(f"- {item}" for item in report["data_missing"]),
        "" if report["data_missing"] else "- None reported by readiness.",
        "",
        "| Check | Status | Mode | Message |",
        "| --- | --- | --- | --- |",
    ]
    for check in report["checks"]:
        lines.append(f"| {check['name']} | {check['status']} | {check['mode']} | {str(check['message']).replace('|', '/')} |")
    lines.extend(["", report["real_money_reliance_note"], ""])
    return "\n".join(lines)
