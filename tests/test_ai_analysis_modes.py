from __future__ import annotations

import json
from pathlib import Path

import tradebruv.daily_decision as daily_decision
from tradebruv.ai_analysis import build_candidate_packet, review_candidate_packet


def _setup_universes(tmp_path: Path) -> dict[str, Path]:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    core = config_dir / "active_core_investing_universe.txt"
    outlier = config_dir / "active_outlier_universe.txt"
    velocity = config_dir / "active_velocity_universe.txt"
    tracked = config_dir / "tracked_tickers.txt"
    broad = config_dir / "universe_us_liquid_stocks.txt"
    core.write_text("MSFT\nAAPL\n", encoding="utf-8")
    outlier.write_text("NVDA\nPLTR\n", encoding="utf-8")
    velocity.write_text("MU\nCOIN\n", encoding="utf-8")
    tracked.write_text("NVDA\n", encoding="utf-8")
    broad.write_text("NVDA\nPLTR\nMU\nAAPL\nMSFT\nCOIN\n", encoding="utf-8")
    return {
        "core": core,
        "outlier": outlier,
        "velocity": velocity,
        "tracked": tracked,
        "broad": broad,
    }


def test_default_daily_decision_does_not_call_ai(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    paths = _setup_universes(tmp_path)
    called = {"review": 0, "committee": 0}
    monkeypatch.setattr(daily_decision, "review_candidates", lambda *args, **kwargs: called.__setitem__("review", called["review"] + 1))
    monkeypatch.setattr(daily_decision, "run_ai_committee", lambda *args, **kwargs: called.__setitem__("committee", called["committee"] + 1))

    payload = daily_decision.run_daily_decision(
        provider_name="sample",
        core_universe=paths["core"],
        outlier_universe=paths["outlier"],
        velocity_universe=paths["velocity"],
        broad_universe=paths["broad"],
        tracked=paths["tracked"],
        output_dir=tmp_path / "outputs" / "daily",
    )

    assert payload["analysis_mode"] == "deterministic"
    assert payload["ai_mode"] == "off"
    assert called == {"review": 0, "committee": 0}


def test_ai_review_requires_explicit_mode_and_stays_separate(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    paths = _setup_universes(tmp_path)
    captured: dict[str, object] = {}

    def fake_review(decisions: list[dict[str, object]], **kwargs: object) -> dict[str, object]:
        captured["count"] = len(decisions)
        first = str(decisions[0]["ticker"])
        return {
            "enabled": True,
            "mode": "ai_review",
            "provider": "openai",
            "model": "gpt-test",
            "names_reviewed": 1,
            "downgraded": 1,
            "caution_flags": 1,
            "top_ai_agreed_names": [],
            "names_ai_says_not_to_chase": [first],
            "unsupported_claims_detected": 0,
            "reviews_unavailable": [],
            "reviews": {
                first: {
                    "available": True,
                    "provider": "openai",
                    "model": "gpt-test",
                    "reviewed_at": "2026-05-01T00:00:00Z",
                    "ticker": first,
                    "deterministic_label": decisions[0]["actionability_label"],
                    "ai_final_view": "downgrade",
                    "ai_caution_level": "high",
                    "bull_case": "Interesting setup.",
                    "bear_case": "Too extended.",
                    "what_would_make_me_buy": "A cleaner pullback.",
                    "what_would_make_me_wait": "Wait for price compression.",
                    "what_would_make_me_avoid": "Avoid if invalidation breaks.",
                    "missing_evidence": ["fresh catalyst"],
                    "unsupported_claims": [],
                    "confidence_reasoning": "Only deterministic packet used.",
                    "deterministic_label_too_aggressive": True,
                    "deterministic_label_too_conservative": False,
                    "suggested_user_action": "avoid_chase",
                    "ai_summary_one_liner": "Interesting but extended.",
                    "unsupported_claims_detected": False,
                    "ai_guardrail_warnings": [],
                }
            },
        }

    monkeypatch.setattr(daily_decision, "review_candidates", fake_review)

    payload = daily_decision.run_daily_decision(
        provider_name="sample",
        core_universe=paths["core"],
        outlier_universe=paths["outlier"],
        velocity_universe=paths["velocity"],
        broad_universe=paths["broad"],
        tracked=paths["tracked"],
        output_dir=tmp_path / "outputs" / "daily",
        analysis_mode="ai_review",
        ai_provider="openai",
    )

    assert payload["analysis_mode"] == "ai_review"
    assert int(captured["count"]) >= 1
    reviewed = [row for row in payload["decisions"] if row.get("ai_review")]
    assert reviewed
    assert reviewed[0]["actionability_label"] != ""
    assert reviewed[0]["ai_review"]["ai_final_view"] == "downgrade"
    assert reviewed[0]["actionability_label"] == reviewed[0]["ai_review"]["deterministic_label"]


def test_ai_committee_runs_multiple_providers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    paths = _setup_universes(tmp_path)
    captured: dict[str, object] = {}

    def fake_committee(decisions: list[dict[str, object]], **kwargs: object) -> dict[str, object]:
        captured["providers"] = kwargs["providers"]
        ticker = str(decisions[0]["ticker"])
        return {
            "enabled": True,
            "mode": "ai_committee",
            "models_used": ["openai:gpt-test", "gemini:gemini-test", "anthropic:claude-test"],
            "models_failed": [],
            "consensus_candidates": [ticker],
            "disagreement_candidates": [],
            "names_all_models_like": [ticker],
            "names_all_models_warn_against": [],
            "top_ai_consensus_watchlist": [ticker],
            "committee_summary": "Consensus found.",
            "per_ticker_reviews": {
                ticker: {
                    "per_ticker_votes": {"bullish": 3, "cautious": 0, "avoid": 0, "needs_more_data": 0},
                    "committee_label": "bullish",
                    "row_review": {
                        "available": True,
                        "provider": "committee",
                        "model": "openai, gemini, anthropic",
                        "reviewed_at": "2026-05-01T00:00:00Z",
                        "ticker": ticker,
                        "deterministic_label": decisions[0]["actionability_label"],
                        "ai_final_view": "agree",
                        "ai_caution_level": "low",
                        "bull_case": "Consensus agrees.",
                        "bear_case": "Limited downside flags.",
                        "what_would_make_me_buy": "Keep confirmation intact.",
                        "what_would_make_me_wait": "Wait if confirmation weakens.",
                        "what_would_make_me_avoid": "Avoid if risk rises.",
                        "missing_evidence": [],
                        "unsupported_claims": [],
                        "confidence_reasoning": "All models saw the same packet.",
                        "deterministic_label_too_aggressive": False,
                        "deterministic_label_too_conservative": False,
                        "suggested_user_action": "watch",
                        "ai_summary_one_liner": "Committee agrees.",
                        "unsupported_claims_detected": False,
                        "ai_guardrail_warnings": [],
                    },
                }
            },
        }

    monkeypatch.setattr(daily_decision, "run_ai_committee", fake_committee)

    payload = daily_decision.run_daily_decision(
        provider_name="sample",
        core_universe=paths["core"],
        outlier_universe=paths["outlier"],
        velocity_universe=paths["velocity"],
        broad_universe=paths["broad"],
        tracked=paths["tracked"],
        output_dir=tmp_path / "outputs" / "daily",
        analysis_mode="ai_committee",
        ai_providers="openai,gemini,anthropic",
    )

    assert payload["analysis_mode"] == "ai_committee"
    assert captured["providers"] == ["openai", "gemini", "anthropic"]
    assert payload["ai_committee"]["consensus_candidates"]
    assert any(row.get("ai_review", {}).get("provider") == "committee" for row in payload["decisions"])


def test_unavailable_ai_provider_fails_gracefully(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    packet = build_candidate_packet(
        {
            "ticker": "NVDA",
            "actionability_label": "Breakout Actionable Today",
            "primary_action": "Research / Buy Candidate",
            "actionability_score": 80,
            "reason": "Strong setup",
            "why_not": "Can fail",
            "source_row": {"ticker": "NVDA", "current_price": 100.0, "relative_volume_20d": 2.0},
        }
    )
    provider = type(
        "UnavailableProvider",
        (),
        {
            "provider_name": "openai",
            "model": "unavailable",
            "configured": False,
            "unavailable_reason": "OPENAI_API_KEY is not configured.",
        },
    )()

    review = review_candidate_packet(packet, provider=provider, cache=False)

    assert review["available"] is False
    assert review["ai_final_view"] == "needs_more_research"
    assert "OPENAI_API_KEY" in " ".join(review["missing_evidence"])


def test_invalid_json_like_provider_response_is_handled_cleanly(tmp_path: Path) -> None:
    class InvalidJSONProvider:
        provider_name = "mock"
        model = "mock-model"
        configured = True
        unavailable_reason = None

        def complete_json(self, *, system_prompt: str, payload: dict[str, object]) -> dict[str, object]:
            return {"ok": False, "error": "invalid json", "provider": self.provider_name, "model": self.model}

    packet = build_candidate_packet(
        {
            "ticker": "NVDA",
            "actionability_label": "Watch for Better Entry",
            "primary_action": "Watch",
            "actionability_score": 61,
            "reason": "Needs confirmation",
            "why_not": "Extended",
            "source_row": {"ticker": "NVDA", "current_price": 100.0},
        }
    )

    review = review_candidate_packet(packet, provider=InvalidJSONProvider(), cache=True, cache_dir=tmp_path / "cache")

    assert review["available"] is False
    assert review["ai_summary_one_liner"] == "invalid json"


def test_ai_cache_prevents_duplicate_calls(tmp_path: Path) -> None:
    class CountingProvider:
        provider_name = "mock"
        model = "counting-model"
        configured = True
        unavailable_reason = None

        def __init__(self) -> None:
            self.calls = 0

        def complete_json(self, *, system_prompt: str, payload: dict[str, object]) -> dict[str, object]:
            self.calls += 1
            return {
                "ok": True,
                "provider": self.provider_name,
                "model": self.model,
                "content": {
                    "ai_final_view": "agree",
                    "ai_caution_level": "low",
                    "bull_case": "Supported.",
                    "bear_case": "Standard risk.",
                    "what_would_make_me_buy": "Deterministic setup holds.",
                    "what_would_make_me_wait": "Confirmation weakens.",
                    "what_would_make_me_avoid": "Invalidation breaks.",
                    "missing_evidence": [],
                    "unsupported_claims": [],
                    "confidence_reasoning": "Packet only.",
                    "deterministic_label_too_aggressive": False,
                    "deterministic_label_too_conservative": False,
                    "suggested_user_action": "watch",
                    "ai_summary_one_liner": "Looks fine.",
                },
            }

    provider = CountingProvider()
    packet = build_candidate_packet(
        {
            "ticker": "MSFT",
            "actionability_label": "Long-Term Research Candidate",
            "primary_action": "Research / Buy Candidate",
            "actionability_score": 72,
            "reason": "Constructive quality setup",
            "why_not": "Needs time",
            "source_row": {"ticker": "MSFT", "current_price": 100.0, "relative_volume_20d": 1.1},
        }
    )
    cache_dir = tmp_path / "cache"

    first = review_candidate_packet(packet, provider=provider, cache=True, cache_dir=cache_dir)
    second = review_candidate_packet(packet, provider=provider, cache=True, cache_dir=cache_dir)

    assert first["available"] is True
    assert second["cached"] is True
    assert provider.calls == 1


def test_ai_prompt_uses_only_structured_deterministic_data() -> None:
    decision = {
        "ticker": "NVDA",
        "company": "NVIDIA",
        "actionability_label": "Breakout Actionable Today",
        "primary_action": "Research / Buy Candidate",
        "actionability_score": 84,
        "reason": "Deterministic thesis",
        "why_not": "Can fail",
        "source_groups": ["Tracked", "Broad"],
        "source_row": {
            "ticker": "NVDA",
            "company_name": "NVIDIA",
            "current_price": 100.0,
            "price_change_1d_pct": 2.5,
            "relative_volume_20d": 1.8,
            "ema_21": 98.0,
            "ema_50": 96.0,
            "ema_150": 90.0,
            "ema_200": 88.0,
            "price_vs_ema_21_pct": 2.0,
            "signal_summary": "Breakout with Volume",
            "why_it_passed": ["Strong setup"],
            "why_it_could_fail": ["Extended"],
            "data_availability_notes": ["No earnings date supplied."],
        },
    }

    packet = build_candidate_packet(decision)

    assert set(packet.keys()) == {
        "ticker",
        "company",
        "deterministic_label",
        "primary_action",
        "actionability_score",
        "mover_quality_score",
        "price",
        "percent_change",
        "relative_volume",
        "dollar_volume",
        "ema_21",
        "ema_50",
        "ema_150",
        "ema_200",
        "price_vs_ema_21_pct",
        "price_vs_ema_50_pct",
        "price_vs_ema_150_pct",
        "price_vs_ema_200_pct",
        "signal_summary",
        "entry_or_trigger",
        "stop_or_invalidation",
        "tp1",
        "tp2",
        "risk_level",
        "why_interesting",
        "why_it_may_fail",
        "source_groups",
        "event_catalyst_data",
        "data_availability_notes",
        "explicit_missing_fields",
    }


def test_daily_markdown_shows_ai_summary_when_enabled() -> None:
    markdown = daily_decision._build_daily_decision_markdown(
        {
            "generated_at": "2026-05-01T00:00:00Z",
            "analysis_date": "2026-05-01",
            "provider": "real",
            "analysis_mode": "ai_review",
            "demo_mode": False,
            "scan_health": {"status": "healthy"},
            "benchmark_health": {"benchmark_health": "healthy"},
            "movers_scan_summary": {},
            "highs_scan_summary": {},
            "earnings_scan_summary": {},
            "theme_scan_summary": {},
            "fast_actionable_setups": [],
            "long_term_research_candidates": [],
            "high_volume_mover_watch": [],
            "tracked_watchlist_setups": [],
            "watch_candidates": [],
            "avoid_candidates": [],
            "data_issues": [],
            "top_gainers": [],
            "breakout_volume": [],
            "coverage_missed_risk": [],
            "ai_review_summary": {
                "provider": "openai",
                "model": "gpt-test",
                "names_reviewed": 3,
                "downgraded": 1,
                "caution_flags": 2,
                "top_ai_agreed_names": ["NVDA"],
                "names_ai_says_not_to_chase": ["PLTR"],
                "unsupported_claims_detected": 0,
            },
        }
    )

    assert "## AI Review Summary" in markdown
    assert "Top AI-agreed names: NVDA" in markdown
