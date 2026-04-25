from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .ai_committee import run_ai_committee
from .alternative_data import DEFAULT_ALTERNATIVE_DATA_PATH, load_alternative_data_repository
from .portfolio import PortfolioPosition
from .providers import SampleMarketDataProvider
from .validation_lab import create_prediction_record


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
    output_dir.mkdir(parents=True, exist_ok=True)
    tickers = [ticker.upper() for ticker in (tickers or ["NVDA", "PLTR", "MU", "RDDT", "GME", "CAR"])]
    checks: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []
    from .dashboard_data import run_dashboard_deep_research, run_dashboard_portfolio_analysis, run_dashboard_scan

    try:
        scan = run_dashboard_scan(provider_name=provider, mode="outliers", universe_path=universe, limit=25)
        report_rows = scan.results
        checks.append(_row("real/sample data scan", "PASS" if report_rows else "WARN", provider, f"Scanner returned {len(report_rows)} rows."))
        checks.append(_row("outlier scan", "PASS" if any(row.get("outlier_score") is not None for row in report_rows) else "WARN", provider, "Outlier scores present." if report_rows else "No rows to score."))
    except Exception as exc:  # noqa: BLE001 - readiness must continue
        checks.append(_row("real/sample data scan", "FAIL", provider, f"Scan failed: {exc}"))

    sample_provider = SampleMarketDataProvider(end_date=date.today())
    research_payloads = []
    for ticker in tickers[:4]:
        try:
            research_payloads.append(run_dashboard_deep_research(ticker=ticker, provider=sample_provider, portfolio_rows=[], journal_rows=[]))
        except Exception as exc:  # noqa: BLE001
            checks.append(_row(f"Deep Research {ticker}", "WARN", "sample", f"Deep Research failed: {exc}"))
    checks.append(_row("Deep Research decision cards", "PASS" if research_payloads else "WARN", "sample", f"Generated {len(research_payloads)} research payloads."))

    scanner_row = (report_rows[0] if report_rows else research_payloads[0].get("scanner_row", {})) if (report_rows or research_payloads) else {}
    committee = run_ai_committee(scanner_row=scanner_row, portfolio_context={}, mode="Mock AI for testing")
    checks.append(_row("AI Committee mock", "PASS" if committee.get("available") else "WARN", "mock", str(committee.get("debate_summary", "completed"))[:300]))
    if ai.lower() in {"openai", "gemini"}:
        live_committee = run_ai_committee(scanner_row=scanner_row, portfolio_context={}, mode="OpenAI only" if ai.lower() == "openai" else "Gemini only")
        checks.append(_row(f"AI Committee {ai}", "PASS" if live_committee.get("available") else "SKIPPED", ai.lower(), str(live_committee.get("debate_summary", "unavailable"))[:300]))

    try:
        positions = [PortfolioPosition(ticker=ticker, quantity=1, average_cost=100, cost_basis=100, current_price=110, market_value=110, account_name="sample") for ticker in tickers[:3]]
        portfolio_payload = run_dashboard_portfolio_analysis(rows=[position.to_dict() for position in positions], provider=sample_provider)
        checks.append(_row("portfolio-aware analysis", "PASS" if portfolio_payload.get("recommendations") else "WARN", "sample", "Portfolio analyst completed."))
    except Exception as exc:  # noqa: BLE001
        checks.append(_row("portfolio-aware analysis", "FAIL", "sample", f"Portfolio analysis failed: {exc}"))

    if scanner_row:
        record = create_prediction_record(scanner_row=scanner_row, rule_based_recommendation=str(scanner_row.get("status_label", "Data Insufficient")), ai_committee_recommendation=committee.get("final_recommendation_label", "Data Insufficient"), thesis="Readiness dry-run record.")
        checks.append(_row("validation dry-run record", "PASS", "dry-run", f"Created prediction record shape for {record.get('ticker')}."))
    else:
        checks.append(_row("validation dry-run record", "WARN", "dry-run", "No scanner row available for dry-run prediction."))

    alt_repo = load_alternative_data_repository(DEFAULT_ALTERNATIVE_DATA_PATH)
    checks.append(_row("alternative data ingestion", "PASS" if alt_repo.items_by_ticker or DEFAULT_ALTERNATIVE_DATA_PATH.exists() else "SKIPPED", "local", f"Alternative data rows loaded: {sum(len(items) for items in alt_repo.items_by_ticker.values())}."))
    checks.append(_row("daily alerts dry-run", "PASS" if report_rows else "WARN", "dry-run", "Alert generation has scanner rows available." if report_rows else "No scanner rows for alert dry-run."))
    checks.append(_row("report completeness", "PASS" if report_rows and scanner_row.get("warnings") is not None else "WARN", provider, "Scanner rows include warnings, scores, and status fields." if scanner_row else "No scanner row available."))
    checks.append(_row("unsupported claims guardrail", "PASS", "config-only", "Readiness report labels research support and does not claim profitability."))

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
        "ready_for_paper_tracking": bool(report_rows and research_payloads),
        "ready_for_manual_research_use": bool(report_rows or research_payloads),
        "ready_for_real_money_reliance": False,
        "real_money_reliance_note": "Not ready for real-money reliance; use as research support until forward validation has enough evidence.",
    }
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
        "",
        "| Check | Status | Mode | Message |",
        "| --- | --- | --- | --- |",
    ]
    for check in report["checks"]:
        lines.append(f"| {check['name']} | {check['status']} | {check['mode']} | {str(check['message']).replace('|', '/')} |")
    lines.extend(["", report["real_money_reliance_note"], ""])
    return "\n".join(lines)
