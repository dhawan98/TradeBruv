from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from .data_sources import build_data_source_status, secret_values_present_in_text
from .env import load_local_env
from .external_sources import cheap_provider_statuses
from .providers import ProviderConfigurationError, YFinanceMarketDataProvider


DEFAULT_DOCTOR_JSON = Path("outputs/doctor_report.json")
DEFAULT_DOCTOR_MD = Path("outputs/doctor_report.md")


def run_doctor(*, live: bool = False, ai: str = "none", ticker: str = "NVDA", output_dir: Path = Path("outputs")) -> dict[str, Any]:
    load_local_env()
    output_dir.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []
    checks.append(_check_imports())
    checks.append(_check_writable(Path(os.getenv("TRADEBRUV_OUTPUT_DIR", str(output_dir))), "output directory"))
    checks.append(_check_writable(Path(os.getenv("TRADEBRUV_DATA_DIR", "data")), "data directory"))
    checks.append(_check_env_loaded())
    checks.append(_check_git_ignores_env())
    checks.append(_check_yfinance(live=live, ticker=ticker))
    checks.extend(_check_ai(ai=ai, live=live))
    checks.extend(cheap_provider_statuses(live=live, ticker=ticker))
    checks.append(_check_http("Backend API", "http://127.0.0.1:8000/api/health", live=True))
    checks.append(_check_http("Frontend", "http://127.0.0.1:5173/", live=True))
    checks.append(_check_data_sources())

    report = {
        "available": True,
        "kind": "doctor",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "mode": "live" if live else "config-only",
        "requested_ai": ai,
        "ticker": ticker.upper(),
        "summary": _summarize_checks(checks),
        "checks": checks,
        "secret_leak_check": "PASS",
        "notes": [
            "Doctor is a readiness and connectivity check, not a profitability claim.",
            "Live tests only run when requested and when relevant keys are configured.",
        ],
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    leaked = secret_values_present_in_text(text)
    if leaked:
        report["secret_leak_check"] = "FAIL"
        report["secret_leak_env_vars"] = leaked
    json_path = output_dir / "doctor_report.json"
    md_path = output_dir / "doctor_report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_doctor_markdown(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["markdown_path"] = str(md_path)
    return report


def load_latest_doctor(path: Path = DEFAULT_DOCTOR_JSON) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "status": "not_run", "message": "Doctor has not run yet."}
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["available"] = True
    return payload


def _check_imports() -> dict[str, Any]:
    try:
        import fastapi  # noqa: F401
        import pandas  # noqa: F401
        import yfinance  # noqa: F401

        return _row("Python/package imports", "PASS", "config-only", "FastAPI, pandas, and yfinance imports succeeded.")
    except ImportError as exc:
        return _row("Python/package imports", "FAIL", "config-only", f"Import failed: {exc}")


def _check_writable(path: Path, label: str) -> dict[str, Any]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".tradebruv_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return _row(label, "PASS", "config-only", f"{path} is writable.", {"path": str(path)})
    except OSError as exc:
        return _row(label, "FAIL", "config-only", f"{path} is not writable: {exc}", {"path": str(path)})


def _check_env_loaded() -> dict[str, Any]:
    path = Path(".env")
    return _row(".env loaded status", "PASS" if path.exists() else "WARN", "config-only", ".env exists and was loaded if python-dotenv is available." if path.exists() else ".env is absent; app continues with shell/default environment.")


def _check_git_ignores_env() -> dict[str, Any]:
    try:
        result = subprocess.run(["git", "check-ignore", ".env"], check=False, capture_output=True, text=True, timeout=10)
        ok = result.returncode == 0
        return _row(".env git ignore", "PASS" if ok else "FAIL", "config-only", ".env is ignored by git." if ok else ".env is not ignored by git.")
    except (OSError, subprocess.SubprocessError) as exc:
        return _row(".env git ignore", "WARN", "config-only", f"Could not verify git ignore status: {exc}")


def _check_yfinance(*, live: bool, ticker: str) -> dict[str, Any]:
    if not live:
        return _row("yfinance ticker fetch", "SKIPPED", "config-only", "Live yfinance fetch skipped; run doctor --live to test it.")
    try:
        provider = YFinanceMarketDataProvider(history_period="6mo")
        security = provider.get_security(ticker.upper())
        price = security.current_price
        status = "PASS" if price and price > 0 else "WARN"
        return _row("yfinance ticker fetch", status, "live", f"Fetched {ticker.upper()} with current_price={price or 'unavailable'}.", {"ticker": ticker.upper(), "price_available": bool(price)})
    except (ProviderConfigurationError, Exception) as exc:  # noqa: BLE001 - doctor must continue
        return _row("yfinance ticker fetch", "FAIL", "live", f"yfinance fetch failed: {exc}")


def _check_ai(*, ai: str, live: bool) -> list[dict[str, Any]]:
    checks = [
        _row("OpenAI key configured", "PASS" if os.getenv("OPENAI_API_KEY") else "WARN", "config-only", "OPENAI_API_KEY configured." if os.getenv("OPENAI_API_KEY") else "OPENAI_API_KEY missing."),
        _row("Gemini key configured", "PASS" if os.getenv("GEMINI_API_KEY") else "WARN", "config-only", "GEMINI_API_KEY configured." if os.getenv("GEMINI_API_KEY") else "GEMINI_API_KEY missing."),
    ]
    selected = ai.lower()
    if live and selected == "openai" and os.getenv("OPENAI_API_KEY"):
        checks.append(_openai_live_check())
    elif selected == "openai":
        checks.append(_row("OpenAI one-shot structured response", "SKIPPED", "config-only", "OpenAI live test skipped or key missing."))
    if live and selected == "gemini" and os.getenv("GEMINI_API_KEY"):
        checks.append(_gemini_live_check())
    elif selected == "gemini":
        checks.append(_row("Gemini one-shot structured response", "SKIPPED", "config-only", "Gemini live test skipped or key missing."))
    return checks


def _openai_live_check() -> dict[str, Any]:
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": "{\"status\":\"ok\",\"purpose\":\"TradeBruv doctor\"}"},
        ],
    }
    url = f"{os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/')}/chat/completions"
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            ok = response.status < 400
        return _row("OpenAI one-shot structured response", "PASS" if ok else "WARN", "live", "OpenAI live structured response check completed.")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return _row("OpenAI one-shot structured response", "FAIL", "live", f"OpenAI live check failed: {exc}")


def _gemini_live_check() -> dict[str, Any]:
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={os.getenv('GEMINI_API_KEY')}"
    payload = {"contents": [{"parts": [{"text": "Return JSON with status ok for a TradeBruv doctor connectivity check."}]}]}
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            ok = response.status < 400
        return _row("Gemini one-shot structured response", "PASS" if ok else "WARN", "live", "Gemini live response check completed.")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return _row("Gemini one-shot structured response", "FAIL", "live", f"Gemini live check failed: {exc}")


def _check_http(name: str, url: str, *, live: bool) -> dict[str, Any]:
    if not live:
        return _row(name, "SKIPPED", "config-only", "HTTP health check skipped.")
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            ok = response.status < 400
        return _row(name, "PASS" if ok else "WARN", "local", f"{url} returned HTTP {response.status}.")
    except (urllib.error.URLError, TimeoutError) as exc:
        return _row(name, "WARN", "local", f"{url} was not reachable: {exc}")


def _check_data_sources() -> dict[str, Any]:
    rows = build_data_source_status()
    configured = sum(1 for row in rows if row["configured"])
    return _row("data-source env status", "PASS", "config-only", f"{configured}/{len(rows)} providers configured or no-key available.", {"providers": len(rows), "configured": configured})


def _summarize_checks(checks: list[dict[str, Any]]) -> dict[str, int]:
    statuses = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIPPED": 0}
    for check in checks:
        status = str(check.get("status", "WARN"))
        statuses[status] = statuses.get(status, 0) + 1
    return statuses


def _row(name: str, status: str, mode: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "mode": mode,
        "message": message,
        "details": details or {},
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }


def _doctor_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# TradeBruv Doctor Report",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Mode: {report['mode']}",
        f"- Ticker: {report['ticker']}",
        f"- Summary: {report['summary']}",
        "",
        "| Check | Status | Mode | Message |",
        "| --- | --- | --- | --- |",
    ]
    for check in report["checks"]:
        lines.append(f"| {check['name']} | {check['status']} | {check['mode']} | {str(check['message']).replace('|', '/')} |")
    lines.extend(["", "Research support only. This report does not validate profitability or prediction accuracy.", ""])
    return "\n".join(lines)
