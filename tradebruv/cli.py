from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .ai_explanations import apply_ai_explanations, build_explanation_provider
from .app_status import build_app_status_report
from .alternative_data import DEFAULT_ALTERNATIVE_DATA_PATH, AlternativeDataOverlayProvider, load_alternative_data_repository
from .automation import (
    DEFAULT_DAILY_OUTPUT_DIR,
    DEFAULT_SCAN_ARCHIVE_ROOT,
    DEFAULT_WATCHLIST_STATE_PATH,
    archive_scan_report,
    build_daily_summary_payload,
    build_simple_market_regime,
    generate_alerts,
    load_watchlist_state,
    save_watchlist_state,
    update_watchlist_state,
    write_daily_outputs,
)
from .catalysts import CatalystOverlayProvider, load_catalyst_repository
from .doctor import run_doctor
from .env import load_local_env
from .journal import (
    DEFAULT_JOURNAL_PATH,
    add_journal_entry,
    export_journal,
    journal_stats,
    read_journal,
    update_journal_entry,
)
from .portfolio import (
    DEFAULT_PORTFOLIO_PATH,
    export_portfolio_csv,
    import_portfolio_csv,
    load_portfolio,
    refresh_portfolio_prices,
    save_portfolio,
    upsert_position,
)
from .analysis import analyze_portfolio
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
from .readiness import run_readiness
from .replay import (
    FAMOUS_OUTLIER_WINDOWS,
    run_investing_proof_report,
    run_investing_replay,
    run_famous_outlier_studies,
    run_historical_replay,
    run_outlier_study,
    run_portfolio_replay,
    run_proof_report,
)
from .scanner import DeterministicScanner
from .signal_quality import run_case_study, run_signal_audit
from .ticker_symbols import display_ticker
from .validation_lab import DEFAULT_PREDICTIONS_PATH, load_predictions, save_predictions, update_prediction_outcomes, validation_metrics


def main(argv: list[str] | None = None) -> int:
    load_local_env()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        analysis_date = args.as_of_date or date.today()

        try:
            results, provider = _run_scan(args=args, analysis_date=analysis_date)
        except ProviderConfigurationError as exc:
            print(f"Provider configuration error: {exc}")
            return 2
        except FileNotFoundError as exc:
            print(f"Scan error: {exc}")
            return 2

        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        default_stem = "velocity_scan_report" if args.mode == "velocity" else "outlier_scan_report" if args.mode == "outliers" else "scan_report"
        json_path = args.json_path or output_dir / f"{default_stem}.json"
        csv_path = args.csv_path or output_dir / f"{default_stem}.csv"

        print_console_summary(results, mode=args.mode)
        write_json_report(
            results,
            json_path,
            mode=args.mode,
            provider=args.provider,
            source=f"live scan: {args.universe}",
            metadata={"analysis_date": analysis_date.isoformat(), "selected_provider": args.provider, "data_mode": "live_scan"},
        )
        write_csv_report(results, csv_path)
        if args.archive:
            archived = archive_scan_report(
                results=results,
                provider=args.provider,
                mode=args.mode,
                universe_file=args.universe,
                catalyst_file=args.catalyst_file,
                ai_enabled=args.ai_explanations,
                command_used=_command_used(),
                archive_root=args.archive_root,
            )
            print(f"Archived JSON: {archived['json_path']}")
            print(f"Archived CSV:  {archived['csv_path']}")
        print(f"\nJSON report: {json_path}")
        print(f"CSV report:  {csv_path}")
        return 0

    if args.command == "daily":
        return _handle_daily(args)

    if args.command == "decision-today":
        try:
            from .daily_decision import run_daily_decision
            payload = run_daily_decision(
                provider_name=args.provider,
                core_universe=args.core_universe,
                outlier_universe=args.outlier_universe,
                velocity_universe=args.velocity_universe,
                broad_universe=args.broad_universe,
                tracked=args.tracked,
                include_movers=args.include_movers,
                top_n=args.top_n,
                history_period=args.history_period,
                data_dir=args.data_dir,
                refresh_cache=args.refresh_cache,
                analysis_date=args.as_of_date or date.today(),
                output_dir=args.output_dir,
            )
        except (ProviderConfigurationError, FileNotFoundError, ValueError) as exc:
            print(f"Decision-today error: {exc}")
            return 2
        print(f"Daily decision JSON: {payload['json_path']}")
        print(f"Daily decision MD:   {payload['markdown_path']}")
        print(f"Validated actionable rows: {sum(1 for row in payload.get('decisions', []) if row.get('price_validation_status') == 'PASS')}")
        return 0

    if args.command == "universe":
        from .universe_registry import clean_universe_file, import_universe_csv, list_universe_definitions, universe_text, validate_universe_file

        if args.universe_command == "list":
            for definition in list_universe_definitions():
                print(f"{definition.source}: {definition.label} -> {definition.default_output}")
            return 0
        if args.universe_command == "build":
            content = universe_text(args.source)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
            print(f"Wrote {args.output}")
            return 0
        if args.universe_command == "validate":
            print(json.dumps(validate_universe_file(args.path), indent=2))
            return 0
        if args.universe_command == "import-csv":
            print(json.dumps(import_universe_csv(args.input, ticker_column=args.ticker_column, output_path=args.output), indent=2))
            return 0
        if args.universe_command == "clean":
            print(json.dumps(clean_universe_file(args.input, args.output), indent=2))
            return 0

    if args.command == "tracked":
        from .tracked import add_tracked_ticker, list_tracked_tickers, remove_tracked_ticker

        if args.tracked_command == "list":
            tickers = list_tracked_tickers(args.path)
            for ticker in tickers:
                print(ticker)
            return 0
        if args.tracked_command == "add":
            tickers = add_tracked_ticker(args.ticker, args.path)
            print(",".join(tickers))
            return 0
        if args.tracked_command == "remove":
            tickers = remove_tracked_ticker(args.ticker, args.path)
            print(",".join(tickers))
            return 0

    if args.command == "broad-scan":
        try:
            from .broad_scan import run_broad_scan

            payload = run_broad_scan(
                universe=load_universe(args.universe),
                provider_name=args.provider,
                analysis_date=args.as_of_date or date.today(),
                history_period=args.history_period,
                data_dir=args.data_dir,
                limit=args.limit,
                batch_size=args.batch_size,
                top_n=args.top_n,
                tracked_path=args.tracked,
                output_dir=args.output_dir,
                refresh_cache=args.refresh_cache,
                progress=print,
            )
        except (ProviderConfigurationError, FileNotFoundError, ValueError) as exc:
            print(f"Broad-scan error: {exc}")
            return 2
        print(f"Broad scan JSON: {payload.json_path}")
        print(f"Broad scan CSV:  {payload.csv_path}")
        print(f"Broad scan MD:   {payload.markdown_path}")
        return 0

    if args.command == "market-health":
        try:
            from .market_reliability import build_market_health_report

            payload = build_market_health_report(args.provider, history_period=args.history_period, sample_ticker=args.ticker)
        except (ProviderConfigurationError, ValueError) as exc:
            print(f"Market-health error: {exc}")
            return 2
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "movers":
        try:
            from .movers import run_movers_scan

            payload = run_movers_scan(
                universe=load_universe(args.universe),
                provider_name=args.provider,
                analysis_date=args.as_of_date or date.today(),
                history_period=args.history_period,
                data_dir=args.data_dir,
                top_n=args.top_n,
                min_price=args.min_price,
                min_dollar_volume=args.min_dollar_volume,
                include_speculative=args.include_speculative,
                output_dir=args.output_dir,
                refresh_cache=args.refresh_cache,
                progress=print,
            )
        except (ProviderConfigurationError, FileNotFoundError, ValueError) as exc:
            print(f"Movers error: {exc}")
            return 2
        print(f"Movers JSON: {payload.json_path}")
        print(f"Movers CSV:  {payload.csv_path}")
        print(f"Movers MD:   {payload.markdown_path}")
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

    if args.command == "portfolio":
        return _handle_portfolio(args)

    if args.command == "predictions":
        return _handle_predictions(args)

    if args.command == "doctor":
        payload = run_doctor(live=args.live, ai=args.ai, ticker=args.ticker, output_dir=args.output_dir)
        print(f"Doctor summary: {payload['summary']}")
        print(f"Doctor JSON: {payload['json_path']}")
        print(f"Doctor MD:   {payload['markdown_path']}")
        return 0

    if args.command == "readiness":
        payload = run_readiness(
            universe=args.universe,
            provider=args.provider,
            tickers=[ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()],
            ai=args.ai,
            output_dir=args.output_dir,
        )
        print(f"Readiness summary: {payload['summary']}")
        print(f"Ready for paper tracking: {payload['ready_for_paper_tracking']}")
        print(f"Ready for real-money reliance: {payload['ready_for_real_money_reliance']}")
        print(f"Readiness JSON: {payload['json_path']}")
        print(f"Readiness MD:   {payload['markdown_path']}")
        return 0

    if args.command == "signal-audit":
        payload = run_signal_audit(
            reports_dir=args.reports_dir,
            baseline=[item.strip().upper() for item in args.baseline.split(",") if item.strip()],
            random_baseline=args.random_baseline,
            output_dir=args.output_dir,
        )
        print(f"Signal audit conclusion: {payload['conclusion']}")
        print(f"Signal audit JSON: {payload['json_path']}")
        print(f"Signal audit MD:   {payload['markdown_path']}")
        return 0

    if args.command == "app-status":
        payload = build_app_status_report(output_dir=args.output_dir)
        print(f"App status JSON: {payload['json_path']}")
        print(f"App status MD:   {payload['markdown_path']}")
        return 0

    if args.command == "price-debug":
        try:
            from .price_debug import build_price_debug_report, build_price_lineage_report
            tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
            build_price_lineage_report(
                tickers=tickers,
                output_dir=args.output_dir,
                reference_date=args.as_of_date or date.today(),
            )
            payload = build_price_debug_report(
                tickers=tickers,
                provider_name=args.provider,
                history_period=args.history_period,
                analysis_date=args.as_of_date or date.today(),
                output_dir=args.output_dir,
            )
        except (ProviderConfigurationError, FileNotFoundError, ValueError) as exc:
            print(f"Price-debug error: {exc}")
            return 2
        print(f"Price debug JSON: {payload['json_path']}")
        print(f"Price debug MD:   {payload['markdown_path']}")
        print(f"Price lineage JSON: {args.output_dir / 'price_lineage_report.json'}")
        print(f"Price lineage MD:   {args.output_dir / 'price_lineage_report.md'}")
        return 0

    if args.command == "replay":
        try:
            provider = build_provider(args=args, analysis_date=args.end_date)
            payload = run_historical_replay(
                provider=provider,
                universe=load_universe(args.universe),
                start_date=args.start_date,
                end_date=args.end_date,
                frequency=args.frequency,
                mode=args.mode,
                horizons=_parse_horizons(args.horizons),
                top_n=args.top_n,
                output_dir=args.output_dir,
            )
        except (ProviderConfigurationError, FileNotFoundError, ValueError) as exc:
            print(f"Replay error: {exc}")
            return 2
        print(f"Replay candidates: {payload['summary']['total_candidates']}")
        print(f"Replay JSON: {payload['json_path']}")
        print(f"Replay CSV:  {payload['csv_path']}")
        print(f"Replay summary MD: {payload['summary_markdown_path']}")
        return 0

    if args.command == "investing-replay":
        try:
            provider = build_provider(args=args, analysis_date=args.end_date)
            payload = run_investing_replay(
                provider=provider,
                universe=load_universe(args.universe),
                start_date=args.start_date,
                end_date=args.end_date,
                frequency=args.frequency,
                horizons=_parse_horizons(args.horizons),
                top_n=args.top_n,
                output_dir=args.output_dir,
                baselines=[item.strip().upper() for item in args.baseline.split(",") if item.strip()],
                random_baseline=args.random_baseline,
            )
        except (ProviderConfigurationError, FileNotFoundError, ValueError) as exc:
            print(f"Investing replay error: {exc}")
            return 2
        print(f"Investing replay candidates: {payload['summary']['total_candidates']}")
        print(f"Investing replay JSON: {payload['json_path']}")
        print(f"Investing replay CSV:  {payload['csv_path']}")
        print(f"Investing replay summary MD: {payload['summary_markdown_path']}")
        return 0

    if args.command == "portfolio-replay":
        try:
            provider = build_provider(args=args, analysis_date=args.end_date)
            payload = run_portfolio_replay(
                provider=provider,
                universe=load_universe(args.universe),
                start_date=args.start_date,
                end_date=args.end_date,
                frequency=args.frequency,
                output_dir=args.output_dir,
            )
        except (ProviderConfigurationError, FileNotFoundError, ValueError) as exc:
            print(f"Portfolio replay error: {exc}")
            return 2
        print(f"Portfolio replay decisions: {payload['summary']['total_decisions']}")
        print(f"Portfolio replay JSON: {payload['json_path']}")
        print(f"Portfolio replay MD:   {payload['markdown_path']}")
        return 0

    if args.command == "outlier-study":
        try:
            provider = build_provider(args=args, analysis_date=args.end_date or date.today())
            if args.preset == "famous":
                payload = run_famous_outlier_studies(provider=provider, output_dir=args.output_dir, mode=args.mode)
                print(f"Famous outlier summary JSON: {payload['json_path']}")
                print(f"Famous outlier summary MD:   {payload['markdown_path']}")
                return 0
            if not args.ticker or not args.start_date or not args.end_date:
                print("--ticker, --start-date, and --end-date are required unless --preset famous is used.")
                return 2
            payload = run_outlier_study(
                provider=provider,
                ticker=args.ticker,
                start_date=args.start_date,
                end_date=args.end_date,
                mode=args.mode,
                output_dir=args.output_dir,
            )
        except (ProviderConfigurationError, FileNotFoundError, ValueError) as exc:
            print(f"Outlier study error: {exc}")
            return 2
        print(f"Case study verdict: {payload.get('did_it_catch_move')}")
        print(f"Case study JSON: {payload.get('json_path')}")
        print(f"Case study MD:   {payload.get('markdown_path')}")
        return 0

    if args.command == "proof-report":
        try:
            provider = build_provider(args=args, analysis_date=args.end_date)
            payload = run_proof_report(
                provider=provider,
                universe=load_universe(args.universe),
                start_date=args.start_date,
                end_date=args.end_date,
                include_famous_outliers=args.include_famous_outliers,
                include_velocity=args.include_velocity,
                baselines=[item.strip().upper() for item in args.baseline.split(",") if item.strip()],
                random_baseline=args.random_baseline,
                output_dir=args.output_dir,
            )
        except (ProviderConfigurationError, FileNotFoundError, ValueError) as exc:
            print(f"Proof report error: {exc}")
            return 2
        print(f"Evidence strength: {payload['evidence_strength']}")
        print(f"Proof report JSON: {payload['json_path']}")
        print(f"Proof report MD:   {payload['markdown_path']}")
        return 0

    if args.command == "investing-proof-report":
        try:
            provider = build_provider(args=args, analysis_date=args.end_date)
            payload = run_investing_proof_report(
                provider=provider,
                universe=load_universe(args.universe),
                start_date=args.start_date,
                end_date=args.end_date,
                baselines=[item.strip().upper() for item in args.baseline.split(",") if item.strip()],
                random_baseline=args.random_baseline,
                output_dir=args.output_dir,
            )
        except (ProviderConfigurationError, FileNotFoundError, ValueError) as exc:
            print(f"Investing proof report error: {exc}")
            return 2
        print(f"Core investing evidence strength: {payload['evidence_strength']}")
        print(f"Investing proof JSON: {payload['json_path']}")
        print(f"Investing proof MD:   {payload['markdown_path']}")
        return 0

    if args.command == "case-study":
        payload = run_case_study(
            ticker=args.ticker,
            signal_date=args.signal_date,
            horizons=_parse_horizons(args.horizons),
            output_dir=args.output_dir,
        )
        print(f"Case study JSON: {payload['json_path']}")
        print(f"Case study MD:   {payload['markdown_path']}")
        return 0

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
        choices=("standard", "outliers", "velocity", "investing"),
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
        "--alternative-data-file",
        type=Path,
        default=DEFAULT_ALTERNATIVE_DATA_PATH,
        help="Optional CSV or JSON file with verified insider/politician/alternative-data rows.",
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
    scan.add_argument("--archive", action="store_true", help="Archive a timestamped scan report under reports/scans/.")
    scan.add_argument("--archive-root", type=Path, default=DEFAULT_SCAN_ARCHIVE_ROOT, help="Root directory for archived scans.")

    daily = subparsers.add_parser("daily", help="Run scanner, archive results, generate alerts, and write daily summary.")
    daily.add_argument("--universe", type=Path, required=True, help="Path to a newline-delimited ticker file.")
    daily.add_argument("--provider", choices=("sample", "local", "real"), default="sample")
    daily.add_argument("--mode", choices=("standard", "outliers", "velocity", "investing"), default="outliers")
    daily.add_argument("--data-dir", type=Path)
    daily.add_argument("--history-period", default="3y")
    daily.add_argument("--output-dir", type=Path, default=DEFAULT_DAILY_OUTPUT_DIR)
    daily.add_argument("--archive-root", type=Path, default=DEFAULT_SCAN_ARCHIVE_ROOT)
    daily.add_argument("--state-path", type=Path, default=DEFAULT_WATCHLIST_STATE_PATH)
    daily.add_argument("--catalyst-file", type=Path)
    daily.add_argument("--alternative-data-file", type=Path, default=DEFAULT_ALTERNATIVE_DATA_PATH)
    daily.add_argument("--ai-explanations", action="store_true")
    daily.add_argument("--mock-ai-explanations", action="store_true")
    daily.add_argument("--limit", type=int, default=0)
    daily.add_argument("--as-of-date", type=_parse_date)

    decision_today = subparsers.add_parser("decision-today", help="Build the live Daily Decision snapshot used by the cockpit.")
    decision_today.add_argument("--provider", choices=("sample", "local", "real"), default="real")
    decision_today.add_argument("--core-universe", type=Path, default=Path("config/active_core_investing_universe.txt"))
    decision_today.add_argument("--outlier-universe", type=Path, default=Path("config/active_outlier_universe.txt"))
    decision_today.add_argument("--velocity-universe", type=Path, default=Path("config/active_velocity_universe.txt"))
    decision_today.add_argument("--broad-universe", type=Path)
    decision_today.add_argument("--tracked", type=Path, default=Path("config/tracked_tickers.txt"))
    decision_today.add_argument("--include-movers", action="store_true")
    decision_today.add_argument("--top-n", type=int, default=25)
    decision_today.add_argument("--data-dir", type=Path)
    decision_today.add_argument("--history-period", default="3y")
    decision_today.add_argument("--refresh-cache", action="store_true")
    decision_today.add_argument("--output-dir", type=Path, default=Path("outputs/daily"))
    decision_today.add_argument("--as-of-date", type=_parse_date)

    universe = subparsers.add_parser("universe", help="List or write curated starter universe files.")
    universe_subparsers = universe.add_subparsers(dest="universe_command", required=True)
    universe_subparsers.add_parser("list", help="List built-in universe sources.")
    universe_build = universe_subparsers.add_parser("build", help="Write a curated starter universe file.")
    universe_build.add_argument("--source", choices=("sp500", "nasdaq100", "top1000", "us_broad_1000", "liquid_growth", "ai_semis_software", "tracked"), required=True)
    universe_build.add_argument("--output", type=Path, required=True)
    universe_validate = universe_subparsers.add_parser("validate", help="Validate universe coverage labels and expected size.")
    universe_validate.add_argument("path", type=Path)
    universe_import = universe_subparsers.add_parser("import-csv", help="Import a CSV ticker list into a newline universe file.")
    universe_import.add_argument("--input", type=Path, required=True)
    universe_import.add_argument("--ticker-column", required=True)
    universe_import.add_argument("--output", type=Path, required=True)
    universe_clean = universe_subparsers.add_parser("clean", help="Clean, normalize, and dedupe a universe file.")
    universe_clean.add_argument("--input", type=Path, required=True)
    universe_clean.add_argument("--output", type=Path, required=True)

    tracked = subparsers.add_parser("tracked", help="Manage the tracked-tickers watchlist file.")
    tracked_subparsers = tracked.add_subparsers(dest="tracked_command", required=True)
    tracked_list = tracked_subparsers.add_parser("list", help="List tracked tickers.")
    tracked_list.add_argument("--path", type=Path, default=Path("config/tracked_tickers.txt"))
    tracked_add = tracked_subparsers.add_parser("add", help="Add one tracked ticker.")
    tracked_add.add_argument("ticker")
    tracked_add.add_argument("--path", type=Path, default=Path("config/tracked_tickers.txt"))
    tracked_remove = tracked_subparsers.add_parser("remove", help="Remove one tracked ticker.")
    tracked_remove.add_argument("ticker")
    tracked_remove.add_argument("--path", type=Path, default=Path("config/tracked_tickers.txt"))

    broad_scan = subparsers.add_parser("broad-scan", help="Scan a broader universe with caching and top-N ranking.")
    broad_scan.add_argument("--universe", type=Path, required=True)
    broad_scan.add_argument("--provider", choices=("sample", "local", "real"), default="real")
    broad_scan.add_argument("--data-dir", type=Path)
    broad_scan.add_argument("--history-period", default="3y")
    broad_scan.add_argument("--limit", type=int, default=0)
    broad_scan.add_argument("--batch-size", type=int, default=25)
    broad_scan.add_argument("--top-n", type=int, default=25)
    broad_scan.add_argument("--tracked", type=Path, default=Path("config/tracked_tickers.txt"))
    broad_scan.add_argument("--output-dir", type=Path, default=Path("outputs/broad_scan"))
    broad_scan.add_argument("--refresh-cache", action="store_true")
    broad_scan.add_argument("--as-of-date", type=_parse_date)

    market_health = subparsers.add_parser("market-health", help="Check live provider health and fallback readiness.")
    market_health.add_argument("--provider", choices=("sample", "local", "real"), default="real")
    market_health.add_argument("--history-period", default="6mo")
    market_health.add_argument("--ticker", default="SPY")

    movers = subparsers.add_parser("movers", help="Scan for top gainers, losers, and unusual-volume setups.")
    movers.add_argument("--universe", type=Path, required=True)
    movers.add_argument("--provider", choices=("sample", "local", "real"), default="real")
    movers.add_argument("--data-dir", type=Path)
    movers.add_argument("--history-period", default="3y")
    movers.add_argument("--top-n", type=int, default=25)
    movers.add_argument("--min-price", type=float, default=5.0)
    movers.add_argument("--min-dollar-volume", type=float, default=20_000_000.0)
    movers.add_argument("--include-speculative", action="store_true")
    movers.add_argument("--output-dir", type=Path, default=Path("outputs/movers"))
    movers.add_argument("--refresh-cache", action="store_true")
    movers.add_argument("--as-of-date", type=_parse_date)

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

    portfolio = subparsers.add_parser("portfolio", help="Manage local stock portfolio CSV.")
    portfolio_subparsers = portfolio.add_subparsers(dest="portfolio_command", required=True)
    portfolio_import = portfolio_subparsers.add_parser("import", help="Import generic/Fidelity-style holdings CSV.")
    portfolio_import.add_argument("--input", type=Path, required=True)
    portfolio_import.add_argument("--portfolio-path", type=Path, default=DEFAULT_PORTFOLIO_PATH)
    portfolio_list = portfolio_subparsers.add_parser("list", help="List local portfolio positions.")
    portfolio_list.add_argument("--portfolio-path", type=Path, default=DEFAULT_PORTFOLIO_PATH)
    portfolio_add = portfolio_subparsers.add_parser("add", help="Add or update a portfolio position.")
    portfolio_add.add_argument("--portfolio-path", type=Path, default=DEFAULT_PORTFOLIO_PATH)
    portfolio_add.add_argument("--ticker", required=True)
    portfolio_add.add_argument("--set", action="append", default=[], help="Set a field as key=value. May be repeated.")
    portfolio_refresh = portfolio_subparsers.add_parser("update-prices", help="Refresh current prices with a market data provider.")
    _add_review_provider_args(portfolio_refresh)
    portfolio_refresh.add_argument("--portfolio-path", type=Path, default=DEFAULT_PORTFOLIO_PATH)
    portfolio_analyze = portfolio_subparsers.add_parser("analyze", help="Analyze portfolio holdings.")
    _add_review_provider_args(portfolio_analyze)
    portfolio_analyze.add_argument("--portfolio-path", type=Path, default=DEFAULT_PORTFOLIO_PATH)
    portfolio_export = portfolio_subparsers.add_parser("export", help="Export portfolio CSV.")
    portfolio_export.add_argument("--portfolio-path", type=Path, default=DEFAULT_PORTFOLIO_PATH)
    portfolio_export.add_argument("--output", type=Path, required=True)

    predictions = subparsers.add_parser("predictions", help="Update and summarize paper prediction records.")
    predictions_subparsers = predictions.add_subparsers(dest="predictions_command", required=True)
    predictions_update = predictions_subparsers.add_parser("update", help="Refresh forward outcomes.")
    _add_review_provider_args(predictions_update)
    predictions_update.add_argument("--predictions-path", type=Path, default=DEFAULT_PREDICTIONS_PATH)
    predictions_summary = predictions_subparsers.add_parser("summary", help="Show validation metrics.")
    predictions_summary.add_argument("--predictions-path", type=Path, default=DEFAULT_PREDICTIONS_PATH)

    doctor = subparsers.add_parser("doctor", help="Run safe local/API readiness checks without printing secrets.")
    doctor.add_argument("--live", action="store_true", help="Run live provider checks where configured.")
    doctor.add_argument("--ai", choices=("none", "openai", "gemini"), default="none", help="Optional AI live check target.")
    doctor.add_argument("--ticker", default="NVDA", help="Ticker used for live provider probes.")
    doctor.add_argument("--output-dir", type=Path, default=Path("outputs"))

    readiness = subparsers.add_parser("readiness", help="Check whether TradeBruv is operational as a research/paper-tracking workflow.")
    readiness.add_argument("--universe", type=Path, default=Path("config/active_outlier_universe.txt"))
    readiness.add_argument("--provider", choices=("sample", "local", "real"), default="sample")
    readiness.add_argument("--tickers", default="NVDA,PLTR,MU,RDDT,SMCI,COIN,HOOD,ARM,CAVA,AAPL,MSFT,LLY,TSLA,AMD,AVGO")
    readiness.add_argument("--ai", choices=("mock", "openai", "gemini"), default="mock")
    readiness.add_argument("--output-dir", type=Path, default=Path("outputs"))

    signal_audit = subparsers.add_parser("signal-audit", help="Audit saved signals against baseline/random comparisons.")
    signal_audit.add_argument("--reports-dir", type=Path, default=Path("reports/scans"))
    signal_audit.add_argument("--baseline", default="SPY,QQQ")
    signal_audit.add_argument("--random-baseline", action="store_true")
    signal_audit.add_argument("--output-dir", type=Path, default=Path("outputs"))

    app_status = subparsers.add_parser("app-status", help="Write outputs/app_status_report.md summarizing actual app readiness.")
    app_status.add_argument("--output-dir", type=Path, default=Path("outputs"))

    price_debug = subparsers.add_parser("price-debug", help="Compare scanner/displayed prices against validated quote/latest close.")
    price_debug.add_argument("--tickers", required=True, help="Comma-separated tickers.")
    price_debug.add_argument("--provider", choices=("sample", "local", "real"), default="real")
    price_debug.add_argument("--history-period", default="3y")
    price_debug.add_argument("--as-of-date", type=_parse_date)
    price_debug.add_argument("--output-dir", type=Path, default=Path("outputs/debug"))

    replay = subparsers.add_parser("replay", help="Run no-lookahead historical scanner replay.")
    _add_review_provider_args(replay)
    replay.set_defaults(history_period="max")
    replay.add_argument("--universe", type=Path, required=True)
    replay.add_argument("--start-date", type=_parse_date, required=True)
    replay.add_argument("--end-date", type=_parse_date, required=True)
    replay.add_argument("--frequency", choices=("daily", "weekly"), default="weekly")
    replay.add_argument("--mode", choices=("outliers", "velocity"), default="outliers")
    replay.add_argument("--horizons", default="1,5,10,20,60,120")
    replay.add_argument("--top-n", type=int, default=20)
    replay.add_argument("--output-dir", type=Path, default=Path("outputs/replay"))

    investing_replay = subparsers.add_parser("investing-replay", help="Run monthly regular-investing validation against SPY/QQQ/random/equal-weight baselines.")
    _add_review_provider_args(investing_replay)
    investing_replay.set_defaults(history_period="max")
    investing_replay.add_argument("--universe", type=Path, required=True)
    investing_replay.add_argument("--start-date", type=_parse_date, required=True)
    investing_replay.add_argument("--end-date", type=_parse_date, required=True)
    investing_replay.add_argument("--frequency", choices=("daily", "weekly", "monthly"), default="monthly")
    investing_replay.add_argument("--horizons", default="20,60,120,252")
    investing_replay.add_argument("--top-n", type=int, default=10)
    investing_replay.add_argument("--baseline", default="SPY,QQQ")
    investing_replay.add_argument("--random-baseline", action="store_true")
    investing_replay.add_argument("--output-dir", type=Path, default=Path("outputs/investing"))

    portfolio_replay = subparsers.add_parser("portfolio-replay", help="Validate portfolio-aware core investing decisions in a simulated historical portfolio.")
    _add_review_provider_args(portfolio_replay)
    portfolio_replay.set_defaults(history_period="max")
    portfolio_replay.add_argument("--universe", type=Path, required=True)
    portfolio_replay.add_argument("--start-date", type=_parse_date, required=True)
    portfolio_replay.add_argument("--end-date", type=_parse_date, required=True)
    portfolio_replay.add_argument("--frequency", choices=("daily", "weekly", "monthly"), default="monthly")
    portfolio_replay.add_argument("--output-dir", type=Path, default=Path("outputs/investing"))

    outlier_study = subparsers.add_parser("outlier-study", help="Run famous outlier point-in-time case studies.")
    _add_review_provider_args(outlier_study)
    outlier_study.set_defaults(history_period="max")
    outlier_study.add_argument("--ticker")
    outlier_study.add_argument("--start-date", type=_parse_date)
    outlier_study.add_argument("--end-date", type=_parse_date)
    outlier_study.add_argument("--preset", choices=("famous",), help="Run the built-in famous outlier windows.")
    outlier_study.add_argument("--mode", choices=("outliers", "velocity"), default="outliers")
    outlier_study.add_argument("--output-dir", type=Path, default=Path("outputs/case_studies"))

    proof = subparsers.add_parser("proof-report", help="Run replay, optional famous outliers, optional velocity, and write an evidence report.")
    _add_review_provider_args(proof)
    proof.set_defaults(history_period="max")
    proof.add_argument("--universe", type=Path, required=True)
    proof.add_argument("--start-date", type=_parse_date, required=True)
    proof.add_argument("--end-date", type=_parse_date, required=True)
    proof.add_argument("--include-famous-outliers", action="store_true")
    proof.add_argument("--include-velocity", action="store_true")
    proof.add_argument("--baseline", default="SPY,QQQ")
    proof.add_argument("--random-baseline", action="store_true")
    proof.add_argument("--output-dir", type=Path, default=Path("outputs/proof"))

    investing_proof = subparsers.add_parser("investing-proof-report", help="Write the Core Investing evidence report.")
    _add_review_provider_args(investing_proof)
    investing_proof.set_defaults(history_period="max")
    investing_proof.add_argument("--universe", type=Path, required=True)
    investing_proof.add_argument("--start-date", type=_parse_date, required=True)
    investing_proof.add_argument("--end-date", type=_parse_date, required=True)
    investing_proof.add_argument("--baseline", default="SPY,QQQ")
    investing_proof.add_argument("--random-baseline", action="store_true")
    investing_proof.add_argument("--output-dir", type=Path, default=Path("outputs/investing"))

    case_study = subparsers.add_parser("case-study", help="Run a famous outlier case-study workflow.")
    case_study.add_argument("--ticker", required=True)
    case_study.add_argument("--signal-date", type=_parse_date, required=True)
    case_study.add_argument("--horizons", default="5,10,20,60,120")
    case_study.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser


def load_universe(path: Path) -> list[str]:
    tickers: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tickers.append(display_ticker(line))
    return tickers


def _run_scan(*, args: argparse.Namespace, analysis_date: date):
    universe = load_universe(args.universe)
    provider = build_provider(args=args, analysis_date=analysis_date)
    catalyst_repository = load_catalyst_repository(args.catalyst_file)
    if catalyst_repository.warnings:
        for warning in catalyst_repository.warnings:
            print(f"Catalyst warning: {warning}")
    if catalyst_repository.items_by_ticker:
        provider = CatalystOverlayProvider(provider, catalyst_repository)
    alternative_repository = load_alternative_data_repository(args.alternative_data_file)
    if alternative_repository.warnings:
        for warning in alternative_repository.warnings:
            print(f"Alternative data warning: {warning}")
    if alternative_repository.items_by_ticker:
        provider = AlternativeDataOverlayProvider(provider, alternative_repository)

    scanner = DeterministicScanner(provider=provider, analysis_date=analysis_date)
    results = scanner.scan(universe, mode=args.mode)
    if args.ai_explanations:
        explanation_provider = build_explanation_provider(enabled=True, mock=args.mock_ai_explanations)
        apply_ai_explanations(results, explanation_provider)
    if args.limit:
        results = results[: args.limit]
    return results, provider


def _handle_daily(args: argparse.Namespace) -> int:
    analysis_date = args.as_of_date or date.today()
    try:
        results, provider = _run_scan(args=args, analysis_date=analysis_date)
    except (ProviderConfigurationError, FileNotFoundError) as exc:
        print(f"Daily scan error: {exc}")
        return 2

    archived = archive_scan_report(
        results=results,
        provider=args.provider,
        mode=args.mode,
        universe_file=args.universe,
        catalyst_file=args.catalyst_file,
        ai_enabled=args.ai_explanations,
        command_used=_command_used(),
        archive_root=args.archive_root,
    )
    rows = [result.to_dict() for result in results]
    previous_state = load_watchlist_state(args.state_path)
    new_state, changes = update_watchlist_state(
        previous_state=previous_state,
        rows=rows,
        scan_id=archived["scan_id"],
        timestamp=archived["metadata"]["created_at"],
    )
    alerts = generate_alerts(
        changes=changes,
        source_scan_id=archived["scan_id"],
        timestamp=archived["metadata"]["created_at"],
        ai_enabled=args.ai_explanations,
    )
    save_watchlist_state(new_state, args.state_path)
    summary = build_daily_summary_payload(
        rows=rows,
        alerts=alerts,
        scan_metadata=archived["metadata"],
        market_regime=build_simple_market_regime(provider),
    )
    outputs = write_daily_outputs(alerts=alerts, summary_payload=summary, output_dir=args.output_dir)
    print_console_summary(results, mode=args.mode)
    print(f"\nArchived JSON: {archived['json_path']}")
    print(f"Archived CSV:  {archived['csv_path']}")
    print(f"Watchlist state: {args.state_path}")
    print(f"Alerts JSON: {outputs['alerts_json']}")
    print(f"Alerts CSV:  {outputs['alerts_csv']}")
    print(f"Daily summary JSON: {outputs['summary_json']}")
    print(f"Daily summary MD:   {outputs['summary_markdown']}")
    print(f"Alerts generated: {len(alerts)}")
    return 0


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


def _command_used() -> str:
    return " ".join(sys.argv)


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


def _handle_portfolio(args: argparse.Namespace) -> int:
    try:
        if args.portfolio_command == "import":
            rows = import_portfolio_csv(args.input, args.portfolio_path)
            print(f"Imported positions: {len(rows)}")
            return 0
        if args.portfolio_command == "list":
            rows = load_portfolio(args.portfolio_path)
            if not rows:
                print("No portfolio positions found.")
                return 0
            for row in rows:
                payload = row.to_dict()
                print(
                    f"{payload['account_name']} | {payload['ticker']} | qty={payload['quantity']} | "
                    f"value={payload['market_value']} | weight={payload['position_weight_pct']} | {payload['decision_status']}"
                )
            return 0
        if args.portfolio_command == "add":
            updates = _parse_set_args(args.set)
            position = upsert_position(position={"ticker": args.ticker, **updates}, portfolio_path=args.portfolio_path)
            print(f"Saved position: {position.account_name} {position.ticker}")
            return 0
        if args.portfolio_command == "update-prices":
            provider = build_provider(args=args, analysis_date=args.price_as_of_date or date.today())
            rows = refresh_portfolio_prices(positions=load_portfolio(args.portfolio_path), provider=provider)
            save_portfolio(rows, args.portfolio_path)
            print(f"Updated prices for {len(rows)} positions.")
            return 0
        if args.portfolio_command == "analyze":
            provider = build_provider(args=args, analysis_date=args.price_as_of_date or date.today())
            payload = analyze_portfolio(positions=load_portfolio(args.portfolio_path), provider=provider)
            print(json.dumps(payload, indent=2))
            return 0
        if args.portfolio_command == "export":
            export_portfolio_csv(load_portfolio(args.portfolio_path), args.output)
            print(f"Portfolio exported: {args.output}")
            return 0
    except (ValueError, ProviderConfigurationError, FileNotFoundError) as exc:
        print(f"Portfolio error: {exc}")
        return 2
    print(f"Unknown portfolio command: {args.portfolio_command}")
    return 2


def _handle_predictions(args: argparse.Namespace) -> int:
    try:
        if args.predictions_command == "update":
            provider = build_provider(args=args, analysis_date=args.price_as_of_date or date.today())
            records = update_prediction_outcomes(records=load_predictions(args.predictions_path), provider=provider)
            save_predictions(records, args.predictions_path)
            print(f"Updated predictions: {len(records)}")
            return 0
        if args.predictions_command == "summary":
            print(json.dumps(validation_metrics(load_predictions(args.predictions_path)), indent=2))
            return 0
    except (ProviderConfigurationError, FileNotFoundError, ValueError) as exc:
        print(f"Prediction error: {exc}")
        return 2
    print(f"Unknown predictions command: {args.predictions_command}")
    return 2


def _parse_set_args(values: list[str]) -> dict[str, str]:
    updates = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--set values must be key=value, got: {value}")
        key, raw = value.split("=", 1)
        updates[key.strip()] = raw.strip()
    return updates
