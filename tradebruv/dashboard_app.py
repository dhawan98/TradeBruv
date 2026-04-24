from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

from tradebruv.dashboard_data import (
    DEFAULT_UNIVERSE_FILES,
    DashboardReport,
    build_daily_summary,
    classify_avoid_reasons,
    extract_options_fields,
    filter_results,
    find_latest_report,
    is_avoid,
    load_dashboard_report,
    run_dashboard_scan,
    sort_results,
    unique_theme_tags,
    unique_values,
)
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
        st.info("Run a scan or load a JSON report to start.")
        return

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

    tabs = st.tabs(["Outlier Feed", "Scanner Table", "Stock Detail", "Avoid Panel", "Watchlists", "Options Placeholder"])
    with tabs[0]:
        _outlier_feed(filtered)
    with tabs[1]:
        _scanner_table(filtered)
    with tabs[2]:
        _stock_detail(filtered or rows)
    with tabs[3]:
        _avoid_panel(rows)
    with tabs[4]:
        _watchlist_help()
    with tabs[5]:
        _options_placeholder(rows)


def _sidebar_controls() -> None:
    with st.sidebar:
        st.header("Run Scanner")
        provider_name = st.selectbox("Provider", ["sample", "real"], index=0)
        mode = st.selectbox("Mode", ["outliers", "standard"], index=0)
        universe_label = st.selectbox("Universe file", list(DEFAULT_UNIVERSE_FILES), index=0)
        universe_path = Path(st.text_input("Universe path", str(DEFAULT_UNIVERSE_FILES[universe_label])))
        limit = st.number_input("Result limit", min_value=0, max_value=500, value=50, step=5)
        history_period = st.text_input("Real provider history period", "3y")
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
        st.markdown("**Options placeholder**")
        st.write(row.get("options_placeholders", {}))


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


def _single_compact(row: dict[str, Any] | None) -> str:
    if not row:
        return "unavailable"
    return f"{row['ticker']} ({row['outlier_score']} outlier / {row['winner_score']} winner / risk {row['risk_score']})"


def _counter_list(items: list[tuple[str, int]]) -> str:
    return "\n".join(f"{name}: {count}" for name, count in items) or "unavailable"


if __name__ == "__main__":
    main()
