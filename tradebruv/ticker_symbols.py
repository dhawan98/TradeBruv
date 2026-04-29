from __future__ import annotations

import re


_CLASS_SYMBOL_PROVIDER_MAP = {
    "BRK.B": "BRK-B",
    "BRK-B": "BRK-B",
    "BF.B": "BF-B",
    "BF-B": "BF-B",
}

_CLASS_SYMBOL_DISPLAY_MAP = {
    provider: display
    for display, provider in _CLASS_SYMBOL_PROVIDER_MAP.items()
    if "." in display
}
_CLASS_SYMBOL_DISPLAY_MAP.update({display: display for display in _CLASS_SYMBOL_PROVIDER_MAP if "." in display})


def normalize_ticker_symbol(ticker: str) -> str:
    return str(ticker or "").strip().upper().replace("/", ".")


def canonical_ticker_key(ticker: str) -> str:
    return display_ticker(ticker)


def display_ticker(ticker: str) -> str:
    normalized = normalize_ticker_symbol(ticker)
    if not normalized:
        return ""
    return _CLASS_SYMBOL_DISPLAY_MAP.get(normalized, normalized)


def provider_ticker(ticker: str) -> str:
    normalized = normalize_ticker_symbol(ticker)
    if not normalized:
        return ""
    if normalized in _CLASS_SYMBOL_PROVIDER_MAP:
        return _CLASS_SYMBOL_PROVIDER_MAP[normalized]
    if re.fullmatch(r"[A-Z]+\.[A-Z]", normalized):
        return normalized.replace(".", "-")
    return normalized
