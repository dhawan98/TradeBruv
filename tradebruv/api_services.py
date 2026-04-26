from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .automation import DEFAULT_DAILY_OUTPUT_DIR, DEFAULT_SCAN_ARCHIVE_ROOT
from .app_status import build_app_status_report, load_latest_app_status
from .decision_engine import build_unified_decision, build_unified_decisions, build_validation_context
from .cli import build_provider, load_universe
from .alternative_data import DEFAULT_ALTERNATIVE_DATA_PATH, AlternativeDataOverlayProvider, load_alternative_data_repository
from .dashboard_data import (
    build_dashboard_combined_recommendation,
    build_dashboard_data_source_status,
    build_dashboard_portfolio_summary,
    build_dashboard_validation_metrics,
    build_daily_summary,
    find_latest_report,
    load_alerts_report,
    load_daily_summary_report,
    load_dashboard_journal,
    load_dashboard_portfolio,
    load_dashboard_predictions,
    load_dashboard_report,
    run_dashboard_ai_committee,
    run_dashboard_case_study,
    run_dashboard_deep_research,
    run_dashboard_portfolio_analysis,
    run_dashboard_scan,
    upsert_dashboard_position,
)
from .env import (
    LOCAL_ENV_WARNING,
    create_local_env_from_template,
    local_env_editor_enabled,
    read_env_template,
    update_local_env,
)
from .doctor import load_latest_doctor, run_doctor
from .readiness import load_latest_readiness, run_readiness
from .replay import (
    run_famous_outlier_studies,
    run_historical_replay,
    run_investing_proof_report,
    run_investing_replay,
    run_outlier_study,
    run_portfolio_replay,
    run_proof_report,
)
from .signal_quality import load_latest_signal_quality, run_case_study, run_signal_audit
from .journal import DEFAULT_JOURNAL_PATH, add_journal_entry, journal_stats, update_journal_entry
from .portfolio import DEFAULT_PORTFOLIO_PATH, delete_position, import_portfolio_csv, save_portfolio
from .price_sanity import build_price_sanity_from_row
from .reporting import write_csv_report, write_json_report
from .validation_lab import (
    DEFAULT_PREDICTIONS_PATH,
    add_prediction,
    create_prediction_record,
    save_predictions,
    update_prediction_outcomes,
)


DEFAULT_UNIVERSE = Path("config/sample_universe.txt")
ACTIVE_CORE_UNIVERSE = Path("config/active_core_investing_universe.txt")
ACTIVE_OUTLIER_UNIVERSE = Path("config/active_outlier_universe.txt")
ACTIVE_VELOCITY_UNIVERSE = Path("config/active_velocity_universe.txt")
FAMOUS_CASE_STUDIES = Path("config/famous_outlier_case_studies.txt")


def health() -> dict[str, Any]:
    sources = data_sources()
    portfolio = portfolio_state()
    latest = reports_latest()
    return {
        "ok": True,
        "app": "TradeBruv",
        "environment": "local",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "primary_ui": "vite-react",
        "fallback_ui": "streamlit",
        "provider": latest.get("provider", "sample"),
        "mode": latest.get("mode", "outliers"),
        "last_scan_time": latest.get("generated_at", "unavailable"),
        "data_source_health": sources["summary"],
        "ai": _ai_status(sources["rows"]),
        "portfolio_value": portfolio["summary"].get("total_market_value", 0),
        "alert_count": len(alerts()),
        "local_env_editor_enabled": local_env_editor_enabled(),
        "warning": "Research support only. No broker execution or order placement.",
    }


def data_sources() -> dict[str, Any]:
    payload = build_dashboard_data_source_status()
    rows = [_safe_source_row(row) for row in payload["rows"]]
    return {
        "rows": rows,
        "summary": payload["summary"],
        "local_env_editor_enabled": local_env_editor_enabled(),
        "local_env_warning": LOCAL_ENV_WARNING,
    }


def env_template() -> dict[str, Any]:
    return read_env_template()


def create_env_template() -> dict[str, Any]:
    return create_local_env_from_template()


def update_env(values: dict[str, str]) -> dict[str, Any]:
    return update_local_env(values)


def run_scan(payload: dict[str, Any]) -> dict[str, Any]:
    provider = str(payload.get("provider") or "sample")
    mode = str(payload.get("mode") or "outliers")
    universe_path = Path(str(payload.get("universe_path") or DEFAULT_UNIVERSE))
    catalyst_file = payload.get("catalyst_file")
    analysis_date = _parse_date(payload.get("as_of_date")) or date.today()
    report = run_dashboard_scan(
        provider_name=provider,
        mode=mode,
        universe_path=universe_path,
        limit=int(payload.get("limit") or 0),
        analysis_date=analysis_date,
        data_dir=Path(str(payload["data_dir"])) if payload.get("data_dir") else None,
        catalyst_file=Path(str(catalyst_file)) if catalyst_file else None,
        alternative_data_file=Path(str(payload.get("alternative_data_file") or DEFAULT_ALTERNATIVE_DATA_PATH)),
        ai_explanations=bool(payload.get("ai_explanations", False)),
        mock_ai_explanations=bool(payload.get("mock_ai_explanations", False)),
    )
    output_dir = Path(str(payload.get("output_dir") or "outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = "velocity_scan_report" if mode == "velocity" else "outlier_scan_report" if mode == "outliers" else "scan_report"
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    validation_context = _validation_context()
    portfolio_rows = load_dashboard_portfolio(DEFAULT_PORTFOLIO_PATH)
    enriched_results = _enrich_results(report.results, generated_at=report.generated_at, reference_date=analysis_date)
    decisions = build_unified_decisions(
        enriched_results,
        portfolio_rows=portfolio_rows,
        scan_generated_at=report.generated_at,
        validation_context=validation_context,
        reference_date=analysis_date,
        preferred_lane=_preferred_lane_for_mode(mode),
    )
    result_objects = [SimpleNamespace(to_dict=lambda row=row: row) for row in enriched_results]
    write_json_report(result_objects, json_path, mode=mode)
    write_csv_report(result_objects, csv_path)
    return {
        "generated_at": report.generated_at,
        "scanner": report.scanner,
        "provider": report.provider,
        "mode": report.mode,
        "source": report.source,
        "market_regime": report.market_regime,
        "results": enriched_results,
        "summary": build_daily_summary(enriched_results),
        "decisions": decisions,
        "validation_context": validation_context,
        "json_path": str(json_path),
        "csv_path": str(csv_path),
    }


def reports_latest() -> dict[str, Any]:
    latest = find_latest_report(Path("outputs"))
    if latest is None:
        return {"available": False, "results": [], "decisions": [], "generated_at": "unavailable", "validation_context": _validation_context()}
    report = load_dashboard_report(latest)
    validation_context = _validation_context()
    enriched_results = _enrich_results(report.results, generated_at=report.generated_at)
    decisions = build_unified_decisions(
        enriched_results,
        portfolio_rows=load_dashboard_portfolio(DEFAULT_PORTFOLIO_PATH),
        scan_generated_at=report.generated_at,
        validation_context=validation_context,
        preferred_lane=_preferred_lane_for_mode(str(report.mode)),
    )
    return {
        "available": True,
        "path": str(latest),
        "generated_at": report.generated_at,
        "scanner": report.scanner,
        "provider": report.provider,
        "mode": report.mode,
        "source": report.source,
        "market_regime": report.market_regime,
        "results": enriched_results,
        "summary": build_daily_summary(enriched_results),
        "decisions": decisions,
        "validation_context": validation_context,
    }


def reports_archive() -> dict[str, Any]:
    files = sorted(DEFAULT_SCAN_ARCHIVE_ROOT.rglob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True) if DEFAULT_SCAN_ARCHIVE_ROOT.exists() else []
    return {
        "archive_root": str(DEFAULT_SCAN_ARCHIVE_ROOT),
        "reports": [
            {"path": str(path), "name": path.name, "modified_at": datetime.utcfromtimestamp(path.stat().st_mtime).isoformat() + "Z"}
            for path in files[:100]
        ],
    }


def daily_summary() -> dict[str, Any]:
    path = DEFAULT_DAILY_OUTPUT_DIR / "daily_summary.json"
    if path.exists():
        return load_daily_summary_report(path)
    latest = reports_latest()
    return {
        "available": latest.get("available", False),
        "generated_at": latest.get("generated_at", "unavailable"),
        "top_outlier_candidates": latest.get("summary", {}).get("top_outlier_candidates", []),
        "top_avoid_names": latest.get("summary", {}).get("top_avoid_names", []),
        "market_regime": latest.get("market_regime", {}),
        "markdown": "",
    }


def alerts() -> list[dict[str, Any]]:
    path = DEFAULT_DAILY_OUTPUT_DIR / "alerts.json"
    if not path.exists():
        return []
    return load_alerts_report(path).get("alerts", [])


def deep_research(payload: dict[str, Any]) -> dict[str, Any]:
    provider = _provider(payload)
    result = run_dashboard_deep_research(
        ticker=str(payload.get("ticker") or "").upper(),
        provider=provider,
        portfolio_rows=load_dashboard_portfolio(DEFAULT_PORTFOLIO_PATH),
        journal_rows=load_dashboard_journal(DEFAULT_JOURNAL_PATH),
        analysis_date=_parse_date(payload.get("as_of_date")),
    )
    scanner_row = _enrich_result_row(
        dict(result.get("scanner_row") or {}),
        generated_at=datetime.utcnow().isoformat() + "Z",
        reference_date=_parse_date(payload.get("as_of_date")) or date.today(),
    )
    validation_context = _validation_context()
    unified_decision = build_unified_decision(
        scanner_row,
        portfolio_row=next((row for row in load_dashboard_portfolio(DEFAULT_PORTFOLIO_PATH) if str(row.get("ticker", "")).upper() == scanner_row.get("ticker")), None),
        scan_generated_at=datetime.utcnow().isoformat() + "Z",
        validation_context=validation_context,
        reference_date=_parse_date(payload.get("as_of_date")) or date.today(),
        preferred_lane=_preferred_lane_from_row(scanner_row),
    )
    result["scanner_row"] = scanner_row
    result["price_sanity"] = build_price_sanity_from_row(scanner_row, reference_date=_parse_date(payload.get("as_of_date")) or date.today())
    result["unified_decision"] = unified_decision
    result["validation_context"] = validation_context
    return result


def portfolio_state() -> dict[str, Any]:
    rows = load_dashboard_portfolio(DEFAULT_PORTFOLIO_PATH)
    return {"positions": rows, "summary": build_dashboard_portfolio_summary(rows)}


def import_portfolio(payload: dict[str, Any]) -> dict[str, Any]:
    rows = [position.to_dict() for position in import_portfolio_csv(Path(str(payload["path"])), DEFAULT_PORTFOLIO_PATH)]
    return {"positions": rows, "summary": build_dashboard_portfolio_summary(rows)}


def upsert_portfolio_position(payload: dict[str, Any]) -> dict[str, Any]:
    position = upsert_dashboard_position(payload, DEFAULT_PORTFOLIO_PATH)
    return {"position": position, **portfolio_state()}


def delete_portfolio_position(ticker: str, account_name: str | None = None) -> dict[str, Any]:
    removed = delete_position(ticker=ticker, account_name=account_name, portfolio_path=DEFAULT_PORTFOLIO_PATH)
    return {"removed": removed, **portfolio_state()}


def refresh_portfolio_prices(payload: dict[str, Any]) -> dict[str, Any]:
    rows = load_dashboard_portfolio(DEFAULT_PORTFOLIO_PATH)
    provider = _provider(payload)
    from .dashboard_data import refresh_dashboard_portfolio_prices

    refreshed = refresh_dashboard_portfolio_prices(rows=rows, provider=provider)
    save_portfolio(refreshed, DEFAULT_PORTFOLIO_PATH)
    return {"positions": refreshed, "summary": build_dashboard_portfolio_summary(refreshed)}


def analyze_portfolio(payload: dict[str, Any]) -> dict[str, Any]:
    return run_dashboard_portfolio_analysis(
        rows=load_dashboard_portfolio(DEFAULT_PORTFOLIO_PATH),
        provider=_provider(payload),
        analysis_date=_parse_date(payload.get("as_of_date")),
    )


def ai_committee(payload: dict[str, Any]) -> dict[str, Any]:
    scanner_row = payload.get("scanner_row")
    if not scanner_row:
        ticker = str(payload.get("ticker") or "NVDA").upper()
        scanner_row = deep_research({"ticker": ticker, "provider": payload.get("provider", "sample")}).get("scanner_row", {})
    output = run_dashboard_ai_committee(
        scanner_row=scanner_row,
        portfolio_context=payload.get("portfolio_context"),
        mode=str(payload.get("mode") or "Mock AI for testing"),
    )
    combined = build_dashboard_combined_recommendation(
        rule_based=str(scanner_row.get("status_label", "Data Insufficient")),
        ai_output=output,
        scanner_row=scanner_row,
    )
    return {"committee": output, "combined": combined, "scanner_row": scanner_row}


def predictions() -> list[dict[str, Any]]:
    return load_dashboard_predictions(DEFAULT_PREDICTIONS_PATH)


def add_prediction_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    if "scanner_row" in payload:
        record = create_prediction_record(
            scanner_row=payload["scanner_row"],
            rule_based_recommendation=str(payload.get("rule_based_recommendation") or payload["scanner_row"].get("status_label", "Data Insufficient")),
            ai_committee_recommendation=str(payload.get("ai_committee_recommendation") or "Data Insufficient"),
            final_combined_recommendation=payload.get("final_combined_recommendation"),
            thesis=str(payload.get("thesis") or ""),
            invalidation=payload.get("invalidation"),
            tp1=payload.get("TP1") or payload.get("tp1"),
            tp2=payload.get("TP2") or payload.get("tp2"),
            expected_holding_period=str(payload.get("expected_holding_period") or ""),
            events_to_watch=payload.get("events_to_watch") or [],
            recommendation_snapshot=payload.get("recommendation_snapshot"),
            owned_at_signal=bool(payload.get("owned_at_signal", False)),
            portfolio_weight_at_signal=payload.get("portfolio_weight_at_signal", ""),
        )
    else:
        record = dict(payload)
    return add_prediction(record, DEFAULT_PREDICTIONS_PATH)


def update_predictions(payload: dict[str, Any]) -> dict[str, Any]:
    records = update_prediction_outcomes(
        records=predictions(),
        provider=_provider(payload),
        as_of_date=_parse_date(payload.get("as_of_date")),
    )
    save_predictions(records, DEFAULT_PREDICTIONS_PATH)
    return {"predictions": records, "summary": build_dashboard_validation_metrics(records)}


def predictions_summary() -> dict[str, Any]:
    return build_dashboard_validation_metrics(predictions())


def case_study(payload: dict[str, Any]) -> dict[str, Any]:
    signal_date = _parse_date(payload.get("signal_date")) or date(2021, 1, 4)
    if payload.get("write_report"):
        horizons = [int(item) for item in str(payload.get("horizons") or "5,10,20,60,120").split(",") if str(item).strip()]
        return run_case_study(ticker=str(payload.get("ticker") or "NVDA").upper(), signal_date=signal_date, horizons=horizons)
    return run_dashboard_case_study(
        ticker=str(payload.get("ticker") or "NVDA").upper(),
        provider=_provider(payload),
        signal_date=signal_date,
        end_date=_parse_date(payload.get("end_date")),
    )


def replay_run(payload: dict[str, Any]) -> dict[str, Any]:
    return run_historical_replay(
        provider=_provider({**payload, "history_period": payload.get("history_period") or "max"}),
        universe=load_universe(Path(str(payload.get("universe") or FAMOUS_CASE_STUDIES))),
        start_date=_parse_date(payload.get("start_date")) or date(2020, 1, 1),
        end_date=_parse_date(payload.get("end_date")) or date.today(),
        frequency=str(payload.get("frequency") or "weekly"),
        mode=str(payload.get("mode") or "outliers"),
        horizons=[int(item) for item in str(payload.get("horizons") or "1,5,10,20,60,120").split(",") if item.strip()],
        top_n=int(payload.get("top_n") or 20),
        output_dir=Path(str(payload.get("output_dir") or "outputs/replay")),
    )


def replay_latest(mode: str = "outliers") -> dict[str, Any]:
    base = Path("outputs/replay")
    candidates = [base / "replay_results.json"]
    if mode == "velocity":
        candidates.insert(0, base / "velocity_replay_results.json")
    for path in candidates:
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                return json.load(handle)
    return {"available": False, "summary": {}, "results": [], "point_in_time_limitations": "No replay report loaded yet."}


def investing_replay_run(payload: dict[str, Any]) -> dict[str, Any]:
    return run_investing_replay(
        provider=_provider({**payload, "history_period": payload.get("history_period") or "max"}),
        universe=load_universe(Path(str(payload.get("universe") or "config/mega_cap_universe.txt"))),
        start_date=_parse_date(payload.get("start_date")) or date(2020, 1, 1),
        end_date=_parse_date(payload.get("end_date")) or date.today(),
        frequency=str(payload.get("frequency") or "monthly"),
        horizons=[int(item) for item in str(payload.get("horizons") or "20,60,120,252").split(",") if item.strip()],
        top_n=int(payload.get("top_n") or 10),
        output_dir=Path(str(payload.get("output_dir") or "outputs/investing")),
        baselines=[item.strip().upper() for item in str(payload.get("baseline") or "SPY,QQQ").split(",") if item.strip()],
        random_baseline=bool(payload.get("random_baseline", True)),
    )


def investing_replay_latest() -> dict[str, Any]:
    path = Path("outputs/investing/investing_replay_results.json")
    if not path.exists():
        return {"available": False, "summary": {}, "results": [], "point_in_time_limitations": "No investing replay report loaded yet."}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def portfolio_replay_run(payload: dict[str, Any]) -> dict[str, Any]:
    return run_portfolio_replay(
        provider=_provider({**payload, "history_period": payload.get("history_period") or "max"}),
        universe=load_universe(Path(str(payload.get("universe") or "config/mega_cap_universe.txt"))),
        start_date=_parse_date(payload.get("start_date")) or date(2020, 1, 1),
        end_date=_parse_date(payload.get("end_date")) or date.today(),
        frequency=str(payload.get("frequency") or "monthly"),
        output_dir=Path(str(payload.get("output_dir") or "outputs/investing")),
    )


def portfolio_replay_latest() -> dict[str, Any]:
    path = Path("outputs/investing/portfolio_replay_report.json")
    if not path.exists():
        return {"available": False, "summary": {}, "results": []}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def outlier_study_run(payload: dict[str, Any]) -> dict[str, Any]:
    provider = _provider({**payload, "history_period": payload.get("history_period") or "max"})
    if payload.get("preset") == "famous":
        return run_famous_outlier_studies(provider=provider, mode=str(payload.get("mode") or "outliers"))
    return run_outlier_study(
        provider=provider,
        ticker=str(payload.get("ticker") or "GME").upper(),
        start_date=_parse_date(payload.get("start_date")) or date(2020, 8, 1),
        end_date=_parse_date(payload.get("end_date")) or date(2021, 2, 15),
        mode=str(payload.get("mode") or "outliers"),
        output_dir=Path(str(payload.get("output_dir") or "outputs/case_studies")),
    )


def proof_report_run(payload: dict[str, Any]) -> dict[str, Any]:
    return run_proof_report(
        provider=_provider({**payload, "history_period": payload.get("history_period") or "max"}),
        universe=load_universe(Path(str(payload.get("universe") or ACTIVE_OUTLIER_UNIVERSE))),
        start_date=_parse_date(payload.get("start_date")) or date(2020, 1, 1),
        end_date=_parse_date(payload.get("end_date")) or date.today(),
        include_famous_outliers=bool(payload.get("include_famous_outliers", True)),
        include_velocity=bool(payload.get("include_velocity", True)),
        baselines=[item.strip().upper() for item in str(payload.get("baseline") or "SPY,QQQ").split(",") if item.strip()],
        random_baseline=bool(payload.get("random_baseline", True)),
    )


def proof_report_latest() -> dict[str, Any]:
    path = Path("outputs/proof/proof_report.json")
    if not path.exists():
        return {"available": False, "evidence_strength": "Not enough evidence", "answers": {}}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def investing_proof_report_run(payload: dict[str, Any]) -> dict[str, Any]:
    return run_investing_proof_report(
        provider=_provider({**payload, "history_period": payload.get("history_period") or "max"}),
        universe=load_universe(Path(str(payload.get("universe") or "config/mega_cap_universe.txt"))),
        start_date=_parse_date(payload.get("start_date")) or date(2020, 1, 1),
        end_date=_parse_date(payload.get("end_date")) or date.today(),
        baselines=[item.strip().upper() for item in str(payload.get("baseline") or "SPY,QQQ").split(",") if item.strip()],
        random_baseline=bool(payload.get("random_baseline", True)),
        output_dir=Path(str(payload.get("output_dir") or "outputs/investing")),
    )


def investing_proof_report_latest() -> dict[str, Any]:
    path = Path("outputs/investing/investing_proof_report.json")
    if not path.exists():
        return {"available": False, "evidence_strength": "Not enough evidence", "answers": {}}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def journal() -> dict[str, Any]:
    rows = load_dashboard_journal(DEFAULT_JOURNAL_PATH)
    return {"entries": rows, "stats": journal_stats(rows)}


def add_journal(payload: dict[str, Any]) -> dict[str, Any]:
    entry = add_journal_entry(
        journal_path=DEFAULT_JOURNAL_PATH,
        from_report=payload.get("from_report"),
        ticker=payload.get("ticker"),
        updates=payload.get("updates") or payload,
    )
    return {"entry": entry, **journal()}


def update_journal(entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    entry = update_journal_entry(entry_id=entry_id, updates=payload, journal_path=DEFAULT_JOURNAL_PATH)
    return {"entry": entry, **journal()}


def doctor_latest() -> dict[str, Any]:
    return load_latest_doctor()


def readiness_latest() -> dict[str, Any]:
    return load_latest_readiness()


def app_status_latest() -> dict[str, Any]:
    return load_latest_app_status()


def app_status_run() -> dict[str, Any]:
    return build_app_status_report()


def doctor_run(payload: dict[str, Any]) -> dict[str, Any]:
    return run_doctor(
        live=bool(payload.get("live", False)),
        ai=str(payload.get("ai") or "none"),
        ticker=str(payload.get("ticker") or "NVDA").upper(),
    )


def readiness_run(payload: dict[str, Any]) -> dict[str, Any]:
    raw_tickers = str(payload.get("tickers") or "NVDA,PLTR,MU,RDDT,SMCI,COIN,HOOD,ARM,CAVA,AAPL,MSFT,LLY,TSLA,AMD,AVGO")
    tickers = [ticker.strip().upper() for ticker in raw_tickers.split(",") if ticker.strip()]
    return run_readiness(
        universe=Path(str(payload.get("universe") or ACTIVE_OUTLIER_UNIVERSE)),
        provider=str(payload.get("provider") or "sample"),
        tickers=tickers,
        ai=str(payload.get("ai") or "mock"),
    )


def signal_audit_run(payload: dict[str, Any]) -> dict[str, Any]:
    baseline = [item.strip().upper() for item in str(payload.get("baseline") or "SPY,QQQ").split(",") if item.strip()]
    return run_signal_audit(
        reports_dir=Path(str(payload.get("reports_dir") or "reports/scans")),
        baseline=baseline,
        random_baseline=bool(payload.get("random_baseline", True)),
    )


def signal_audit_latest() -> dict[str, Any]:
    return load_latest_signal_quality()


def universes() -> dict[str, Any]:
    items = [
        {"label": "Active Core Investing", "path": str(ACTIVE_CORE_UNIVERSE), "description": "Quality compounders and practical portfolio research names."},
        {"label": "Active Outliers", "path": str(ACTIVE_OUTLIER_UNIVERSE), "description": "Current high-growth and high-momentum research names."},
        {"label": "Active Velocity", "path": str(ACTIVE_VELOCITY_UNIVERSE), "description": "High-volume / velocity monitor names."},
        {"label": "Mega Cap", "path": "config/mega_cap_universe.txt", "description": "Large-cap leadership basket."},
        {"label": "Momentum", "path": "config/momentum_universe.txt", "description": "Momentum-leaning universe."},
        {"label": "Famous Case Studies", "path": str(FAMOUS_CASE_STUDIES), "description": "Historical validation names only."},
    ]
    return {
        "items": [{**item, "available": Path(item["path"]).exists()} for item in items],
        "warning": "Famous Case Studies are for historical validation, not active monitoring.",
        "home_defaults": [str(ACTIVE_CORE_UNIVERSE), str(ACTIVE_OUTLIER_UNIVERSE)],
    }


def _provider(payload: dict[str, Any]):
    provider_name = str(payload.get("provider") or "sample")
    args = SimpleNamespace(
        provider=provider_name,
        data_dir=Path(str(payload["data_dir"])) if payload.get("data_dir") else None,
        history_period=str(payload.get("history_period") or "3y"),
    )
    provider = build_provider(args=args, analysis_date=_parse_date(payload.get("as_of_date")) or date.today())
    alternative_file = Path(str(payload.get("alternative_data_file") or DEFAULT_ALTERNATIVE_DATA_PATH))
    repository = load_alternative_data_repository(alternative_file)
    if repository.items_by_ticker:
        provider = AlternativeDataOverlayProvider(provider, repository)
    return provider


def _safe_source_row(row: dict[str, Any]) -> dict[str, Any]:
    safe = dict(row)
    safe["required_env_vars"] = _display_env_names(safe)
    safe["missing_env_vars_list"] = _split_env_names(safe.get("missing_env_vars"))
    safe["configured_env_vars_list"] = _split_env_names(safe.get("configured_env_vars"))
    safe["last_checked"] = safe.get("last_successful_check")
    return safe


def _display_env_names(row: dict[str, Any]) -> list[str]:
    names = _split_env_names(row.get("env_vars_needed"))
    extras = {
        "OpenAI": ["OPENAI_MODEL"],
        "Anthropic Claude": ["ANTHROPIC_MODEL"],
        "Google Gemini": ["GEMINI_MODEL"],
        "OpenRouter / OpenAI-compatible endpoint": ["TRADEBRUV_LLM_MODEL"],
    }
    return [*names, *extras.get(str(row.get("name")), [])]


def _split_env_names(value: Any) -> list[str]:
    text = str(value or "")
    if text == "none":
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _ai_status(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ai_rows = [row for row in rows if row.get("category") == "AI providers"]
    configured = [row["name"] for row in ai_rows if row.get("configured")]
    missing = {row["name"]: row.get("missing_env_vars_list", []) for row in ai_rows if not row.get("configured")}
    return {"configured": configured, "missing": missing, "any_configured": bool(configured)}


def _enrich_results(
    rows: list[dict[str, Any]],
    *,
    generated_at: str,
    reference_date: date | None = None,
) -> list[dict[str, Any]]:
    return [_enrich_result_row(row, generated_at=generated_at, reference_date=reference_date) for row in rows]


def _enrich_result_row(
    row: dict[str, Any],
    *,
    generated_at: str,
    reference_date: date | None = None,
) -> dict[str, Any]:
    enriched = dict(row)
    enriched.update(
        build_price_sanity_from_row(
            enriched,
            reference_date=reference_date or date.today(),
            scan_generated_at=generated_at,
        )
    )
    return enriched


def _validation_context() -> dict[str, Any]:
    return build_validation_context(
        investing_proof_report=investing_proof_report_latest(),
        proof_report=proof_report_latest(),
        signal_quality_report=signal_audit_latest(),
    )


def _preferred_lane_for_mode(mode: str | None) -> str | None:
    normalized = str(mode or "").strip().lower()
    if normalized in {"investing", "core", "core investing"}:
        return "Core Investing"
    if normalized in {"outliers", "outlier"}:
        return "Outlier"
    if normalized == "velocity":
        return "Velocity"
    return None


def _preferred_lane_from_row(row: dict[str, Any]) -> str | None:
    velocity_score = _to_float(row.get("velocity_score"))
    outlier_score = _to_float(row.get("outlier_score"))
    investing_score = _to_float(row.get("regular_investing_score"))
    if velocity_score >= max(outlier_score, investing_score) and velocity_score > 0:
        return "Velocity"
    if outlier_score >= max(velocity_score, investing_score) and outlier_score > 0:
        return "Outlier"
    if investing_score > 0:
        return "Core Investing"
    return None


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
