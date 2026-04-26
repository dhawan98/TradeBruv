from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tradebruv.automation import (
    archive_scan_report,
    build_daily_summary_markdown,
    build_daily_summary_payload,
    filter_alerts,
    generate_alerts,
    load_watchlist_state,
    save_watchlist_state,
    summarize_watchlist_changes,
    update_watchlist_state,
    write_alerts_csv,
    write_alerts_json,
    write_daily_summary_json,
    write_daily_summary_markdown,
)
from tradebruv.dashboard_data import (
    build_daily_brief_view,
    build_watchlist_change_summary,
    filter_dashboard_alerts,
    load_alerts_report,
    load_daily_summary_report,
)
from tests.helpers import sample_outlier_results


TIMESTAMP = "2026-04-24T13:30:00Z"
SCAN_ID = "20260424T133000Z_outliers_sample"


def row(
    ticker: str = "NVDA",
    *,
    status: str = "Watch Only",
    winner: int = 70,
    outlier: int = 70,
    risk: int = 20,
    setup: int = 60,
    price: float = 100,
    entry_zone: str = "99 - 101",
    invalidation: float = 90,
    tp1: float = 110,
    tp2: float = 120,
    warnings: list[str] | None = None,
    catalyst_quality: str = "Narrative Supported",
    hype_risk: bool = False,
    pump_risk: bool = False,
) -> dict:
    return {
        "ticker": ticker,
        "company_name": ticker,
        "status_label": status,
        "strategy_label": "Breakout Momentum",
        "outlier_type": "Long-Term Monster",
        "winner_score": winner,
        "outlier_score": outlier,
        "risk_score": risk,
        "setup_quality_score": setup,
        "current_price": price,
        "entry_zone": entry_zone,
        "invalidation_level": invalidation,
        "tp1": tp1,
        "tp2": tp2,
        "warnings": warnings or [],
        "theme_tags": ["AI"],
        "catalyst_quality": catalyst_quality,
        "hype_risk": hype_risk,
        "pump_risk": pump_risk,
        "ai_explanation_available": False,
    }


def changes(previous_row: dict | None, current_row: dict | None):
    previous_state = {"version": 1, "tickers": {}}
    if previous_row:
        state, _ = update_watchlist_state(
            previous_state=previous_state,
            rows=[previous_row],
            scan_id="old",
            timestamp="2026-04-23T13:30:00Z",
        )
        previous_state = state
    rows = [current_row] if current_row else []
    _, result = update_watchlist_state(
        previous_state=previous_state,
        rows=rows,
        scan_id=SCAN_ID,
        timestamp=TIMESTAMP,
    )
    return result


class Pass5DailyTests(unittest.TestCase):
    def test_scan_archive_naming_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = sample_outlier_results()["NVDA"]
            archive = archive_scan_report(
                results=[result],
                provider="sample",
                mode="outliers",
                universe_file=Path("config/active_outlier_universe.txt"),
                catalyst_file=Path("config/catalysts_watchlist.csv"),
                ai_enabled=False,
                command_used="python3 -m tradebruv scan --archive",
                archive_root=Path(temp_dir),
                created_at=datetime(2026, 4, 24, 9, 30, 0),
            )
            payload = json.loads(archive["json_path"].read_text(encoding="utf-8"))
            self.assertTrue(str(archive["json_path"]).endswith("2026-04-24/scan_outliers_sample_093000.json"))
            self.assertTrue(str(archive["csv_path"]).endswith("2026-04-24/scan_outliers_sample_093000.csv"))
            self.assertEqual(payload["metadata"]["scan_id"], archive["scan_id"])
            self.assertEqual(payload["metadata"]["provider"], "sample")
            self.assertEqual(payload["metadata"]["result_count"], 1)

    def test_watchlist_state_creation_and_update_carries_previous_fields(self) -> None:
        empty = load_watchlist_state(Path("/tmp/nonexistent_tradebruv_state.json"))
        state, _ = update_watchlist_state(previous_state=empty, rows=[row(status="Watch Only", winner=60)], scan_id="old", timestamp="old_time")
        new_state, change = update_watchlist_state(
            previous_state=state,
            rows=[row(status="Active Setup", winner=82)],
            scan_id=SCAN_ID,
            timestamp=TIMESTAMP,
        )
        self.assertEqual(new_state["tickers"]["NVDA"]["previous_status"], "Watch Only")
        self.assertEqual(new_state["tickers"]["NVDA"]["current_status"], "Active Setup")
        self.assertEqual(new_state["tickers"]["NVDA"]["previous_winner_score"], 60)
        self.assertEqual(change["NVDA"]["previous"]["current_status"], "Watch Only")

    def test_status_upgrade_and_downgrade_detection(self) -> None:
        alerts = generate_alerts(changes=changes(row(status="Watch Only"), row(status="Trade Setup Forming")), source_scan_id=SCAN_ID, timestamp=TIMESTAMP)
        self.assertTrue(any(alert["alert_type"] == "Watch Only upgraded to Trade Setup Forming" for alert in alerts))
        alerts = generate_alerts(changes=changes(row(status="Active Setup"), row(status="Avoid")), source_scan_id=SCAN_ID, timestamp=TIMESTAMP)
        self.assertTrue(any(alert["alert_type"] == "Status downgraded to Avoid" for alert in alerts))
        self.assertTrue(any(alert["alert_type"] == "Breakout failed" for alert in alerts))

    def test_score_threshold_crossing(self) -> None:
        alerts = generate_alerts(
            changes=changes(row(winner=75, outlier=79), row(winner=81, outlier=85)),
            source_scan_id=SCAN_ID,
            timestamp=TIMESTAMP,
        )
        self.assertTrue(any(alert["alert_type"] == "Outlier Score crossed threshold" for alert in alerts))
        self.assertTrue(any(alert["alert_type"] == "Winner Score crossed threshold" for alert in alerts))

    def test_entry_zone_tp_and_invalidation_alerts(self) -> None:
        alerts = generate_alerts(
            changes=changes(row(price=95), row(price=100)),
            source_scan_id=SCAN_ID,
            timestamp=TIMESTAMP,
        )
        self.assertTrue(any(alert["alert_type"] == "Price entered entry zone" for alert in alerts))
        alerts = generate_alerts(changes=changes(row(price=100), row(price=112)), source_scan_id=SCAN_ID, timestamp=TIMESTAMP)
        self.assertTrue(any(alert["alert_type"] == "TP1 reached" for alert in alerts))
        alerts = generate_alerts(changes=changes(row(price=100), row(price=88)), source_scan_id=SCAN_ID, timestamp=TIMESTAMP)
        self.assertTrue(any(alert["alert_type"] == "Setup invalidated" for alert in alerts))
        self.assertTrue(any(alert["alert_type"] == "Stop/invalidation hit" for alert in alerts))

    def test_hype_pump_and_missing_data_alerts(self) -> None:
        alerts = generate_alerts(
            changes=changes(None, row(warnings=["Headline attention looks hype-driven."], hype_risk=True)),
            source_scan_id=SCAN_ID,
            timestamp=TIMESTAMP,
        )
        self.assertTrue(any(alert["alert_type"] == "Hype/pump warning appeared" for alert in alerts))
        self.assertTrue(any(alert["alert_type"] == "Social-only hype without price confirmation" for alert in alerts))
        alerts = generate_alerts(
            changes=changes(None, row(status="Avoid", warnings=["Data fetch failed for AAPL: missing"])),
            source_scan_id=SCAN_ID,
            timestamp=TIMESTAMP,
        )
        self.assertTrue(any(alert["alert_type"] == "Ticker missing data" for alert in alerts))
        self.assertTrue(any(alert["alert_type"] == "Data provider failed for ticker" for alert in alerts))

    def test_daily_summary_and_markdown_outputs(self) -> None:
        alerts = generate_alerts(changes=changes(row(winner=75, outlier=79), row(winner=81, outlier=85)), source_scan_id=SCAN_ID, timestamp=TIMESTAMP)
        payload = build_daily_summary_payload(
            rows=[row(status="Active Setup", winner=81, outlier=85), row("BAD", status="Avoid", risk=95)],
            alerts=alerts,
            scan_metadata={"scan_id": SCAN_ID, "provider": "sample", "mode": "outliers"},
            market_regime={"regime": "Bullish", "summary": "SPY and QQQ uptrend."},
        )
        markdown = build_daily_summary_markdown(payload)
        self.assertIn("Top Outlier Candidates", markdown)
        self.assertIn("Deterministic research prompts", markdown)
        self.assertEqual(payload["top_avoid_names"][0]["ticker"], "BAD")

    def test_alerts_and_summary_file_outputs(self) -> None:
        alerts = generate_alerts(changes=changes(None, row(status="Active Setup")), source_scan_id=SCAN_ID, timestamp=TIMESTAMP)
        payload = build_daily_summary_payload(rows=[row(status="Active Setup")], alerts=alerts, scan_metadata={"scan_id": SCAN_ID})
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            alerts_json = write_alerts_json(alerts, root / "alerts.json")
            alerts_csv = write_alerts_csv(alerts, root / "alerts.csv")
            summary_json = write_daily_summary_json(payload, root / "daily_summary.json")
            summary_md = write_daily_summary_markdown(payload, root / "daily_summary.md")
            self.assertTrue(alerts_json.exists())
            self.assertTrue(alerts_csv.exists())
            self.assertTrue(summary_json.exists())
            self.assertTrue(summary_md.exists())
            self.assertTrue(load_alerts_report(alerts_json)["alerts"])
            self.assertEqual(load_daily_summary_report(summary_json)["scan_metadata"]["scan_id"], SCAN_ID)

    def test_dashboard_alert_filtering_and_watchlist_transformations(self) -> None:
        alerts = [
            {"ticker": "NVDA", "severity": "Important", "alert_type": "Winner Score crossed threshold", "category": "Opportunity", "deterministic_reason": "winner_score_crossed_80"},
            {"ticker": "BAD", "severity": "Critical", "alert_type": "Status downgraded to Avoid", "category": "Risk", "deterministic_reason": "status_downgraded_to_avoid"},
        ]
        filtered = filter_dashboard_alerts(alerts, {"severity": ["Critical"]})
        changes_summary = build_watchlist_change_summary(alerts)
        direct_summary = summarize_watchlist_changes(alerts)
        brief = build_daily_brief_view({"top_outlier_candidates": [{"ticker": "NVDA"}], "top_avoid_names": []}, alerts)
        self.assertEqual(filtered[0]["ticker"], "BAD")
        self.assertTrue(changes_summary["score_changes"])
        self.assertTrue(direct_summary["risk_changes"])
        self.assertEqual(brief["top_candidates"][0]["ticker"], "NVDA")

    def test_state_save_is_inspectable_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "watchlist_state.json"
            state, _ = update_watchlist_state(previous_state={"version": 1, "tickers": {}}, rows=[row()], scan_id=SCAN_ID, timestamp=TIMESTAMP)
            save_watchlist_state(state, path)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["tickers"]["NVDA"]["current_status"], "Watch Only")


if __name__ == "__main__":
    unittest.main()
