from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .dashboard_data import find_latest_report, load_dashboard_report
from .decision_engine import build_unified_decisions, build_validation_context
from .price_sanity import build_price_sanity_from_row
from .providers import ProviderConfigurationError, SampleMarketDataProvider, YFinanceMarketDataProvider
from .scanner import DeterministicScanner


def build_price_lineage_report(
    *,
    tickers: list[str],
    output_dir: Path = Path("outputs/debug"),
    reference_date: date | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    latest_path = find_latest_report(Path("outputs"))
    if latest_path is None:
        payload = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "available": False,
            "source_endpoint": "/api/reports/latest",
            "message": "No saved report found under outputs/.",
            "items": [],
        }
    else:
        report = load_dashboard_report(latest_path)
        rows = {
            str(row.get("ticker") or "").upper(): _enrich_report_row(
                row,
                generated_at=report.generated_at,
                reference_date=reference_date or date.today(),
                report_path=latest_path,
            )
            for row in report.results
        }
        decisions = {
            str(row.get("ticker") or "").upper(): row
            for row in build_unified_decisions(
                list(rows.values()),
                scan_generated_at=report.generated_at,
                validation_context=build_validation_context(),
                reference_date=reference_date or date.today(),
                preferred_lane="Outlier",
            )
        }
        payload = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "available": True,
            "source_endpoint": "/api/reports/latest",
            "source_file": str(latest_path),
            "scan_timestamp": report.generated_at,
            "provider": report.provider,
            "mode": report.mode,
            "items": [
                _lineage_item(
                    ticker=ticker,
                    row=rows.get(ticker),
                    decision=decisions.get(ticker),
                )
                for ticker in tickers
            ],
        }
    json_path = output_dir / "price_lineage_report.json"
    md_path = output_dir / "price_lineage_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_lineage_markdown(payload), encoding="utf-8")
    payload["json_path"] = str(json_path)
    payload["markdown_path"] = str(md_path)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def build_price_debug_report(
    *,
    tickers: list[str],
    provider_name: str,
    history_period: str = "3y",
    analysis_date: date | None = None,
    output_dir: Path = Path("outputs/debug"),
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    provider = build_provider(
        provider_name=provider_name,
        history_period=history_period,
        analysis_date=analysis_date or date.today(),
    )
    scanner = DeterministicScanner(provider=provider, analysis_date=analysis_date or date.today())
    generated_at = datetime.utcnow().isoformat() + "Z"
    rows = []
    for result in scanner.scan(tickers, mode="outliers"):
        row = result.to_dict() | {
            "data_mode": "live_scan",
            "selected_provider": provider_name,
            "provider_is_live_capable": provider_name == "real",
            "is_report_only": False,
            "report_snapshot_selected": False,
        }
        row.update(build_price_sanity_from_row(row, reference_date=analysis_date or date.today(), scan_generated_at=generated_at))
        rows.append(row)
    decisions = {
        str(row.get("ticker") or "").upper(): row
        for row in build_unified_decisions(
            rows,
            scan_generated_at=generated_at,
            validation_context=build_validation_context(),
            reference_date=analysis_date or date.today(),
            preferred_lane="Outlier",
        )
    }
    latest_report_path = find_latest_report(Path("outputs"))
    latest_report = load_dashboard_report(latest_report_path) if latest_report_path else None
    latest_report_rows = {
        str(row.get("ticker") or "").upper(): row
        for row in (latest_report.results if latest_report else [])
    }
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "provider": provider_name,
        "demo_mode": provider_name == "sample",
        "analysis_date": (analysis_date or date.today()).isoformat(),
        "items": [
            {
                "ticker": ticker,
                "live_quote": row.get("quote_price_if_available", "unavailable"),
                "latest_historical_close": row.get("latest_available_close", "unavailable"),
                "scanner_current_price": row.get("current_price", "unavailable"),
                "decision_displayed_price": row.get("displayed_price", row.get("current_price", "unavailable")),
                "entry": decisions.get(ticker, {}).get("entry_zone", "unavailable"),
                "stop_loss": decisions.get(ticker, {}).get("stop_loss", "unavailable"),
                "tp1": decisions.get(ticker, {}).get("tp1", "unavailable"),
                "tp2": decisions.get(ticker, {}).get("tp2", "unavailable"),
                "provider": row.get("provider"),
                "latest_market_date": row.get("last_market_date", "unavailable"),
                "last_scan_timestamp": generated_at,
                "is_sample": row.get("is_sample_data", False),
                "is_replay": row.get("is_replay", False),
                "is_report_only": row.get("is_report_only", False),
                "stale_flag": row.get("is_stale", False),
                "split_mismatch_flag": row.get("possible_split_adjustment_mismatch", False),
                "validation_status": row.get("price_validation_status", "FAIL"),
                "validation_reason": row.get("price_validation_reason", "unavailable"),
                "source_file_report": str(latest_report_path) if ticker in latest_report_rows and latest_report_path else "unavailable",
            }
            for ticker, row in ((str(row.get("ticker") or "").upper(), row) for row in rows)
        ],
    }
    json_path = output_dir / "price_debug_report.json"
    md_path = output_dir / "price_debug_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_price_debug_markdown(payload), encoding="utf-8")
    payload["json_path"] = str(json_path)
    payload["markdown_path"] = str(md_path)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def build_provider(*, provider_name: str, history_period: str, analysis_date: date):
    if provider_name == "sample":
        return SampleMarketDataProvider(end_date=analysis_date)
    if provider_name == "local":
        raise ProviderConfigurationError("Local provider is not supported by price-debug without explicit data-dir support.")
    return YFinanceMarketDataProvider(history_period=history_period)


def _enrich_report_row(
    row: dict[str, Any],
    *,
    generated_at: str,
    reference_date: date,
    report_path: Path,
) -> dict[str, Any]:
    enriched = dict(row) | {
        "data_mode": "report_snapshot",
        "is_report_only": True,
        "report_snapshot_selected": False,
        "report_source_path": str(report_path),
        "provider_is_live_capable": str(row.get("provider") or row.get("provider_name") or "") == "real",
    }
    enriched.update(build_price_sanity_from_row(enriched, reference_date=reference_date, scan_generated_at=generated_at))
    return enriched


def _lineage_item(
    *,
    ticker: str,
    row: dict[str, Any] | None,
    decision: dict[str, Any] | None,
) -> dict[str, Any]:
    row = row or {}
    decision = decision or {}
    return {
        "ticker": ticker,
        "displayed_price": row.get("current_price", "unavailable"),
        "displayed_entry": decision.get("entry_zone", row.get("entry_zone", "unavailable")),
        "displayed_stop": decision.get("stop_loss", row.get("stop_loss_reference", "unavailable")),
        "displayed_tp1": decision.get("tp1", row.get("tp1", "unavailable")),
        "displayed_tp2": decision.get("tp2", row.get("tp2", "unavailable")),
        "source_endpoint": "/api/reports/latest",
        "source_file": row.get("report_source_path", "unavailable"),
        "provider": row.get("provider", row.get("provider_name", "unavailable")),
        "quote_price": row.get("quote_price_if_available", "unavailable"),
        "latest_close": row.get("latest_available_close", "unavailable"),
        "validated_price": row.get("validated_price", "unavailable"),
        "latest_market_date": row.get("last_market_date", "unavailable"),
        "scan_timestamp": row.get("price_timestamp", "unavailable"),
        "is_sample": row.get("is_sample_data", False),
        "is_replay": row.get("is_replay", False),
        "is_case_study": row.get("is_case_study", False),
        "is_stale": row.get("is_stale", False),
        "is_split_adjusted": row.get("is_adjusted_price", False),
        "frontend_page": "Home / Decision Cockpit",
        "primary_action": decision.get("primary_action", "unavailable"),
        "price_validation_status": row.get("price_validation_status", "FAIL"),
        "price_validation_reason": row.get("price_validation_reason", "unavailable"),
    }


def _lineage_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Price Lineage Report",
        "",
        f"- Generated: {payload.get('generated_at', 'unavailable')}",
        f"- Available: {payload.get('available', False)}",
        f"- Source endpoint: `{payload.get('source_endpoint', 'unavailable')}`",
        f"- Source file: `{payload.get('source_file', 'unavailable')}`",
        "",
    ]
    for item in payload.get("items", []):
        lines.extend(
            [
                f"## {item.get('ticker')}",
                f"- displayed price: {item.get('displayed_price')}",
                f"- displayed entry: {item.get('displayed_entry')}",
                f"- displayed stop: {item.get('displayed_stop')}",
                f"- displayed TP1 / TP2: {item.get('displayed_tp1')} / {item.get('displayed_tp2')}",
                f"- provider: {item.get('provider')}",
                f"- quote / latest close / validated: {item.get('quote_price')} / {item.get('latest_close')} / {item.get('validated_price')}",
                f"- latest market date: {item.get('latest_market_date')}",
                f"- sample / replay / case study / stale: {item.get('is_sample')} / {item.get('is_replay')} / {item.get('is_case_study')} / {item.get('is_stale')}",
                f"- validation: {item.get('price_validation_status')} | {item.get('price_validation_reason')}",
                "",
            ]
        )
    return "\n".join(lines)


def _price_debug_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Price Debug Report",
        "",
        f"- Generated: {payload.get('generated_at', 'unavailable')}",
        f"- Provider: {payload.get('provider', 'unavailable')}",
        f"- Demo mode: {payload.get('demo_mode', False)}",
        "",
    ]
    if payload.get("demo_mode"):
        lines.append("Demo sample data — not real prices.")
        lines.append("")
    for item in payload.get("items", []):
        lines.extend(
            [
                f"## {item.get('ticker')}",
                f"- live quote: {item.get('live_quote')}",
                f"- latest historical close: {item.get('latest_historical_close')}",
                f"- scanner current price: {item.get('scanner_current_price')}",
                f"- decision displayed price: {item.get('decision_displayed_price')}",
                f"- entry / stop / TP1 / TP2: {item.get('entry')} / {item.get('stop_loss')} / {item.get('tp1')} / {item.get('tp2')}",
                f"- validation: {item.get('validation_status')} | {item.get('validation_reason')}",
                f"- stale flag / split mismatch: {item.get('stale_flag')} / {item.get('split_mismatch_flag')}",
                f"- source report: {item.get('source_file_report')}",
                "",
            ]
        )
    return "\n".join(lines)
