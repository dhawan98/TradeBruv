from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from .ai_guardrails import validate_ai_output
from .data_sources import redact_secrets

ANALYSIS_MODES = ("deterministic", "ai_review", "ai_committee")
SUPPORTED_AI_PROVIDERS = ("openai", "gemini", "anthropic", "generic")
AI_REVIEW_FINAL_VIEWS = ("agree", "downgrade", "upgrade_watch_only", "needs_more_research", "avoid")
AI_CAUTION_LEVELS = ("low", "medium", "high")
AI_USER_ACTIONS = ("research", "watch", "wait_for_pullback", "avoid_chase", "ignore")
COMMITTEE_VOTES = ("bullish", "cautious", "avoid", "needs_more_data")
DEFAULT_AI_MAX_NAMES = 10
DEFAULT_AI_TIMEOUT_SECONDS = 30
DEFAULT_AI_MAX_TOKENS = 1200
DEFAULT_AI_OUTPUT_DIR = Path("outputs/ai")
DEFAULT_AI_CACHE_DIR = DEFAULT_AI_OUTPUT_DIR / "cache"
AI_REVIEW_PROMPT_VERSION = "tradebruv-ai-review-v1"
AI_BRIEF_PROMPT_VERSION = "tradebruv-ai-brief-v1"


class AIProvider(Protocol):
    provider_name: str
    model: str
    configured: bool
    unavailable_reason: str | None

    def complete_json(self, *, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class AIProviderStatus:
    provider: str
    configured: bool
    model: str
    reason: str = ""
    base_url: str = ""


@dataclass
class UnavailableAIProvider:
    provider_name: str
    model: str = "unavailable"
    configured: bool = False
    unavailable_reason: str | None = None

    def complete_json(self, *, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": False,
            "error": self.unavailable_reason or f"{self.provider_name} is unavailable.",
            "provider": self.provider_name,
            "model": self.model,
        }


@dataclass
class OpenAICompatibleAIProvider:
    api_key: str
    model: str
    base_url: str
    provider_name: str
    configured: bool = True
    unavailable_reason: str | None = None
    timeout_seconds: int = DEFAULT_AI_TIMEOUT_SECONDS
    max_tokens: int = DEFAULT_AI_MAX_TOKENS

    def complete_json(self, *, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = {
            "model": self.model,
            "temperature": 0.1,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, indent=2)},
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
                body = json.loads(response.read().decode("utf-8"))
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            parsed = json.loads(content)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
            return {
                "ok": False,
                "error": _provider_error(exc, prefix=f"{self.provider_name} request failed"),
                "provider": self.provider_name,
                "model": self.model,
            }
        return {"ok": True, "content": parsed, "provider": self.provider_name, "model": self.model}


@dataclass
class GeminiAIProvider:
    api_key: str
    model: str
    provider_name: str = "gemini"
    configured: bool = True
    unavailable_reason: str | None = None
    timeout_seconds: int = DEFAULT_AI_TIMEOUT_SECONDS

    def complete_json(self, *, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\n{json.dumps(payload, indent=2)}"}],
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
                body = json.loads(response.read().decode("utf-8"))
            text = body.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
            parsed = json.loads(_strip_json_fences(text))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
            return {
                "ok": False,
                "error": _provider_error(exc, prefix="gemini request failed"),
                "provider": self.provider_name,
                "model": self.model,
            }
        return {"ok": True, "content": parsed, "provider": self.provider_name, "model": self.model}


@dataclass
class AnthropicAIProvider:
    api_key: str
    model: str
    provider_name: str = "anthropic"
    configured: bool = True
    unavailable_reason: str | None = None
    timeout_seconds: int = DEFAULT_AI_TIMEOUT_SECONDS
    max_tokens: int = DEFAULT_AI_MAX_TOKENS

    def complete_json(self, *, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": 0.1,
            "system": system_prompt,
            "messages": [{"role": "user", "content": json.dumps(payload, indent=2)}],
        }
        request = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
            text = ""
            for block in body.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    text += str(block.get("text") or "")
            parsed = json.loads(_strip_json_fences(text or "{}"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
            return {
                "ok": False,
                "error": _provider_error(exc, prefix="anthropic request failed"),
                "provider": self.provider_name,
                "model": self.model,
            }
        return {"ok": True, "content": parsed, "provider": self.provider_name, "model": self.model}


def normalize_analysis_mode(mode: str | None, *, legacy_ai_rerank: str | None = None) -> str:
    if legacy_ai_rerank and legacy_ai_rerank != "off":
        return "ai_review"
    chosen = str(mode or "deterministic").strip().lower()
    return chosen if chosen in ANALYSIS_MODES else "deterministic"


def normalize_ai_provider(provider: str | None, *, legacy_ai_rerank: str | None = None) -> str | None:
    if legacy_ai_rerank and legacy_ai_rerank != "off":
        return "openai" if legacy_ai_rerank == "openai" else "gemini"
    if provider is None:
        return None
    chosen = str(provider).strip().lower()
    return chosen if chosen in SUPPORTED_AI_PROVIDERS else None


def normalize_ai_providers(providers: str | list[str] | None, *, fallback_provider: str | None = None) -> list[str]:
    if isinstance(providers, str):
        raw = [item.strip().lower() for item in providers.split(",")]
    else:
        raw = [str(item).strip().lower() for item in (providers or [])]
    normalized = [item for item in raw if item in SUPPORTED_AI_PROVIDERS]
    if not normalized and fallback_provider:
        normalized = [fallback_provider]
    deduped: list[str] = []
    for provider in normalized:
        if provider not in deduped:
            deduped.append(provider)
    return deduped


def resolve_default_ai_provider() -> str | None:
    for provider in ("openai", "gemini", "anthropic", "generic"):
        if build_ai_provider(provider).configured:
            return provider
    return None


def build_ai_provider(
    provider: str | None,
    *,
    timeout_seconds: int = DEFAULT_AI_TIMEOUT_SECONDS,
    max_tokens: int = DEFAULT_AI_MAX_TOKENS,
) -> AIProvider:
    chosen = str(provider or resolve_default_ai_provider() or "").strip().lower()
    if chosen == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return UnavailableAIProvider("openai", unavailable_reason="OPENAI_API_KEY is not configured.")
        return OpenAICompatibleAIProvider(
            api_key=api_key,
            model=os.getenv("OPENAI_MODEL") or "gpt-4o-mini",
            base_url=os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1",
            provider_name="openai",
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
        )
    if chosen == "generic":
        api_key = os.getenv("TRADEBRUV_LLM_API_KEY")
        if not api_key:
            return UnavailableAIProvider("generic", unavailable_reason="TRADEBRUV_LLM_API_KEY is not configured.")
        return OpenAICompatibleAIProvider(
            api_key=api_key,
            model=os.getenv("TRADEBRUV_LLM_MODEL") or "gpt-4o-mini",
            base_url=os.getenv("TRADEBRUV_LLM_BASE_URL") or "https://api.openai.com/v1",
            provider_name="generic",
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
        )
    if chosen == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return UnavailableAIProvider("gemini", unavailable_reason="GEMINI_API_KEY is not configured.")
        return GeminiAIProvider(
            api_key=api_key,
            model=os.getenv("GEMINI_MODEL") or "gemini-1.5-flash",
            timeout_seconds=timeout_seconds,
        )
    if chosen == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return UnavailableAIProvider("anthropic", unavailable_reason="ANTHROPIC_API_KEY is not configured.")
        return AnthropicAIProvider(
            api_key=api_key,
            model=os.getenv("ANTHROPIC_MODEL") or "claude-3-5-sonnet-latest",
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
        )
    return UnavailableAIProvider(chosen or "unavailable", unavailable_reason="No supported AI provider is configured.")


def build_ai_health_report() -> dict[str, Any]:
    statuses = {
        provider: _provider_status(provider)
        for provider in ("openai", "gemini", "anthropic", "generic")
    }
    default_provider = resolve_default_ai_provider()
    return {
        "providers": statuses,
        "default_provider": default_provider or "none",
        "warning": "No AI keys configured." if not default_provider else "",
        "any_configured": bool(default_provider),
    }


def build_candidate_packet(decision: dict[str, Any]) -> dict[str, Any]:
    source_row = dict(decision.get("source_row") or {})
    current_price = _num(source_row.get("current_price"))
    packet = {
        "ticker": str(decision.get("ticker") or source_row.get("ticker") or "UNKNOWN").upper(),
        "company": decision.get("company") or source_row.get("company_name") or "unavailable",
        "deterministic_label": decision.get("actionability_label") or "Data Insufficient",
        "primary_action": decision.get("primary_action") or "Data Insufficient",
        "actionability_score": decision.get("actionability_score") or 0,
        "mover_quality_score": source_row.get("velocity_score") or decision.get("mover_score") or "unavailable",
        "price": source_row.get("current_price", "unavailable"),
        "percent_change": source_row.get("price_change_1d_pct", "unavailable"),
        "relative_volume": source_row.get("relative_volume_20d", "unavailable"),
        "dollar_volume": source_row.get("avg_dollar_volume20") or source_row.get("dollar_volume") or "unavailable",
        "ema_21": source_row.get("ema_21", "unavailable"),
        "ema_50": source_row.get("ema_50", "unavailable"),
        "ema_150": source_row.get("ema_150", "unavailable"),
        "ema_200": source_row.get("ema_200", "unavailable"),
        "price_vs_ema_21_pct": source_row.get("price_vs_ema_21_pct", "unavailable"),
        "price_vs_ema_50_pct": source_row.get("price_vs_ema_50_pct", "unavailable"),
        "price_vs_ema_150_pct": source_row.get("price_vs_ema_150_pct", "unavailable"),
        "price_vs_ema_200_pct": source_row.get("price_vs_ema_200_pct", "unavailable"),
        "signal_summary": source_row.get("signal_summary") or decision.get("actionability_reason") or "unavailable",
        "entry_or_trigger": decision.get("action_trigger") if decision.get("trigger_needed") else decision.get("entry_zone"),
        "stop_or_invalidation": decision.get("stop_loss") or decision.get("invalidation") or "unavailable",
        "tp1": decision.get("tp1", "unavailable"),
        "tp2": decision.get("tp2", "unavailable"),
        "risk_level": decision.get("risk_level") or source_row.get("risk_score") or "Unknown",
        "why_interesting": _clean_list(source_row.get("why_it_passed")) or [str(decision.get("reason") or decision.get("actionability_reason") or "unavailable")],
        "why_it_may_fail": _clean_list(source_row.get("why_it_could_fail")) or [str(decision.get("why_not") or "unavailable")],
        "source_groups": list(dict.fromkeys((decision.get("source_groups") or [decision.get("source_group")]) or [])),
        "event_catalyst_data": _compact_catalyst_items(source_row),
        "data_availability_notes": _clean_list(source_row.get("data_availability_notes")),
    }
    packet["explicit_missing_fields"] = _missing_fields(packet, current_price=current_price)
    return packet


def build_candidate_packets(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [build_candidate_packet(row) for row in decisions]


def shortlist_ai_candidates(payload: dict[str, Any], *, max_names: int = DEFAULT_AI_MAX_NAMES) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for key, limit in (
        ("fast_actionable_setups", 5),
        ("high_volume_mover_watch", 5),
        ("earnings_news_movers", 5),
        ("tracked_watchlist_setups", 5),
        ("long_term_research_candidates", 5),
    ):
        for row in payload.get(key, [])[:limit]:
            if isinstance(row, dict):
                candidates.append(row)
    if not candidates:
        candidates = [row for row in payload.get("decisions", []) if isinstance(row, dict)][:max_names]
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in candidates:
        ticker = str(row.get("ticker") or "").upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            deduped.append(row)
    return deduped[:max_names]


def review_candidates(
    decisions: list[dict[str, Any]],
    *,
    provider_name: str,
    ai_max_names: int = DEFAULT_AI_MAX_NAMES,
    timeout_seconds: int = DEFAULT_AI_TIMEOUT_SECONDS,
    max_tokens: int = DEFAULT_AI_MAX_TOKENS,
    cache: bool = True,
    force_refresh: bool = False,
    cache_dir: Path = DEFAULT_AI_CACHE_DIR,
) -> dict[str, Any]:
    provider = build_ai_provider(provider_name, timeout_seconds=timeout_seconds, max_tokens=max_tokens)
    reviewed_at = datetime.utcnow().isoformat() + "Z"
    selected = decisions[:ai_max_names]
    packets = build_candidate_packets(selected)
    review_map: dict[str, dict[str, Any]] = {}
    names_reviewed = 0
    unsupported_detected = 0
    downgraded = 0
    caution_flags = 0
    unavailable = []
    for decision, packet in zip(selected, packets):
        review = review_candidate_packet(
            packet,
            provider=provider,
            cache=cache,
            force_refresh=force_refresh,
            cache_dir=cache_dir,
            reviewed_at=reviewed_at,
        )
        ticker = str(packet.get("ticker"))
        review_map[ticker] = review
        names_reviewed += 1
        unsupported_detected += len(review.get("unsupported_claims") or [])
        downgraded += 1 if review.get("ai_final_view") == "downgrade" or review.get("deterministic_label_too_aggressive") else 0
        caution_flags += 1 if review.get("ai_caution_level") == "high" else 0
        if not review.get("available", True):
            unavailable.append(ticker)
    ai_agreed = [ticker for ticker, review in review_map.items() if review.get("ai_final_view") == "agree"]
    not_to_chase = [
        ticker
        for ticker, review in review_map.items()
        if review.get("suggested_user_action") == "avoid_chase" or review.get("ai_final_view") in {"downgrade", "avoid"}
    ]
    return {
        "enabled": True,
        "mode": "ai_review",
        "provider": provider.provider_name,
        "model": provider.model,
        "names_reviewed": names_reviewed,
        "downgraded": downgraded,
        "caution_flags": caution_flags,
        "top_ai_agreed_names": ai_agreed[:5],
        "names_ai_says_not_to_chase": not_to_chase[:5],
        "unsupported_claims_detected": unsupported_detected,
        "reviews_unavailable": unavailable,
        "reviews": review_map,
    }


def review_candidate_packet(
    packet: dict[str, Any],
    *,
    provider: AIProvider,
    cache: bool = True,
    force_refresh: bool = False,
    cache_dir: Path = DEFAULT_AI_CACHE_DIR,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    reviewed_at = reviewed_at or (datetime.utcnow().isoformat() + "Z")
    if not provider.configured:
        return unavailable_ai_review(provider, reason=provider.unavailable_reason or "Provider is unavailable.", packet=packet, reviewed_at=reviewed_at)
    cache_path = _cache_path(
        kind="review",
        ticker=str(packet.get("ticker") or "UNKNOWN"),
        provider=provider.provider_name,
        model=provider.model,
        payload=packet,
        prompt_version=AI_REVIEW_PROMPT_VERSION,
        cache_dir=cache_dir,
    )
    if cache and not force_refresh and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached["cached"] = True
        return cached
    prompt_payload = {
        "contract": {
            "required_keys": [
                "ai_final_view",
                "ai_caution_level",
                "bull_case",
                "bear_case",
                "what_would_make_me_buy",
                "what_would_make_me_wait",
                "what_would_make_me_avoid",
                "missing_evidence",
                "unsupported_claims",
                "deterministic_label_too_aggressive",
                "deterministic_label_too_conservative",
                "suggested_user_action",
                "ai_summary_one_liner",
                "confidence_reasoning",
            ],
            "allowed_final_views": list(AI_REVIEW_FINAL_VIEWS),
            "allowed_caution_levels": list(AI_CAUTION_LEVELS),
            "allowed_user_actions": list(AI_USER_ACTIONS),
        },
        "instructions": [
            "You are a second-pass analyst.",
            "You may only use the structured data provided.",
            "You must not invent catalysts, news, earnings, fundamentals, insider activity, or analyst changes.",
            "You must list missing evidence explicitly.",
            "You must not override hard deterministic risk gates.",
            "Return JSON only.",
        ],
        "candidate": packet,
    }
    completion = provider.complete_json(
        system_prompt=(
            "You are a second-pass stock research analyst. Use only the structured packet. "
            "Do not browse, do not infer hidden news, and do not invent unsupported claims. "
            "Do not convert deterministic avoid/risk gates into a bullish call. Return strict JSON only."
        ),
        payload=prompt_payload,
    )
    if not completion.get("ok"):
        return unavailable_ai_review(provider, reason=str(completion.get("error") or "Invalid response."), packet=packet, reviewed_at=reviewed_at)
    review = sanitize_ai_review(
        generated=completion.get("content") or {},
        packet=packet,
        provider=completion.get("provider") or provider.provider_name,
        model=completion.get("model") or provider.model,
        reviewed_at=reviewed_at,
    )
    if cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(review, indent=2), encoding="utf-8")
    return review


def sanitize_ai_review(
    *,
    generated: dict[str, Any],
    packet: dict[str, Any],
    provider: str,
    model: str,
    reviewed_at: str,
) -> dict[str, Any]:
    deterministic_label = str(packet.get("deterministic_label") or "Data Insufficient")
    generated_view = str(generated.get("ai_final_view") or "").strip().lower()
    ai_final_view = generated_view if generated_view in AI_REVIEW_FINAL_VIEWS else _fallback_final_view(deterministic_label)
    if deterministic_label == "Avoid / Do Not Chase":
        ai_final_view = "avoid"
    caution = str(generated.get("ai_caution_level") or "medium").strip().lower()
    ai_caution_level = caution if caution in AI_CAUTION_LEVELS else "medium"
    action = str(generated.get("suggested_user_action") or "").strip().lower()
    suggested_user_action = action if action in AI_USER_ACTIONS else _fallback_user_action(ai_final_view)
    response = {
        "available": True,
        "provider": provider,
        "model": model,
        "reviewed_at": reviewed_at,
        "ticker": packet.get("ticker"),
        "deterministic_label": deterministic_label,
        "ai_final_view": ai_final_view,
        "ai_caution_level": ai_caution_level,
        "bull_case": _clean_text(generated.get("bull_case")) or "The deterministic setup has some constructive signals, but the review is limited to the supplied packet.",
        "bear_case": _clean_text(generated.get("bear_case")) or "The packet does not prove enough to remove execution or trend risk.",
        "what_would_make_me_buy": _clean_text(generated.get("what_would_make_me_buy")) or "Only if the deterministic trigger and risk controls remain valid.",
        "what_would_make_me_wait": _clean_text(generated.get("what_would_make_me_wait")) or "Wait if the setup is extended or the trigger is still conditional.",
        "what_would_make_me_avoid": _clean_text(generated.get("what_would_make_me_avoid")) or "Avoid if the deterministic invalidation breaks or missing evidence remains unresolved.",
        "missing_evidence": _merge_unique(_clean_list(generated.get("missing_evidence")), list(packet.get("explicit_missing_fields") or [])),
        "unsupported_claims": _clean_list(generated.get("unsupported_claims")),
        "confidence_reasoning": _clean_text(generated.get("confidence_reasoning")) or "Confidence is based only on the supplied deterministic packet.",
        "deterministic_label_too_aggressive": bool(generated.get("deterministic_label_too_aggressive")),
        "deterministic_label_too_conservative": bool(generated.get("deterministic_label_too_conservative")),
        "suggested_user_action": suggested_user_action,
        "ai_summary_one_liner": _clean_text(generated.get("ai_summary_one_liner")) or "AI review stayed inside the deterministic packet and did not add new evidence.",
    }
    response["unsupported_claims"] = _merge_unique(response["unsupported_claims"], detect_unsupported_claims(response, packet))
    guardrail = validate_ai_output(
        {
            "bear_case": [response["bear_case"]],
            "risk_manager_view": response["what_would_make_me_avoid"],
            "missing_data": response["missing_evidence"],
            "events_to_watch": [response["what_would_make_me_buy"], response["what_would_make_me_wait"]],
            "what_would_change_my_mind": [response["what_would_make_me_buy"]],
            "final_recommendation_label": deterministic_label,
            "safety_notes": ["Research support only. No trade execution or order placement."],
        },
        _packet_to_guardrail_row(packet),
    )
    response["unsupported_claims_detected"] = bool(response["unsupported_claims"]) or bool(guardrail.get("unsupported_claims_detected"))
    response["ai_guardrail_warnings"] = guardrail.get("ai_guardrail_warnings") or []
    return response


def unavailable_ai_review(provider: AIProvider, *, reason: str, packet: dict[str, Any], reviewed_at: str) -> dict[str, Any]:
    return {
        "available": False,
        "provider": provider.provider_name,
        "model": provider.model,
        "reviewed_at": reviewed_at,
        "ticker": packet.get("ticker"),
        "deterministic_label": packet.get("deterministic_label"),
        "ai_final_view": "needs_more_research",
        "ai_caution_level": "high",
        "bull_case": "AI review unavailable.",
        "bear_case": reason,
        "what_would_make_me_buy": "Run deterministic review only until an AI provider is configured.",
        "what_would_make_me_wait": "Wait until the AI provider is configured or the request succeeds.",
        "what_would_make_me_avoid": "Avoid treating missing AI output as additional conviction.",
        "missing_evidence": _merge_unique([reason], list(packet.get("explicit_missing_fields") or [])),
        "unsupported_claims": [],
        "confidence_reasoning": "No AI review was available, so confidence stays with the deterministic engine only.",
        "deterministic_label_too_aggressive": False,
        "deterministic_label_too_conservative": False,
        "suggested_user_action": "research",
        "ai_summary_one_liner": reason,
        "unsupported_claims_detected": False,
        "ai_guardrail_warnings": [],
    }


def run_ai_committee(
    decisions: list[dict[str, Any]],
    *,
    providers: list[str],
    ai_max_names: int = DEFAULT_AI_MAX_NAMES,
    timeout_seconds: int = DEFAULT_AI_TIMEOUT_SECONDS,
    max_tokens: int = DEFAULT_AI_MAX_TOKENS,
    cache: bool = True,
    force_refresh: bool = False,
    cache_dir: Path = DEFAULT_AI_CACHE_DIR,
) -> dict[str, Any]:
    selected = decisions[:ai_max_names]
    packets = build_candidate_packets(selected)
    provider_clients = [build_ai_provider(name, timeout_seconds=timeout_seconds, max_tokens=max_tokens) for name in providers]
    per_ticker_reviews: dict[str, dict[str, Any]] = {}
    models_used: list[str] = []
    models_failed: list[dict[str, str]] = []
    for packet in packets:
        ticker = str(packet.get("ticker"))
        reviews: list[dict[str, Any]] = []
        for client in provider_clients:
            review = review_candidate_packet(
                packet,
                provider=client,
                cache=cache,
                force_refresh=force_refresh,
                cache_dir=cache_dir,
            )
            reviews.append(review)
            model_name = f"{review.get('provider')}:{review.get('model')}"
            if review.get("available"):
                if model_name not in models_used:
                    models_used.append(model_name)
            else:
                models_failed.append({"provider": str(review.get("provider")), "reason": str(review.get("bear_case"))})
        available_reviews = [review for review in reviews if review.get("available")]
        per_ticker_reviews[ticker] = _aggregate_committee_reviews(packet, reviews=available_reviews or reviews)
    names_all_models_like = [
        ticker for ticker, item in per_ticker_reviews.items()
        if item.get("review_count", 0) > 0 and item.get("per_ticker_votes", {}).get("bullish", 0) == item.get("review_count", 0)
    ]
    names_all_models_warn_against = [
        ticker for ticker, item in per_ticker_reviews.items()
        if item.get("review_count", 0) > 0 and item.get("per_ticker_votes", {}).get("avoid", 0) == item.get("review_count", 0)
    ]
    consensus_candidates = [
        ticker for ticker, item in per_ticker_reviews.items()
        if item.get("committee_label") == "bullish"
    ]
    disagreement_candidates = [
        ticker for ticker, item in per_ticker_reviews.items()
        if int(sum(1 for count in (item.get("per_ticker_votes") or {}).values() if count)) > 1
    ]
    top_watchlist = [
        ticker for ticker, item in per_ticker_reviews.items()
        if item.get("committee_label") in {"bullish", "cautious"}
    ][:5]
    return {
        "enabled": True,
        "mode": "ai_committee",
        "models_used": models_used,
        "models_failed": models_failed,
        "consensus_candidates": consensus_candidates,
        "disagreement_candidates": disagreement_candidates,
        "names_all_models_like": names_all_models_like,
        "names_all_models_warn_against": names_all_models_warn_against,
        "top_ai_consensus_watchlist": top_watchlist,
        "committee_summary": _committee_summary(
            consensus_candidates=consensus_candidates,
            disagreement_candidates=disagreement_candidates,
            failed=models_failed,
        ),
        "per_ticker_reviews": per_ticker_reviews,
    }


def build_brief_payload(
    payload: dict[str, Any],
    *,
    provider_name: str,
    timeout_seconds: int = DEFAULT_AI_TIMEOUT_SECONDS,
    max_tokens: int = DEFAULT_AI_MAX_TOKENS,
    cache: bool = True,
    force_refresh: bool = False,
    cache_dir: Path = DEFAULT_AI_CACHE_DIR,
) -> dict[str, Any]:
    provider = build_ai_provider(provider_name, timeout_seconds=timeout_seconds, max_tokens=max_tokens)
    brief_input = {
        "contract": {
            "required_keys": [
                "market_setup_summary",
                "top_deterministic_setups",
                "top_mover_opportunities",
                "top_risks_or_chase_warnings",
                "best_tracked_ticker_setup",
                "themes_showing_strength",
                "names_needing_deeper_research",
                "what_not_to_chase_today",
                "final_watchlist_for_tomorrow",
                "brief_one_liner",
            ],
        },
        "instructions": [
            "Based only on TradeBruv deterministic scan data.",
            "Do not invent any missing market, news, earnings, or fundamental context.",
            "Return JSON only.",
        ],
        "daily_scan": _brief_scan_packet(payload),
    }
    cache_path = _cache_path(
        kind="brief",
        ticker="daily",
        provider=provider.provider_name,
        model=provider.model,
        payload=brief_input,
        prompt_version=AI_BRIEF_PROMPT_VERSION,
        cache_dir=cache_dir,
    )
    if cache and not force_refresh and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    if not provider.configured:
        result = {
            "available": False,
            "provider": provider.provider_name,
            "model": provider.model,
            "warning": provider.unavailable_reason or "AI provider unavailable.",
            "based_only_on": "TradeBruv deterministic scan data.",
        }
        if cache:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    completion = provider.complete_json(
        system_prompt=(
            "You are writing a concise daily brief from structured TradeBruv scan data only. "
            "Do not add outside context. Return strict JSON only."
        ),
        payload=brief_input,
    )
    if not completion.get("ok"):
        result = {
            "available": False,
            "provider": provider.provider_name,
            "model": provider.model,
            "warning": str(completion.get("error") or "AI brief failed."),
            "based_only_on": "TradeBruv deterministic scan data.",
        }
    else:
        content = completion.get("content") or {}
        result = {
            "available": True,
            "provider": completion.get("provider"),
            "model": completion.get("model"),
            "based_only_on": "TradeBruv deterministic scan data.",
            "market_setup_summary": _clean_text(content.get("market_setup_summary")) or "No brief summary returned.",
            "top_deterministic_setups": _clean_list(content.get("top_deterministic_setups")),
            "top_mover_opportunities": _clean_list(content.get("top_mover_opportunities")),
            "top_risks_or_chase_warnings": _clean_list(content.get("top_risks_or_chase_warnings")),
            "best_tracked_ticker_setup": _clean_text(content.get("best_tracked_ticker_setup")) or "None.",
            "themes_showing_strength": _clean_list(content.get("themes_showing_strength")),
            "names_needing_deeper_research": _clean_list(content.get("names_needing_deeper_research")),
            "what_not_to_chase_today": _clean_list(content.get("what_not_to_chase_today")),
            "final_watchlist_for_tomorrow": _clean_list(content.get("final_watchlist_for_tomorrow")),
            "brief_one_liner": _clean_text(content.get("brief_one_liner")) or "Based only on TradeBruv deterministic scan data.",
        }
    if cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def build_brief_markdown(brief: dict[str, Any]) -> str:
    lines = [
        "# TradeBruv Daily AI Brief",
        "",
        "Based only on TradeBruv deterministic scan data.",
        "",
        f"- Provider: {brief.get('provider', 'unavailable')}",
        f"- Model: {brief.get('model', 'unavailable')}",
    ]
    if not brief.get("available"):
        lines.extend(["", f"- Warning: {brief.get('warning', 'AI brief unavailable.')}"])
        return "\n".join(lines)
    lines.extend(["", "## Market Setup Summary", brief.get("market_setup_summary") or "No summary.", ""])
    for title, key in (
        ("Top Deterministic Setups", "top_deterministic_setups"),
        ("Top Mover Opportunities", "top_mover_opportunities"),
        ("Top Risks / Chase Warnings", "top_risks_or_chase_warnings"),
        ("Themes Showing Strength", "themes_showing_strength"),
        ("Names Needing Deeper Research", "names_needing_deeper_research"),
        ("What Not To Chase Today", "what_not_to_chase_today"),
        ("Final Watchlist For Tomorrow", "final_watchlist_for_tomorrow"),
    ):
        lines.extend([f"## {title}"])
        items = brief.get(key) or []
        if not items:
            lines.append("- None.")
        else:
            for item in items:
                lines.append(f"- {item}")
        lines.append("")
    lines.extend(["## Best Tracked Ticker Setup", str(brief.get("best_tracked_ticker_setup") or "None."), "", str(brief.get("brief_one_liner") or "")])
    return "\n".join(lines)


def write_brief_outputs(brief: dict[str, Any], *, output_dir: Path = DEFAULT_AI_OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "daily_ai_brief.json"
    md_path = output_dir / "daily_ai_brief.md"
    json_path.write_text(json.dumps(brief, indent=2), encoding="utf-8")
    md_path.write_text(build_brief_markdown(brief), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(md_path)}


def write_single_ticker_review(review: dict[str, Any], *, ticker: str, output_dir: Path = DEFAULT_AI_OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{ticker.upper()}_ai_review"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(review, indent=2), encoding="utf-8")
    md_path.write_text(_single_review_markdown(review), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(md_path)}


def _single_review_markdown(review: dict[str, Any]) -> str:
    lines = [
        f"# {review.get('ticker', 'Ticker')} AI Review",
        "",
        "Based only on TradeBruv deterministic scan data.",
        "",
        f"- Provider: {review.get('provider', 'unavailable')}",
        f"- Model: {review.get('model', 'unavailable')}",
        f"- Deterministic label: {review.get('deterministic_label', 'unavailable')}",
        f"- AI final view: {review.get('ai_final_view', 'unavailable')}",
        f"- AI caution: {review.get('ai_caution_level', 'unavailable')}",
        "",
        "## Bull Case",
        str(review.get("bull_case") or "None."),
        "",
        "## Bear Case",
        str(review.get("bear_case") or "None."),
        "",
        "## What Would Make Me Buy",
        str(review.get("what_would_make_me_buy") or "None."),
        "",
        "## What Would Make Me Wait",
        str(review.get("what_would_make_me_wait") or "None."),
        "",
        "## What Would Make Me Avoid",
        str(review.get("what_would_make_me_avoid") or "None."),
    ]
    for title, key in (("Missing Evidence", "missing_evidence"), ("Unsupported Claims", "unsupported_claims")):
        lines.extend(["", f"## {title}"])
        items = review.get(key) or []
        if not items:
            lines.append("- None.")
        else:
            for item in items:
                lines.append(f"- {item}")
    lines.extend(["", "## Summary", str(review.get("ai_summary_one_liner") or "")])
    return "\n".join(lines)


def _aggregate_committee_reviews(packet: dict[str, Any], *, reviews: list[dict[str, Any]]) -> dict[str, Any]:
    votes = {key: 0 for key in COMMITTEE_VOTES}
    for review in reviews:
        votes[_review_vote(review, deterministic_label=str(packet.get("deterministic_label") or ""))] += 1
    committee_label = max(votes, key=votes.get) if reviews else "needs_more_data"
    review_count = len([review for review in reviews if review.get("available")])
    consensus = {
        "bullish": committee_label == "bullish",
        "cautious": committee_label == "cautious",
        "avoid": committee_label == "avoid",
        "needs_more_data": committee_label == "needs_more_data",
    }
    summary = _committee_row_summary(packet, votes=votes, committee_label=committee_label)
    return {
        "ticker": packet.get("ticker"),
        "deterministic_label": packet.get("deterministic_label"),
        "review_count": review_count,
        "per_ticker_votes": votes,
        "committee_label": committee_label,
        "consensus": consensus,
        "committee_summary": summary,
        "reviews": reviews,
        "row_review": {
            "available": bool(reviews),
            "provider": "committee",
            "model": ", ".join(sorted({str(review.get("provider")) for review in reviews if review.get("provider")})),
            "reviewed_at": datetime.utcnow().isoformat() + "Z",
            "ticker": packet.get("ticker"),
            "deterministic_label": packet.get("deterministic_label"),
            "ai_final_view": "agree" if committee_label == "bullish" else "avoid" if committee_label == "avoid" else "needs_more_research" if committee_label == "needs_more_data" else "downgrade",
            "ai_caution_level": "low" if committee_label == "bullish" else "high" if committee_label == "avoid" else "medium",
            "bull_case": summary if committee_label == "bullish" else "Committee did not form a clean bullish consensus.",
            "bear_case": summary if committee_label in {"avoid", "cautious"} else "Committee did not highlight a dominant bear case.",
            "what_would_make_me_buy": "Only if the deterministic setup remains valid and committee concerns resolve.",
            "what_would_make_me_wait": "Wait when committee votes are mixed or more confirmation is needed.",
            "what_would_make_me_avoid": "Avoid if the committee view stays negative or the deterministic setup breaks.",
            "missing_evidence": _merge_unique(*(review.get("missing_evidence") or [] for review in reviews)) if reviews else [],
            "unsupported_claims": _merge_unique(*(review.get("unsupported_claims") or [] for review in reviews)) if reviews else [],
            "confidence_reasoning": summary,
            "deterministic_label_too_aggressive": votes["avoid"] > 0 or votes["cautious"] > votes["bullish"],
            "deterministic_label_too_conservative": False,
            "suggested_user_action": "watch" if committee_label == "bullish" else "avoid_chase" if committee_label == "cautious" else "ignore" if committee_label == "avoid" else "research",
            "ai_summary_one_liner": summary,
            "unsupported_claims_detected": any(bool(review.get("unsupported_claims_detected")) for review in reviews),
            "ai_guardrail_warnings": _merge_unique(*(review.get("ai_guardrail_warnings") or [] for review in reviews)) if reviews else [],
        },
    }


def detect_unsupported_claims(review: dict[str, Any], packet: dict[str, Any]) -> list[str]:
    text = json.dumps(review, sort_keys=True).lower()
    supplied = json.dumps(packet, sort_keys=True).lower()
    claims: list[str] = []
    url_claims = validate_ai_output(review, _packet_to_guardrail_row(packet)).get("ai_guardrail_warnings") or []
    if any("url" in item.lower() for item in url_claims):
        claims.append("AI referenced a URL that was not present in the deterministic packet.")
    for token, label in (
        ("earnings", "AI mentioned earnings without supplied earnings evidence."),
        ("news", "AI mentioned news without supplied news evidence."),
        ("insider", "AI mentioned insider activity without supplied insider evidence."),
        ("analyst", "AI mentioned analyst activity without supplied analyst evidence."),
        ("upgrade", "AI mentioned an analyst upgrade/downgrade without supplied evidence."),
        ("fundamental", "AI mentioned fundamentals without supplied evidence."),
        ("revenue", "AI mentioned revenue without supplied evidence."),
        ("margin", "AI mentioned margins without supplied evidence."),
    ):
        if token in text and token not in supplied:
            claims.append(label)
    return list(dict.fromkeys(claims))


def _provider_status(provider: str) -> AIProviderStatus:
    client = build_ai_provider(provider)
    base_url = ""
    if isinstance(client, OpenAICompatibleAIProvider):
        base_url = client.base_url
    return AIProviderStatus(
        provider=provider,
        configured=client.configured,
        model=client.model,
        reason=client.unavailable_reason or "",
        base_url=base_url,
    )


def _packet_to_guardrail_row(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "current_price": packet.get("price"),
        "status_label": "Avoid" if packet.get("deterministic_label") == "Avoid / Do Not Chase" else "Watch",
        "catalyst_items": packet.get("event_catalyst_data") or [],
    }


def _fallback_final_view(deterministic_label: str) -> str:
    if deterministic_label == "Avoid / Do Not Chase":
        return "avoid"
    if deterministic_label in {"Breakout Actionable Today", "Momentum Actionable Today", "Pullback Actionable Today"}:
        return "agree"
    if deterministic_label in {"Watch for Better Entry", "Slow Compounder Watch", "High-Volume Mover Watch"}:
        return "upgrade_watch_only"
    return "needs_more_research"


def _fallback_user_action(ai_final_view: str) -> str:
    return {
        "agree": "watch",
        "downgrade": "wait_for_pullback",
        "upgrade_watch_only": "watch",
        "needs_more_research": "research",
        "avoid": "ignore",
    }.get(ai_final_view, "research")


def _compact_catalyst_items(source_row: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in (source_row.get("catalyst_items") or [])[:5]:
        if not isinstance(raw, dict):
            continue
        items.append(
            {
                "source_type": raw.get("source_type"),
                "headline": raw.get("headline"),
                "summary": raw.get("summary"),
                "timestamp": raw.get("timestamp"),
                "catalyst_type": raw.get("catalyst_type"),
                "source_url": raw.get("source_url"),
            }
        )
    return items


def _missing_fields(packet: dict[str, Any], *, current_price: float | None) -> list[str]:
    missing: list[str] = []
    for key in (
        "price",
        "relative_volume",
        "dollar_volume",
        "ema_21",
        "ema_50",
        "ema_150",
        "ema_200",
        "entry_or_trigger",
        "stop_or_invalidation",
    ):
        if packet.get(key) in (None, "", "unavailable"):
            missing.append(key)
    if current_price is None:
        missing.append("validated price")
    for note in packet.get("data_availability_notes") or []:
        if "unavailable" in str(note).lower():
            missing.append(str(note))
    return list(dict.fromkeys(missing))


def _cache_path(
    *,
    kind: str,
    ticker: str,
    provider: str,
    model: str,
    payload: dict[str, Any],
    prompt_version: str,
    cache_dir: Path,
) -> Path:
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    filename = f"{kind}_{ticker}_{provider}_{_safe_name(model)}_{prompt_version}_{payload_hash}.json"
    return cache_dir / filename


def _safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in text)[:80]


def _provider_error(exc: Exception, *, prefix: str) -> str:
    return f"{prefix}: {redact_secrets(exc)}"


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return " ".join(text.split())


def _clean_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item for item in (_clean_text(item) for item in value) if item]
    if value in (None, "", "unavailable"):
        return []
    return [_clean_text(value)]


def _merge_unique(*groups: list[str] | tuple[str, ...]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for item in group:
            clean = _clean_text(item)
            if clean and clean not in merged:
                merged.append(clean)
    return merged


def _num(value: Any) -> float | None:
    try:
        if value in (None, "", "unavailable"):
            raise ValueError
        return float(value)
    except (TypeError, ValueError):
        return None


def _strip_json_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    return cleaned


def _review_vote(review: dict[str, Any], *, deterministic_label: str) -> str:
    final_view = str(review.get("ai_final_view") or "")
    if final_view == "avoid":
        return "avoid"
    if final_view == "needs_more_research":
        return "needs_more_data"
    if final_view in {"downgrade", "upgrade_watch_only"}:
        return "cautious"
    if final_view == "agree":
        if deterministic_label in {"Watch for Better Entry", "Slow Compounder Watch", "High-Volume Mover Watch"}:
            return "cautious"
        if deterministic_label == "Avoid / Do Not Chase":
            return "avoid"
        return "bullish"
    return "needs_more_data"


def _committee_row_summary(packet: dict[str, Any], *, votes: dict[str, int], committee_label: str) -> str:
    ticker = packet.get("ticker")
    if committee_label == "bullish":
        return f"{ticker}: committee mostly agrees the deterministic setup is one of the stronger names, but only within the supplied evidence."
    if committee_label == "avoid":
        return f"{ticker}: committee consensus leans away from chasing or acting because the packet shows too much unresolved risk."
    if committee_label == "cautious":
        return f"{ticker}: committee sees some merit, but the balance of evidence argues for patience rather than aggression."
    return f"{ticker}: committee needs more confirmation because the supplied packet leaves too many open questions."


def _committee_summary(*, consensus_candidates: list[str], disagreement_candidates: list[str], failed: list[dict[str, str]]) -> str:
    if consensus_candidates:
        return (
            f"Committee found {len(consensus_candidates)} consensus watchlist name(s)"
            f"{' while some providers failed gracefully' if failed else ''}."
        )
    if disagreement_candidates:
        return "Committee was mixed, so deterministic output should stay primary."
    if failed:
        return "Committee providers were unavailable, so deterministic output remains untouched."
    return "Committee did not find strong incremental evidence beyond the deterministic scan."


def _brief_scan_packet(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "analysis_date": payload.get("analysis_date"),
        "provider": payload.get("provider"),
        "market_regime": payload.get("market_regime"),
        "top_candidate": payload.get("top_candidate"),
        "fast_actionable_setups": payload.get("fast_actionable_setups", [])[:5],
        "high_volume_movers": payload.get("high_volume_movers", [])[:5],
        "watch_candidates": payload.get("watch_candidates", [])[:5],
        "avoid_candidates": payload.get("avoid_candidates", [])[:5],
        "best_tracked_setup": payload.get("best_tracked_setup"),
        "strong_themes": payload.get("strong_themes", [])[:5],
        "long_term_research_candidates": payload.get("long_term_research_candidates", [])[:5],
        "top_gainers": payload.get("top_gainers", [])[:5],
        "breakout_volume": payload.get("breakout_volume", [])[:5],
    }
