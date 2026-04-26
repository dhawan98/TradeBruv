from __future__ import annotations

from typing import Any

from .env import load_local_env

load_local_env()

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware
except ImportError as exc:  # pragma: no cover - exercised by CLI users without api extras
    FastAPI = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

from . import api_services as services


def create_app() -> "FastAPI":
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Install API dependencies with: python3 -m pip install '.[api]'") from _IMPORT_ERROR
    app = FastAPI(title="TradeBruv API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:5175",
            "http://127.0.0.1:5175",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return services.health()

    @app.get("/api/data-sources")
    def data_sources() -> dict[str, Any]:
        return services.data_sources()

    @app.get("/api/universes")
    def universes() -> dict[str, Any]:
        return services.universes()

    @app.get("/api/env-template")
    def env_template() -> dict[str, Any]:
        return services.env_template()

    @app.post("/api/env/create-template")
    def create_env_template() -> dict[str, Any]:
        try:
            return services.create_env_template()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/env/update-local")
    def update_env(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return services.update_env({str(key): str(value) for key, value in (payload.get("values") or payload).items()})
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/api/scan")
    def scan(payload: dict[str, Any]) -> dict[str, Any]:
        return services.run_scan(payload)

    @app.get("/api/reports/latest")
    def reports_latest() -> dict[str, Any]:
        return services.reports_latest()

    @app.get("/api/reports/archive")
    def reports_archive() -> dict[str, Any]:
        return services.reports_archive()

    @app.get("/api/daily-summary")
    def daily_summary() -> dict[str, Any]:
        return services.daily_summary()

    @app.get("/api/alerts")
    def alerts() -> list[dict[str, Any]]:
        return services.alerts()

    @app.post("/api/deep-research")
    def deep_research(payload: dict[str, Any]) -> dict[str, Any]:
        return services.deep_research(payload)

    @app.get("/api/portfolio")
    def portfolio() -> dict[str, Any]:
        return services.portfolio_state()

    @app.post("/api/portfolio/import")
    def portfolio_import(payload: dict[str, Any]) -> dict[str, Any]:
        return services.import_portfolio(payload)

    @app.post("/api/portfolio/positions")
    def portfolio_position(payload: dict[str, Any]) -> dict[str, Any]:
        return services.upsert_portfolio_position(payload)

    @app.put("/api/portfolio/positions/{ticker}")
    def portfolio_position_update(ticker: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload["ticker"] = ticker
        return services.upsert_portfolio_position(payload)

    @app.delete("/api/portfolio/positions/{ticker}")
    def portfolio_position_delete(ticker: str, account_name: str | None = Query(default=None)) -> dict[str, Any]:
        return services.delete_portfolio_position(ticker, account_name)

    @app.post("/api/portfolio/refresh-prices")
    def portfolio_refresh(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return services.refresh_portfolio_prices(payload or {})

    @app.post("/api/portfolio/analyze")
    def portfolio_analyze(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return services.analyze_portfolio(payload or {})

    @app.post("/api/ai-committee")
    def ai_committee(payload: dict[str, Any]) -> dict[str, Any]:
        return services.ai_committee(payload)

    @app.get("/api/predictions")
    def predictions() -> list[dict[str, Any]]:
        return services.predictions()

    @app.post("/api/predictions")
    def prediction_add(payload: dict[str, Any]) -> dict[str, Any]:
        return services.add_prediction_endpoint(payload)

    @app.post("/api/predictions/update")
    def prediction_update(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return services.update_predictions(payload or {})

    @app.get("/api/predictions/summary")
    def prediction_summary() -> dict[str, Any]:
        return services.predictions_summary()

    @app.post("/api/case-study")
    def case_study(payload: dict[str, Any]) -> dict[str, Any]:
        return services.case_study(payload)

    @app.post("/api/replay/run")
    def replay_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return services.replay_run(payload or {})

    @app.get("/api/replay/latest")
    def replay_latest(mode: str = Query(default="outliers")) -> dict[str, Any]:
        return services.replay_latest(mode=mode)

    @app.post("/api/investing-replay/run")
    def investing_replay_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return services.investing_replay_run(payload or {})

    @app.get("/api/investing-replay/latest")
    def investing_replay_latest() -> dict[str, Any]:
        return services.investing_replay_latest()

    @app.post("/api/portfolio-replay/run")
    def portfolio_replay_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return services.portfolio_replay_run(payload or {})

    @app.get("/api/portfolio-replay/latest")
    def portfolio_replay_latest() -> dict[str, Any]:
        return services.portfolio_replay_latest()

    @app.post("/api/outlier-study/run")
    def outlier_study_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return services.outlier_study_run(payload or {})

    @app.post("/api/proof-report/run")
    def proof_report_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return services.proof_report_run(payload or {})

    @app.get("/api/proof-report/latest")
    def proof_report_latest() -> dict[str, Any]:
        return services.proof_report_latest()

    @app.post("/api/investing-proof-report/run")
    def investing_proof_report_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return services.investing_proof_report_run(payload or {})

    @app.get("/api/investing-proof-report/latest")
    def investing_proof_report_latest() -> dict[str, Any]:
        return services.investing_proof_report_latest()

    @app.get("/api/journal")
    def journal() -> dict[str, Any]:
        return services.journal()

    @app.post("/api/journal")
    def journal_add(payload: dict[str, Any]) -> dict[str, Any]:
        return services.add_journal(payload)

    @app.put("/api/journal/{entry_id}")
    def journal_update(entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return services.update_journal(entry_id, payload)

    @app.get("/api/doctor/latest")
    def doctor_latest() -> dict[str, Any]:
        return services.doctor_latest()

    @app.post("/api/doctor/run")
    def doctor_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return services.doctor_run(payload or {})

    @app.get("/api/readiness/latest")
    def readiness_latest() -> dict[str, Any]:
        return services.readiness_latest()

    @app.post("/api/readiness/run")
    def readiness_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return services.readiness_run(payload or {})

    @app.get("/api/app-status/latest")
    def app_status_latest() -> dict[str, Any]:
        return services.app_status_latest()

    @app.post("/api/app-status/run")
    def app_status_run() -> dict[str, Any]:
        return services.app_status_run()

    @app.get("/api/signal-audit/latest")
    def signal_audit_latest() -> dict[str, Any]:
        return services.signal_audit_latest()

    @app.post("/api/signal-audit/run")
    def signal_audit_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return services.signal_audit_run(payload or {})

    return app


app = create_app()


def main() -> int:
    if uvicorn is None:
        raise RuntimeError("Uvicorn is not installed. Install API dependencies with: python3 -m pip install '.[api]'")
    uvicorn.run("tradebruv.api:app", host="127.0.0.1", port=8000, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
