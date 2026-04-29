from __future__ import annotations

import json
from pathlib import Path

from tradebruv.cli import main


def test_price_debug_command_creates_reports(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "outputs" / "debug"

    result = main(
        [
            "price-debug",
            "--tickers",
            "NVDA,PLTR,MU,COIN,RDDT",
            "--provider",
            "sample",
            "--as-of-date",
            "2026-04-24",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert result == 0
    debug_json = output_dir / "price_debug_report.json"
    debug_md = output_dir / "price_debug_report.md"
    lineage_json = output_dir / "price_lineage_report.json"
    lineage_md = output_dir / "price_lineage_report.md"
    assert debug_json.exists()
    assert debug_md.exists()
    assert lineage_json.exists()
    assert lineage_md.exists()

    payload = json.loads(debug_json.read_text(encoding="utf-8"))
    assert payload["demo_mode"] is True
    assert len(payload["items"]) == 5
    assert all(item["validation_status"] == "FAIL" for item in payload["items"])


def test_decision_today_sample_provider_stays_demo_only(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "active_core_investing_universe.txt").write_text("MSFT\nAAPL\n", encoding="utf-8")
    (config_dir / "active_outlier_universe.txt").write_text("NVDA\nPLTR\n", encoding="utf-8")
    (config_dir / "active_velocity_universe.txt").write_text("MU\nRIVN\n", encoding="utf-8")
    output_dir = tmp_path / "outputs" / "daily"

    result = main(
        [
            "decision-today",
            "--provider",
            "sample",
            "--core-universe",
            str(config_dir / "active_core_investing_universe.txt"),
            "--outlier-universe",
            str(config_dir / "active_outlier_universe.txt"),
            "--velocity-universe",
            str(config_dir / "active_velocity_universe.txt"),
            "--as-of-date",
            "2026-04-24",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert result == 0
    payload = json.loads((output_dir / "decision_today.json").read_text(encoding="utf-8"))
    assert payload["demo_mode"] is True
    assert payload["report_snapshot"] is False
    assert payload["decisions"]
    assert all(row["price_validation_status"] == "FAIL" for row in payload["decisions"])
    assert all(row["primary_action"] == "Data Insufficient" for row in payload["decisions"])
