"""Live weekly fantasy-football Start/Sit Lab."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from dashboard.providers.sportsdataio import context_freshness, format_injury_context
    from dashboard.outlooks import build_player_outlook
    from dashboard.states import empty_player_pool_message, provider_issue_message
    from dashboard.methodology_copy import DISCLAIMER_LANGUAGE, METHODOLOGY_LANGUAGE, SOURCE_ATTRIBUTION
    from dashboard.presentation import comparison_summary, filter_player_search, matchup_summary, role_summary, selection_availability_summary, team_logo_url, weather_summary
except ModuleNotFoundError:
    from providers.sportsdataio import context_freshness, format_injury_context
    from outlooks import build_player_outlook
    from states import empty_player_pool_message, provider_issue_message
    from methodology_copy import DISCLAIMER_LANGUAGE, METHODOLOGY_LANGUAGE, SOURCE_ATTRIBUTION
    from presentation import comparison_summary, filter_player_search, matchup_summary, role_summary, selection_availability_summary, team_logo_url, weather_summary

try:
    from dashboard.data import current_nfl_season
except ModuleNotFoundError:
    from data import current_nfl_season


COLORS = {"QB": "#00529b", "RB": "#69be28", "WR": "#4b788f", "TE": "#a5acaf"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEASON = current_nfl_season()

st.set_page_config(page_title="Start / Sit Lab", page_icon="🏈", layout="wide", initial_sidebar_state="auto")
st.markdown(
    """
<style>
:root { --ink:#071b2c; --muted:#5f6b73; --navy:#002244; --cream:#f3f6f7; --card:#ffffff; --line:#d7dde0; --teal:#397f18; --gold:#69be28; --wolf:#a5acaf; }
.stApp { background:var(--cream); color:var(--ink); }
[data-testid="stSidebar"] { background:var(--navy); }
[data-testid="stSidebar"] * { color:#f7fafb; }
[data-testid="stSidebar"] [data-baseweb="select"] * { color:var(--ink) !important; }
[data-testid="stSidebar"] button[kind="secondary"] * { color:var(--ink) !important; }
.block-container { max-width:1440px; padding-top:1.55rem; }
h1,h2,h3 { letter-spacing:-.025em; }
.hero { display:flex; align-items:flex-end; justify-content:space-between; gap:2rem; border-bottom:1px solid #cfd5cf; padding-bottom:1.15rem; margin-bottom:1.2rem; }
.hero h1 { margin:.2rem 0 .45rem; font-size:2.65rem; line-height:1; }
.hero p { color:var(--muted); margin:0; max-width:720px; }
.eyebrow { color:#397f18; text-transform:uppercase; letter-spacing:.13em; font-size:.74rem; font-weight:800; }
.fresh { color:var(--muted); text-align:right; font-size:.78rem; white-space:nowrap; }
.verdict { background:var(--card); color:var(--ink); border:1px solid var(--line); border-radius:16px; padding:1.3rem 1.45rem; min-height:280px; }
.verdict.start { background:var(--navy); color:white; border-color:var(--gold); box-shadow:0 12px 28px rgba(0,34,68,.18); }
.verdict .tag { display:inline-block; background:#edf4e8; color:#397f18; border-radius:999px; padding:.28rem .52rem; letter-spacing:.12em; font-size:.67rem; font-weight:800; }
.verdict.start .tag { background:rgba(105,190,40,.16); color:#9ee468; }
.verdict .name { font-size:1.7rem; font-weight:750; margin:.65rem 0 .1rem; }
.player-heading { display:flex; align-items:center; gap:.75rem; margin:.65rem 0 .1rem; min-width:0; }
.player-heading .name { margin:0; overflow-wrap:anywhere; }
.player-photo { width:58px; height:58px; flex:0 0 58px; border-radius:50%; background-size:cover; background-position:center top; background-repeat:no-repeat; background-color:#e8ecee; border:2px solid #d7dde0; }
.verdict.start .player-photo { border-color:#69be28; background-color:#173854; }
.verdict .opponent { color:var(--muted); font-size:.8rem; }
.verdict.start .opponent { color:#c0c8cc; }
.verdict .score { color:var(--teal); font-size:1.35rem; font-weight:750; margin-top:.8rem; }
.verdict.start .score { color:#9ee468; }
.verdict .unit { display:flex; align-items:center; gap:.34rem; flex-wrap:wrap; }
.range-help { position:relative; display:inline-flex; align-items:center; justify-content:center; width:1.05rem; height:1.05rem; border:1px solid currentColor; border-radius:50%; font-size:.68rem; font-weight:800; cursor:help; opacity:.82; }
.range-tooltip { visibility:hidden; opacity:0; position:absolute; z-index:20; left:50%; bottom:calc(100% + .5rem); transform:translateX(-50%); width:250px; padding:.55rem .65rem; border-radius:8px; background:#071b2c; color:#f7fafb; font-size:.74rem; font-weight:500; line-height:1.35; text-align:left; box-shadow:0 8px 22px rgba(0,0,0,.22); transition:opacity .12s ease; }
.range-help:hover .range-tooltip, .range-help:focus .range-tooltip, .range-help:focus-within .range-tooltip { visibility:visible; opacity:1; }
.verdict .outlook-label { color:var(--muted); text-transform:uppercase; letter-spacing:.1em; font-size:.65rem; font-weight:800; margin-top:1rem; }
.verdict.start .outlook-label { color:#9ee468; }
.verdict .reason { color:#536166; font-size:.91rem; line-height:1.5; margin-top:.28rem; }
.verdict.start .reason { color:#e0e6e8; }
.at-a-glance { border-left:4px solid var(--gold); background:#edf4e8; color:#183515; padding:.78rem .95rem; border-radius:10px; margin:.25rem 0 1rem; font-size:.88rem; }
.broadcast-context { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.48rem; margin-top:1rem; }
.broadcast-context-item { background:#eef2f3; color:var(--ink); padding:.58rem .65rem; border-radius:9px; min-width:0; font-size:.76rem; line-height:1.3; overflow-wrap:anywhere; }
.broadcast-context-item span { display:block; color:var(--muted); font-size:.62rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; margin-bottom:.18rem; }
.verdict.start .broadcast-context-item { background:rgba(255,255,255,.1); color:#f4f8fa; }
.verdict.start .broadcast-context-item span { color:#9ee468; }
.reporting-sources { margin-top:.65rem; font-size:.72rem; color:var(--muted); line-height:1.35; }
.reporting-sources a { color:#397f18; font-weight:700; text-decoration:none; }
.verdict.start .reporting-sources { color:#c0c8cc; }
.verdict.start .reporting-sources a { color:#9ee468; }
.section-title { font-size:1.16rem; font-weight:750; margin:1.2rem 0 .1rem; }
.section-copy { color:var(--muted); font-size:.87rem; margin-bottom:.65rem; }
.note { border-left:4px solid var(--gold); background:#edf4e8; color:#183515; padding:.72rem .9rem; border-radius:8px; font-size:.84rem; margin-top:1rem; }
.warning { border-left:4px solid var(--gold); background:#eef5e9; color:#29451f; padding:.72rem .9rem; border-radius:8px; font-size:.84rem; margin:.85rem 0; }
.player-finder { margin:.35rem 0 .8rem; }
.finder-copy { color:var(--muted); font-size:.78rem; margin:-.25rem 0 .55rem; }
.selected-player-name { font-size:.94rem; font-weight:750; line-height:1.2; margin-top:.2rem; }
.selected-player-meta { color:var(--muted); font-size:.72rem; line-height:1.3; }
.context-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.85rem; width:100%; }
.context-card { background:var(--card); border:1px solid var(--line); border-radius:14px; overflow:hidden; min-width:0; }
.context-card h3 { margin:0; padding:.9rem 1rem; background:#ebe7dc; color:var(--ink); font-size:1.05rem; display:flex; align-items:center; gap:.6rem; }
.context-card .player-photo { width:42px; height:42px; flex-basis:42px; border-width:1px; }
.context-row { display:grid; grid-template-columns:minmax(112px,.78fr) minmax(0,1.22fr); gap:.7rem; padding:.67rem 1rem; border-top:1px solid #e5e8e9; align-items:start; }
.context-label { color:var(--muted); font-size:.72rem; font-weight:800; letter-spacing:.02em; line-height:1.25; }
.context-value { color:var(--ink); font-size:.82rem; font-weight:600; line-height:1.35; overflow-wrap:anywhere; }
.context-help { cursor:help; border-bottom:1px dotted currentColor; }
div[data-testid="stMetric"] { background:var(--card); border:1px solid var(--line); padding:.8rem 1rem; border-radius:12px; }
.stPlotlyChart { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:.2rem; }
@media(max-width:1100px) {
  div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) { flex-wrap:wrap; }
  div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) > div { flex:1 1 calc(50% - .6rem); min-width:240px; }
  div[data-testid="stMetricValue"] > div { font-size:1.65rem; white-space:normal; overflow:visible; text-overflow:clip; line-height:1.12; }
  .context-grid { grid-template-columns:1fr; }
}
@media(max-width:800px) {
  html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] { max-width:100vw; overflow-x:hidden; }
  section.main, [data-testid="stMain"], [data-testid="stMainBlockContainer"], .block-container { width:100% !important; max-width:100vw !important; min-width:0 !important; box-sizing:border-box; }
  .block-container { padding:1rem .85rem 2rem; }
  .hero{display:block}.fresh{text-align:left;margin-top:.7rem}.hero h1{font-size:2.05rem}
  .hero, .warning, .section-copy, .note { width:calc(100vw - 1.7rem) !important; max-width:calc(100vw - 1.7rem) !important; }
  .hero > div, .hero p { width:100% !important; max-width:100% !important; min-width:0 !important; box-sizing:border-box; white-space:normal; overflow-wrap:anywhere; }
  .verdict { min-height:0; padding:1rem; }
  .verdict .name { font-size:1.45rem; }
  .range-tooltip { left:0; transform:none; width:min(250px, 75vw); }
  [data-testid="stSidebar"] { width:min(18.75rem, 88vw) !important; }
}
@media(max-width:520px) {
  div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) > div { flex-basis:100%; min-width:0; }
  div[data-baseweb="select"] > div { flex-wrap:wrap; }
}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600, show_spinner=False)
def get_published_snapshot(season: int, passing_td_points: int) -> tuple[pd.DataFrame, pd.DataFrame, int, str, str, str | None, str]:
    import json

    processed = PROJECT_ROOT / "data" / "processed"
    metadata_path = processed / "live_refresh_metadata.json"
    board_path = processed / f"live_start_sit_board_{passing_td_points}pt_current.parquet"
    weekly_path = processed / "live_weekly_current.parquet"
    if not metadata_path.exists() or not board_path.exists() or not weekly_path.exists():
        raise FileNotFoundError("A validated production snapshot has not been published.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if int(metadata.get("season", -1)) != season or passing_td_points not in metadata.get("refreshed_qb_passing_td_formats", []):
        raise ValueError("The published snapshot does not match this season or scoring format.")
    board = pd.read_parquet(board_path)
    weekly = pd.read_parquet(weekly_path)
    provider_status = str(metadata.get("sportsdataio_status", "Snapshot unavailable"))
    provider_refreshed_at = metadata.get("sportsdataio_refreshed_at")
    injury_sources = metadata.get("injury_source_status", {})
    injury_status = f"NFLVERSE · {injury_sources.get('nflverse', 'Unavailable')} | SLEEPER · {injury_sources.get('sleeper', 'Unavailable')}"
    checked_at = metadata.get("refreshed_at", datetime.now(timezone.utc).isoformat())
    refreshed = datetime.fromisoformat(str(checked_at).replace("Z", "+00:00")).strftime("%b %d, %Y · %H:%M UTC")
    return board, weekly, int(metadata["next_week"]), refreshed, provider_status, provider_refreshed_at, injury_status


def polish(fig: go.Figure, height: int = 390) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=18, r=18, t=52, b=20),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(family="Arial", color="#33434f", size=12),
        title_font=dict(size=16, color="#071b2c"),
        hoverlabel=dict(bgcolor="#002244", font_color="white"),
        legend_title_text="",
    )
    fig.update_xaxes(gridcolor="#e3e8ea", zeroline=False)
    fig.update_yaxes(gridcolor="#e3e8ea", zeroline=False)
    return fig


def player_photo_html(value: object, label: object) -> str:
    """Render a safe CSS headshot that fails invisibly instead of showing a broken icon."""
    if value is None or pd.isna(value):
        return ""
    url = str(value).strip()
    if not url.startswith("https://sleepercdn.com/content/nfl/players/") or not url.endswith(".jpg"):
        return ""
    return (
        f'<span class="player-photo" role="img" aria-label="{html.escape(str(label), quote=True)} roster photo" '
        f'style="background-image:url(&quot;{html.escape(url, quote=True)}&quot;)"></span>'
    )


with st.sidebar:
    st.markdown("## ◒ Player Comparison Lab")
    st.caption("Live, explainable matchup analysis")
    page = st.radio("View", ["Decision Room", "Player Trends", "How It Works"], label_visibility="collapsed")
    st.divider()
    season = st.selectbox("Season", [SEASON], index=0)
    st.markdown("**SCORING**")
    qb_td_label = st.radio("QB passing TD", ["4 points", "6 points"], horizontal=True)
    QB_PASS_TD_POINTS = int(qb_td_label.split()[0])
    st.caption(f"Full PPR · {QB_PASS_TD_POINTS}-pt passing TD")
    st.divider()
    st.markdown("**LIVE DATA**")
    st.caption("Validated cloud snapshots supply every public view; visitors never call upstream providers.")
    st.caption("The cloud scheduler refreshes weekly projections and daily injury/practice context.")
    if st.button("Refresh now", width="stretch"):
        st.cache_data.clear()
        st.rerun()

try:
    with st.spinner("Updating weekly stats and matchups…"):
        BOARD, WEEKLY, NEXT_WEEK, REFRESHED, PROVIDER_STATUS, PROVIDER_REFRESHED_AT, INJURY_SOURCE_STATUS = get_published_snapshot(season, QB_PASS_TD_POINTS)
except Exception as error:
    st.error("The weekly player dataset could not be loaded, so projections are temporarily unavailable.")
    st.info("Check your connection, then use **Refresh now**. The app will not show cached estimates as if they were current.")
    with st.expander("Technical details"):
        st.code(f"{type(error).__name__}: {error}")
    st.stop()

with st.sidebar:
    st.caption(f"SPORTSDATAIO · {PROVIDER_STATUS}")
    st.caption(INJURY_SOURCE_STATUS)

st.markdown(
    f'<div class="hero"><div><div class="eyebrow">{season} season · Week {NEXT_WEEK}</div>'
    '<h1>Player Comparison Lab</h1><p>Compare production, matchup context, and projected outcome ranges. You make the lineup decision.</p></div>'
    f'<div class="fresh">UPDATED<br>{html.escape(REFRESHED)}</div></div>',
    unsafe_allow_html=True,
)

if page == "Decision Room":
    st.markdown('<div class="warning"><b>Before kickoff:</b> live injuries, practice, weather, and depth context are supplementary. Confirm official late-breaking status before locking a lineup.</div>', unsafe_allow_html=True)
    context_age_minutes, context_is_stale = context_freshness(PROVIDER_REFRESHED_AT)
    if context_is_stale:
        st.warning("SportsDataIO weather/depth context is more than 90 minutes old or unavailable. Daily injury reports remain separate; confirm late-breaking status before kickoff.")
    else:
        st.caption(f"Weather/depth context checked {context_age_minutes} minute{'s' if context_age_minutes != 1 else ''} ago. Injury/practice reports refresh daily.")
    provider_issue = provider_issue_message(PROVIDER_STATUS)
    if provider_issue:
        st.warning(provider_issue)
    c1, c2 = st.columns([.62, 1.38])
    position = c1.segmented_control("Position", ["QB", "RB", "WR", "TE"], default="WR")
    pool = BOARD.loc[
        BOARD["position"].eq(position)
        & BOARD["next_opponent"].notna()
        & BOARD["is_roster_relevant"]
        & BOARD["verified_qb_starter"]
    ].copy()
    excluded_qbs = BOARD.iloc[0:0]
    if position == "QB":
        excluded_qbs = BOARD.loc[
            BOARD["position"].eq("QB") & BOARD["base_roster_relevant"] & ~BOARD["verified_qb_starter"]
        ]
        if not excluded_qbs.empty:
            st.caption(f"{len(excluded_qbs)} QB(s) hidden because the live depth chart does not verify them as QB1.")
    if pool.empty:
        c2.warning(empty_player_pool_message(position, len(excluded_qbs)))
        names = []
    else:
        selection_key = f"smart_search_selected_{position}"
        valid_names = set(pool["player"].tolist())
        if selection_key not in st.session_state:
            st.session_state[selection_key] = pool.sort_values("projected_ppr", ascending=False).head(3)["player"].tolist()
        st.session_state[selection_key] = [name for name in st.session_state[selection_key] if name in valid_names][:3]
        names = list(st.session_state[selection_key])
        with c2:
            query = st.text_input(
                "Find players",
                key=f"smart_search_query_{position}",
                placeholder="Search by player or team…",
            )
            st.markdown(f'<div class="finder-copy">{len(names)} of 3 selected · results include roster photos, team, opponent, availability and projection</div>', unsafe_allow_html=True)

        if names:
            st.markdown('<div class="section-copy">Selected players</div>', unsafe_allow_html=True)
            selected_columns = st.columns(3)
            for selected_column, name in zip(selected_columns, names):
                selected_row = pool.loc[pool["player"].eq(name)].iloc[0]
                with selected_column:
                    with st.container(border=True):
                        photo_column, info_column = st.columns([.34, .66])
                        photo_url = selected_row.get("headshot_url")
                        if photo_url is not None and pd.notna(photo_url):
                            photo_column.image(str(photo_url), width=72)
                        logo_url = team_logo_url(selected_row.get("team"))
                        with info_column:
                            st.markdown(f'<div class="selected-player-name">{html.escape(str(selected_row["player"]))}</div>', unsafe_allow_html=True)
                            logo_column, team_column = st.columns([.2, .8], vertical_alignment="center")
                            if logo_url:
                                logo_column.image(logo_url, width=24)
                            team_column.markdown(f'<div class="selected-player-meta">{html.escape(str(selected_row["team"]))} · {html.escape(str(selected_row["venue"]))} vs {html.escape(str(selected_row["next_opponent"]))}</div>', unsafe_allow_html=True)
                            st.markdown(f'<div class="selected-player-meta">{float(selected_row["median_ppr"]):.1f} projected PPR</div>', unsafe_allow_html=True)
                        if st.button("Remove", key=f"remove_{position}_{selected_row['player_id']}", width="stretch"):
                            st.session_state[selection_key] = [value for value in names if value != name]
                            st.rerun()

        results = filter_player_search(pool.loc[~pool["player"].isin(names)], query)
        st.markdown('<div class="section-copy">Search results</div>', unsafe_allow_html=True)
        if results.empty:
            st.info("No eligible players match that search. Try a full name or team abbreviation.")
        else:
            for _, result_row in results.iterrows():
                with st.container(border=True):
                    photo_column, details_column, logo_column, action_column = st.columns([.10, .56, .10, .24], vertical_alignment="center")
                    photo_url = result_row.get("headshot_url")
                    if photo_url is not None and pd.notna(photo_url):
                        photo_column.image(str(photo_url), width=52)
                    availability = selection_availability_summary(result_row)
                    details_column.markdown(
                        f'<b>{html.escape(str(result_row["player"]))}</b><br>'
                        f'{html.escape(str(result_row["team"]))} · {html.escape(str(result_row["position"]))} · {html.escape(str(result_row["venue"]))} vs {html.escape(str(result_row["next_opponent"]))}<br>'
                        f'<span class="selected-player-meta">{html.escape(availability)}</span>',
                        unsafe_allow_html=True,
                    )
                    logo_url = team_logo_url(result_row.get("team"))
                    if logo_url:
                        logo_column.image(logo_url, width=34)
                    if action_column.button(
                        f"Add · {float(result_row['median_ppr']):.1f}",
                        key=f"add_{position}_{result_row['player_id']}",
                        disabled=len(names) >= 3,
                        width="stretch",
                    ):
                        st.session_state[selection_key] = [*names, str(result_row["player"])]
                        st.rerun()
    compare = pool.loc[pool["player"].isin(names)].sort_values("projected_ppr", ascending=False)

    if compare.empty:
        if not pool.empty:
            st.info("Choose at least one available player above to begin the comparison.")
    else:
        leader = compare.iloc[0]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Model Start", leader["player"])
        m2.metric("Start projection", f"{compare['median_ppr'].max():.1f} PPR")
        m3.metric("Projection spread", f"{compare['median_ppr'].max() - compare['median_ppr'].min():.1f} PPR")
        m4.metric("Next week", f"Week {NEXT_WEEK}")

        projection_spread = float(compare["median_ppr"].max() - compare["median_ppr"].min())
        if len(compare) > 1 and projection_spread < 2.5:
            st.info("Close call: the model still labels Start and Sit, but the gap is under 2.5 PPR—far smaller than its typical weekly error. Treat this as a lean, not a confident separation.")

        st.markdown('<div class="section-title">Start / Sit verdict</div><div class="section-copy">The approved model blends current production, repeatable workload, a fading prior-season anchor, touchdown regression, and a sample-scaled matchup adjustment. Decision Context below is excluded.</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="at-a-glance"><b>At a glance:</b> {html.escape(comparison_summary(compare))}</div>', unsafe_allow_html=True)
        outlook_columns = st.columns(len(compare))
        for index, (column, (_, row)) in enumerate(zip(outlook_columns, compare.iterrows())):
            with column:
                if index == 0 and len(compare) > 1:
                    verdict = "START · PREFERRED"
                elif len(compare) > 1 and float(leader["median_ppr"] - row["median_ppr"]) < 2.5:
                    verdict = "SIT · CLOSE ALTERNATIVE"
                elif len(compare) > 1:
                    verdict = "SIT · RISKIER OPTION"
                else:
                    verdict = "ONLY PLAYER"
                card_class = "start" if index == 0 else "sit"
                reason = build_player_outlook(row, index, len(compare), projection_spread, row.get("reporting_summary"))
                try:
                    reporting_sources = json.loads(str(row.get("reporting_sources_json", "[]")))
                except (TypeError, ValueError, json.JSONDecodeError):
                    reporting_sources = []
                safe_links = []
                for source in reporting_sources[:3]:
                    url = str(source.get("url", ""))
                    if url.startswith("https://"):
                        label = html.escape(str(source.get("source_name", "Source")))
                        safe_links.append(f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{label}</a>')
                reporting_links = f'<div class="reporting-sources">Reporting: {" · ".join(safe_links)}</div>' if safe_links else ""
                photo = player_photo_html(row.get("headshot_url"), row["player"])
                practice = format_injury_context(row, "Connected" in INJURY_SOURCE_STATUS)
                quick_context = "".join([
                    f'<div class="broadcast-context-item"><span>Practice</span>{html.escape(practice)}</div>',
                    f'<div class="broadcast-context-item"><span>Matchup</span>{html.escape(matchup_summary(row))}</div>',
                    f'<div class="broadcast-context-item"><span>Role</span>{html.escape(role_summary(row))}</div>',
                    f'<div class="broadcast-context-item"><span>Weather</span>{html.escape(weather_summary(row))}</div>',
                ])
                st.markdown(
                    f'<div class="verdict {card_class}"><div class="tag">{verdict}</div><div class="player-heading">{photo}<div class="name">{html.escape(str(row["player"]))}</div></div>'
                    f'<div class="opponent">{html.escape(str(row["team"]))} · {html.escape(str(row["venue"]))} vs {html.escape(str(row["next_opponent"]))}</div>'
                    f'<div class="score">{row["floor_ppr"]:.1f} · {row["median_ppr"]:.1f} · {row["ceiling_ppr"]:.1f}</div>'
                    f'<div class="unit">Floor · projection · ceiling <span class="range-help" tabindex="0" aria-label="Range definition">i<span class="range-tooltip" role="tooltip">Floor is the P10 downside outcome, projection is the median estimate, and ceiling is the P90 upside outcome. About 80% of results should fall between floor and ceiling.</span></span></div><div class="outlook-label">Player outlook</div>'
                    f'<div class="reason">{html.escape(reason)}</div>{reporting_links}<div class="broadcast-context">{quick_context}</div></div>',
                    unsafe_allow_html=True,
                )

        st.markdown('<div class="section-title">Projected outcome</div><div class="section-copy">The center mark is the median projection; the whisker shows the P10-to-P90 range.</div>', unsafe_allow_html=True)
        colors = ["#69be28"] + ["#a5acaf"] * (len(compare) - 1)
        fig = go.Figure(go.Bar(
            x=compare["median_ppr"], y=compare["player"], orientation="h", marker_color=colors,
            customdata=list(zip(compare["recent_ppr"], compare["season_ppr"], compare["next_opponent"], compare["matchup_label"], compare["confidence"])),
            text=compare["median_ppr"].map(lambda value: f"{value:.1f}"), textposition="outside",
            error_x=dict(type="data", symmetric=False, array=compare["ceiling_ppr"] - compare["median_ppr"], arrayminus=compare["median_ppr"] - compare["floor_ppr"], color="#5f6b73"),
            hovertemplate="<b>%{y}</b><br>Projection %{x:.1f}<br>Recent %{customdata[0]:.1f}<br>Season %{customdata[1]:.1f}<br>vs %{customdata[2]} · %{customdata[3]}<br>%{customdata[4]} confidence<extra></extra>",
        ))
        fig.update_layout(title=f"Week {NEXT_WEEK} projected PPR", xaxis_title="PPR points", yaxis_title="", showlegend=False)
        fig.update_yaxes(autorange="reversed")
        fig.update_xaxes(range=[0, max(compare["projected_ppr"].max() * 1.22, 10)])
        st.plotly_chart(polish(fig, 330), width="stretch", config={"displayModeBar": False})

        common = ["player", "team", "next_opponent", "games_played", "season_ppr", "recent_ppr", "recent_opportunities"]
        position_stats = {
            "QB": ["ytd_attempts", "ytd_passing_yards", "ytd_passing_tds", "ytd_rushing_yards", "ytd_rushing_tds"],
            "RB": ["ytd_carries", "ytd_targets", "ytd_rushing_yards", "ytd_receiving_yards", "ytd_rushing_tds", "ytd_receiving_tds"],
            "WR": ["ytd_targets", "ytd_receptions", "ytd_receiving_yards", "ytd_receiving_tds"],
            "TE": ["ytd_targets", "ytd_receptions", "ytd_receiving_yards", "ytd_receiving_tds"],
        }
        with st.expander("How this projection was built"):
            st.markdown("**Included in the model:** current-season production, recent repeatable workload, a fading prior-season anchor, touchdown regression, and a capped matchup adjustment.")
            st.caption("Practice, injuries, weather, snap share, pace, game totals, personnel changes, and journalism are displayed for your decision but do not change the projection or Start/Sit order.")
            view = compare[common + position_stats[position] + ["matchup_label", "points_allowed", "projected_ppr", "confidence"]].copy()
            st.dataframe(view, hide_index=True, width="stretch", column_config={
                "player":"Player", "team":"Team", "next_opponent":"Opponent", "games_played":"GP",
                "season_ppr":st.column_config.NumberColumn("Season PPR/G", format="%.1f"),
                "recent_ppr":st.column_config.NumberColumn("Last 4 PPR/G", format="%.1f"),
                "recent_opportunities":st.column_config.NumberColumn("Last 3 opp/G", format="%.1f"),
                "ytd_attempts":"Pass att", "ytd_carries":"Carries", "ytd_targets":"Targets", "ytd_receptions":"Rec",
                "ytd_passing_yards":"Pass yds", "ytd_rushing_yards":"Rush yds", "ytd_receiving_yards":"Rec yds",
                "ytd_passing_tds":"Pass TD", "ytd_rushing_tds":"Rush TD", "ytd_receiving_tds":"Rec TD",
                "matchup_label":"Matchup", "points_allowed":st.column_config.NumberColumn("Opp. PPR allowed", format="%.1f"),
                "projected_ppr":st.column_config.NumberColumn("Projection", format="%.1f"), "confidence":"Confidence",
            })

        with st.expander("More matchup context"):
            st.caption("Additional live information for your final decision. None of these details changes the model ranking.")
            context_cards = []
            for _, row in compare.iterrows():
                provider_total = row.get("betting_total_live")
                if provider_total is None or pd.isna(provider_total):
                    provider_total = row.get("total_line")
                expected_points = f"{float(provider_total):.1f} combined points" if provider_total is not None and pd.notna(provider_total) else "Not available"
                pace = f"{row['pace_label']} pace · {row['combined_recent_plays']:.0f} combined plays" if pd.notna(row.get("combined_recent_plays")) else "Not available"
                if pd.notna(row.get("qb_changed")):
                    changes = []
                    if bool(row.get("qb_changed")): changes.append("Starting QB changed")
                    if bool(row.get("ol_changed")): changes.append("Starting O-line changed")
                    personnel = " · ".join(changes) if changes else "No changes"
                else:
                    personnel = "Not enough history" if PROVIDER_STATUS.startswith("Connected") else "Not available"
                fields = [
                    ("Game pace", pace, "Expected play volume based on recent team pace"),
                    ("Expected game points", expected_points, "Sportsbook estimate for the combined score"),
                    ("QB / O-line", personnel, "Confirmed starting quarterback or offensive-line changes"),
                ]
                rows_html = "".join(
                    f'<div class="context-row"><div class="context-label context-help" title="{html.escape(help_text)}">{html.escape(label)}</div><div class="context-value">{html.escape(value)}</div></div>'
                    for label, value, help_text in fields
                )
                photo = player_photo_html(row.get("headshot_url"), row["player"])
                context_cards.append(f'<article class="context-card"><h3>{photo}<span>{html.escape(str(row["player"]))}</span></h3>{rows_html}</article>')
            st.markdown(f'<div class="context-grid">{"".join(context_cards)}</div>', unsafe_allow_html=True)
            st.markdown('<div class="note"><b>Separation rule:</b> Start/Sit comes only from the core projection. This additional context is here so you can make the final call.</div>', unsafe_allow_html=True)

elif page == "Player Trends":
    selected_position = st.segmented_control("Position", ["QB", "RB", "WR", "TE"], default="WR")
    pool = BOARD.loc[
        BOARD["position"].eq(selected_position)
        & BOARD["next_opponent"].notna()
        & BOARD["is_roster_relevant"]
        & BOARD["verified_qb_starter"]
    ]
    if pool.empty:
        hidden = int((BOARD["position"].eq("QB") & BOARD["base_roster_relevant"] & ~BOARD["verified_qb_starter"]).sum()) if selected_position == "QB" else 0
        st.warning(empty_player_pool_message(selected_position, hidden))
        st.stop()
    player_name = st.selectbox("Player", pool["player"].sort_values().tolist())
    matches = pool.loc[pool["player"].eq(player_name)]
    if matches.empty:
        st.warning("That player record is no longer available after the latest refresh. Choose another player.")
        st.stop()
    player = matches.iloc[0]
    id_column = "player_id" if "player_id" in BOARD.columns and "player_id" in WEEKLY.columns else None
    name_column = "player_display_name" if "player_display_name" in WEEKLY.columns else "player_name"
    history = WEEKLY.loc[WEEKLY[name_column].eq(player_name)].sort_values("week")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Week projection", f"{player['projected_ppr']:.1f}")
    f2.metric("Last four", f"{player['recent_ppr']:.1f}")
    f3.metric("Season", f"{player['season_ppr']:.1f}")
    f4.metric("Next opponent", player["next_opponent"])
    if history.empty:
        st.warning("Weekly game history is unavailable for this player. The current projection remains visible above, but no trend chart can be shown.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=history["week"], y=history["fantasy_points_ppr"], name="Weekly PPR", marker_color=COLORS[selected_position], hovertemplate="Week %{x}<br>%{y:.1f} PPR<extra></extra>"))
        fig.add_hline(y=player["season_ppr"], line_dash="dash", line_color="#5f6b73", annotation_text="Season avg", annotation_position="top left")
        fig.add_hline(y=player["projected_ppr"], line_dash="dot", line_color="#69be28", annotation_text=f"Week {NEXT_WEEK} projection", annotation_position="top right")
        fig.update_layout(title=f"{player_name} · weekly production", xaxis_title="Week", yaxis_title="PPR points", showlegend=False)
        st.plotly_chart(polish(fig, 440), width="stretch", config={"displayModeBar": False})
    if pd.notna(player.get("points_allowed")):
        st.markdown(f'<div class="note"><b>Matchup:</b> {player["next_opponent"]} has allowed {player["points_allowed"]:.1f} PPR per {selected_position} performance in this dataset, a {str(player["matchup_label"]).lower()} index for the position.</div>', unsafe_allow_html=True)
    else:
        st.info("Opponent matchup history is unavailable for this player; no matchup claim is shown.")

else:
    st.subheader("How the Start / Sit Lab works")
    st.markdown(METHODOLOGY_LANGUAGE)
    st.info("The scoring-role touchdown exception remains disabled until reliable red-zone or goal-line opportunity data is integrated and validated.")
    st.subheader("Sources and refresh timing")
    st.markdown(SOURCE_ATTRIBUTION)
    st.caption(f"Season {season} data · app cache refreshes hourly · this page loaded {REFRESHED} · supplementary provider: {PROVIDER_STATUS}")
    st.subheader("Responsible use")
    st.markdown(DISCLAIMER_LANGUAGE)

st.divider()
with st.expander("Sources, methodology & important disclaimer"):
    st.markdown(SOURCE_ATTRIBUTION)
    st.markdown(METHODOLOGY_LANGUAGE)
    st.markdown(DISCLAIMER_LANGUAGE)
