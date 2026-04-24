from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .indicators import clamp
from .models import CatalystItem, CatalystSnapshot, SecurityData, SocialAttentionSnapshot
from .providers import MarketDataProvider


CATALYST_TYPES = {
    "Earnings beat",
    "Guidance raise",
    "Analyst upgrade",
    "Estimate revision",
    "Major contract",
    "Product launch",
    "AI/data center narrative",
    "Semiconductor narrative",
    "Defense/geopolitical narrative",
    "Energy/nuclear narrative",
    "Financials/rate-cut narrative",
    "IPO/post-IPO narrative",
    "Regulatory/policy catalyst",
    "Insider/institutional activity",
    "Short squeeze / crowded repricing",
    "Social hype only",
    "Unknown/unconfirmed",
}

OFFICIAL_SOURCE_TYPES = {"sec_filing", "earnings", "analyst", "insider", "institutional"}
SOCIAL_SOURCE_TYPES = {"reddit", "twitter_x", "truth_social"}
NEWS_SOURCE_TYPES = {"news"}
SUPPORTED_SOURCE_TYPES = {
    "news",
    "reddit",
    "twitter_x",
    "truth_social",
    "sec_filing",
    "earnings",
    "analyst",
    "insider",
    "institutional",
    "manual",
}
NARRATIVE_TYPES = {
    "AI/data center narrative",
    "Semiconductor narrative",
    "Defense/geopolitical narrative",
    "Energy/nuclear narrative",
    "Financials/rate-cut narrative",
    "IPO/post-IPO narrative",
    "Regulatory/policy catalyst",
    "Short squeeze / crowded repricing",
}


@dataclass(frozen=True)
class CatalystLoadResult:
    items_by_ticker: dict[str, list[CatalystItem]]
    warnings: list[str]


class CatalystRepository:
    def __init__(self, items_by_ticker: dict[str, list[CatalystItem]] | None = None, warnings: list[str] | None = None) -> None:
        self.items_by_ticker = items_by_ticker or {}
        self.warnings = warnings or []

    def items_for(self, ticker: str) -> list[CatalystItem]:
        return list(self.items_by_ticker.get(ticker.upper(), []))


class CatalystOverlayProvider:
    """Adds manual catalyst/social items to an existing market data provider."""

    def __init__(self, base_provider: MarketDataProvider, repository: CatalystRepository) -> None:
        self.base_provider = base_provider
        self.repository = repository

    def get_security_data(self, ticker: str) -> SecurityData:
        security = self.base_provider.get_security_data(ticker)
        items = self.repository.items_for(ticker)
        if not items:
            return security

        catalyst = _merge_catalyst_snapshot(security, items)
        social_attention = _merge_social_attention(security, items)
        tags = sorted(
            dict.fromkeys(
                [
                    *security.catalyst_tags,
                    *(item.catalyst_type for item in items if item.catalyst_type != "Unknown/unconfirmed"),
                ]
            )
        )
        notes = [
            *security.data_notes,
            f"Manual catalyst overlay loaded {len(items)} source item(s).",
        ]
        return replace(
            security,
            catalyst=catalyst,
            social_attention=social_attention,
            catalyst_items=items,
            catalyst_tags=tags,
            data_notes=notes,
        )


def load_catalyst_repository(path: Path | None) -> CatalystRepository:
    if path is None:
        return CatalystRepository()
    result = load_catalyst_items(path)
    return CatalystRepository(result.items_by_ticker, result.warnings)


def load_catalyst_items(path: Path) -> CatalystLoadResult:
    if not path.exists():
        return CatalystLoadResult({}, [f"Catalyst file missing: {path}"])
    if path.suffix.lower() == ".json":
        rows = _read_json_rows(path)
    else:
        rows = _read_csv_rows(path)
    return _parse_rows(rows, source_path=path)


def build_catalyst_intelligence(
    *,
    security: SecurityData,
    features: Any,
    analysis_date: date,
) -> tuple[dict[str, Any], list[str]]:
    items = _all_catalyst_items(security)
    warnings: list[str] = []
    price_confirms = bool(
        features.volume_confirmation
        and (
            features.return_5d is not None
            and features.return_5d > 0
            or features.close_near_week_high
            or features.breakout_confirmed
        )
    )
    official = any(_is_official(item) for item in items) or bool(
        security.catalyst
        and security.catalyst.has_catalyst
        and not security.catalyst.hype_risk
        and security.catalyst.price_reaction_positive
    )
    narrative = any(item.catalyst_type in NARRATIVE_TYPES for item in items)
    social_items = [item for item in items if item.source_type in SOCIAL_SOURCE_TYPES]
    news_items = [item for item in items if item.source_type in NEWS_SOURCE_TYPES]
    hype = any(_is_hype_item(item) for item in items) or bool(security.catalyst and security.catalyst.hype_risk)
    attention_count = sum(item.attention_count or 0 for item in social_items)
    velocity_values = [item.attention_velocity for item in social_items if item.attention_velocity is not None]
    social_velocity = max(velocity_values) if velocity_values else (
        security.social_attention.attention_velocity if security.social_attention else None
    )
    attention_spike = any(bool(item.attention_spike) for item in social_items) or bool(
        social_velocity is not None and social_velocity >= 1.2
    )
    low_float = bool(
        security.short_interest
        and security.short_interest.float_shares is not None
        and security.short_interest.float_shares <= 50_000_000
    )
    pump_risk = any(bool(item.pump_risk) for item in items) or bool(
        attention_spike
        and low_float
        and (features.return_5d is not None and features.return_5d >= 0.20 or features.extreme_overextension)
    )

    recency = _recency_label(items, analysis_date)
    sentiment_label = _sentiment_label(items, security)
    social_score = _attention_score(social_items, security.social_attention)
    news_score = _attention_score(news_items, None)
    score = _catalyst_score(
        official=official,
        narrative=narrative,
        social_score=social_score,
        news_score=news_score,
        price_confirms=price_confirms,
        hype=hype,
        stale=recency == "Stale",
    )
    quality = _quality_label(
        available=bool(items or security.catalyst),
        official=official,
        narrative=narrative,
        social_items=bool(social_items),
        price_confirms=price_confirms,
        hype=hype or pump_risk,
    )
    catalyst_type = _dominant_type(items, security.catalyst_tags)
    source_urls = sorted({item.source_url for item in items if item.source_url})
    source_timestamps = sorted({item.timestamp for item in items if item.timestamp})
    provider_notes = _provider_notes(security, items)

    if not items and not security.catalyst:
        warnings.append("Catalyst unavailable.")
    if items and not source_urls:
        warnings.append("Catalyst source URL unavailable.")
    if items and not source_timestamps:
        warnings.append("Catalyst timestamp unavailable.")
    if recency == "Stale":
        warnings.append("Catalyst is stale.")
    if social_items and not official and not narrative:
        warnings.append("Social-only hype risk is present.")
    if social_items and not price_confirms:
        warnings.append("Social/news attention is not confirmed by price and volume.")
    if news_items and not price_confirms:
        warnings.append("News attention is not confirmed by price action.")
    if attention_spike and not features.volume_confirmation:
        warnings.append("Attention spike is not confirmed by volume.")
    if (features.return_5d is not None and features.return_5d >= 0.12 or features.unusual_volume) and not official:
        warnings.append("Price spike does not have an official catalyst.")
    if pump_risk:
        warnings.append("Low-float social spike creates pump risk.")
    if any(item.source_type == "truth_social" for item in items) and not official:
        warnings.append("Political/policy mention is indirect unless tied to the company.")

    return {
        "catalyst_items": [item.to_dict() for item in items],
        "catalyst_score": score,
        "catalyst_quality": quality,
        "catalyst_type": catalyst_type,
        "catalyst_source_count": len(items),
        "catalyst_recency": recency,
        "official_catalyst_found": official,
        "narrative_catalyst_found": narrative,
        "hype_catalyst_found": hype,
        "social_attention_available": bool(security.social_attention or social_items),
        "social_attention_score": social_score,
        "social_attention_velocity": _format_number(social_velocity),
        "news_attention_score": news_score,
        "news_sentiment_label": sentiment_label,
        "source_urls": source_urls,
        "source_timestamps": source_timestamps,
        "source_provider_notes": provider_notes,
        "catalyst_data_available": bool(items or security.catalyst or security.social_attention),
        "catalyst_data_missing_reason": "unavailable" if (items or security.catalyst or security.social_attention) else "No catalyst/news/social evidence was provided.",
        "price_volume_confirms_catalyst": price_confirms,
        "attention_spike": attention_spike,
        "hype_risk": hype,
        "pump_risk": pump_risk,
    }, sorted(dict.fromkeys(warnings))


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_json_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("items", payload.get("catalysts", []))
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _parse_rows(rows: Iterable[dict[str, Any]], *, source_path: Path) -> CatalystLoadResult:
    warnings: list[str] = []
    seen: set[tuple[str, str, str, str]] = set()
    items_by_ticker: dict[str, list[CatalystItem]] = {}
    for line_number, row in enumerate(rows, start=2):
        try:
            item = _parse_row(row)
        except ValueError as exc:
            warnings.append(f"{source_path}:{line_number}: skipped bad catalyst row: {exc}")
            continue
        dedupe_key = (
            item.ticker,
            item.source_url or "",
            item.headline or item.summary or "",
            item.timestamp or "",
        )
        if dedupe_key in seen:
            warnings.append(f"{source_path}:{line_number}: skipped duplicate catalyst row for {item.ticker}.")
            continue
        seen.add(dedupe_key)
        items_by_ticker.setdefault(item.ticker, []).append(item)
    return CatalystLoadResult(items_by_ticker, warnings)


def _parse_row(row: dict[str, Any]) -> CatalystItem:
    ticker = str(row.get("ticker", "")).strip().upper()
    if not ticker:
        raise ValueError("ticker is required")
    source_type = str(row.get("source_type", "manual")).strip().lower() or "manual"
    if source_type not in SUPPORTED_SOURCE_TYPES:
        source_type = "manual"
    timestamp = _clean(row.get("timestamp"))
    if timestamp:
        _parse_timestamp(timestamp)
    catalyst_type = _normalize_catalyst_type(row.get("catalyst_type"))
    return CatalystItem(
        ticker=ticker,
        source_type=source_type,
        source_name=_clean(row.get("source_name")),
        source_url=_clean(row.get("source_url")),
        timestamp=timestamp,
        headline=_clean(row.get("headline")),
        summary=_clean(row.get("summary")),
        sentiment=_clean(row.get("sentiment")),
        catalyst_type=catalyst_type,
        attention_count=_to_int(row.get("attention_count")),
        attention_velocity=_to_float(row.get("attention_velocity")),
        official_source=_to_bool(row.get("official_source")),
        confidence=_to_float(row.get("confidence")),
        notes=_clean(row.get("notes")),
        source_platform=source_type if source_type in SOCIAL_SOURCE_TYPES else None,
        official_or_verified=_to_bool(row.get("official_or_verified")),
        attention_spike=_to_bool(row.get("attention_spike")),
        hype_risk=_to_bool(row.get("hype_risk")),
        pump_risk=_to_bool(row.get("pump_risk")),
    )


def _merge_catalyst_snapshot(security: SecurityData, items: list[CatalystItem]) -> CatalystSnapshot:
    base = security.catalyst
    official = any(_is_official(item) for item in items)
    hype = any(_is_hype_item(item) for item in items)
    positive = any((item.sentiment or "").lower() in {"positive", "bullish"} for item in items)
    summary = " | ".join((item.headline or item.summary or item.catalyst_type) for item in items[:3])
    return CatalystSnapshot(
        has_catalyst=True,
        description=summary or (base.description if base else None),
        price_reaction_positive=base.price_reaction_positive if base else positive or None,
        volume_confirmation=base.volume_confirmation if base else None,
        holds_gains=base.holds_gains if base else None,
        hype_risk=(base.hype_risk if base and base.hype_risk is not None else hype),
        catalyst_tags=tuple(sorted(dict.fromkeys([*(base.catalyst_tags if base else ()), *(item.catalyst_type for item in items)]))),
    )


def _merge_social_attention(security: SecurityData, items: list[CatalystItem]) -> SocialAttentionSnapshot | None:
    social_items = [item for item in items if item.source_type in SOCIAL_SOURCE_TYPES]
    news_items = [item for item in items if item.source_type == "news"]
    if not social_items and not news_items:
        return security.social_attention
    base = security.social_attention
    reddit = _max_optional(_sum_attention(social_items, "reddit"), base.reddit_mention_count if base else None)
    twitter = _max_optional(_sum_attention(social_items, "twitter_x"), base.twitter_mention_count if base else None)
    truth = any(item.source_type == "truth_social" for item in social_items) or (base.truth_social_mention_flag if base else False)
    news = _max_optional(len(news_items) if news_items else None, base.news_headline_count if base else None)
    velocities = [item.attention_velocity for item in [*social_items, *news_items] if item.attention_velocity is not None]
    return SocialAttentionSnapshot(
        reddit_mention_count=reddit,
        twitter_mention_count=twitter,
        truth_social_mention_flag=truth,
        news_headline_count=news,
        news_sentiment=_sentiment_float([*social_items, *news_items]) if [*social_items, *news_items] else (base.news_sentiment if base else None),
        catalyst_source="manual catalyst file",
        attention_velocity=max(velocities) if velocities else (base.attention_velocity if base else None),
    )


def _all_catalyst_items(security: SecurityData) -> list[CatalystItem]:
    items = list(security.catalyst_items)
    if security.catalyst and security.catalyst.has_catalyst and not items:
        items.append(
            CatalystItem(
                ticker=security.ticker,
                source_type="manual",
                source_name=security.provider_name,
                headline=security.catalyst.description,
                summary=security.catalyst.description,
                catalyst_type=_normalize_catalyst_type((security.catalyst.catalyst_tags or ("Unknown/unconfirmed",))[0]),
                official_source=not security.catalyst.hype_risk,
                hype_risk=security.catalyst.hype_risk,
            )
        )
    return items


def _quality_label(
    *,
    available: bool,
    official: bool,
    narrative: bool,
    social_items: bool,
    price_confirms: bool,
    hype: bool,
) -> str:
    if not available:
        return "Unavailable"
    if hype:
        return "Hype Risk"
    if official and price_confirms:
        return "Official Confirmed"
    if price_confirms:
        return "Price Confirmed"
    if narrative:
        return "Narrative Supported"
    if social_items:
        return "Social Attention Only"
    return "Unconfirmed"


def _catalyst_score(
    *,
    official: bool,
    narrative: bool,
    social_score: int,
    news_score: int,
    price_confirms: bool,
    hype: bool,
    stale: bool,
) -> int:
    score = 0
    if official:
        score += 30
    if narrative:
        score += 15
    score += min(news_score, 20)
    score += min(social_score, 15)
    if price_confirms:
        score += 20
    if hype:
        score -= 20
    if stale:
        score -= 10
    return int(clamp(score, 0, 100))


def _attention_score(items: list[CatalystItem], social: SocialAttentionSnapshot | None) -> int:
    count = sum(item.attention_count or 0 for item in items)
    velocity = max([item.attention_velocity for item in items if item.attention_velocity is not None] or [0])
    if social:
        count += (social.reddit_mention_count or 0) + (social.twitter_mention_count or 0) + (social.news_headline_count or 0)
        velocity = max(velocity, social.attention_velocity or 0)
    score = 0
    if count >= 5000:
        score += 20
    elif count >= 1000:
        score += 15
    elif count >= 100:
        score += 10
    elif count > 0:
        score += 5
    if velocity >= 2.0:
        score += 15
    elif velocity >= 1.0:
        score += 10
    elif velocity >= 0.4:
        score += 5
    return int(clamp(score, 0, 100))


def _recency_label(items: list[CatalystItem], analysis_date: date) -> str:
    dates = [_parse_timestamp(item.timestamp).date() for item in items if item.timestamp and _parse_timestamp(item.timestamp)]
    if not dates:
        return "unavailable"
    age = (analysis_date - max(dates)).days
    if age <= 7:
        return "Fresh"
    if age <= 30:
        return "Recent"
    if age <= 90:
        return "Aging"
    return "Stale"


def _dominant_type(items: list[CatalystItem], tags: list[str]) -> str:
    values = [item.catalyst_type for item in items if item.catalyst_type != "Unknown/unconfirmed"]
    values.extend(_normalize_catalyst_type(tag) for tag in tags)
    counts = Counter(value for value in values if value != "Unknown/unconfirmed")
    if not counts:
        return "Unknown/unconfirmed"
    return counts.most_common(1)[0][0]


def _provider_notes(security: SecurityData, items: list[CatalystItem]) -> list[str]:
    notes = list(security.source_notes)
    source_names = sorted({item.source_name for item in items if item.source_name})
    if source_names:
        notes.append(f"Manual catalyst sources: {', '.join(source_names)}.")
    return notes


def _sentiment_label(items: list[CatalystItem], security: SecurityData) -> str:
    labels = [(item.sentiment or "").lower() for item in items if item.sentiment]
    if labels:
        positives = sum(label in {"positive", "bullish"} for label in labels)
        negatives = sum(label in {"negative", "bearish"} for label in labels)
        if positives > negatives:
            return "Positive"
        if negatives > positives:
            return "Negative"
        return "Mixed"
    if security.social_attention and security.social_attention.news_sentiment is not None:
        if security.social_attention.news_sentiment > 0.15:
            return "Positive"
        if security.social_attention.news_sentiment < -0.15:
            return "Negative"
        return "Neutral"
    return "unavailable"


def _sentiment_float(items: list[CatalystItem]) -> float | None:
    if not items:
        return None
    scores = []
    for item in items:
        label = (item.sentiment or "").lower()
        if label in {"positive", "bullish"}:
            scores.append(0.6)
        elif label in {"negative", "bearish"}:
            scores.append(-0.6)
        elif label:
            scores.append(0.0)
    if not scores:
        return None
    return sum(scores) / len(scores)


def _sum_attention(items: list[CatalystItem], source_type: str) -> int | None:
    values = [item.attention_count or 0 for item in items if item.source_type == source_type]
    return sum(values) if values else None


def _max_optional(left: int | None, right: int | None) -> int | None:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None


def _is_official(item: CatalystItem) -> bool:
    return bool(item.official_source or item.official_or_verified or item.source_type in OFFICIAL_SOURCE_TYPES)


def _is_hype_item(item: CatalystItem) -> bool:
    return bool(
        item.hype_risk
        or item.catalyst_type == "Social hype only"
        or (item.source_type in SOCIAL_SOURCE_TYPES and not _is_official(item) and (item.attention_velocity or 0) >= 1.2)
    )


def _normalize_catalyst_type(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Unknown/unconfirmed"
    lowered = raw.lower()
    aliases = {
        "earnings": "Earnings beat",
        "earnings beat": "Earnings beat",
        "guidance": "Guidance raise",
        "upgrade": "Analyst upgrade",
        "analyst upgrade": "Analyst upgrade",
        "revision": "Estimate revision",
        "estimate revision": "Estimate revision",
        "contract": "Major contract",
        "major contract": "Major contract",
        "product": "Product launch",
        "product launch": "Product launch",
        "ai": "AI/data center narrative",
        "ai/data center narrative": "AI/data center narrative",
        "semiconductor": "Semiconductor narrative",
        "semiconductor narrative": "Semiconductor narrative",
        "defense": "Defense/geopolitical narrative",
        "defense/geopolitical narrative": "Defense/geopolitical narrative",
        "energy": "Energy/nuclear narrative",
        "energy/nuclear narrative": "Energy/nuclear narrative",
        "financials": "Financials/rate-cut narrative",
        "financials/rate-cut narrative": "Financials/rate-cut narrative",
        "ipo": "IPO/post-IPO narrative",
        "ipo/post-ipo narrative": "IPO/post-IPO narrative",
        "policy": "Regulatory/policy catalyst",
        "regulatory/policy catalyst": "Regulatory/policy catalyst",
        "insider": "Insider/institutional activity",
        "institutional": "Insider/institutional activity",
        "insider/institutional activity": "Insider/institutional activity",
        "short squeeze": "Short squeeze / crowded repricing",
        "short squeeze / crowded repricing": "Short squeeze / crowded repricing",
        "social hype only": "Social hype only",
    }
    if raw in CATALYST_TYPES:
        return raw
    return aliases.get(lowered, "Unknown/unconfirmed")


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError as exc:
        raise ValueError(f"invalid timestamp {value!r}") from exc


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value: float | int | None) -> float | int | str:
    if value is None:
        return "unavailable"
    if isinstance(value, int):
        return value
    return round(value, 2)
