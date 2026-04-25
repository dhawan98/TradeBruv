from __future__ import annotations

import re
from typing import Any


GUARANTEED_PATTERNS = ("guaranteed", "risk-free", "can't lose", "cannot lose", "sure thing", "will definitely")
ORDER_LANGUAGE = ("buy now", "sell now", "place an order", "market order", "limit order", "execute the trade")
SOURCE_URL_RE = re.compile(r"https?://[^\s)]+", re.IGNORECASE)
PRICE_CLAIM_RE = re.compile(r"\b(current price|trading at|price is)\s+\$?\d+(\.\d+)?", re.IGNORECASE)


def validate_ai_output(ai_output: dict[str, Any], scanner_row: dict[str, Any] | None = None) -> dict[str, Any]:
    scanner_row = scanner_row or {}
    text = _flatten(ai_output)
    lower = text.lower()
    warnings: list[str] = []
    unsupported = False

    if any(pattern in lower for pattern in GUARANTEED_PATTERNS):
        warnings.append("AI output used guaranteed/profit-certainty language.")
        unsupported = True
    if any(pattern in lower for pattern in ORDER_LANGUAGE):
        warnings.append("AI output used order-placement language; TradeBruv is research support only.")
        unsupported = True
    source_urls = SOURCE_URL_RE.findall(text)
    supplied_urls = _supplied_urls(scanner_row)
    invented_urls = [url for url in source_urls if url not in supplied_urls]
    if invented_urls:
        warnings.append("AI output included URLs that were not present in supplied evidence.")
        unsupported = True
    if PRICE_CLAIM_RE.search(text) and scanner_row.get("current_price") in (None, "", "unavailable"):
        warnings.append("AI output claimed a current price when supplied evidence did not include one.")
        unsupported = True

    if not _has_risks(ai_output):
        warnings.append("AI output is missing explicit risk discussion.")
    if not _has_invalidation(ai_output):
        warnings.append("AI output is missing invalidation or a missing-invalidation note.")
    if not _has_missing_data(ai_output):
        warnings.append("AI output is missing missing-data notes.")
    if "research support" not in lower and "not trade execution" not in lower:
        warnings.append("AI output should label itself as research support.")

    ai_label = str(ai_output.get("final_recommendation_label", ""))
    if scanner_row.get("status_label") == "Avoid" and "Buy" in ai_label:
        warnings.append("AI recommendation conflicts with deterministic Avoid status.")
        unsupported = True

    quality = max(0, 100 - len(warnings) * 15)
    grounding = max(0, 100 - len(invented_urls) * 30 - (25 if unsupported else 0))
    return {
        "ai_guardrail_warnings": warnings,
        "ai_output_quality_score": quality,
        "evidence_grounding_score": grounding,
        "unsupported_claims_detected": unsupported,
    }


def _flatten(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten(item) for item in value)
    return str(value or "")


def _supplied_urls(scanner_row: dict[str, Any]) -> set[str]:
    urls: set[str] = set()
    for key in ("catalyst_items", "alternative_data_items"):
        items = scanner_row.get(key) or []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("source_url"):
                    urls.add(str(item["source_url"]))
    return urls


def _has_risks(ai_output: dict[str, Any]) -> bool:
    return bool(ai_output.get("bear_case") or ai_output.get("risk_manager_view") or ai_output.get("ai_guardrail_warnings"))


def _has_invalidation(ai_output: dict[str, Any]) -> bool:
    text = _flatten([ai_output.get("events_to_watch"), ai_output.get("what_would_change_my_mind"), ai_output.get("risk_manager_view")]).lower()
    return "invalidation" in text or "missing-invalidation" in text or "stop" in text


def _has_missing_data(ai_output: dict[str, Any]) -> bool:
    missing = ai_output.get("missing_data")
    return bool(missing) or "missing data" in _flatten(ai_output).lower()
