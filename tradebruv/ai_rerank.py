from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from .actionability import ACTIONABILITY_LABELS, AVOID_LABELS, DATA_LABELS, actionability_priority
from .ai_guardrails import validate_ai_output
from .data_sources import redact_secrets


class AIRerankProvider(Protocol):
    name: str

    def review(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass
class UnavailableAIRerankProvider:
    name: str
    reason: str

    def review(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        return unavailable_ai_rerank(self.reason, provider=self.name)


@dataclass
class OpenAICompatibleAIRerankProvider:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    name: str = "openai-compatible"
    timeout_seconds: int = 30

    def review(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a grounded stock-research reranker. Use only supplied fields. "
                        "Do not invent prices, news, fundamentals, sources, or catalysts. "
                        "Do not place trades or promise outcomes. Return strict JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "required_keys": [
                                "bullish_case",
                                "bearish_case",
                                "what_would_make_me_buy",
                                "what_would_make_me_avoid",
                                "deterministic_label_too_aggressive",
                                "suggested_label",
                                "final_ai_caution",
                                "rerank_score",
                                "disagreement_reason",
                                "missing_data",
                            ],
                            "allowed_labels": sorted(ACTIONABILITY_LABELS),
                            "allowed_caution": ["low", "medium", "high"],
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
            return unavailable_ai_rerank(f"AI rerank unavailable: {redact_secrets(exc)}", provider=self.name)
        return sanitize_ai_rerank(generated, prompt_payload, provider=self.name)


@dataclass
class GeminiAIRerankProvider:
    api_key: str
    model: str
    name: str = "gemini"
    timeout_seconds: int = 30

    def review(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "required_keys": [
                                        "bullish_case",
                                        "bearish_case",
                                        "what_would_make_me_buy",
                                        "what_would_make_me_avoid",
                                        "deterministic_label_too_aggressive",
                                        "suggested_label",
                                        "final_ai_caution",
                                        "rerank_score",
                                        "disagreement_reason",
                                        "missing_data",
                                    ],
                                    "allowed_labels": sorted(ACTIONABILITY_LABELS),
                                    "allowed_caution": ["low", "medium", "high"],
                                    "rules": [
                                        "Use only supplied structured fields.",
                                        "Do not invent prices, catalysts, or sources.",
                                        "Do not place trades or promise outcomes.",
                                        "Return JSON only.",
                                    ],
                                    "payload": prompt_payload,
                                },
                                indent=2,
                            )
                        }
                    ],
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
            return unavailable_ai_rerank(f"Gemini rerank unavailable: {redact_secrets(exc)}", provider=self.name)
        return sanitize_ai_rerank(generated, prompt_payload, provider=self.name)


def build_ai_rerank_provider(mode: str) -> AIRerankProvider:
    chosen = mode.strip().lower()
    if chosen == "off":
        return UnavailableAIRerankProvider("disabled", "AI rerank disabled.")
    if chosen == "openai":
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("TRADEBRUV_LLM_API_KEY")
        if not api_key:
            return UnavailableAIRerankProvider("openai-compatible", "OPENAI_API_KEY or TRADEBRUV_LLM_API_KEY is not configured.")
        return OpenAICompatibleAIRerankProvider(
            api_key=api_key,
            model=os.getenv("TRADEBRUV_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini",
            base_url=os.getenv("TRADEBRUV_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1",
        )
    if chosen == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return UnavailableAIRerankProvider("gemini", "GEMINI_API_KEY is not configured.")
        return GeminiAIRerankProvider(api_key=api_key, model=os.getenv("GEMINI_MODEL") or "gemini-1.5-flash")
    return UnavailableAIRerankProvider("unknown", f"Unknown AI rerank mode: {mode}")


def apply_ai_rerank(
    decisions: list[dict[str, Any]],
    *,
    mode: str = "off",
    provider: AIRerankProvider | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    chosen_provider = provider or build_ai_rerank_provider(mode)
    if mode == "off":
        return decisions
    reviewed: list[dict[str, Any]] = []
    for index, decision in enumerate(decisions):
        item = deepcopy(decision)
        if index >= limit or str(item.get("actionability_label") or "") in AVOID_LABELS | DATA_LABELS:
            reviewed.append(item)
            continue
        payload = {
            "deterministic_decision": _grounded_decision_payload(item),
            "instructions": {
                "deterministic_source_of_truth": True,
                "only_downgrade_if_needed": True,
                "missing_data_rule": "Keep unavailable fields unavailable.",
            },
        }
        review = chosen_provider.review(payload)
        guardrail_input = {
            "bear_case": review.get("bearish_case") or [],
            "risk_manager_view": review.get("what_would_make_me_avoid") or review.get("disagreement_reason"),
            "missing_data": review.get("missing_data") or [],
            "events_to_watch": [review.get("what_would_make_me_buy"), review.get("disagreement_reason")],
            "what_would_change_my_mind": [review.get("what_would_make_me_buy")],
            "final_recommendation_label": review.get("suggested_label"),
            "safety_notes": ["AI output is research support, not trade execution."],
        }
        review.update(validate_ai_output(guardrail_input, item.get("source_row") or {}))
        item["ai_review"] = {
            "available": review.get("available", False),
            "provider": review.get("provider"),
            "bullish_case": review.get("bullish_case") or [],
            "bearish_case": review.get("bearish_case") or [],
            "what_would_make_me_buy": review.get("what_would_make_me_buy") or "unavailable",
            "what_would_make_me_avoid": review.get("what_would_make_me_avoid") or "unavailable",
            "deterministic_label_too_aggressive": bool(review.get("deterministic_label_too_aggressive")),
            "suggested_label": review.get("suggested_label") or item.get("actionability_label"),
            "final_ai_caution": review.get("final_ai_caution") or "medium",
            "rerank_score": int(review.get("rerank_score") or 0),
            "disagreement_reason": review.get("disagreement_reason") or "",
            "missing_data": review.get("missing_data") or [],
            "ai_guardrail_warnings": review.get("ai_guardrail_warnings") or [],
            "unsupported_claims_detected": bool(review.get("unsupported_claims_detected")),
        }
        item["ai_rerank_score"] = int(review.get("rerank_score") or 0)
        item["ai_caution"] = str(review.get("final_ai_caution") or "medium")
        item["ai_disagreement_reason"] = str(review.get("disagreement_reason") or "")

        current_label = str(item.get("actionability_label") or "Data Insufficient")
        suggested_label = str(review.get("suggested_label") or current_label)
        if _can_downgrade_label(current_label, suggested_label, review):
            item["ai_adjusted_actionability_label"] = suggested_label
        reviewed.append(item)
    return reviewed


def sanitize_ai_rerank(generated: dict[str, Any], prompt_payload: dict[str, Any], *, provider: str) -> dict[str, Any]:
    decision = (prompt_payload.get("deterministic_decision") or {})
    fallback_label = str(decision.get("actionability_label") or "Data Insufficient")
    return {
        "available": True,
        "provider": provider,
        "bullish_case": _clean_list(generated.get("bullish_case")),
        "bearish_case": _clean_list(generated.get("bearish_case")),
        "what_would_make_me_buy": _clean_text(generated.get("what_would_make_me_buy")) or "Use the deterministic entry, risk, and catalyst fields only if they stay valid.",
        "what_would_make_me_avoid": _clean_text(generated.get("what_would_make_me_avoid")) or "Avoid if deterministic risk or confirmation weakens.",
        "deterministic_label_too_aggressive": bool(generated.get("deterministic_label_too_aggressive")),
        "suggested_label": _clean_label(generated.get("suggested_label")) or fallback_label,
        "final_ai_caution": _clean_caution(generated.get("final_ai_caution")) or "medium",
        "rerank_score": _clean_score(generated.get("rerank_score"), fallback=int(decision.get("actionability_score") or 0)),
        "disagreement_reason": _clean_text(generated.get("disagreement_reason")) or "AI rerank reviewed the deterministic label without adding new evidence.",
        "missing_data": _clean_list(generated.get("missing_data")),
    }


def unavailable_ai_rerank(reason: str, *, provider: str = "unavailable") -> dict[str, Any]:
    return {
        "available": False,
        "provider": provider,
        "bullish_case": [],
        "bearish_case": [reason],
        "what_would_make_me_buy": "unavailable",
        "what_would_make_me_avoid": reason,
        "deterministic_label_too_aggressive": False,
        "suggested_label": "Data Insufficient",
        "final_ai_caution": "high",
        "rerank_score": 0,
        "disagreement_reason": reason,
        "missing_data": [reason],
    }


def _grounded_decision_payload(decision: dict[str, Any]) -> dict[str, Any]:
    source_row = decision.get("source_row") or {}
    keys = [
        "ticker",
        "company",
        "primary_action",
        "actionability_label",
        "actionability_score",
        "actionability_reason",
        "current_setup_state",
        "risk_level",
        "entry_zone",
        "stop_loss",
        "tp1",
        "tp2",
        "reward_risk",
        "momentum_actionability_score",
        "breakout_actionability_score",
        "pullback_actionability_score",
        "long_term_research_score",
        "mover_score",
        "slow_compounder_score",
        "reason",
        "why_not",
        "events_to_watch",
        "price_validation_status",
        "price_validation_reason",
    ]
    payload = {key: decision.get(key) for key in keys}
    payload["source_row"] = {
        key: source_row.get(key)
        for key in (
            "ticker",
            "current_price",
            "relative_volume_20d",
            "relative_volume_50d",
            "price_change_1d_pct",
            "price_change_5d_pct",
            "signal_summary",
            "signal_explanation",
            "ema_stack",
            "catalyst_quality",
            "catalyst_source_count",
            "sector_relative_strength",
            "investing_style",
            "regular_investing_score",
            "outlier_score",
            "velocity_score",
            "setup_quality_score",
            "warnings",
            "why_it_could_fail",
            "data_availability_notes",
        )
    }
    return payload


def _can_downgrade_label(current_label: str, suggested_label: str, review: dict[str, Any]) -> bool:
    if not review.get("available"):
        return False
    if review.get("unsupported_claims_detected"):
        return False
    if current_label in AVOID_LABELS | DATA_LABELS:
        return False
    if not review.get("deterministic_label_too_aggressive"):
        return False
    if suggested_label not in ACTIONABILITY_LABELS:
        return False
    return actionability_priority(suggested_label) > actionability_priority(current_label)


def _strip_json_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    return cleaned


def _clean_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item)[:500] for item in value if str(item)]
    if isinstance(value, str) and value:
        return [value[:500]]
    return []


def _clean_text(value: Any) -> str:
    return str(value)[:1200] if value not in (None, "") else ""


def _clean_label(value: Any) -> str:
    text = str(value or "")
    return text if text in ACTIONABILITY_LABELS else ""


def _clean_caution(value: Any) -> str:
    text = str(value or "").lower()
    return text if text in {"low", "medium", "high"} else ""


def _clean_score(value: Any, *, fallback: int) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return fallback
    return max(0, min(100, score))
