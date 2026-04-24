from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Protocol

from .models import ScannerResult


FORBIDDEN_AI_TERMS = ("buy", "guaranteed", "guarantee")


class ExplanationProvider(Protocol):
    name: str

    def explain(self, result: ScannerResult) -> dict[str, Any]:
        ...


class UnavailableExplanationProvider:
    name = "unavailable"

    def __init__(self, reason: str = "AI explanation unavailable.") -> None:
        self.reason = reason

    def explain(self, result: ScannerResult) -> dict[str, Any]:
        return _unavailable_payload(self.reason)


class MockExplanationProvider:
    name = "mock"

    def explain(self, result: ScannerResult) -> dict[str, Any]:
        row = result.to_dict()
        sources = row.get("catalyst_items", [])[:3]
        return {
            "available": True,
            "provider": self.name,
            "generated": True,
            "summary": (
                f"{row['ticker']} is labeled {row['status_label']} by deterministic scanner output. "
                f"Outlier score {row['outlier_score']}, winner score {row['winner_score']}, risk score {row['risk_score']}."
            ),
            "bull_case": list(row.get("why_it_passed", [])[:4]),
            "bear_case": list(row.get("why_it_could_fail", [])[:4]),
            "why_not_to_buy": list(row.get("warnings", [])[:5]) or list(row.get("why_it_could_fail", [])[:3]),
            "catalyst_summary": _evidence_summary(row),
            "social_attention_summary": _social_summary(row),
            "setup_invalidation": f"Setup invalidates around {row.get('invalidation_level', 'unavailable')} per scanner output.",
            "research_checklist": [
                "Verify source URLs and timestamps before acting.",
                "Confirm price and volume still agree with the reported setup.",
                "Review warnings and Why NOT to buy before considering any trade.",
            ],
            "source_item_refs": [_source_ref(item) for item in sources],
            "safety_notes": _safety_notes(),
        }


class OpenAICompatibleExplanationProvider:
    name = "openai-compatible"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: int = 20,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> ExplanationProvider:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("TRADEBRUV_LLM_API_KEY")
        if not api_key:
            return UnavailableExplanationProvider("AI explanation unavailable: OPENAI_API_KEY or TRADEBRUV_LLM_API_KEY is not configured.")
        model = os.getenv("TRADEBRUV_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        base_url = os.getenv("TRADEBRUV_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        return cls(api_key=api_key, model=model, base_url=base_url)

    def explain(self, result: ScannerResult) -> dict[str, Any]:
        row = _grounded_payload(result)
        request_payload = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You explain deterministic stock scanner output. You are not a trading system. "
                        "Never create buy/sell signals, never invent evidence, never say guaranteed, "
                        "and never create price targets beyond provided scanner levels. Return strict JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instructions": {
                                "allowed_sections": [
                                    "summary",
                                    "bull_case",
                                    "bear_case",
                                    "why_not_to_buy",
                                    "catalyst_summary",
                                    "social_attention_summary",
                                    "setup_invalidation",
                                    "research_checklist",
                                ],
                                "must_use_only_this_payload": True,
                                "missing_data_rule": "Say unavailable when evidence is unavailable.",
                            },
                            "scanner_payload": row,
                        },
                        indent=2,
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return _unavailable_payload(f"AI explanation unavailable: provider request failed: {exc}")

        content = payload.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        try:
            generated = json.loads(content)
        except json.JSONDecodeError:
            return _unavailable_payload("AI explanation unavailable: provider returned non-JSON content.")
        return _sanitize_generated(generated, result)


def build_explanation_provider(*, enabled: bool, mock: bool = False) -> ExplanationProvider:
    if not enabled:
        return UnavailableExplanationProvider("AI explanation unavailable: disabled.")
    if mock:
        return MockExplanationProvider()
    return OpenAICompatibleExplanationProvider.from_env()


def apply_ai_explanations(results: list[ScannerResult], provider: ExplanationProvider) -> None:
    for result in results:
        result.ai_explanation = provider.explain(result)


def _sanitize_generated(generated: dict[str, Any], result: ScannerResult) -> dict[str, Any]:
    payload = {
        "available": True,
        "provider": "openai-compatible",
        "generated": True,
        "summary": _clean_text(generated.get("summary")) or _grounded_fallback(result),
        "bull_case": _clean_list(generated.get("bull_case")),
        "bear_case": _clean_list(generated.get("bear_case")),
        "why_not_to_buy": _clean_list(generated.get("why_not_to_buy")),
        "catalyst_summary": _clean_text(generated.get("catalyst_summary")) or "unavailable",
        "social_attention_summary": _clean_text(generated.get("social_attention_summary")) or "unavailable",
        "setup_invalidation": _clean_text(generated.get("setup_invalidation")) or f"Scanner invalidation: {result.trade_plan.invalidation_level or 'unavailable'}.",
        "research_checklist": _clean_list(generated.get("research_checklist")),
        "source_item_refs": [_source_ref(item) for item in result.to_dict().get("catalyst_items", [])[:5]],
        "safety_notes": _safety_notes(),
    }
    if not payload["why_not_to_buy"]:
        payload["why_not_to_buy"] = list(result.warnings[:5]) or list(result.why_it_could_fail[:3]) or ["No specific risk note was generated; check scanner warnings and data availability."]
    return payload


def _grounded_payload(result: ScannerResult) -> dict[str, Any]:
    row = result.to_dict()
    allowed_keys = [
        "ticker",
        "company_name",
        "current_price",
        "status_label",
        "strategy_label",
        "winner_score",
        "outlier_score",
        "outlier_type",
        "outlier_risk",
        "risk_score",
        "setup_quality_score",
        "entry_zone",
        "invalidation_level",
        "stop_loss_reference",
        "tp1",
        "tp2",
        "reward_risk",
        "why_it_passed",
        "why_it_could_fail",
        "why_it_could_be_a_big_winner",
        "warnings",
        "data_availability_notes",
        "catalyst_items",
        "catalyst_score",
        "catalyst_quality",
        "catalyst_type",
        "source_urls",
        "source_timestamps",
        "social_attention_score",
        "news_attention_score",
        "news_sentiment_label",
    ]
    return {key: row.get(key) for key in allowed_keys}


def _unavailable_payload(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "provider": "unavailable",
        "generated": False,
        "summary": reason,
        "bull_case": [],
        "bear_case": [],
        "why_not_to_buy": [reason],
        "catalyst_summary": "unavailable",
        "social_attention_summary": "unavailable",
        "setup_invalidation": "unavailable",
        "research_checklist": [],
        "source_item_refs": [],
        "safety_notes": _safety_notes(),
    }


def _evidence_summary(row: dict[str, Any]) -> str:
    return (
        f"Catalyst quality: {row.get('catalyst_quality', 'Unavailable')}; "
        f"type: {row.get('catalyst_type', 'Unknown/unconfirmed')}; "
        f"sources: {row.get('catalyst_source_count', 0)}."
    )


def _social_summary(row: dict[str, Any]) -> str:
    if not row.get("social_attention_available"):
        return "Social attention unavailable."
    return (
        f"Social attention score {row.get('social_attention_score', 0)}, "
        f"velocity {row.get('social_attention_velocity', 'unavailable')}, "
        f"hype risk {row.get('hype_risk', False)}."
    )


def _grounded_fallback(result: ScannerResult) -> str:
    return (
        f"{result.ticker} has deterministic status {result.status_label}; "
        f"outlier score {result.outlier_score}, winner score {result.winner_score}."
    )


def _source_ref(item: dict[str, Any]) -> str:
    headline = item.get("headline") or item.get("summary") or item.get("catalyst_type") or "source"
    timestamp = item.get("timestamp", "unavailable")
    url = item.get("source_url", "unavailable")
    return f"{headline} | {timestamp} | {url}"


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    for term in FORBIDDEN_AI_TERMS:
        if term in text.lower():
            text = text.replace(term, "[restricted term]")
    return text


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean_text(item) for item in value if _clean_text(item)]


def _safety_notes() -> list[str]:
    return [
        "AI-generated explanation is optional and grounded in scanner/report fields.",
        "AI does not create deterministic scores, status labels, catalysts, or trade signals.",
        "Verify source evidence manually before making any trading or investing decision.",
    ]
