from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .providers import LocalFileMarketDataProvider, SampleMarketDataProvider
from .reporting import print_console_summary, write_csv_report, write_json_report
from .scanner import DeterministicScanner


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        universe = load_universe(args.universe)
        analysis_date = args.as_of_date or date.today()

        if args.provider == "sample":
            provider = SampleMarketDataProvider(end_date=analysis_date)
        else:
            if args.data_dir is None:
                parser.error("--data-dir is required when --provider local is used.")
            provider = LocalFileMarketDataProvider(args.data_dir)

        scanner = DeterministicScanner(provider=provider, analysis_date=analysis_date)
        results = scanner.scan(universe)
        if args.limit:
            results = results[: args.limit]

        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = args.json_path or output_dir / "scan_report.json"
        csv_path = args.csv_path or output_dir / "scan_report.csv"

        print_console_summary(results)
        write_json_report(results, json_path)
        write_csv_report(results, csv_path)
        print(f"\nJSON report: {json_path}")
        print(f"CSV report:  {csv_path}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TradeBruv deterministic stock scanner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Run the deterministic scanner on a universe file.")
    scan.add_argument("--universe", type=Path, required=True, help="Path to a newline-delimited ticker file.")
    scan.add_argument(
        "--provider",
        choices=("sample", "local"),
        default="sample",
        help="Built-in sample data or a local file adapter.",
    )
    scan.add_argument(
        "--data-dir",
        type=Path,
        help="Local data directory containing prices/<TICKER>.csv and metadata.json.",
    )
    scan.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="Directory for JSON and CSV reports.",
    )
    scan.add_argument("--json-path", type=Path, help="Optional override for the JSON report path.")
    scan.add_argument("--csv-path", type=Path, help="Optional override for the CSV report path.")
    scan.add_argument("--limit", type=int, default=0, help="Optional limit for console and file output.")
    scan.add_argument(
        "--as-of-date",
        type=_parse_date,
        help="Anchor date in YYYY-MM-DD format for deterministic sample scans.",
    )
    return parser


def load_universe(path: Path) -> list[str]:
    tickers: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tickers.append(line.upper())
    return tickers


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)

