from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .ai_explanations import apply_ai_explanations, build_explanation_provider
from .catalysts import CatalystOverlayProvider, load_catalyst_repository
from .journal import (
    DEFAULT_JOURNAL_PATH,
    add_journal_entry,
    export_journal,
    journal_stats,
    read_journal,
    update_journal_entry,
)
from .performance import build_strategy_performance_report, write_performance_csv, write_performance_json
from .providers import (
    LocalFileMarketDataProvider,
    ProviderConfigurationError,
    SampleMarketDataProvider,
    YFinanceMarketDataProvider,
)
from .reporting import print_console_summary, write_csv_report, write_json_report
from .review import (
    load_reports_from_dir,
    load_scan_report,
    review_report,
    review_reports,
    write_review_csv,
    write_review_json,
)
from .scanner import DeterministicScanner


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        universe = load_universe(args.universe)
        analysis_date = args.as_of_date or date.today()

        try:
            provider = build_provider(args=args, analysis_date=analysis_date)
        except ProviderConfigurationError as exc:
            print(f"Provider configuration error: {exc}")
            return 2
        catalyst_repository = load_catalyst_repository(args.catalyst_file)
        if catalyst_repository.warnings:
            for warning in catalyst_repository.warnings:
                print(f"Catalyst warning: {warning}")
        if catalyst_repository.items_by_ticker:
            provider = CatalystOverlayProvider(provider, catalyst_repository)

        scanner = DeterministicScanner(provider=provider, analysis_date=analysis_date)
        results = scanner.scan(universe, mode=args.mode)
        if args.ai_explanations:
            explanation_provider = build_explanation_provider(enabled=True, mock=args.mock_ai_explanations)
            apply_ai_explanations(results, explanation_provider)
        if args.limit:
            results = results[: args.limit]

        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        default_stem = "outlier_scan_report" if args.mode == "outliers" else "scan_report"
        json_path = args.json_path or output_dir / f"{default_stem}.json"
        csv_path = args.csv_path or output_dir / f"{default_stem}.csv"

        print_console_summary(results, mode=args.mode)
        write_json_report(results, json_path, mode=args.mode)
        write_csv_report(results, csv_path)
        print(f"\nJSON report: {json_path}")
        print(f"CSV report:  {csv_path}")
        return 0

    if args.command == "review":
        try:
            provider = build_provider(args=args, analysis_date=args.price_as_of_date or date.today())
            report = load_scan_report(args.report)
            payload = review_report(
                report=report,
                provider=provider,
                horizons=_parse_horizons(args.horizons),
                signal_date=args.signal_date,
            )
        except (ProviderConfigurationError, FileNotFoundError, ValueError) as exc:
            print(f"Review error: {exc}")
            return 2
        return _write_review_outputs(payload, args.output_dir)

    if args.command == "review-batch":
        try:
            provider = build_provider(args=args, analysis_date=args.price_as_of_date or date.today())
            reports = load_reports_from_dir(args.reports_dir)
            payload = review_reports(
                reports=reports,
                provider=provider,
                horizons=_parse_horizons(args.horizons),
                signal_date=args.signal_date,
            )
        except (ProviderConfigurationError, FileNotFoundError, ValueError) as exc:
            print(f"Review error: {exc}")
            return 2
        return _write_review_outputs(payload, args.output_dir)

    if args.command == "journal":
        return _handle_journal(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


def build_provider(*, args: argparse.Namespace, analysis_date: date):
    if args.provider == "sample":
        return SampleMarketDataProvider(end_date=analysis_date)
    if args.provider == "local":
        if args.data_dir is None:
            raise ProviderConfigurationError("--data-dir is required when --provider local is used.")
        return LocalFileMarketDataProvider(args.data_dir)
    return YFinanceMarketDataProvider(history_period=args.history_period)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TradeBruv deterministic stock scanner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Run the deterministic scanner on a universe file.")
    scan.add_argument("--universe", type=Path, required=True, help="Path to a newline-delimited ticker file.")
    scan.add_argument(
        "--provider",
        choices=("sample", "local", "real"),
        default="sample",
        help="Use built-in sample data, a local file adapter, or a yfinance-backed real-data adapter.",
    )
    scan.add_argument(
        "--mode",
        choices=("standard", "outliers"),
        default="standard",
        help="Standard winner ranking or the outlier-winner ranking view.",
    )
    scan.add_argument(
        "--data-dir",
        type=Path,
        help="Local data directory containing prices/<TICKER>.csv and metadata.json.",
    )
    scan.add_argument(
        "--history-period",
        default="3y",
        help="History period passed to the real provider (default: 3y).",
    )
    scan.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="Directory for JSON and CSV reports.",
    )
    scan.add_argument("--json-path", type=Path, help="Optional override for the JSON report path.")
    scan.add_argument("--csv-path", type=Path, help="Optional override for the CSV report path.")
    scan.add_argument(
        "--catalyst-file",
        type=Path,
        help="Optional CSV or JSON file with manual catalyst/news/social source items.",
    )
    scan.add_argument(
        "--ai-explanations",
        action="store_true",
        help="Attach optional AI-generated explanations when an OpenAI-compatible provider is configured.",
    )
    scan.add_argument(
        "--mock-ai-explanations",
        action="store_true",
        help="Use the local mock explanation provider for tests and offline demos.",
    )
    scan.add_argument("--limit", type=int, default=0, help="Optional limit for console and file output.")
    scan.add_argument(
        "--as-of-date",
        type=_parse_date,
        help="Anchor date in YYYY-MM-DD format for deterministic sample scans.",
    )

    review = subparsers.add_parser("review", help="Review a saved scan report against later OHLCV data.")
    _add_review_provider_args(review)
    review.add_argument("--report", type=Path, required=True, help="Saved scan_report.json/csv or outlier report.")
    review.add_argument("--horizons", default="1,5,10,20,60,120", help="Comma-separated forward trading-day horizons.")
    review.add_argument("--signal-date", type=_parse_date, help="Override report signal date in YYYY-MM-DD format.")
    review.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="Directory for review_report and strategy_performance outputs.",
    )

    review_batch = subparsers.add_parser("review-batch", help="Review a directory of saved scan reports.")
    _add_review_provider_args(review_batch)
    review_batch.add_argument("--reports-dir", type=Path, required=True, help="Directory containing saved reports.")
    review_batch.add_argument("--horizons", default="1,5,10,20,60,120", help="Comma-separated forward trading-day horizons.")
    review_batch.add_argument("--signal-date", type=_parse_date, help="Optional override applied to every report.")
    review_batch.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="Directory for review_report and strategy_performance outputs.",
    )

    journal = subparsers.add_parser("journal", help="Manage the local TradeBruv research/trade journal.")
    journal_subparsers = journal.add_subparsers(dest="journal_command", required=True)
    journal_add = journal_subparsers.add_parser("add", help="Add a journal entry.")
    journal_add.add_argument("--journal-path", type=Path, default=DEFAULT_JOURNAL_PATH)
    journal_add.add_argument("--from-report", type=Path, help="Populate fields from a saved scanner report.")
    journal_add.add_argument("--ticker", required=True, help="Ticker to add.")
    journal_add.add_argument("--set", action="append", default=[], help="Set a field as key=value. May be repeated.")
    journal_list = journal_subparsers.add_parser("list", help="List journal entries.")
    journal_list.add_argument("--journal-path", type=Path, default=DEFAULT_JOURNAL_PATH)
    journal_update = journal_subparsers.add_parser("update", help="Update a journal entry.")
    journal_update.add_argument("--journal-path", type=Path, default=DEFAULT_JOURNAL_PATH)
    journal_update.add_argument("--id", required=True, help="Journal entry id.")
    journal_update.add_argument("--set", action="append", default=[], required=True, help="Set a field as key=value.")
    journal_export = journal_subparsers.add_parser("export", help="Export journal CSV.")
    journal_export.add_argument("--journal-path", type=Path, default=DEFAULT_JOURNAL_PATH)
    journal_export.add_argument("--output", type=Path, required=True)
    journal_stats_cmd = journal_subparsers.add_parser("stats", help="Show journal process/outcome stats.")
    journal_stats_cmd.add_argument("--journal-path", type=Path, default=DEFAULT_JOURNAL_PATH)
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


def _add_review_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--provider",
        choices=("sample", "local", "real"),
        default="sample",
        help="Provider used to fetch later OHLCV data.",
    )
    parser.add_argument("--data-dir", type=Path, help="Required when --provider local is used.")
    parser.add_argument("--history-period", default="3y", help="History period passed to the real provider.")
    parser.add_argument(
        "--price-as-of-date",
        type=_parse_date,
        help="End date for deterministic sample review data in YYYY-MM-DD format.",
    )


def _parse_horizons(raw: str) -> list[int]:
    horizons = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        horizons.append(int(item))
    return horizons


def _write_review_outputs(payload: dict, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    review_json = write_review_json(payload, output_dir / "review_report.json")
    review_csv = write_review_csv(payload, output_dir / "review_report.csv")
    performance = build_strategy_performance_report(payload)
    perf_json = write_performance_json(performance, output_dir / "strategy_performance.json")
    perf_csv = write_performance_csv(performance, output_dir / "strategy_performance.csv")
    available = sum(1 for row in payload.get("results", []) if row.get("available"))
    total = len(payload.get("results", []))
    print(f"Reviewed rows: {available}/{total} available")
    print(f"Review JSON: {review_json}")
    print(f"Review CSV:  {review_csv}")
    print(f"Strategy performance JSON: {perf_json}")
    print(f"Strategy performance CSV:  {perf_csv}")
    return 0


def _handle_journal(args: argparse.Namespace) -> int:
    try:
        if args.journal_command == "add":
            entry = add_journal_entry(
                journal_path=args.journal_path,
                from_report=args.from_report,
                ticker=args.ticker,
                updates=_parse_set_args(args.set),
            )
            print(f"Journal entry added: {entry['id']} {entry['ticker']} ({entry['decision']})")
            return 0
        if args.journal_command == "list":
            rows = read_journal(args.journal_path)
            if not rows:
                print("No journal entries found.")
                return 0
            for row in rows:
                print(
                    f"{row.get('id')} | {row.get('ticker')} | {row.get('decision')} | "
                    f"entry={row.get('actual_entry_price') or 'unavailable'} | "
                    f"exit={row.get('actual_exit_price') or 'unavailable'} | "
                    f"result={row.get('result_pct') or 'unavailable'}"
                )
            return 0
        if args.journal_command == "update":
            entry = update_journal_entry(
                entry_id=args.id,
                updates=_parse_set_args(args.set),
                journal_path=args.journal_path,
            )
            print(f"Journal entry updated: {entry['id']} {entry['ticker']}")
            return 0
        if args.journal_command == "export":
            path = export_journal(output_path=args.output, journal_path=args.journal_path)
            print(f"Journal exported: {path}")
            return 0
        if args.journal_command == "stats":
            stats = journal_stats(read_journal(args.journal_path))
            print(json.dumps(stats, indent=2))
            return 0
    except ValueError as exc:
        print(f"Journal error: {exc}")
        return 2
    print(f"Unknown journal command: {args.journal_command}")
    return 2


def _parse_set_args(values: list[str]) -> dict[str, str]:
    updates = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--set values must be key=value, got: {value}")
        key, raw = value.split("=", 1)
        updates[key.strip()] = raw.strip()
    return updates
