from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .ai_guardrails import validate_ai_output
from .data_sources import redact_secrets


AI_MODES = (
    "No AI",
    "OpenAI only",
    "Claude only",
    "Gemini only",
    "Multi-agent committee",
    "Mock AI for testing",
)


class CommitteeProvider(Protocol):
    name: str

    def generate(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass
class MockCommitteeProvider:
    name: str = "mock"

    def generate(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        scanner = prompt_payload.get("scanner_row", {})
        portfolio = prompt_payload.get("portfolio_context") or {}
        warnings = (scanner.get("warnings") or [])[:4]
        passed = (scanner.get("why_it_passed") or [])[:4]
        label = _mock_ai_label(scanner, portfolio)
        return {
            "available": True,
            "provider": self.name,
            "bull_case": passed or ["No clear bull case was available in the deterministic payload."],
            "bear_case": (scanner.get("why_it_could_fail") or [])[:4] or warnings or ["No clear bear case was available."],
            "risk_manager_view": _risk_view(scanner, portfolio),
            "catalyst_view": _catalyst_view(scanner),
            "debate_summary": _debate_summary(scanner, label),
            "final_recommendation_label": label,
            "confidence_label": _confidence(scanner),
            "evidence_used": _evidence_used(scanner, portfolio),
            "missing_data": _missing_data(scanner),
            "events_to_watch": _events_to_watch(scanner),
            "what_would_change_my_mind": _what_would_change(scanner),
            "portfolio_specific_action": _portfolio_action(portfolio, label),
            "recommended_next_step": _next_step(label, portfolio),
            "disagreement": _disagreement(scanner, label),
            "safety_notes": _safety_notes(),
        }


@dataclass
class UnavailableCommitteeProvider:
    name: str
    reason: str

    def generate(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        return unavailable_committee_payload(self.reason, provider=self.name)


@dataclass
class OpenAICompatibleCommitteeProvider:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    name: str = "openai-compatible"
    timeout_seconds: int = 30

    def generate(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a grounded research analyst committee. Use only supplied fields. "
                        "Do not invent news, prices, fundamentals, sources, or portfolio positions. "
                        "Do not place trades or promise profit. Return strict JSON with the requested keys."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "required_keys": [
                                "bull_case",
                                "bear_case",
                                "risk_manager_view",
                                "catalyst_view",
                                "debate_summary",
                                "final_recommendation_label",
                                "confidence_label",
                                "evidence_used",
                                "missing_data",
                                "events_to_watch",
                                "what_would_change_my_mind",
                                "portfolio_specific_action",
                                "recommended_next_step",
                            ],
                            "allowed_recommendations": [
                                "Strong Buy Candidate",
                                "Buy Candidate",
                                "Hold / Watch",
                                "Wait for Better Entry",
                                "Avoid",
                                "Sell / Exit Candidate",
                                "Data Insufficient",
                            ],
                            "payload": prompt_payload,
                        },
                        indent=2,
                    ),
                },
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            generated = json.loads(content)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
            return unavailable_committee_payload(f"AI committee unavailable: {redact_secrets(exc)}", provider=self.name)
        return sanitize_committee_output(generated, prompt_payload, provider=self.name)


@dataclass
class GeminiCommitteeProvider:
    api_key: str
    model: str
    name: str = "gemini"
    timeout_seconds: int = 30

    def generate(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        prompt = {
            "required_keys": [
                "bull_case",
                "bear_case",
                "risk_manager_view",
                "catalyst_view",
                "debate_summary",
                "final_recommendation_label",
                "confidence_label",
                "evidence_used",
                "missing_data",
                "events_to_watch",
                "what_would_change_my_mind",
                "portfolio_specific_action",
                "recommended_next_step",
            ],
            "allowed_recommendations": [
                "Strong Buy Candidate",
                "Buy Candidate",
                "Hold / Watch",
                "Wait for Better Entry",
                "Avoid",
                "Sell / Exit Candidate",
                "Data Insufficient",
            ],
            "rules": [
                "Use only scanner_row and portfolio_context.",
                "Do not invent prices, news, sources, filings, or portfolio positions.",
                "Do not place trades or promise profit.",
                "Return JSON only.",
            ],
            "payload": prompt_payload,
        }
        request_payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": json.dumps(prompt, indent=2)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        request = urllib.request.Request(
            url,
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
            generated = json.loads(_strip_json_fences(text))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
            return unavailable_committee_payload(f"Gemini committee unavailable: {redact_secrets(exc)}", provider=self.name)
        return sanitize_committee_output(generated, prompt_payload, provider=self.name)


def build_committee_provider(mode: str, *, mock: bool = False) -> CommitteeProvider:
    if mode == "No AI":
        return UnavailableCommitteeProvider("disabled", "AI committee disabled.")
    if mock or mode == "Mock AI for testing":
        return MockCommitteeProvider()
    if mode in {"OpenAI only", "Multi-agent committee"}:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("TRADEBRUV_LLM_API_KEY")
        if not api_key:
            return UnavailableCommitteeProvider("openai-compatible", "OPENAI_API_KEY or TRADEBRUV_LLM_API_KEY is not configured.")
        return OpenAICompatibleCommitteeProvider(
            api_key=api_key,
            model=os.getenv("TRADEBRUV_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini",
            base_url=os.getenv("TRADEBRUV_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1",
        )
    if mode == "Claude only":
        if not os.getenv("ANTHROPIC_API_KEY"):
            return UnavailableCommitteeProvider("anthropic", "ANTHROPIC_API_KEY is not configured.")
        return UnavailableCommitteeProvider("anthropic", "Claude adapter is detected but not enabled in this MVP; use OpenAI-compatible or mock mode.")
    if mode == "Gemini only":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return UnavailableCommitteeProvider("gemini", "GEMINI_API_KEY is not configured.")
        return GeminiCommitteeProvider(api_key=api_key, model=os.getenv("GEMINI_MODEL") or "gemini-1.5-flash")
    return UnavailableCommitteeProvider("unknown", f"Unknown AI mode: {mode}")


def run_ai_committee(
    *,
    scanner_row: dict[str, Any],
    portfolio_context: dict[str, Any] | None = None,
    provider: CommitteeProvider | None = None,
    mode: str = "Mock AI for testing",
) -> dict[str, Any]:
    chosen_provider = provider or build_committee_provider(mode)
    payload = {
        "scanner_row": _grounded_scanner_payload(scanner_row),
        "portfolio_context": portfolio_context or {},
        "instructions": {
            "grounding": "Use only scanner_row and portfolio_context.",
            "execution": "No trade execution or order placement.",
            "missing_data": "List unavailable fields rather than inventing them.",
        },
    }
    output = chosen_provider.generate(payload)
    return {**output, **validate_ai_output(output, scanner_row)}


def combine_recommendations(rule_based: str, ai_output: dict[str, Any], scanner_row: dict[str, Any]) -> dict[str, Any]:
    ai_label = ai_output.get("final_recommendation_label", "Data Insufficient")
    hard_risk = scanner_row.get("status_label") == "Avoid" or _to_float(scanner_row.get("risk_score")) >= 75
    if hard_risk:
        final = "Avoid" if "Sell" not in rule_based else rule_based
        rationale = "Hard deterministic risk flags remain primary; AI cannot silently override them."
    elif not ai_output.get("available"):
        final = rule_based
        rationale = "AI unavailable; final recommendation follows deterministic rules."
    elif _labels_agree(rule_based, ai_label):
        final = rule_based
        rationale = "Rule-based and AI committee views broadly agree."
    else:
        final = rule_based
        rationale = "Rule-based recommendation kept primary; AI disagreement is shown for review."
    return {
        "rule_based_recommendation": rule_based,
        "ai_committee_recommendation": ai_label,
        "agreement": _labels_agree(rule_based, ai_label),
        "final_combined_recommendation": final,
        "rationale": rationale,
        "hard_risk_flag": hard_risk,
    }


def sanitize_committee_output(generated: dict[str, Any], prompt_payload: dict[str, Any], *, provider: str) -> dict[str, Any]:
    scanner = prompt_payload.get("scanner_row", {})
    fallback = MockCommitteeProvider(provider).generate(prompt_payload)
    output = {
        "available": True,
        "provider": provider,
        "bull_case": _clean_list(generated.get("bull_case")) or fallback["bull_case"],
        "bear_case": _clean_list(generated.get("bear_case")) or fallback["bear_case"],
        "risk_manager_view": _clean_text(generated.get("risk_manager_view")) or fallback["risk_manager_view"],
        "catalyst_view": _clean_text(generated.get("catalyst_view")) or fallback["catalyst_view"],
        "debate_summary": _clean_text(generated.get("debate_summary")) or fallback["debate_summary"],
        "final_recommendation_label": _clean_label(generated.get("final_recommendation_label")) or fallback["final_recommendation_label"],
        "confidence_label": _clean_confidence(generated.get("confidence_label")) or fallback["confidence_label"],
        "evidence_used": _clean_list(generated.get("evidence_used")) or fallback["evidence_used"],
        "missing_data": _clean_list(generated.get("missing_data")) or fallback["missing_data"],
        "events_to_watch": _clean_list(generated.get("events_to_watch")) or fallback["events_to_watch"],
        "what_would_change_my_mind": _clean_list(generated.get("what_would_change_my_mind")) or fallback["what_would_change_my_mind"],
        "portfolio_specific_action": _clean_text(generated.get("portfolio_specific_action")) or fallback["portfolio_specific_action"],
        "recommended_next_step": _clean_next_step(generated.get("recommended_next_step")) or fallback["recommended_next_step"],
        "disagreement": _disagreement(scanner, _clean_label(generated.get("final_recommendation_label")) or fallback["final_recommendation_label"]),
        "safety_notes": _safety_notes(),
    }
    return output


def _strip_json_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    return cleaned


def unavailable_committee_payload(reason: str, *, provider: str = "unavailable") -> dict[str, Any]:
    return {
        "available": False,
        "provider": provider,
        "bull_case": [],
        "bear_case": [reason],
        "risk_manager_view": reason,
        "catalyst_view": "unavailable",
        "debate_summary": reason,
        "final_recommendation_label": "Data Insufficient",
        "confidence_label": "Low",
        "evidence_used": [],
        "missing_data": [reason],
        "events_to_watch": [],
        "what_would_change_my_mind": ["Configure a supported AI provider or use mock mode for testing."],
        "portfolio_specific_action": "AI unavailable.",
        "recommended_next_step": "Data Insufficient",
        "disagreement": "unavailable",
        "safety_notes": _safety_notes(),
    }


def _grounded_scanner_payload(row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "ticker",
        "company_name",
        "current_price",
        "status_label",
        "strategy_label",
        "winner_score",
        "outlier_score",
        "outlier_type",
        "risk_score",
        "setup_quality_score",
        "confidence_label",
        "entry_zone",
        "invalidation_level",
        "tp1",
        "tp2",
        "reward_risk",
        "catalyst_quality",
        "catalyst_type",
        "catalyst_items",
        "social_attention_score",
        "why_it_passed",
        "why_it_could_fail",
        "why_it_could_be_a_big_winner",
        "warnings",
        "data_availability_notes",
        "alternative_data_summary",
        "alternative_data_quality",
        "alternative_data_source_count",
        "insider_buy_count",
        "insider_sell_count",
        "net_insider_value",
        "CEO_CFO_buy_flag",
        "cluster_buying_flag",
        "heavy_insider_selling_flag",
        "politician_buy_count",
        "politician_sell_count",
        "net_politician_value",
        "recent_politician_activity",
        "disclosure_lag_warning",
        "alternative_data_confirmed_by_price_volume",
        "alternative_data_warnings",
        "alternative_data_items",
    ]
    return {key: row.get(key) for key in keys}


def _mock_ai_label(scanner: dict[str, Any], portfolio: dict[str, Any]) -> str:
    if _missing_data(scanner):
        return "Data Insufficient"
    if portfolio.get("recommendation_label") == "Exit / Sell":
        return "Sell / Exit Candidate"
    if scanner.get("status_label") == "Avoid" or _to_float(scanner.get("risk_score")) >= 70:
        return "Avoid"
    if _to_float(scanner.get("winner_score")) >= 80 and _to_float(scanner.get("setup_quality_score")) >= 70 and _to_float(scanner.get("risk_score")) <= 35:
        return "Strong Buy Candidate"
    if _to_float(scanner.get("winner_score")) >= 65 and _to_float(scanner.get("risk_score")) <= 50:
        return "Buy Candidate"
    if _to_float(scanner.get("risk_score")) >= 55:
        return "Wait for Better Entry"
    return "Hold / Watch"


def _risk_view(scanner: dict[str, Any], portfolio: dict[str, Any]) -> str:
    points = [f"Risk score {scanner.get('risk_score', 'unavailable')}."]
    if scanner.get("invalidation_level") not in (None, "", "unavailable"):
        points.append(f"Invalidation is {scanner.get('invalidation_level')}.")
    if portfolio.get("position_weight_pct", 0):
        points.append(f"Portfolio weight is {portfolio.get('position_weight_pct')}%.")
    points.extend((scanner.get("warnings") or [])[:2])
    return " ".join(str(point) for point in points)


def _catalyst_view(scanner: dict[str, Any]) -> str:
    return (
        f"Catalyst quality {scanner.get('catalyst_quality', 'Unavailable')}; "
        f"type {scanner.get('catalyst_type', 'unavailable')}; "
        f"social score {scanner.get('social_attention_score', 0)}."
    )


def _debate_summary(scanner: dict[str, Any], label: str) -> str:
    return (
        f"Bull case is tied to deterministic score {scanner.get('winner_score', 'unavailable')} and setup "
        f"{scanner.get('setup_quality_score', 'unavailable')}; bear case is tied to risk "
        f"{scanner.get('risk_score', 'unavailable')}. Final AI label: {label}."
    )


def _evidence_used(scanner: dict[str, Any], portfolio: dict[str, Any]) -> list[str]:
    evidence = [
        f"ticker={scanner.get('ticker')}",
        f"status_label={scanner.get('status_label')}",
        f"winner_score={scanner.get('winner_score')}",
        f"outlier_score={scanner.get('outlier_score')}",
        f"risk_score={scanner.get('risk_score')}",
        f"setup_quality_score={scanner.get('setup_quality_score')}",
        f"invalidation_level={scanner.get('invalidation_level')}",
    ]
    if portfolio:
        evidence.append(f"portfolio_weight={portfolio.get('position_weight_pct', 'unavailable')}")
    return evidence


def _missing_data(scanner: dict[str, Any]) -> list[str]:
    missing = []
    for key in ("current_price", "winner_score", "risk_score", "setup_quality_score"):
        if scanner.get(key) in (None, "", "unavailable"):
            missing.append(key)
    missing.extend(str(note) for note in (scanner.get("data_availability_notes") or []) if "unavailable" in str(note).lower())
    return missing


def _events_to_watch(scanner: dict[str, Any]) -> list[str]:
    events = []
    if scanner.get("invalidation_level") not in (None, "", "unavailable"):
        events.append(f"Invalidation: {scanner.get('invalidation_level')}")
    if scanner.get("tp1") not in (None, "", "unavailable"):
        events.append(f"TP1: {scanner.get('tp1')}")
    events.extend((scanner.get("warnings") or [])[:3])
    return events or ["Refresh source data and watch for verified catalyst changes."]


def _what_would_change(scanner: dict[str, Any]) -> list[str]:
    return [
        "A refreshed scan changes deterministic status/risk flags.",
        "Price loses or reclaims invalidation/support.",
        "Verified catalyst/news data appears or disproves the current narrative.",
    ]


def _portfolio_action(portfolio: dict[str, Any], label: str) -> str:
    if not portfolio:
        return "Not owned in the local portfolio."
    if label in {"Sell / Exit Candidate", "Avoid"}:
        return "Add to Portfolio Review; evaluate invalidation and risk before any manual decision."
    if label in {"Strong Buy Candidate", "Buy Candidate"}:
        return "Consider Add only if deterministic risk, concentration, and entry quality agree."
    return f"Portfolio rule label: {portfolio.get('recommendation_label', 'unavailable')}."


def _next_step(label: str, portfolio: dict[str, Any]) -> str:
    if label == "Data Insufficient":
        return "Data Insufficient"
    if label == "Avoid":
        return "Avoid"
    if label == "Sell / Exit Candidate":
        return "Consider Exit"
    if label in {"Strong Buy Candidate", "Buy Candidate"}:
        return "Consider Add" if portfolio else "Add to Watchlist"
    if label == "Wait for Better Entry":
        return "Watch"
    return "Hold" if portfolio else "Research"


def _disagreement(scanner: dict[str, Any], label: str) -> str:
    hard_risk = scanner.get("status_label") == "Avoid" or _to_float(scanner.get("risk_score")) >= 70
    if hard_risk and label not in {"Avoid", "Sell / Exit Candidate", "Data Insufficient"}:
        return "AI conflicts with deterministic hard risk flags."
    return "No major deterministic conflict detected."


def _labels_agree(rule_label: str, ai_label: str) -> bool:
    positive_rule = any(word in rule_label for word in ("Hold", "Add", "Buy"))
    negative_rule = any(word in rule_label for word in ("Trim", "Exit", "Avoid", "Sell"))
    positive_ai = any(word in ai_label for word in ("Buy", "Hold"))
    negative_ai = any(word in ai_label for word in ("Avoid", "Sell", "Exit"))
    return (positive_rule and positive_ai) or (negative_rule and negative_ai) or rule_label == ai_label


def _confidence(scanner: dict[str, Any]) -> str:
    if _missing_data(scanner):
        return "Low"
    if _to_float(scanner.get("setup_quality_score")) >= 70 and _to_float(scanner.get("risk_score")) <= 35:
        return "High"
    if _to_float(scanner.get("setup_quality_score")) >= 50:
        return "Medium"
    return "Low"


def _clean_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item)[:500] for item in value if str(item)]
    if isinstance(value, str) and value:
        return [value[:500]]
    return []


def _clean_text(value: Any) -> str:
    return str(value)[:1200] if value not in (None, "") else ""


def _clean_label(value: Any) -> str:
    allowed = {
        "Strong Buy Candidate",
        "Buy Candidate",
        "Hold / Watch",
        "Wait for Better Entry",
        "Avoid",
        "Sell / Exit Candidate",
        "Data Insufficient",
    }
    text = str(value or "")
    return text if text in allowed else ""


def _clean_confidence(value: Any) -> str:
    text = str(value or "")
    return text if text in {"High", "Medium", "Low"} else ""


def _clean_next_step(value: Any) -> str:
    text = str(value or "")
    allowed = {
        "Research",
        "Watch",
        "Add to Watchlist",
        "Add to Portfolio Review",
        "Hold",
        "Consider Add",
        "Consider Trim",
        "Consider Exit",
        "Avoid",
        "Data Insufficient",
    }
    return text if text in allowed else ""


def _to_float(value: Any) -> float:
    try:
        if value in (None, "", "unavailable"):
            raise ValueError
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safety_notes() -> list[str]:
    return [
        "AI output is research support, not trade execution.",
        "Use only displayed evidence fields; missing data must stay missing.",
        "Hard deterministic risk flags remain visible and primary.",
    ]
