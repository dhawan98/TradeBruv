from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .tracked import DEFAULT_TRACKED_TICKERS
from .ticker_symbols import display_ticker


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

US_BROAD_EXTRA = (
    "A","AAL","AAP","AEE","AEP","AES","AFL","AIG","AJG","AKAM","ALB","ALGN","ALLE","ALL","AMCR","AME","AMP","AOS","APA","APTV",
    "ARE","ATO","AWK","BBWI","BBY","BEN","BG","BAX","BIO","BRO","BSX","BXP","CAG","CAH","CARR","CBRE","CE","CEG","CF","CHD",
    "CHRW","CHTR","CINF","CLX","CMS","CNC","CNP","COF","COO","COR","CPB","CTRA","CTVA","DAL","DAY","DD","DFS","DGX","DHI","DOV",
    "DOW","DPZ","DTE","DVA","DVN","EBAY","ECL","ED","EFX","EIX","EL","EPAM","EQT","ERIE","ES","ESS","ETR","EVRG","EXPE","EXR",
    "FDS","FDX","FE","FICO","FITB","FMC","FRT","FSLR","FTV","GEHC","GEN","GPN","GRMN","HAS","HBAN","HES","HIG","HLT","HOLX",
    "HPE","HPQ","HRL","HSIC","HST","HSY","HUM","HWM","IDXX","INCY","INVH","IP","IPG","IQV","IRM","IT","ITW","JBHT","JKHY","JNPR",
    "K","KEY","KHC","KIM","KMX","LDOS","LEN","LKQ","LNT","LUV","LW","LYV","MAA","MAS","MCK","MET","MGM","MKC","MKTX","MLM","MOH",
    "MOS","MPC","MRNA","MSCI","MTB","MTD","NCLH","NDAQ","NDSN","NEE","NEM","NI","NOC","NRG","NSC","NTRS","NUE","NVR","NWSA","O",
    "ODFL","OKE","OMC","ON","OTIS","OXY","PARA","PEAK","PFG","PKG","PNR","PNW","PODD","POOL","PPG","PPL","PTC","PWR","RCL","REG",
    "RF","RJF","RMD","ROK","ROL","SJM","SLG","SNA","SPG","SRE","STE","STT","STX","SWK","SWKS","SYF","TECH","TEL","TER","TFC",
    "TFX","TPR","TRGP","TRMB","TRV","TSCO","TTWO","TXT","TYL","UAL","UDR","UHS","ULTA","URI","VFC","VICI","VLTO","VMC","VRSK",
    "VTR","VTRS","WAB","WAT","WBA","WEC","WELL","WDC","WRB","WSM","WTW","WY","WYNN","XEL","XYL","YUM","ZBH","ZBRA","ZION",
    "CAR","GME","CVNA","DKNG","DASH","CHWY","ETSY","ROKU","AFRM","UPST","SOFI","LYFT","PTON","BROS","ELF","CROX","ONON","HIMS",
    "ASTS","IONQ","APP","APPF","DUOL","MRNA","SMR","ACHR","JOBY","TEM","ALAB",
)

US_BROAD_1000_TARGET = tuple(dict.fromkeys(
    TOP1000_STYLE_STARTER
    + US_BROAD_EXTRA
))


UNIVERSE_DEFINITIONS: dict[str, UniverseDefinition] = {
    "sp500": UniverseDefinition(
        source="sp500",
        label="Large Cap Starter",
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
    "us_broad_1000": UniverseDefinition(
        source="us_broad_1000",
        label="US Broad 1000 Target",
        description="Broader static U.S. discovery starter that combines large caps, liquid midcaps, and unusual movers without defaulting into microcaps.",
        starter_note="Static curated starter file that targets broad-market discovery. It is intentionally honest about partial coverage versus a live official top-1000 feed.",
        tickers=US_BROAD_1000_TARGET,
        default_output=Path("config/universe_us_broad_1000.txt"),
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
    return [UNIVERSE_DEFINITIONS[key] for key in ("sp500", "nasdaq100", "top1000", "us_broad_1000", "liquid_growth", "ai_semis_software", "tracked")]


def get_universe_definition(source: str) -> UniverseDefinition:
    key = source.strip().lower()
    if key not in UNIVERSE_DEFINITIONS:
        raise KeyError(source)
    return UNIVERSE_DEFINITIONS[key]


def universe_text(source: str) -> str:
    definition = get_universe_definition(source)
    return "\n".join(definition.tickers) + "\n"


def validate_universe_file(path: Path) -> dict[str, Any]:
    rows = clean_ticker_lines(path.read_text(encoding="utf-8").splitlines())
    row_count = len(rows)
    file_name = path.name.lower()
    universe_label = "Custom Universe"
    expected_universe_size = row_count
    if "sp500" in file_name:
        expected_universe_size = 500
        universe_label = "Large Cap Starter" if row_count < 450 else "S&P 500"
    elif "nasdaq100" in file_name:
        expected_universe_size = 100
        universe_label = "Nasdaq 100"
    elif "us_broad_1000" in file_name:
        expected_universe_size = 1000
        universe_label = "US Broad 1000 Target"
    elif "liquid_expanded" in file_name:
        expected_universe_size = 1000
        universe_label = "US Liquid Expanded"
    elif "top1000" in file_name or "russell1000" in file_name:
        expected_universe_size = 1000
        universe_label = "Top 1000 Style Starter"
    elif "large_cap_starter" in file_name:
        expected_universe_size = 500
        universe_label = "Large Cap Starter"
    coverage_percent = round((row_count / expected_universe_size) * 100, 1) if expected_universe_size else 100.0
    is_partial_universe = expected_universe_size > 0 and row_count < expected_universe_size
    universe_warning = ""
    if "sp500" in file_name and row_count < 450:
        universe_warning = "This file is a Large Cap Starter, not a full live S&P 500 membership list."
    elif is_partial_universe and expected_universe_size > row_count:
        universe_warning = "Universe file is a partial starter list and should not be treated as complete market coverage."
    return {
        "universe_label": universe_label,
        "universe_file": str(path),
        "universe_row_count": row_count,
        "expected_universe_size": expected_universe_size,
        "coverage_percent": coverage_percent,
        "is_partial_universe": is_partial_universe,
        "universe_warning": universe_warning,
        "sample_tickers": rows[:10],
    }


def clean_ticker_lines(lines: list[str]) -> list[str]:
    rows: list[str] = []
    for raw in lines:
        ticker = display_ticker(raw.strip())
        if not ticker or ticker.startswith("#") or ticker in rows:
            continue
        rows.append(ticker)
    return rows


def import_universe_csv(input_path: Path, *, ticker_column: str, output_path: Path) -> dict[str, Any]:
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if ticker_column not in (reader.fieldnames or []):
            raise KeyError(f"Ticker column '{ticker_column}' not found in CSV.")
        rows = clean_ticker_lines([str(row.get(ticker_column) or "") for row in reader])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    return {
        "input": str(input_path),
        "output": str(output_path),
        "row_count": len(rows),
        "sample_tickers": rows[:10],
    }


def clean_universe_file(input_path: Path, output_path: Path) -> dict[str, Any]:
    rows = clean_ticker_lines(input_path.read_text(encoding="utf-8").splitlines())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    return {
        "input": str(input_path),
        "output": str(output_path),
        "row_count": len(rows),
        "sample_tickers": rows[:10],
    }


def expand_universe(
    *,
    output_path: Path,
    target_size: int = 1000,
    csv_inputs: list[tuple[Path, str]] | None = None,
    extra_files: list[Path] | None = None,
) -> dict[str, Any]:
    target = max(1, target_size)
    combined: list[str] = []
    sources_used: list[dict[str, Any]] = []

    built_in_sources = [
        ("config/universe_us_broad_1000.txt", "existing broad universe"),
        ("config/universe_sp500.txt", "large-cap starter"),
        ("config/universe_nasdaq100.txt", "nasdaq 100 starter"),
        ("config/universe_liquid_growth.txt", "liquid growth starter"),
        ("config/universe_russell1000_or_top1000.txt", "top-1000 style starter"),
        ("config/tracked_tickers.txt", "tracked watchlist"),
    ]
    optional_recent = [
        ("config/universe_recent_movers.txt", "recent movers import"),
        ("config/recent_movers.txt", "recent movers import"),
    ]

    for raw_path, label in [*built_in_sources, *optional_recent]:
        path = Path(raw_path)
        if path.exists():
            rows = clean_ticker_lines(path.read_text(encoding="utf-8").splitlines())
            combined.extend(rows)
            sources_used.append({"source": str(path), "label": label, "row_count": len(rows)})

    for path in extra_files or []:
        if path.exists():
            rows = clean_ticker_lines(path.read_text(encoding="utf-8").splitlines())
            combined.extend(rows)
            sources_used.append({"source": str(path), "label": "extra file", "row_count": len(rows)})

    for input_path, ticker_column in csv_inputs or []:
        with input_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if ticker_column not in (reader.fieldnames or []):
                raise KeyError(f"Ticker column '{ticker_column}' not found in CSV.")
            rows = clean_ticker_lines([str(row.get(ticker_column) or "") for row in reader])
        combined.extend(rows)
        sources_used.append({"source": str(input_path), "label": f"csv:{ticker_column}", "row_count": len(rows)})

    combined.extend(list(US_BROAD_1000_TARGET))
    deduped = clean_ticker_lines(combined)
    if len(deduped) > target:
        deduped = deduped[:target]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(deduped) + ("\n" if deduped else ""), encoding="utf-8")
    payload = validate_universe_file(output_path)
    shortfall = max(0, target - len(deduped))
    payload.update(
        {
            "output": str(output_path),
            "target_size": target,
            "actual_size": len(deduped),
            "target_met": shortfall == 0,
            "shortfall": shortfall,
            "sources_used": sources_used,
            "import_instructions": (
                "For fuller real-world coverage, import an official or broker/exported liquid-universe CSV with "
                "`python3 -m tradebruv universe import-csv --input YOUR_LIST.csv --ticker-column SYMBOL --output config/your_list.txt` "
                "and then rerun `python3 -m tradebruv universe expand --output config/universe_us_liquid_expanded.txt --target-size 1000 --extra-file config/your_list.txt`."
            ),
        }
    )
    if shortfall:
        payload["universe_warning"] = (
            f"{payload.get('universe_warning', '').strip()} "
            f"Local starter data reached {len(deduped)} names, short of the {target} target. "
            "Use the import path to supply an official or broker/exported liquid universe."
        ).strip()
    return payload
