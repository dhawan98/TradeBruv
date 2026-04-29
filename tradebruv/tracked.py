from __future__ import annotations

from pathlib import Path


DEFAULT_TRACKED_TICKERS_PATH = Path("config/tracked_tickers.txt")
DEFAULT_TRACKED_TICKERS = [
    "NVDA",
    "PLTR",
    "MU",
    "AVGO",
    "AMD",
    "MSFT",
    "AAPL",
    "GOOGL",
    "AMZN",
    "META",
    "COIN",
    "RDDT",
    "HOOD",
    "CAVA",
    "ARM",
    "LLY",
    "COST",
]


def list_tracked_tickers(path: Path = DEFAULT_TRACKED_TICKERS_PATH) -> list[str]:
    if not path.exists():
        return list(DEFAULT_TRACKED_TICKERS)
    tickers: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().upper()
        if not line or line.startswith("#"):
            continue
        if line not in tickers:
            tickers.append(line)
    return tickers


def save_tracked_tickers(tickers: list[str], path: Path = DEFAULT_TRACKED_TICKERS_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = []
    for ticker in tickers:
        clean = ticker.strip().upper()
        if clean and clean not in normalized:
            normalized.append(clean)
    path.write_text("\n".join(normalized) + "\n", encoding="utf-8")
    return path


def add_tracked_ticker(ticker: str, path: Path = DEFAULT_TRACKED_TICKERS_PATH) -> list[str]:
    tickers = list_tracked_tickers(path)
    clean = ticker.strip().upper()
    if clean and clean not in tickers:
        tickers.append(clean)
        save_tracked_tickers(tickers, path)
    return tickers


def remove_tracked_ticker(ticker: str, path: Path = DEFAULT_TRACKED_TICKERS_PATH) -> list[str]:
    clean = ticker.strip().upper()
    tickers = [item for item in list_tracked_tickers(path) if item != clean]
    save_tracked_tickers(tickers, path)
    return tickers
