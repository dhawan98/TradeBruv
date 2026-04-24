from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import streamlit as st

from tradebruv.cli import build_provider
from tradebruv.dashboard_data import (
    DEFAULT_UNIVERSE_FILES,
    DashboardReport,
    build_process_quality_summary,
    build_daily_summary,
    build_review_summary,
    build_strategy_performance_highlights,
    classify_avoid_reasons,
    extract_options_fields,
    filter_results,
    filter_review_results,
    find_latest_report,
    is_avoid,
    load_dashboard_journal,
    load_dashboard_report,
    load_review_report,
    load_strategy_performance,
    run_dashboard_review,
    run_dashboard_review_batch,
    run_dashboard_scan,
    sort_results,
    unique_theme_tags,
    unique_values,
)
from tradebruv.journal import (
    DECISIONS,
    DEFAULT_JOURNAL_PATH,
    MISTAKE_CATEGORIES,
    add_journal_entry,
    update_journal_entry,
)
from tradebruv.performance import build_strategy_performance_report
from tradebruv.providers import ProviderConfigurationError


TABLE_COLUMNS = [
    "ticker",
    "current_price",
    "status_label",
    "strategy_label",
    "outlier_type",
    "outlier_score",
    "winner_score",
    "setup_quality_score",
    "risk_score",
    "bullish_score",
    "bearish_pressure_score",
    "reward_risk",
    "catalyst_score",
    "catalyst_quality",
    "catalyst_type",
    "social_attention_score",
    "relative_strength_notes",
    "volume_accumulation_notes",
    "theme_tags",
    "catalyst_tags",
    "data_availability",
]


def main() -> None:
    st.set_page_config(page_title="TradeBruv Research Cockpit", layout="wide")
    _style()

    st.title("TradeBruv Research Cockpit")
    st.caption("Deterministic scanner visualization and research workflow. No AI, no broker integration, no execution.")

    _sidebar_controls()
    report = _active_report()
    if report is None:
        rows: list[dict[str, Any]] = []
        filtered: list[dict[str, Any]] = []
        st.info("Run a scan or load a JSON report to start. Journal and performance pages can still load local files.")
    else:
        rows = sort_results(report.results, sort_by="outlier_score")
        filters = _filter_controls(rows)
        filtered = sort_results(
            filter_results(rows, filters),
            sort_by=st.session_state.get("sort_by", "outlier_score"),
            descending=st.session_state.get("sort_desc", True),
        )

        _report_header(report, filtered_count=len(filtered))
        _market_regime_panel(report)
        _daily_summary_panel(build_daily_summary(rows))

    tabs = st.tabs([
        "Outlier Feed",
        "Scanner Table",
        "Stock Detail",
        "Catalysts",
        "Social Attention",
        "AI Explanation",
        "Avoid Panel",
        "Watchlists",
        "Options Placeholder",
        "Historical Review",
        "Strategy Performance",
        "Journal",
        "Process Quality",
    ])
    with tabs[0]:
        _outlier_feed(filtered)
    with tabs[1]:
        _scanner_table(filtered)
    with tabs[2]:
        _stock_detail(filtered or rows)
    with tabs[3]:
        _catalyst_panel(filtered or rows)
    with tabs[4]:
        _social_attention_panel(filtered or rows)
    with tabs[5]:
        _ai_explanation_panel(filtered or rows)
    with tabs[6]:
        _avoid_panel(rows)
    with tabs[7]:
        _watchlist_help()
    with tabs[8]:
        _options_placeholder(rows)
    with tabs[9]:
        _historical_review_page()
    with tabs[10]:
        _strategy_performance_page()
    with tabs[11]:
        _journal_page(filtered or rows)
    with tabs[12]:
        _process_quality_page()


def _sidebar_controls() -> None:
    with st.sidebar:
        st.header("Run Scanner")
        provider_name = st.selectbox("Provider", ["sample", "real"], index=0)
        mode = st.selectbox("Mode", ["outliers", "standard"], index=0)
        universe_label = st.selectbox("Universe file", list(DEFAULT_UNIVERSE_FILES), index=0)
        universe_path = Path(st.text_input("Universe path", str(DEFAULT_UNIVERSE_FILES[universe_label])))
        limit = st.number_input("Result limit", min_value=0, max_value=500, value=50, step=5)
        history_period = st.text_input("Real provider history period", "3y")
        catalyst_path_raw = st.text_input("Catalyst CSV/JSON path", "config/catalysts_watchlist.csv")
        enable_ai = st.checkbox("Enable AI explanations", value=False)
        mock_ai = st.checkbox("Use mock AI provider", value=False)
        use_as_of = st.checkbox("Use fixed as-of date", value=provider_name == "sample")
        as_of_date = st.date_input("As-of date", date(2026, 4, 24)) if use_as_of else None

        if st.button("Run scan", type="primary", use_container_width=True):
            try:
                report = run_dashboard_scan(
                    provider_name=provider_name,
                    mode=mode,
                    universe_path=universe_path,
                    limit=int(limit),
                    analysis_date=as_of_date,
                    history_period=history_period,
                    catalyst_file=Path(catalyst_path_raw) if catalyst_path_raw else None,
                    ai_explanations=enable_ai,
                    mock_ai_explanations=mock_ai,
                )
            except (ProviderConfigurationError, FileNotFoundError, ValueError) as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Scan failed: {exc}")
            else:
                st.session_state["report"] = report

        st.divider()
        st.header("Load Report")
        if st.button("Load latest JSON report", use_container_width=True):
            latest = find_latest_report()
            if latest is None:
                st.warning("No scan_report.json or outlier_scan_report.json found under outputs/.")
            else:
                st.session_state["report"] = load_dashboard_report(latest)
        custom_path = st.text_input("Custom JSON report path", "")
        if st.button("Load custom report", use_container_width=True):
            if not custom_path:
                st.warning("Enter a JSON report path first.")
            else:
                try:
                    st.session_state["report"] = load_dashboard_report(Path(custom_path))
                except Exception as exc:
                    st.error(f"Could not load report: {exc}")


def _filter_controls(rows: list[dict[str, Any]]) -> dict[str, Any]:
    with st.sidebar:
        st.divider()
        st.header("Filters")
        status = st.multiselect("Status", unique_values(rows, "status_label"))
        strategy = st.multiselect("Strategy", unique_values(rows, "strategy_label"))
        outlier_type = st.multiselect("Outlier type", unique_values(rows, "outlier_type"))
        risk_level = st.multiselect("Risk level", unique_values(rows, "outlier_risk"))
        theme_tag = st.selectbox("Theme tag", ["", *unique_theme_tags(rows)])
        min_outlier_score = st.slider("Minimum outlier score", 0, 100, 0)
        min_winner_score = st.slider("Minimum winner score", 0, 100, 0)
        exclude_avoid = st.checkbox("Exclude Avoid", value=False)
        active_only = st.checkbox("Show only Active Setup", value=False)
        watch_only = st.checkbox("Show only Watch Only", value=False)
        high_risk_outlier_only = st.checkbox("High Risk Outlier / Squeeze Watch only", value=False)
        st.session_state["sort_by"] = st.selectbox(
            "Sort by",
            ["outlier_score", "winner_score", "setup_quality_score", "risk_score", "reward_risk", "ticker"],
        )
        st.session_state["sort_desc"] = st.toggle("Descending", value=True)
    return {
        "status": status,
        "strategy": strategy,
        "outlier_type": outlier_type,
        "risk_level": risk_level,
        "theme_tag": theme_tag,
        "min_outlier_score": min_outlier_score,
        "min_winner_score": min_winner_score,
        "exclude_avoid": exclude_avoid,
        "active_only": active_only,
        "watch_only": watch_only,
        "high_risk_outlier_only": high_risk_outlier_only,
    }


def _active_report() -> DashboardReport | None:
    report = st.session_state.get("report")
    return report if isinstance(report, DashboardReport) else None


def _report_header(report: DashboardReport, *, filtered_count: int) -> None:
    cols = st.columns(5)
    cols[0].metric("Mode", report.mode)
    cols[1].metric("Provider", report.provider)
    cols[2].metric("Results", len(report.results))
    cols[3].metric("Filtered", filtered_count)
    cols[4].metric("Generated", report.generated_at[:19] if report.generated_at else "unavailable")
    st.caption(f"Source: {report.source}")


def _market_regime_panel(report: DashboardReport) -> None:
    regime = report.market_regime
    st.subheader("Market Regime")
    cols = st.columns([1.2, 2, 2, 2])
    cols[0].metric("Regime", regime.get("regime", "Unavailable"))
    cols[1].write(regime.get("spy", {}).get("summary", "SPY unavailable."))
    cols[2].write(regime.get("qqq", {}).get("summary", "QQQ unavailable."))
    stance = []
    if regime.get("aggressive_longs_allowed"):
        stance.append("Aggressive longs allowed")
    if regime.get("be_selective"):
        stance.append("Be selective")
    if regime.get("mostly_watch_cash"):
        stance.append("Mostly watch/cash")
    cols[3].write(" / ".join(stance) or "No stance available")

    tag_cols = st.columns(2)
    tag_cols[0].caption("Leading sector/theme tags")
    tag_cols[0].write(_join_tags(regime.get("leading_tags", [])))
    tag_cols[1].caption("Weak sector/theme tags")
    tag_cols[1].write(_join_tags(regime.get("weak_tags", [])))
    for warning in regime.get("risk_warnings", []):
        st.warning(warning)
    st.caption(f"Regime timestamp/provider: {regime.get('timestamp', 'unavailable')} / {regime.get('provider', 'unavailable')}")


def _daily_summary_panel(summary: dict[str, Any]) -> None:
    st.subheader("Daily Summary")
    cols = st.columns(4)
    cols[0].caption("Top outlier candidates")
    cols[0].write(_compact_list(summary["top_outlier_candidates"]))
    cols[1].caption("Top normal winner candidates")
    cols[1].write(_compact_list(summary["top_winner_candidates"]))
    cols[2].caption("Top avoid names")
    cols[2].write(_compact_list(summary["top_avoid_names"]))
    cols[3].caption("Common warnings")
    cols[3].write(_counter_list(summary["common_warnings"]))

    cols = st.columns(4)
    cols[0].caption("Highest risk")
    cols[0].write(_single_compact(summary["highest_risk_candidate"]))
    cols[1].caption("Best reward/risk")
    cols[1].write(_single_compact(summary["best_reward_risk_candidate"]))
    cols[2].caption("Best long-term monster")
    cols[2].write(_single_compact(summary["best_long_term_monster_candidate"]))
    cols[3].caption("Best squeeze/high-risk watch")
    cols[3].write(_single_compact(summary["best_squeeze_watch_candidate"]))
    cols = st.columns(3)
    cols[0].caption("Top official catalysts")
    cols[0].write(_compact_list(summary["top_official_catalysts"]))
    cols[1].caption("Top narrative catalysts")
    cols[1].write(_compact_list(summary["top_narrative_catalysts"]))
    cols[2].caption("Top social attention")
    cols[2].write(_compact_list(summary["top_social_attention_names"]))
    cols = st.columns(3)
    cols[0].caption("Highest hype risk")
    cols[0].write(_compact_list(summary["highest_hype_risk_names"]))
    cols[1].caption("Price-confirmed catalysts")
    cols[1].write(_compact_list(summary["top_price_confirmed_catalysts"]))
    cols[2].caption("Watch-only attention")
    cols[2].write(_compact_list(summary["watch_only_attention_names"]))


def _outlier_feed(rows: list[dict[str, Any]]) -> None:
    st.subheader("Outlier Winner Feed")
    ranked = sort_results(rows, sort_by="outlier_score")[:30]
    if not ranked:
        st.info("No results match the current filters.")
        return
    for row in ranked:
        _outlier_card(row)


def _outlier_card(row: dict[str, Any]) -> None:
    status_class = _status_class(row)
    st.markdown(
        f"""
        <div class="tb-card {status_class}">
          <div class="tb-card-head">
            <div><strong>{row['ticker']}</strong> <span>{row.get('company_name', 'unavailable')}</span></div>
            <div class="tb-score">Outlier {row['outlier_score']} / Winner {row['winner_score']}</div>
          </div>
          <div class="tb-grid">
            <span>Status: <strong>{row['status_label']}</strong></span>
            <span>Strategy: <strong>{row['strategy_label']}</strong></span>
            <span>Type: <strong>{row['outlier_type']}</strong></span>
            <span>Risk: <strong>{row['outlier_risk']}</strong></span>
            <span>Setup quality: <strong>{row['setup_quality_score']}</strong></span>
            <span>Risk score: <strong>{row['risk_score']}</strong></span>
            <span>Confidence: <strong>{row['confidence_label']}</strong></span>
            <span>Holding: <strong>{row['holding_period']}</strong></span>
          </div>
          <div class="tb-grid">
            <span>Price: <strong>{row['current_price']}</strong></span>
            <span>Entry: <strong>{row['entry_zone']}</strong></span>
            <span>Invalidation: <strong>{row['invalidation_level']}</strong></span>
            <span>Stop: <strong>{row['stop_loss_reference']}</strong></span>
            <span>TP1: <strong>{row['tp1']}</strong></span>
            <span>TP2: <strong>{row['tp2']}</strong></span>
            <span>R/R: <strong>{row['reward_risk']}</strong></span>
          </div>
          <p><strong>Theme:</strong> {_join_tags(row['theme_tags'])}</p>
          <p><strong>Catalysts:</strong> {_join_tags(row['catalyst_tags'])}</p>
          <p><strong>Catalyst quality:</strong> {row['catalyst_quality']} | <strong>Score:</strong> {row['catalyst_score']} | <strong>Sources:</strong> {row['catalyst_source_count']}</p>
          <p><strong>Big winner case:</strong> {_first_sentence(row['why_it_could_be_a_big_winner'], row['outlier_reason'])}</p>
          <p><strong>Failure case:</strong> {_first_sentence(row['why_it_could_fail'], 'No specific failure reason available.')}</p>
          <p class="tb-warning"><strong>Chase risk:</strong> {row.get('chase_risk_warning', 'unavailable')}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _scanner_table(rows: list[dict[str, Any]]) -> None:
    st.subheader("Scanner Table")
    table_rows = []
    for row in rows:
        enriched = dict(row)
        enriched["relative_strength_notes"] = _matching_notes(row, "relative strength")
        enriched["volume_accumulation_notes"] = _matching_notes(row, "volume", "accumulation")
        enriched["theme_tags"] = " | ".join(row["theme_tags"])
        enriched["catalyst_tags"] = " | ".join(row["catalyst_tags"])
        enriched["data_availability"] = " | ".join(row["data_availability_notes"][:3])
        table_rows.append({key: enriched.get(key, "") for key in TABLE_COLUMNS})
    st.dataframe(table_rows, hide_index=True, use_container_width=True)


def _stock_detail(rows: list[dict[str, Any]]) -> None:
    st.subheader("Stock Detail")
    if not rows:
        st.info("No stock selected.")
        return
    tickers = [row["ticker"] for row in rows]
    selected = st.selectbox("Ticker", tickers)
    row = next(item for item in rows if item["ticker"] == selected)
    cols = st.columns([1, 1, 1, 1])
    cols[0].metric("Outlier score", row["outlier_score"])
    cols[1].metric("Winner score", row["winner_score"])
    cols[2].metric("Setup quality", row["setup_quality_score"])
    cols[3].metric("Risk score", row["risk_score"])

    st.error("Why NOT to buy? " + _first_sentence(row["why_it_could_fail"], "No specific failure reason available."))
    for warning in row["warnings"]:
        st.warning(warning)

    cols = st.columns(2)
    with cols[0]:
        st.markdown("**Setup**")
        st.write(
            {
                "status": row["status_label"],
                "strategy": row["strategy_label"],
                "outlier_type": row["outlier_type"],
                "outlier_risk": row["outlier_risk"],
                "holding_period": row["holding_period"],
                "entry_zone": row["entry_zone"],
                "invalidation": row["invalidation_level"],
                "stop_reference": row["stop_loss_reference"],
                "tp1": row["tp1"],
                "tp2": row["tp2"],
                "reward_risk": row["reward_risk"],
            }
        )
        st.markdown("**Why it passed**")
        st.write(row["why_it_passed"] or ["No pass reasons available."])
        st.markdown("**Outlier reason**")
        st.write(row["outlier_reason"])
        st.write(row["why_it_could_be_a_big_winner"] or ["No big-winner reasons available."])
    with cols[1]:
        st.markdown("**Scoring breakdown**")
        st.write(row.get("component_scores", {}))
        st.markdown("**Strategy alignment**")
        st.write(row.get("strategy_alignment", {}))
        st.markdown("**Signals used**")
        st.write(row["signals_used"] or ["No signals listed."])
        st.markdown("**Data availability notes**")
        st.write(row["data_availability_notes"] or ["No data gaps reported."])
        st.markdown("**Squeeze watch**")
        st.write(row.get("squeeze_watch", {}))
        st.markdown("**Catalyst intelligence**")
        st.write(
            {
                "catalyst_score": row["catalyst_score"],
                "catalyst_quality": row["catalyst_quality"],
                "catalyst_type": row["catalyst_type"],
                "official_catalyst_found": row["official_catalyst_found"],
                "narrative_catalyst_found": row["narrative_catalyst_found"],
                "hype_catalyst_found": row["hype_catalyst_found"],
                "recency": row["catalyst_recency"],
                "source_urls": row["source_urls"],
                "source_timestamps": row["source_timestamps"],
            }
        )
        st.markdown("**Catalyst/news/social items**")
        st.write(row.get("catalyst_items", []))
        st.markdown("**Options placeholder**")
        st.write(row.get("options_placeholders", {}))
        st.markdown("**AI-generated explanation**")
        st.write(row.get("ai_explanation", {"summary": "AI explanation unavailable."}))


def _catalyst_panel(rows: list[dict[str, Any]]) -> None:
    st.subheader("Catalyst Panel")
    catalyst_rows = sort_results(rows, sort_by="catalyst_score")
    if not catalyst_rows:
        st.info("No catalyst data available.")
        return
    for row in catalyst_rows[:30]:
        with st.expander(f"{row['ticker']} | {row['catalyst_quality']} | {row['catalyst_type']} | score {row['catalyst_score']}"):
            cols = st.columns(4)
            cols[0].metric("Source count", row["catalyst_source_count"])
            cols[1].metric("Recency", row["catalyst_recency"])
            cols[2].metric("Official", str(row["official_catalyst_found"]))
            cols[3].metric("Hype", str(row["hype_catalyst_found"]))
            st.write(
                {
                    "narrative_catalyst_found": row["narrative_catalyst_found"],
                    "price_volume_confirms_catalyst": row["price_volume_confirms_catalyst"],
                    "source_urls": row["source_urls"],
                    "source_provider_notes": row["source_provider_notes"],
                    "missing_reason": row["catalyst_data_missing_reason"],
                }
            )
            st.dataframe(row.get("catalyst_items", []), hide_index=True, use_container_width=True)


def _social_attention_panel(rows: list[dict[str, Any]]) -> None:
    st.subheader("Social Attention Panel")
    social_rows = sort_results(rows, sort_by="social_attention_score")
    for row in social_rows[:30]:
        if not row["social_attention_available"] and row["social_attention_score"] == 0:
            continue
        with st.expander(f"{row['ticker']} | social {row['social_attention_score']} | velocity {row['social_attention_velocity']}"):
            st.write(
                {
                    "news_attention_score": row["news_attention_score"],
                    "news_sentiment_label": row["news_sentiment_label"],
                    "attention_spike": row["attention_spike"],
                    "hype_risk": row["hype_risk"],
                    "pump_risk": row["pump_risk"],
                    "price_volume_confirms_attention": row["price_volume_confirms_catalyst"],
                }
            )
            social_items = [
                item
                for item in row.get("catalyst_items", [])
                if item.get("source_type") in {"reddit", "twitter_x", "truth_social", "news"}
            ]
            st.dataframe(social_items, hide_index=True, use_container_width=True)


def _ai_explanation_panel(rows: list[dict[str, Any]]) -> None:
    st.subheader("AI Explanation Panel")
    st.caption("Optional, AI-generated explanation. It is grounded in scanner/report fields and does not create scores or trade signals.")
    if not rows:
        st.info("No rows available.")
        return
    selected = st.selectbox("AI ticker", [row["ticker"] for row in rows], key="ai_ticker")
    row = next(item for item in rows if item["ticker"] == selected)
    explanation = row.get("ai_explanation", {})
    if not explanation.get("available"):
        st.info(explanation.get("summary", "AI explanation unavailable."))
        return
    st.markdown("**AI-generated explanation**")
    st.write(explanation.get("summary", "unavailable"))
    cols = st.columns(2)
    cols[0].markdown("**Bull case**")
    cols[0].write(explanation.get("bull_case", []))
    cols[0].markdown("**Catalyst summary**")
    cols[0].write(explanation.get("catalyst_summary", "unavailable"))
    cols[1].markdown("**Bear case / Why not to buy**")
    cols[1].write(explanation.get("bear_case", []))
    cols[1].write(explanation.get("why_not_to_buy", []))
    st.markdown("**Invalidation and checklist**")
    st.write(explanation.get("setup_invalidation", "unavailable"))
    st.write(explanation.get("research_checklist", []))
    st.markdown("**Source item refs**")
    st.write(explanation.get("source_item_refs", []))


def _avoid_panel(rows: list[dict[str, Any]]) -> None:
    st.subheader("Avoid / Bad Setup Panel")
    avoid_rows = [row for row in rows if is_avoid(row) or classify_avoid_reasons(row)]
    if not avoid_rows:
        st.success("No Avoid names in this report.")
        return
    for row in sort_results(avoid_rows, sort_by="risk_score"):
        reasons = classify_avoid_reasons(row)
        st.markdown(
            f"""
            <div class="tb-card avoid">
              <div class="tb-card-head">
                <div><strong>{row['ticker']}</strong> <span>{row.get('company_name', 'unavailable')}</span></div>
                <div class="tb-score">Risk {row['risk_score']} / Bearish {row['bearish_pressure_score']}</div>
              </div>
              <p><strong>Status:</strong> {row['status_label']} | <strong>Reasons:</strong> {_join_tags(reasons)}</p>
              <p><strong>Why NOT to buy:</strong> {_first_sentence(row['why_it_could_fail'], 'No specific failure reason available.')}</p>
              <p><strong>Warnings:</strong> {_join_tags(row['warnings'])}</p>
              <p><strong>Invalidation:</strong> {row['invalidation_level']} | <strong>Reward/risk:</strong> {row['reward_risk']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _watchlist_help() -> None:
    st.subheader("Watchlist View")
    st.write("Use the sidebar to choose provider, scanner mode, universe file, and result limit. No code edits are required.")
    st.write({label: str(path) for label, path in DEFAULT_UNIVERSE_FILES.items()})


def _options_placeholder(rows: list[dict[str, Any]]) -> None:
    st.subheader("Options Placeholder")
    option_rows = []
    for row in rows:
        fields = extract_options_fields(row)
        if fields:
            option_rows.append({"ticker": row["ticker"], **fields})
    if not option_rows:
        st.info("No options placeholder fields are available in this report.")
        return
    st.caption("Placeholder only. No contracts, Greeks, strategy builder, or execution recommendations.")
    st.dataframe(option_rows, hide_index=True, use_container_width=True)


def _historical_review_page() -> None:
    st.subheader("Historical Review")
    st.caption("Saved-report forward review only. It does not guarantee future performance and is not financial advice.")
    cols = st.columns(4)
    report_path = Path(cols[0].text_input("Scan report path", "outputs/outlier_scan_report.json"))
    provider_name = cols[1].selectbox("Review provider", ["sample", "real", "local"], index=0)
    horizons_raw = cols[2].text_input("Horizons", "5,10,20,60")
    price_as_of = cols[3].date_input("Price data as-of", date.today())
    reports_dir = Path(st.text_input("Reports directory", "reports/history"))
    data_dir_raw = st.text_input("Local data dir", "")
    signal_override = st.text_input("Signal date override", "")

    run_cols = st.columns(3)
    if run_cols[0].button("Run forward review", use_container_width=True):
        try:
            provider = build_provider(
                args=SimpleNamespace(
                    provider=provider_name,
                    data_dir=Path(data_dir_raw) if data_dir_raw else None,
                    history_period="3y",
                ),
                analysis_date=price_as_of,
            )
            review = run_dashboard_review(
                report_path=report_path,
                provider=provider,
                horizons=_parse_horizon_text(horizons_raw),
                signal_date=date.fromisoformat(signal_override) if signal_override else None,
            )
            st.session_state["review_report"] = review
        except Exception as exc:
            st.error(f"Review failed: {exc}")
    if run_cols[1].button("Run directory review", use_container_width=True):
        try:
            provider = build_provider(
                args=SimpleNamespace(
                    provider=provider_name,
                    data_dir=Path(data_dir_raw) if data_dir_raw else None,
                    history_period="3y",
                ),
                analysis_date=price_as_of,
            )
            review = run_dashboard_review_batch(
                reports_dir=reports_dir,
                provider=provider,
                horizons=_parse_horizon_text(horizons_raw),
                signal_date=date.fromisoformat(signal_override) if signal_override else None,
            )
            st.session_state["review_report"] = review
        except Exception as exc:
            st.error(f"Directory review failed: {exc}")
    load_path = Path(run_cols[2].text_input("Load review JSON", "outputs/review_report.json"))
    if st.button("Load review report", use_container_width=True):
        try:
            st.session_state["review_report"] = load_review_report(load_path)
        except Exception as exc:
            st.error(f"Could not load review report: {exc}")

    review = st.session_state.get("review_report")
    if not isinstance(review, dict):
        st.info("Run or load a review report to see forward results.")
        return
    summary = build_review_summary(review.get("results", []))
    cols = st.columns(6)
    cols[0].metric("Rows", summary["total_rows"])
    cols[1].metric("Available", summary["available_rows"])
    cols[2].metric("Unavailable", summary["unavailable_rows"])
    cols[3].metric("Avg fwd return", summary["average_forward_return"])
    cols[4].metric("TP1 hits", summary["tp1_hits"])
    cols[5].metric("Invalidations", summary["invalidation_hits"])

    rows = review.get("results", [])
    filters = {
        "strategy": st.multiselect("Review strategy filter", unique_values(rows, "strategy_label")),
        "outlier_type": st.multiselect("Review outlier type filter", unique_values(rows, "outlier_type")),
        "status": st.multiselect("Review status filter", unique_values(rows, "status_label")),
        "only_available": st.checkbox("Only available review rows", value=True),
    }
    st.dataframe(filter_review_results(rows, filters), hide_index=True, use_container_width=True)


def _strategy_performance_page() -> None:
    st.subheader("Strategy Performance")
    st.caption("Use this to evaluate scanner rules over time. Small sample sizes are unreliable.")
    performance_path = Path(st.text_input("Strategy performance JSON", "outputs/strategy_performance.json"))
    cols = st.columns(2)
    if cols[0].button("Load strategy performance", use_container_width=True):
        try:
            st.session_state["strategy_performance"] = load_strategy_performance(performance_path)
        except Exception as exc:
            st.error(f"Could not load strategy performance: {exc}")
    if cols[1].button("Build from current review", use_container_width=True):
        review = st.session_state.get("review_report")
        if not isinstance(review, dict):
            st.warning("Run or load a review report first.")
        else:
            st.session_state["strategy_performance"] = build_strategy_performance_report(review)

    payload = st.session_state.get("strategy_performance")
    if not isinstance(payload, dict):
        st.info("Load a strategy performance report or build one from the current review.")
        return
    rows = payload.get("results", [])
    highlights = build_strategy_performance_highlights(rows)
    cols = st.columns(3)
    cols[0].write({"best_strategy_by_expectancy": highlights["best_strategy_by_expectancy"]})
    cols[1].write({"best_outlier_type": highlights["best_outlier_type"]})
    cols[2].write({"worst_strategy": highlights["worst_strategy"]})
    st.markdown("**Warning types that predicted bad outcomes**")
    st.dataframe(highlights["warning_types_that_predicted_bad_outcomes"], hide_index=True, use_container_width=True)
    st.markdown("**Sample size warnings**")
    st.dataframe(highlights["small_sample_warnings"], hide_index=True, use_container_width=True)
    st.markdown("**All buckets**")
    st.dataframe(rows, hide_index=True, use_container_width=True)


def _journal_page(rows: list[dict[str, Any]]) -> None:
    st.subheader("Journal")
    journal_path = Path(st.text_input("Journal CSV path", str(DEFAULT_JOURNAL_PATH)))
    if rows:
        st.markdown("**Add selected scanner idea**")
        selected = st.selectbox("Scanner ticker", [row["ticker"] for row in rows], key="journal_add_ticker")
        row = next(item for item in rows if item["ticker"] == selected)
        decision = st.selectbox("Decision", sorted(DECISIONS), index=sorted(DECISIONS).index("Research"))
        notes = st.text_area("Notes", key="journal_add_notes")
        if st.button("Add scanner idea to journal", use_container_width=True):
            try:
                entry = add_journal_entry(
                    journal_path=journal_path,
                    ticker=selected,
                    updates={**_journal_updates_from_row(row), "decision": decision, "notes": notes},
                )
                st.success(f"Added {entry['ticker']} as journal entry {entry['id']}.")
            except Exception as exc:
                st.error(f"Could not add journal entry: {exc}")

    journal_rows = load_dashboard_journal(journal_path)
    if not journal_rows:
        st.info("No journal entries yet.")
        return
    open_rows = [row for row in journal_rows if not row.get("exit_date") and not row.get("actual_exit_price")]
    closed_rows = [row for row in journal_rows if row not in open_rows]
    st.markdown("**Open ideas/trades**")
    st.dataframe(open_rows, hide_index=True, use_container_width=True)
    st.markdown("**Closed ideas/trades**")
    st.dataframe(closed_rows, hide_index=True, use_container_width=True)

    st.markdown("**Edit entry**")
    entry_id = st.selectbox("Entry id", [row["id"] for row in journal_rows])
    edit_cols = st.columns(4)
    edit_decision = edit_cols[0].selectbox("New decision", ["", *sorted(DECISIONS)])
    entry_price = edit_cols[1].text_input("Actual entry")
    exit_price = edit_cols[2].text_input("Actual exit")
    result_pct = edit_cols[3].text_input("Result %")
    followed_rules = st.selectbox("Followed rules", ["", "true", "false"])
    mistake = st.selectbox("Mistake category", ["", *sorted(MISTAKE_CATEGORIES)])
    edit_notes = st.text_area("Edit notes")
    if st.button("Update journal entry", use_container_width=True):
        updates = {
            key: value
            for key, value in {
                "decision": edit_decision,
                "actual_entry_price": entry_price,
                "actual_exit_price": exit_price,
                "result_pct": result_pct,
                "followed_rules": followed_rules,
                "mistake_category": mistake,
                "notes": edit_notes,
            }.items()
            if value
        }
        try:
            update_journal_entry(entry_id=entry_id, updates=updates, journal_path=journal_path)
            st.success("Journal entry updated.")
        except Exception as exc:
            st.error(f"Could not update journal entry: {exc}")


def _process_quality_page() -> None:
    st.subheader("Process Quality")
    journal_path = Path(st.text_input("Process journal path", str(DEFAULT_JOURNAL_PATH), key="process_journal_path"))
    rows = load_dashboard_journal(journal_path)
    summary = build_process_quality_summary(rows)
    cols = st.columns(5)
    cols[0].metric("Entries", summary["total_entries"])
    cols[1].metric("Rules followed %", summary["rules_followed_pct"])
    cols[2].metric("Avg result", summary["average_result_pct"])
    cols[3].metric("Chasing", summary["chasing_frequency"])
    cols[4].metric("Invalidation violations", summary["stop_invalidation_violations"])
    cols = st.columns(2)
    cols[0].write({"decision_counts": summary["decision_counts"]})
    cols[1].write({"most_common_mistakes": summary["most_common_mistakes"]})
    st.write(
        {
            "average_result_pct_rules_followed": summary["average_result_pct_rules_followed"],
            "average_result_pct_rules_not_followed": summary["average_result_pct_rules_not_followed"],
            "early_winner_exits": summary["early_winner_exits"],
            "avoided_setups": summary["avoided_setups"],
        }
    )


def _style() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.25rem; }
        div[data-testid="stMetricValue"] { font-size: 1.2rem; }
        .tb-card {
            border: 1px solid #d8dde6;
            border-left: 5px solid #64748b;
            padding: 12px 14px;
            margin: 10px 0;
            border-radius: 6px;
            background: #ffffff;
        }
        .tb-card.strong { border-left-color: #15803d; }
        .tb-card.forming { border-left-color: #2563eb; }
        .tb-card.active { border-left-color: #0f766e; }
        .tb-card.watch { border-left-color: #ca8a04; }
        .tb-card.avoid { border-left-color: #b91c1c; background: #fffafa; }
        .tb-card-head {
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: baseline;
            margin-bottom: 8px;
        }
        .tb-card-head span { color: #475569; font-size: 0.9rem; }
        .tb-score { font-weight: 700; color: #0f172a; white-space: nowrap; }
        .tb-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 4px 14px;
            font-size: 0.9rem;
            margin: 8px 0;
        }
        .tb-warning { color: #991b1b; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _status_class(row: dict[str, Any]) -> str:
    status = row["status_label"]
    if status == "Strong Research Candidate":
        return "strong"
    if status == "Trade Setup Forming":
        return "forming"
    if status == "Active Setup":
        return "active"
    if status == "Watch Only":
        return "watch"
    if status == "Avoid":
        return "avoid"
    return "watch"


def _matching_notes(row: dict[str, Any], *needles: str) -> str:
    notes = []
    for item in [*row["why_it_passed"], *row["signals_used"], *row["warnings"]]:
        lower = item.lower()
        if any(needle in lower for needle in needles):
            notes.append(item)
    return " | ".join(notes[:2])


def _join_tags(tags: Any) -> str:
    if not tags:
        return "unavailable"
    if isinstance(tags, str):
        return tags
    return " | ".join(str(tag) for tag in tags if str(tag)) or "unavailable"


def _first_sentence(items: Any, fallback: str) -> str:
    if isinstance(items, str):
        return items or fallback
    if not items:
        return fallback
    return " | ".join(str(item) for item in items[:3])


def _compact_list(rows: list[dict[str, Any]]) -> str:
    return "\n".join(_single_compact(row) for row in rows) or "unavailable"


def _parse_horizon_text(raw: str) -> list[int]:
    horizons = []
    for item in raw.split(","):
        item = item.strip()
        if item:
            horizons.append(int(item))
    return horizons or [5, 10, 20, 60]


def _journal_updates_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_name": row.get("company_name", ""),
        "strategy_label": row.get("strategy_label", ""),
        "outlier_type": row.get("outlier_type", ""),
        "status_label": row.get("status_label", ""),
        "winner_score": row.get("winner_score", ""),
        "outlier_score": row.get("outlier_score", ""),
        "setup_quality_score": row.get("setup_quality_score", ""),
        "risk_score": row.get("risk_score", ""),
        "confidence_label": row.get("confidence_label", ""),
        "entry_zone": row.get("entry_zone", ""),
        "invalidation_level": row.get("invalidation_level", ""),
        "stop_reference": row.get("stop_loss_reference", ""),
        "tp1": row.get("tp1", ""),
        "tp2": row.get("tp2", ""),
        "reward_risk": row.get("reward_risk", ""),
        "catalyst_quality": row.get("catalyst_quality", ""),
        "theme_tags": _join_tags(row.get("theme_tags", [])),
        "warnings": _join_tags(row.get("warnings", [])),
        "planned_holding_period": row.get("holding_period", ""),
        "position_type": "stock",
    }


def _single_compact(row: dict[str, Any] | None) -> str:
    if not row:
        return "unavailable"
    return f"{row['ticker']} ({row['outlier_score']} outlier / {row['winner_score']} winner / risk {row['risk_score']})"


def _counter_list(items: list[tuple[str, int]]) -> str:
    return "\n".join(f"{name}: {count}" for name, count in items) or "unavailable"


if __name__ == "__main__":
    main()
