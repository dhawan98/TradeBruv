from __future__ import annotations


MANUAL_THEME_MAP: dict[str, tuple[str, ...]] = {
    "NVDA": ("AI", "Semiconductors", "Data center"),
    "PLTR": ("AI", "Defense", "Cloud/software"),
    "MU": ("Semiconductors", "AI", "Data center"),
    "RDDT": ("IPO", "Social platforms", "Advertising"),
    "GME": ("Short squeeze", "Retail speculation"),
    "CAR": ("Travel/reopening", "Short squeeze"),
    "AMD": ("AI", "Semiconductors", "Data center"),
    "SMCI": ("AI", "Data center", "Infrastructure"),
    "ARM": ("IPO", "Semiconductors", "AI"),
    "COIN": ("Crypto-related equities", "Fintech"),
    "HOOD": ("Fintech", "Retail trading"),
    "TSLA": ("EV", "AI", "Consumer squeeze/reopening"),
    "AVGO": ("Semiconductors", "Infrastructure", "AI"),
    "CRWD": ("Cloud/software", "Cybersecurity"),
    "NET": ("Cloud/software", "Infrastructure", "AI"),
    "VRT": ("Data center", "Infrastructure", "AI"),
    "CAVA": ("IPO", "Consumer squeeze/reopening"),
    "CELH": ("Consumer squeeze/reopening", "Growth consumer"),
    "BAC": ("Banks/financials",),
    "BAH": ("Defense", "Government services"),
    "AAPL": ("Consumer technology", "Hardware"),
    "MSFT": ("AI", "Cloud/software", "Data center"),
    "META": ("AI", "Advertising", "Social platforms"),
    "AMZN": ("Cloud/software", "Consumer squeeze/reopening"),
}

SECTOR_THEME_MAP: dict[str, tuple[str, ...]] = {
    "Technology": ("Cloud/software", "Infrastructure"),
    "Healthcare": ("Healthcare",),
    "Consumer Discretionary": ("Consumer squeeze/reopening",),
    "Financial Services": ("Banks/financials",),
    "Financial": ("Banks/financials",),
    "Energy": ("Nuclear/energy", "Energy"),
    "Industrials": ("Defense", "Infrastructure"),
}

KEYWORD_THEME_MAP: dict[str, tuple[str, ...]] = {
    "ai": ("AI",),
    "data center": ("Data center",),
    "semiconductor": ("Semiconductors",),
    "gpu": ("AI", "Semiconductors"),
    "defense": ("Defense",),
    "nuclear": ("Nuclear/energy",),
    "energy": ("Energy",),
    "cloud": ("Cloud/software",),
    "software": ("Cloud/software",),
    "bank": ("Banks/financials",),
    "crypto": ("Crypto-related equities",),
    "policy": ("Political/policy/tariff beneficiaries",),
    "tariff": ("Political/policy/tariff beneficiaries",),
}

CATALYST_KEYWORDS: dict[str, tuple[str, ...]] = {
    "earnings": ("Earnings beat",),
    "beat": ("Earnings beat",),
    "guidance": ("Guidance raise",),
    "upgrade": ("Analyst upgrade",),
    "estimate": ("Raised estimates",),
    "contract": ("Major contract",),
    "product": ("New product cycle",),
    "ai": ("AI/data center/semiconductor narrative",),
    "data center": ("AI/data center/semiconductor narrative",),
    "defense": ("Defense narrative",),
    "energy": ("Energy narrative",),
    "policy": ("Regulatory/policy shift",),
    "regulatory": ("Regulatory/policy shift",),
    "ipo": ("IPO/post-IPO breakout",),
    "squeeze": ("Short squeeze conditions",),
    "insider": ("Insider/institutional activity",),
    "institution": ("Insider/institutional activity",),
}


def infer_theme_tags(*, ticker: str, sector: str | None, industry: str | None, texts: list[str]) -> list[str]:
    tags: list[str] = list(MANUAL_THEME_MAP.get(ticker.upper(), ()))
    if sector:
        tags.extend(SECTOR_THEME_MAP.get(sector, ()))
    blob = " ".join(filter(None, [sector, industry, *texts])).lower()
    for keyword, values in KEYWORD_THEME_MAP.items():
        if keyword in blob:
            tags.extend(values)
    return sorted(dict.fromkeys(tags))


def infer_catalyst_tags(*texts: str) -> list[str]:
    tags: list[str] = []
    blob = " ".join(filter(None, texts)).lower()
    for keyword, values in CATALYST_KEYWORDS.items():
        if keyword in blob:
            tags.extend(values)
    return sorted(dict.fromkeys(tags))
