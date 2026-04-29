from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .tracked import DEFAULT_TRACKED_TICKERS


@dataclass(frozen=True)
class UniverseDefinition:
    source: str
    label: str
    description: str
    starter_note: str
    tickers: tuple[str, ...]
    default_output: Path


SP500_STARTER = (
    "AAPL","MSFT","NVDA","AMZN","GOOGL","META","BRK.B","LLY","JPM","XOM","AVGO","UNH","V","MA","COST","PG","JNJ","HD","ABBV","BAC",
    "WMT","MRK","KO","NFLX","CVX","AMD","CRM","PEP","TMO","ACN","ADBE","LIN","ORCL","MCD","CSCO","ABT","DHR","QCOM","WFC","TXN",
    "DIS","CAT","PM","GE","INTU","IBM","AMGN","NOW","BKNG","RTX","SPGI","AXP","ISRG","UNP","GS","PGR","BLK","HON","SCHW","AMAT",
    "SYK","LOW","GILD","DE","ADP","TJX","VRTX","PANW","MDT","LRCX","ADI","PLD","MMC","ANET","ETN","MU","ELV","CB","SBUX","CI",
    "C","COP","SO","TMUS","BMY","CVS","DUK","UBER","SLB","MO","ICE","EOG","PYPL","AON","CME","PH","EQIX","KLAC","SHW","INTC",
    "TT","SNPS","NKE","WM","MCO","MAR","ZTS","MS","APD","CDNS","USB","UPS","GD","REGN","CL","HCA","PNC","CMCSA","EMR","MMM",
)

NASDAQ100_STARTER = (
    "AAPL","MSFT","NVDA","AMZN","GOOGL","META","AVGO","COST","NFLX","AMD","PLTR","ADBE","CSCO","PEP","TMUS","QCOM","AMGN","INTU","TXN","ISRG",
    "AMAT","BKNG","ADP","GILD","VRTX","LRCX","ADI","MU","PANW","SNPS","CDNS","INTC","CMCSA","PYPL","MRVL","CRWD","FTNT","MELI","TEAM","ASML",
    "MDB","KLAC","ABNB","MNST","ROP","NXPI","MCHP","ORLY","WDAY","CTAS","KDP","EA","DXCM","IDXX","ROST","ADSK","BIIB","CPRT","AEP","DDOG",
    "ZS","FAST","EXC","XEL","CSX","PCAR","ODFL","GEHC","KHC","PAYX","FANG","VRSK","TTWO","LULU","ON","BKR","CCEP","ANSS","CDW","KHC",
)

LIQUID_GROWTH_STARTER = (
    "NVDA","AMD","AVGO","MU","MSFT","GOOGL","AMZN","META","NFLX","PLTR","RDDT","COIN","HOOD","ARM","CAVA","SMCI","CRWD","NET","PANW","SNOW",
    "TTD","MELI","SHOP","UBER","ABNB","TEAM","DDOG","MDB","ZS","OKTA","APP","CELH","HIMS","RKLB","SOFI","NU","DUOL","ONON","SE","SQ",
    "RBLX","IOT","S","PATH","UPST","AFRM","DOCN","SOUN","GTLB","BILL","PAYC","ROKU","ALAB","TEM","SYM","CFLT","ESTC","GLOB","FSLY","ZI",
)

AI_SEMIS_SOFTWARE = (
    "NVDA","AMD","AVGO","MU","AMAT","LRCX","KLAC","ASML","TSM","ARM","MRVL","QCOM","ADI","MCHP","TXN","INTC","SNPS","CDNS","ANSS","CRWD",
    "PANW","NET","PLTR","MSFT","GOOGL","AMZN","META","SNOW","MDB","DDOG","TEAM","ZS","OKTA","GTLB","CFLT","ESTC","HPE","DELL","SMCI","ORCL",
)

TOP1000_STYLE_STARTER = tuple(dict.fromkeys(
    SP500_STARTER
    + NASDAQ100_STARTER
    + LIQUID_GROWTH_STARTER
    + AI_SEMIS_SOFTWARE
    + (
        "TSLA","RIVN","F","GM","NVO","PFE","MRNA","SHOP","SQ","BA","DAL","UAL","AAL","GM","FICO","CBRE","NEM","FCX","NUE","STLD",
        "VRT","ANF","DECK","CMG","ORLY","AZO","TGT","DG","KR","GIS","KMB","MDLZ","EL","TAP","STZ","PYPL","SHOP","SQ","INTU","WDAY",
        "VEEV","DOCU","HUBS","TWLO","PAYX","ROP","RSG","WCN","ODFL","CPRT","CHTR","T","VZ","TM","PDD","BABA","JD","BIDU","NIO","XPEV",
    )
))


UNIVERSE_DEFINITIONS: dict[str, UniverseDefinition] = {
    "sp500": UniverseDefinition(
        source="sp500",
        label="S&P 500 Starter",
        description="Static curated large-cap U.S. starter universe with broad sector coverage.",
        starter_note="Static curated starter file. Refresh periodically; dynamic membership refresh remains future/degraded.",
        tickers=SP500_STARTER,
        default_output=Path("config/universe_sp500.txt"),
    ),
    "nasdaq100": UniverseDefinition(
        source="nasdaq100",
        label="Nasdaq 100 Starter",
        description="Static curated Nasdaq-heavy starter universe focused on liquid growth and platform names.",
        starter_note="Static curated starter file. Refresh periodically; dynamic membership refresh remains future/degraded.",
        tickers=NASDAQ100_STARTER,
        default_output=Path("config/universe_nasdaq100.txt"),
    ),
    "top1000": UniverseDefinition(
        source="top1000",
        label="Top 1000 Style Starter",
        description="Static liquid large-cap / top-1000-style starter universe that avoids penny stocks and microcaps.",
        starter_note="Static curated starter file, not a live official Russell 1000 membership feed.",
        tickers=TOP1000_STYLE_STARTER,
        default_output=Path("config/universe_russell1000_or_top1000.txt"),
    ),
    "liquid_growth": UniverseDefinition(
        source="liquid_growth",
        label="Liquid Growth",
        description="Higher-beta but liquid growth names for discovery without defaulting into microcaps.",
        starter_note="Static curated starter file; refresh periodically.",
        tickers=LIQUID_GROWTH_STARTER,
        default_output=Path("config/universe_liquid_growth.txt"),
    ),
    "ai_semis_software": UniverseDefinition(
        source="ai_semis_software",
        label="AI / Semis / Software",
        description="Focused AI infrastructure, semiconductor, and software leadership basket.",
        starter_note="Static curated starter file; refresh periodically.",
        tickers=AI_SEMIS_SOFTWARE,
        default_output=Path("config/universe_ai_semis_software.txt"),
    ),
    "tracked": UniverseDefinition(
        source="tracked",
        label="Tracked Tickers",
        description="Starter tracked watchlist monitored every daily run.",
        starter_note="Local tracked list. Update it anytime from CLI or the frontend.",
        tickers=tuple(DEFAULT_TRACKED_TICKERS),
        default_output=Path("config/tracked_tickers.txt"),
    ),
}


def list_universe_definitions() -> list[UniverseDefinition]:
    return [UNIVERSE_DEFINITIONS[key] for key in ("sp500", "nasdaq100", "top1000", "liquid_growth", "ai_semis_software", "tracked")]


def get_universe_definition(source: str) -> UniverseDefinition:
    key = source.strip().lower()
    if key not in UNIVERSE_DEFINITIONS:
        raise KeyError(source)
    return UNIVERSE_DEFINITIONS[key]


def universe_text(source: str) -> str:
    definition = get_universe_definition(source)
    return "\n".join(definition.tickers) + "\n"
