"""Live weekly fantasy-football Start/Sit Lab."""

from __future__ import annotations

import html
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from dashboard.providers.sportsdataio import SportsDataIOClient, context_freshness, enrich_board, format_injury_context
    from dashboard.snapshots import load_personnel_snapshot
    from dashboard.outlooks import build_player_outlook
    from dashboard.states import empty_player_pool_message, provider_issue_message
except ModuleNotFoundError:
    from providers.sportsdataio import SportsDataIOClient, context_freshness, enrich_board, format_injury_context
    from snapshots import load_personnel_snapshot
    from outlooks import build_player_outlook
    from states import empty_player_pool_message, provider_issue_message

try:
    from dashboard.data import add_live_supplementary_context, apply_approved_projection_model, apply_verified_starter_gate, build_start_sit_board, current_nfl_season, load_live_context_data, load_live_weekly_data, load_prior_weekly_data
except ModuleNotFoundError:
    from data import add_live_supplementary_context, apply_approved_projection_model, apply_verified_starter_gate, build_start_sit_board, current_nfl_season, load_live_context_data, load_live_weekly_data, load_prior_weekly_data


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
.section-title { font-size:1.16rem; font-weight:750; margin:1.2rem 0 .1rem; }
.section-copy { color:var(--muted); font-size:.87rem; margin-bottom:.65rem; }
.note { border-left:4px solid var(--gold); background:#edf4e8; color:#183515; padding:.72rem .9rem; border-radius:8px; font-size:.84rem; margin-top:1rem; }
.warning { border-left:4px solid var(--gold); background:#eef5e9; color:#29451f; padding:.72rem .9rem; border-radius:8px; font-size:.84rem; margin:.85rem 0; }
div[data-testid="stMetric"] { background:var(--card); border:1px solid var(--line); padding:.8rem 1rem; border-radius:12px; }
.stPlotlyChart { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:.2rem; }
@media(max-width:1100px) {
  div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) { flex-wrap:wrap; }
  div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) > div { flex:1 1 calc(50% - .6rem); min-width:240px; }
  div[data-testid="stMetricValue"] > div { font-size:1.65rem; white-space:normal; overflow:visible; text-overflow:clip; line-height:1.12; }
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


def provider_key() -> str:
    key = os.getenv("SPORTSDATAIO_API_KEY", "").strip()
    if key:
        return key
    try:
        return str(st.secrets.get("SPORTSDATAIO_API_KEY", "")).strip()
    except (FileNotFoundError, KeyError):
        return ""


@st.cache_data(ttl=3600, show_spinner=False)
def get_live_board(season: int, sportsdataio_key: str = "") -> tuple[pd.DataFrame, pd.DataFrame, int, str, str, str | None]:
    weekly, schedules = load_live_weekly_data(season)
    board, next_week = build_start_sit_board(weekly, schedules, season)
    snaps, team_stats = load_live_context_data(season)
    board = add_live_supplementary_context(board, snaps, team_stats)
    provider_status = "Not connected"
    provider_refreshed_at = None
    if sportsdataio_key:
        try:
            context = SportsDataIOClient(sportsdataio_key).weekly_context(season, next_week)
            board = enrich_board(board, context)
            _, team_context = load_personnel_snapshot(PROJECT_ROOT)
            if not team_context.empty:
                board = board.merge(team_context, on="team", how="left")
            provider_status = f"Connected · {context.refreshed_at[:16].replace('T', ' ')} UTC"
            provider_refreshed_at = context.refreshed_at
        except Exception as error:
            provider_status = f"Connection error · {type(error).__name__}"
    refreshed = datetime.now(timezone.utc).strftime("%b %d, %Y · %H:%M UTC")
    return board, weekly, next_week, refreshed, provider_status, provider_refreshed_at


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


with st.sidebar:
    st.markdown("## ◒ Player Comparison Lab")
    st.caption("Live, explainable matchup analysis")
    page = st.radio("View", ["Decision Room", "Player Trends", "How It Works"], label_visibility="collapsed")
    st.divider()
    season = st.selectbox("Season", [SEASON, SEASON - 1], index=0)
    st.markdown("**SCORING**")
    qb_td_label = st.radio("QB passing TD", ["4 points", "6 points"], horizontal=True)
    QB_PASS_TD_POINTS = int(qb_td_label.split()[0])
    st.caption(f"Full PPR · {QB_PASS_TD_POINTS}-pt passing TD")
    st.divider()
    st.markdown("**LIVE DATA**")
    st.caption("Weekly player results and schedule are pulled from nflverse and cached for one hour.")
    st.caption("SportsDataIO supplies optional injury, practice, weather, and depth-chart context.")
    if st.button("Refresh now", width="stretch"):
        st.cache_data.clear()
        st.rerun()

try:
    with st.spinner("Updating weekly stats and matchups…"):
        BOARD, WEEKLY, NEXT_WEEK, REFRESHED, PROVIDER_STATUS, PROVIDER_REFRESHED_AT = get_live_board(season, provider_key())
except Exception as error:
    st.error("The weekly player dataset could not be loaded, so projections are temporarily unavailable.")
    st.info("Check your connection, then use **Refresh now**. The app will not show cached estimates as if they were current.")
    with st.expander("Technical details"):
        st.code(f"{type(error).__name__}: {error}")
    st.stop()

PRIOR_WEEKLY = load_prior_weekly_data(season)
BOARD = apply_approved_projection_model(BOARD, WEEKLY, PRIOR_WEEKLY, NEXT_WEEK, QB_PASS_TD_POINTS)
BOARD = apply_verified_starter_gate(BOARD)

with st.sidebar:
    st.caption(f"SPORTSDATAIO · {PROVIDER_STATUS}")

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
        st.warning("Live injury and practice context is more than 90 minutes old or unavailable. Use **Refresh now** before setting a lineup.")
    else:
        st.caption(f"Live injury and practice context checked {context_age_minutes} minute{'s' if context_age_minutes != 1 else ''} ago.")
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
            BOARD["position"].eq("QB") & BOARD["is_roster_relevant"] & ~BOARD["verified_qb_starter"]
        ]
        if not excluded_qbs.empty:
            st.caption(f"{len(excluded_qbs)} QB(s) hidden because the live depth chart does not verify them as QB1.")
    if pool.empty:
        c2.warning(empty_player_pool_message(position, len(excluded_qbs)))
        names = []
    else:
        names = c2.multiselect(
            "Players to compare",
            pool["player"].sort_values().tolist(),
            default=pool.head(3)["player"].tolist(),
            max_selections=3,
            placeholder="Choose up to three players",
        )
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
        outlook_columns = st.columns(len(compare))
        for index, (column, (_, row)) in enumerate(zip(outlook_columns, compare.iterrows())):
            with column:
                verdict = "START" if index == 0 and len(compare) > 1 else "SIT" if len(compare) > 1 else "ONLY PLAYER"
                card_class = "start" if index == 0 else "sit"
                reason = build_player_outlook(row, index, len(compare), projection_spread)
                st.markdown(
                    f'<div class="verdict {card_class}"><div class="tag">{verdict}</div><div class="name">{html.escape(str(row["player"]))}</div>'
                    f'<div class="opponent">{html.escape(str(row["team"]))} · {html.escape(str(row["venue"]))} vs {html.escape(str(row["next_opponent"]))}</div>'
                    f'<div class="score">{row["floor_ppr"]:.1f} · {row["median_ppr"]:.1f} · {row["ceiling_ppr"]:.1f}</div>'
                    f'<div class="unit">Floor · projection · ceiling <span class="range-help" tabindex="0" aria-label="Range definition">i<span class="range-tooltip" role="tooltip">Floor is the P10 downside outcome, projection is the median estimate, and ceiling is the P90 upside outcome. About 80% of results should fall between floor and ceiling.</span></span></div><div class="outlook-label">Player outlook</div>'
                    f'<div class="reason">{html.escape(reason)}</div></div>',
                    unsafe_allow_html=True,
                )

        left, right = st.columns([1.35, .85])
        with left:
            st.markdown('<div class="section-title">Projected outcome</div><div class="section-copy">Season production anchors the estimate; recent form and matchup make conservative adjustments.</div>', unsafe_allow_html=True)
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
            st.plotly_chart(polish(fig), width="stretch", config={"displayModeBar": False})
        with right:
            st.markdown('<div class="section-title">Projection coverage</div><div class="section-copy">Only “Included” factors affect the model verdict.</div>', unsafe_allow_html=True)
            provider_connected = PROVIDER_STATUS.startswith("Connected")
            coverage = pd.DataFrame([
                ["YTD + recent production", "Included"],
                ["Opponent PPR allowed", "Included · not schedule-adjusted"],
                ["Injury + practice", "Shown live · excluded" if provider_connected else "Not connected"],
                ["Snap participation", "Shown live · excluded"],
                ["Weather", "Shown live · excluded" if provider_connected else "Not connected"],
                ["Pace + game environment", "Shown live · excluded"],
                ["Betting total", "Shown when available"],
                ["OL / QB changes", "Weekly baseline active · excluded" if provider_connected else "Not connected"],
                ["Schedule-adjusted opponent", "Shown live · excluded"],
                ["Floor / projection / ceiling", "Shown · P10 / median / P90 · excluded"],
            ], columns=["Factor", "Status"])
            st.dataframe(coverage, hide_index=True, width="stretch")

        st.markdown('<div class="section-title">Why the model ranks them this way</div><div class="section-copy">Every signal used in the Start / Sit verdict, shown at the same grain.</div>', unsafe_allow_html=True)
        common = ["player", "team", "next_opponent", "games_played", "season_ppr", "recent_ppr", "recent_opportunities"]
        position_stats = {
            "QB": ["ytd_attempts", "ytd_passing_yards", "ytd_passing_tds", "ytd_rushing_yards", "ytd_rushing_tds"],
            "RB": ["ytd_carries", "ytd_targets", "ytd_rushing_yards", "ytd_receiving_yards", "ytd_rushing_tds", "ytd_receiving_tds"],
            "WR": ["ytd_targets", "ytd_receptions", "ytd_receiving_yards", "ytd_receiving_tds"],
            "TE": ["ytd_targets", "ytd_receptions", "ytd_receiving_yards", "ytd_receiving_tds"],
        }
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
        st.markdown('<div class="section-title">Live Decision Context</div><div class="section-copy">Supplementary evidence for the user. None of these fields changes the Start / Sit verdict.</div>', unsafe_allow_html=True)
        context_rows = []
        for factor in ["Injury / practice", "Snap / route participation", "Weather", "Pace / scoring environment", "Betting total", "OL / QB changes", "Schedule-adjusted opponent", "Floor · projection · ceiling"]:
            item = {"Factor": factor}
            for _, row in compare.iterrows():
                if factor == "Injury / practice":
                    value = format_injury_context(row, PROVIDER_STATUS.startswith("Connected"))
                elif factor == "Betting total":
                    provider_total = row.get("betting_total_live")
                    value = f"{float(provider_total):.1f}" if provider_total is not None and pd.notna(provider_total) else f"{row['total_line']:.1f}" if "total_line" in row and pd.notna(row["total_line"]) else "Source not connected"
                elif factor == "Weather":
                    weather_bits = []
                    if pd.notna(row.get("weather_summary_live")): weather_bits.append(str(row.get("weather_summary_live")))
                    if pd.notna(row.get("temperature_live")): weather_bits.append(f"{float(row.get('temperature_live')):.0f}°F")
                    if pd.notna(row.get("wind_live")): weather_bits.append(f"{float(row.get('wind_live')):.0f} mph wind")
                    value = " · ".join(weather_bits) if weather_bits else "Pregame source not connected"
                    if weather_bits and pd.notna(row.get("game_updated_live")): value += f" · as of {row.get('game_updated_live')}"
                elif factor == "Snap / route participation":
                    value = f"{row['latest_snap_pct']:.0%} latest · {row['recent_snap_pct']:.0%} last 3" if pd.notna(row.get("latest_snap_pct")) else "Snap feed unmatched"
                elif factor == "Pace / scoring environment":
                    value = f"{row['pace_label']} · {row['combined_recent_plays']:.1f} combined plays" if pd.notna(row.get("combined_recent_plays")) else "Pace feed unavailable"
                elif factor == "Schedule-adjusted opponent":
                    value = f"{(row['schedule_adjusted_index'] - 1) * 100:+.0f}% vs player baselines" if pd.notna(row.get("schedule_adjusted_index")) else "Insufficient sample"
                elif factor == "OL / QB changes":
                    if pd.notna(row.get("qb_changed")):
                        changes = []
                        if bool(row.get("qb_changed")): changes.append("Starting QB changed")
                        if bool(row.get("ol_changed")): changes.append("Starting OL changed")
                        value = " · ".join(changes) if changes else "No starter change vs prior snapshot"
                    else:
                        value = "Baseline snapshot only" if PROVIDER_STATUS.startswith("Connected") else "Source not connected"
                elif factor == "Floor · projection · ceiling":
                    value = f"{row['floor_ppr']:.1f} · {row['median_ppr']:.1f} · {row['ceiling_ppr']:.1f}"
                else:
                    value = "Source not connected"
                item[str(row["player"])] = value
            context_rows.append(item)
        st.dataframe(pd.DataFrame(context_rows), hide_index=True, width="stretch")
        st.markdown('<div class="note"><b>Separation rule:</b> Start / Sit is generated only from the core projection. Decision Context is refreshed and displayed independently so users can override the model using injuries, participation, weather, game environment, personnel news, and uncertainty.</div>', unsafe_allow_html=True)

elif page == "Player Trends":
    selected_position = st.segmented_control("Position", ["QB", "RB", "WR", "TE"], default="WR")
    pool = BOARD.loc[
        BOARD["position"].eq(selected_position)
        & BOARD["next_opponent"].notna()
        & BOARD["is_roster_relevant"]
        & BOARD["verified_qb_starter"]
    ]
    if pool.empty:
        hidden = int((BOARD["position"].eq("QB") & BOARD["is_roster_relevant"] & ~BOARD["verified_qb_starter"]).sum()) if selected_position == "QB" else 0
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
    st.subheader("A transparent Start / Sit model plus independent context")
    st.write("The app generates a Start / Sit verdict from a narrow core model, then shows separate live context for the user:")
    a, b, c = st.columns(3)
    a.info("**1 · Current production**\n\nSeason PPR per game supplies the stable baseline.")
    b.info("**2 · Recent form**\n\nThe most recent four appearances receive more weight.")
    c.info("**3 · Matchup**\n\nOpponent PPR allowed nudges the estimate, with a strict cap. The user makes the final choice.")
    st.subheader("Limits that matter")
    st.markdown("""
- It is a decision aid, not a sportsbook-grade projection or guarantee.
- Injury status, practice participation, weather, betting totals, and depth-chart news are not yet included.
- Early-season opponent rankings use small samples, so the confidence label stays lower.
- PPR allowed is calculated from individual player-week outcomes, which is useful but not a complete defensive model.
- The current formula favors transparency and weekly stability over complexity.
""")
    st.subheader("Source and refresh")
    st.write(f"Player stats and schedules: nflverse public releases. Data loaded for {season}; app cache refreshes hourly. Last refresh: {REFRESHED}.")
