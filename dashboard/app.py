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
    from dashboard.presentation import filter_player_search, matchup_summary, role_summary, selection_availability_summary, team_logo_url, weather_summary
except ModuleNotFoundError:
    from providers.sportsdataio import context_freshness, format_injury_context
    from outlooks import build_player_outlook
    from states import empty_player_pool_message, provider_issue_message
    from methodology_copy import DISCLAIMER_LANGUAGE, METHODOLOGY_LANGUAGE, SOURCE_ATTRIBUTION
    from presentation import filter_player_search, matchup_summary, role_summary, selection_availability_summary, team_logo_url, weather_summary

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
@import url('https://fonts.googleapis.com/css2?family=Bungee&display=swap');
:root { --ink:#071b2c; --muted:#1b2730; --navy:#002244; --cream:#f3f6f7; --card:#ffffff; --line:#d7dde0; --teal:#397f18; --gold:#69be28; --wolf:#a5acaf; }
.stApp { background:var(--cream); color:var(--ink); }
[data-testid="stMain"] [data-testid="stCaptionContainer"] { color:var(--ink); }
[data-testid="stSidebar"] { background:var(--navy); }
[data-testid="stSidebar"] * { color:#f7fafb; }
[data-testid="stSidebar"] [data-baseweb="select"] * { color:var(--ink) !important; }
[data-testid="stSidebar"] button[kind="secondary"] * { color:var(--ink) !important; }
.block-container { max-width:1440px; padding-top:1.55rem; }
h1,h2,h3 { letter-spacing:-.025em; }
.hero { display:flex; align-items:flex-end; justify-content:space-between; gap:2rem; padding:0; margin:0; }
.hero h1 { margin:.12rem 0 .18rem; font-size:2.55rem; line-height:1.02; }
.graffiti-title { font-family:'Bungee',Impact,sans-serif; color:var(--navy); letter-spacing:.015em !important; text-transform:uppercase; text-shadow:2px 2px 0 rgba(105,190,40,.28); }
.graffiti-title span { color:var(--gold); text-shadow:2px 2px 0 rgba(0,34,68,.22); }
.hero-subtitle { color:#397f18; font-size:.76rem; font-weight:850; letter-spacing:.13em; text-transform:uppercase; margin-bottom:.32rem; }
.sidebar-brand { font-family:'Bungee',Impact,sans-serif; color:#f7fafb; font-size:1.18rem; line-height:1.12; letter-spacing:.02em; margin:.15rem 0 .2rem; }
.sidebar-brand span { color:#9ee468; }
.hero p { color:var(--muted); margin:0; max-width:720px; }
.eyebrow { color:#397f18; text-transform:uppercase; letter-spacing:.13em; font-size:.74rem; font-weight:800; }
.fresh { color:var(--muted); text-align:right; font-size:.78rem; white-space:nowrap; }
.app-header { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:1rem 1.15rem; margin-bottom:1rem; }
.header-status { display:flex; justify-content:flex-end; align-items:center; gap:.38rem; color:var(--muted); font-size:.76rem; margin-top:.35rem; }
.status-dot { display:inline-block; width:.48rem; height:.48rem; border-radius:50%; background:var(--gold); }
.verdict { background:#fbfcfc; color:var(--ink); border:1px solid #dfe4e6; border-radius:16px; padding:1.15rem 1.25rem; min-height:0; }
.verdict.start { background:var(--navy); color:white; border-color:var(--gold); box-shadow:0 12px 28px rgba(0,34,68,.18); }
.verdict .tag { display:inline-block; background:#edf4e8; color:#397f18; border-radius:999px; padding:.28rem .52rem; letter-spacing:.12em; font-size:.67rem; font-weight:800; }
.verdict.start .tag { background:rgba(105,190,40,.16); color:#9ee468; }
.verdict .name { font-size:1.7rem; font-weight:750; margin:.65rem 0 .1rem; }
.player-heading { display:flex; align-items:center; gap:.75rem; margin:.65rem 0 .1rem; min-width:0; }
.player-heading .name { margin:0; overflow-wrap:anywhere; }
.player-photo { width:58px; height:58px; flex:0 0 58px; border-radius:50%; background-size:cover; background-position:center top; background-repeat:no-repeat; background-color:#e8ecee; border:2px solid #d7dde0; }
.verdict.start .player-photo { border-color:#69be28; background-color:#173854; }
.verdict .opponent { color:var(--muted); font-size:.8rem; }
.team-line { display:flex; align-items:center; gap:.42rem; flex-wrap:wrap; }
.team-logo { width:1.35rem; height:1.35rem; object-fit:contain; flex:0 0 1.35rem; }
.verdict.start .opponent { color:#c0c8cc; }
.projection-primary { display:flex; align-items:flex-end; gap:.42rem; margin-top:.72rem; }
.projection-primary strong { color:var(--teal); font-size:2.15rem; line-height:.95; letter-spacing:-.04em; }
.projection-primary span { color:var(--muted); font-size:.68rem; font-weight:750; padding-bottom:.16rem; }
.verdict.start .projection-primary strong { color:#9ee468; }
.verdict.start .projection-primary span { color:#c0c8cc; }
.range-track { position:relative; height:5px; border-radius:999px; background:#d9e0e3; margin:.68rem .15rem .38rem; }
.range-track::before { content:""; position:absolute; inset:0; border-radius:inherit; background:linear-gradient(90deg,#a5acaf,#69be28); opacity:.75; }
.range-marker { position:absolute; top:50%; width:11px; height:11px; border-radius:50%; background:var(--navy); border:2px solid white; transform:translate(-50%,-50%); box-shadow:0 0 0 1px rgba(0,34,68,.25); }
.verdict.start .range-track { background:rgba(255,255,255,.18); }
.verdict.start .range-marker { background:#9ee468; border-color:var(--navy); }
.range-labels { display:flex; justify-content:space-between; color:var(--muted); font-size:.65rem; }
.verdict.start .range-labels { color:#c0c8cc; }
.confidence-label { margin-left:auto; border-radius:999px; padding:.27rem .48rem; font-size:.61rem; font-weight:850; letter-spacing:.04em; text-transform:uppercase; background:#edf4e8; color:#397f18; }
.verdict.start .confidence-label { background:rgba(105,190,40,.16); color:#9ee468; }
.range-help { position:relative; display:inline-flex; align-items:center; justify-content:center; width:1.05rem; height:1.05rem; border:1px solid currentColor; border-radius:50%; font-size:.68rem; font-weight:800; cursor:help; opacity:.82; }
.range-tooltip { visibility:hidden; opacity:0; position:absolute; z-index:20; left:50%; bottom:calc(100% + .5rem); transform:translateX(-50%); width:250px; padding:.55rem .65rem; border-radius:8px; background:#071b2c; color:#f7fafb; font-size:.74rem; font-weight:500; line-height:1.35; text-align:left; box-shadow:0 8px 22px rgba(0,0,0,.22); transition:opacity .12s ease; }
.range-help:hover .range-tooltip, .range-help:focus .range-tooltip, .range-help:focus-within .range-tooltip { visibility:visible; opacity:1; }
.verdict .outlook-label { color:var(--muted); text-transform:uppercase; letter-spacing:.1em; font-size:.65rem; font-weight:800; margin-top:1rem; }
.verdict.start .outlook-label { color:#9ee468; }
.verdict .reason { color:var(--ink); font-size:.84rem; line-height:1.42; margin-top:.28rem; min-height:2.4em; }
.verdict.start .reason { color:#e0e6e8; }
.decision-edge { display:flex; align-items:center; justify-content:space-between; gap:1rem; background:var(--navy); color:#f7fafb; border:1px solid rgba(105,190,40,.65); border-radius:13px; padding:.82rem 1rem; margin:1rem 0 .75rem; box-shadow:0 7px 18px rgba(0,34,68,.10); }
.decision-edge-main { min-width:0; }
.decision-edge-label { color:#9ee468; font-size:.62rem; font-weight:850; letter-spacing:.1em; text-transform:uppercase; margin-bottom:.16rem; }
.decision-edge-title { font-size:1rem; font-weight:780; line-height:1.25; overflow-wrap:anywhere; }
.decision-edge-copy { color:#cbd5da; font-size:.76rem; line-height:1.35; margin-top:.18rem; }
.decision-edge-badge { flex:0 0 auto; background:rgba(105,190,40,.16); color:#9ee468; border:1px solid rgba(158,228,104,.42); border-radius:999px; padding:.38rem .62rem; font-size:.66rem; font-weight:850; letter-spacing:.06em; text-transform:uppercase; white-space:nowrap; }
.broadcast-context { display:grid; grid-template-columns:1fr; gap:.3rem; margin-top:.78rem; }
.broadcast-context-item { display:flex; align-items:flex-start; gap:.42rem; background:transparent; color:var(--ink); padding:.34rem 0; border-top:1px solid #e7eaec; min-width:0; font-size:.72rem; line-height:1.28; overflow-wrap:anywhere; }
.broadcast-context-item span { color:var(--muted); min-width:5.25rem; font-size:.62rem; font-weight:800; letter-spacing:.04em; text-transform:uppercase; }
.broadcast-context-item.context-alert { color:#a33a13; font-weight:750; }
.verdict.start .broadcast-context-item { background:rgba(255,255,255,.1); color:#f4f8fa; }
.verdict.start .broadcast-context-item { background:transparent; border-top-color:rgba(255,255,255,.13); }
.verdict.start .broadcast-context-item span { color:#9ee468; }
.game-detail-line { color:var(--muted); font-size:.7rem; line-height:1.35; margin-top:.4rem; }
.verdict.start .game-detail-line { color:#c0c8cc; }
.relative-sit-note { color:var(--muted); font-size:.68rem; line-height:1.35; margin-top:.62rem; font-style:italic; }
.card-outlook-details { border-top:1px solid #e3e8ea; margin-top:.72rem; padding-top:.22rem; }
.card-outlook-details summary { color:var(--navy); cursor:pointer; font-size:.74rem; font-weight:800; padding:.5rem .1rem .28rem; list-style-position:inside; }
.card-outlook-details summary:hover { color:#397f18; }
.card-outlook-full { color:var(--ink); font-size:.79rem; line-height:1.5; padding:.42rem .2rem .15rem; }
.verdict.start .card-outlook-details { border-top-color:rgba(255,255,255,.16); }
.verdict.start .card-outlook-details summary { color:#9ee468; }
.verdict.start .card-outlook-full { color:#e0e6e8; }
.reporting-sources { margin-top:.65rem; font-size:.72rem; color:var(--muted); line-height:1.35; }
.reporting-sources a { color:#397f18; font-weight:700; text-decoration:none; }
.verdict.start .reporting-sources { color:#c0c8cc; }
.verdict.start .reporting-sources a { color:#9ee468; }
.section-title { font-size:1.16rem; font-weight:750; margin:1.2rem 0 .1rem; }
.section-copy { color:var(--muted); font-size:.87rem; margin-bottom:.65rem; }
.note { border-left:4px solid var(--gold); background:#edf4e8; color:#183515; padding:.72rem .9rem; border-radius:8px; font-size:.84rem; margin-top:1rem; }
.warning { border-left:4px solid var(--gold); background:#eef5e9; color:#29451f; padding:.72rem .9rem; border-radius:8px; font-size:.84rem; margin:.85rem 0; }
.game-status { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.55rem; margin:.85rem 0 .45rem; }
.game-status-item { background:var(--card); border:1px solid var(--line); border-radius:11px; padding:.68rem .78rem; min-width:0; }
.game-status-label { color:var(--muted); font-size:.62rem; font-weight:800; letter-spacing:.07em; text-transform:uppercase; margin-bottom:.16rem; }
.game-status-value { color:var(--ink); font-size:.8rem; font-weight:720; line-height:1.25; overflow-wrap:anywhere; }
.game-status-note { color:var(--muted); font-size:.73rem; margin:0 0 .8rem; }
.player-finder { margin:.35rem 0 .8rem; }
.finder-copy { color:var(--muted); font-size:.78rem; margin:-.25rem 0 .55rem; }
.selected-player-name { font-size:.94rem; font-weight:750; line-height:1.2; margin-top:.2rem; }
.selected-player-meta { color:var(--muted); font-size:.72rem; line-height:1.3; }
.compare-slot-kicker { color:#397f18; font-size:.61rem; font-weight:850; letter-spacing:.09em; text-transform:uppercase; margin-bottom:.55rem; }
.compare-slot-top { display:flex; align-items:center; gap:.68rem; min-height:62px; }
.compare-slot-main { min-width:0; }
.compare-slot-name { color:var(--ink); font-size:1rem; font-weight:800; line-height:1.16; overflow-wrap:anywhere; }
.compare-slot-team { display:flex; align-items:center; gap:.34rem; color:var(--muted); font-size:.72rem; margin-top:.22rem; }
.compare-slot-team img { width:1.15rem; height:1.15rem; object-fit:contain; }
.compare-slot-game { color:var(--muted); font-size:.72rem; line-height:1.3; margin-top:.52rem; }
.compare-slot-footer { display:flex; align-items:center; justify-content:space-between; gap:.5rem; border-top:1px solid #e4e8ea; margin-top:.65rem; padding-top:.58rem; }
.compare-slot-projection { color:var(--navy); font-size:.82rem; font-weight:800; }
.availability-pill { border-radius:999px; padding:.24rem .46rem; font-size:.63rem; font-weight:800; line-height:1.15; text-align:right; }
.availability-ok { background:#edf4e8; color:#397f18; }
.availability-alert { background:#fff0e6; color:#a33a13; border:1px solid #efb79f; }
.open-slot { min-height:166px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; border:2px dashed #bdc8cd; border-radius:11px; color:var(--muted); padding:1rem; }
.open-slot-number { color:#397f18; font-size:.62rem; font-weight:850; letter-spacing:.09em; text-transform:uppercase; }
.open-slot-title { color:var(--ink); font-size:.95rem; font-weight:780; margin:.3rem 0 .12rem; }
.open-slot-copy { font-size:.72rem; line-height:1.35; max-width:210px; }
.replacement-note { background:#edf4e8; border-left:3px solid var(--gold); color:#29451f; border-radius:8px; padding:.55rem .7rem; font-size:.76rem; margin:.35rem 0 .65rem; }
.projection-scope { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.7rem; margin:.35rem 0 1rem; }
.projection-scope-card { border:1px solid var(--line); border-radius:11px; padding:.75rem .85rem; background:#fbfcfc; }
.projection-scope-card.included { border-left:4px solid var(--gold); }
.projection-scope-card.informational { border-left:4px solid var(--wolf); }
.projection-scope-card strong { display:block; color:var(--ink); font-size:.78rem; margin-bottom:.25rem; }
.projection-scope-card span { color:var(--muted); font-size:.71rem; line-height:1.35; }
.driver-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.7rem; }
.driver-card { border:1px solid var(--line); border-radius:12px; overflow:hidden; background:var(--card); min-width:0; }
.driver-card-head { background:var(--navy); color:white; padding:.7rem .8rem; }
.driver-card-head strong { display:block; font-size:.88rem; line-height:1.2; }
.driver-card-head span { color:#c0c8cc; font-size:.67rem; }
.driver-row { padding:.62rem .75rem; border-top:1px solid #e7eaec; }
.driver-row-top { display:flex; align-items:center; justify-content:space-between; gap:.5rem; }
.driver-label { color:var(--ink); font-size:.7rem; font-weight:800; }
.driver-value { color:var(--ink); font-size:.7rem; font-weight:800; white-space:nowrap; }
.driver-explanation { color:var(--muted); font-size:.65rem; line-height:1.32; margin-top:.18rem; }
.driver-direction { display:inline-flex; align-items:center; justify-content:center; width:1rem; font-weight:900; margin-right:.16rem; }
.driver-positive { color:#397f18; }
.driver-neutral { color:#46535a; }
.driver-negative { color:#c45a1a; }
.driver-final { background:#edf4e8; }
.driver-final .driver-value { color:#397f18; font-size:.86rem; }
.advanced-stat-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.7rem; margin-top:.65rem; }
.advanced-stat-card { background:var(--card); border:1px solid var(--line); border-radius:11px; overflow:hidden; min-width:0; }
.advanced-stat-head { background:#eef2f3; padding:.65rem .75rem; }
.advanced-stat-head strong { display:block; color:var(--ink); font-size:.82rem; line-height:1.2; overflow-wrap:anywhere; }
.advanced-stat-head span { color:var(--muted); font-size:.65rem; }
.advanced-stat-row { display:flex; justify-content:space-between; gap:.6rem; padding:.48rem .7rem; border-top:1px solid #e7eaec; font-size:.68rem; line-height:1.25; }
.advanced-stat-row span { color:var(--muted); }
.advanced-stat-row b { color:var(--ink); text-align:right; }
.context-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.85rem; width:100%; }
.context-card { background:var(--card); border:1px solid var(--line); border-radius:14px; overflow:hidden; min-width:0; }
.context-card h3 { margin:0; padding:.9rem 1rem; background:#ebe7dc; color:var(--ink); font-size:1.05rem; display:flex; align-items:center; gap:.6rem; }
.context-card .player-photo { width:42px; height:42px; flex-basis:42px; border-width:1px; }
.context-row { display:grid; grid-template-columns:minmax(112px,.78fr) minmax(0,1.22fr); gap:.7rem; padding:.67rem 1rem; border-top:1px solid #e5e8e9; align-items:start; }
.context-label { color:var(--muted); font-size:.72rem; font-weight:800; letter-spacing:.02em; line-height:1.25; }
.context-value { color:var(--ink); font-size:.82rem; font-weight:600; line-height:1.35; overflow-wrap:anywhere; }
.context-help { cursor:help; border-bottom:1px dotted currentColor; }
.stPlotlyChart { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:.2rem; }
@media(max-width:1100px) {
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
  .game-status { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .driver-grid { grid-template-columns:1fr; }
  .advanced-stat-grid { grid-template-columns:1fr; }
}
@media(max-width:520px) {
  div[data-baseweb="select"] > div { flex-wrap:wrap; }
  .game-status { grid-template-columns:1fr; }
  .decision-edge { align-items:flex-start; flex-direction:column; }
  .projection-scope { grid-template-columns:1fr; }
}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=300, show_spinner=False)
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
        font=dict(family="Arial", color="#071b2c", size=12),
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
    st.markdown('<div class="sidebar-brand">START <span>/</span> SIT LAB</div>', unsafe_allow_html=True)
    st.caption("Fantasy decision tools")
    page = st.radio("View", ["Decision Room", "Player Trends", "How It Works"], label_visibility="collapsed")
season = SEASON

header_metadata = json.loads((PROJECT_ROOT / "data" / "processed" / "live_refresh_metadata.json").read_text(encoding="utf-8"))
header_week = int(header_metadata.get("next_week", 0))
header_checked = datetime.fromisoformat(str(header_metadata.get("refreshed_at", datetime.now(timezone.utc).isoformat())).replace("Z", "+00:00"))
header_age_minutes = max(0, int((datetime.now(timezone.utc) - header_checked.astimezone(timezone.utc)).total_seconds() // 60))

with st.container(border=True):
    header_left, header_right = st.columns([1.55, .75], vertical_alignment="center")
    with header_left:
        st.markdown(
            f'<div class="hero"><div><div class="eyebrow">Week {header_week} · {season}</div>'
            '<h1 class="graffiti-title">START <span>/</span> SIT LAB</h1><div class="hero-subtitle">Player Comparison</div>'
            '<p>Compare up to three players and make the final lineup call.</p></div></div>',
            unsafe_allow_html=True,
        )
    with header_right:
        qb_td_label = st.radio("Full PPR · QB passing TD", ["4 points", "6 points"], horizontal=True)
        QB_PASS_TD_POINTS = int(qb_td_label.split()[0])
        st.markdown(f'<div class="header-status"><span class="status-dot"></span>Data current · updated {header_age_minutes} minutes ago</div>', unsafe_allow_html=True)

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
    with st.expander("● Data status"):
        st.caption(f"Weekly stats · {REFRESHED}")
        st.caption(f"SportsDataIO · {PROVIDER_STATUS}")
        st.caption(INJURY_SOURCE_STATUS)
        if st.button("Check for latest update", width="stretch"):
            st.cache_data.clear()
            st.rerun()

if page == "Decision Room":
    context_age_minutes, context_is_stale = context_freshness(PROVIDER_REFRESHED_AT)
    context_value = "Needs confirmation" if context_is_stale else "Current"
    context_detail = "Unavailable" if context_age_minutes is None else f"Checked {context_age_minutes} min ago"
    high_frequency_day = datetime.now().weekday() in {0, 3, 6}
    next_refresh_copy = "Within 30 min" if high_frequency_day else "Within 2 hours"
    st.markdown(
        '<div class="game-status">'
        f'<div class="game-status-item"><div class="game-status-label">Last update</div><div class="game-status-value">{header_age_minutes} min ago</div></div>'
        f'<div class="game-status-item"><div class="game-status-label">Injury reports</div><div class="game-status-value">Frequent cloud checks</div></div>'
        f'<div class="game-status-item"><div class="game-status-label">Weather / depth</div><div class="game-status-value">{context_value} · {context_detail}</div></div>'
        f'<div class="game-status-item"><div class="game-status-label">Next refresh</div><div class="game-status-value">{next_refresh_copy}</div></div>'
        '</div>'
        '<div class="game-status-note"><b>Before kickoff:</b> confirm official inactives and late-breaking team news before locking your lineup.</div>',
        unsafe_allow_html=True,
    )
    if context_is_stale:
        st.warning("Weather or depth-chart context is older than expected or unavailable. Confirm the latest team status before kickoff.")
    provider_issue = provider_issue_message(PROVIDER_STATUS)
    if provider_issue:
        st.warning(provider_issue)
    position = st.segmented_control("Position", ["QB", "RB", "WR", "TE"], default="WR")
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
        st.warning(empty_player_pool_message(position, len(excluded_qbs)))
        names = []
    else:
        selection_key = f"smart_search_selected_{position}"
        replacement_key = f"smart_search_replace_{position}"
        valid_names = set(pool["player"].tolist())
        if selection_key not in st.session_state:
            st.session_state[selection_key] = pool.sort_values("projected_ppr", ascending=False).head(3)["player"].tolist()
        st.session_state[selection_key] = [name for name in st.session_state[selection_key] if name in valid_names][:3]
        if replacement_key not in st.session_state:
            st.session_state[replacement_key] = None
        names = list(st.session_state[selection_key])
        replacement_index = st.session_state[replacement_key]
        if replacement_index is not None and (replacement_index < 0 or replacement_index >= len(names)):
            replacement_index = None
            st.session_state[replacement_key] = None

        st.markdown(f'<div class="section-copy">Comparison lineup · {len(names)} of 3 slots filled</div>', unsafe_allow_html=True)
        slot_columns = st.columns(3)
        for slot_index, slot_column in enumerate(slot_columns):
            with slot_column:
                with st.container(border=True):
                    if slot_index < len(names):
                        selected_row = pool.loc[pool["player"].eq(names[slot_index])].iloc[0]
                        availability = selection_availability_summary(selected_row)
                        availability_class = "availability-alert" if any(term in availability.casefold() for term in ("questionable", "doubtful", "out", "inactive", "ir", "did not practice")) else "availability-ok"
                        photo = player_photo_html(selected_row.get("headshot_url"), selected_row["player"])
                        logo_url = team_logo_url(selected_row.get("team"))
                        logo = f'<img src="{html.escape(logo_url, quote=True)}" alt="{html.escape(str(selected_row["team"]), quote=True)} logo">' if logo_url else ""
                        kickoff = " · ".join(str(value) for value in (selected_row.get("weekday"), selected_row.get("gametime")) if value is not None and pd.notna(value))
                        st.markdown(
                            f'<div class="compare-slot-kicker">Player {slot_index + 1}</div>'
                            f'<div class="compare-slot-top">{photo}<div class="compare-slot-main"><div class="compare-slot-name">{html.escape(str(selected_row["player"]))}</div>'
                            f'<div class="compare-slot-team">{logo}<span>{html.escape(str(selected_row["team"]))} · {html.escape(str(selected_row["position"]))}</span></div></div></div>'
                            f'<div class="compare-slot-game">{html.escape(str(selected_row["venue"]))} vs {html.escape(str(selected_row["next_opponent"]))}{" · " + html.escape(kickoff) if kickoff else ""}</div>'
                            f'<div class="compare-slot-footer"><span class="compare-slot-projection">{float(selected_row["median_ppr"]):.1f} projected PPR</span><span class="availability-pill {availability_class}">{html.escape(availability)}</span></div>',
                            unsafe_allow_html=True,
                        )
                        remove_column, replace_column = st.columns(2)
                        if remove_column.button("Remove", key=f"remove_{position}_{selected_row['player_id']}", width="stretch"):
                            st.session_state[selection_key] = [value for value in names if value != names[slot_index]]
                            st.session_state[replacement_key] = None
                            st.rerun()
                        replace_label = "Replacing…" if replacement_index == slot_index else "Replace"
                        if replace_column.button(replace_label, key=f"replace_{position}_{selected_row['player_id']}", width="stretch"):
                            st.session_state[replacement_key] = None if replacement_index == slot_index else slot_index
                            st.rerun()
                    else:
                        st.markdown(
                            f'<div class="open-slot"><div class="open-slot-number">Player {slot_index + 1}</div><div class="open-slot-title">Open comparison slot</div><div class="open-slot-copy">Choose a player from the search panel below.</div></div>',
                            unsafe_allow_html=True,
                        )

        panel_label = "Replace a player" if replacement_index is not None else "Find a player"
        with st.expander(panel_label, expanded=len(names) < 3 or replacement_index is not None):
            if len(names) >= 3 and replacement_index is None:
                st.markdown('<div class="replacement-note">All three comparison slots are filled. Select <b>Replace</b> on any player card to swap someone in without removing them first.</div>', unsafe_allow_html=True)
            else:
                if replacement_index is not None:
                    st.markdown(f'<div class="replacement-note">Replacing <b>{html.escape(names[replacement_index])}</b>. Choose a player below to complete the swap.</div>', unsafe_allow_html=True)
                query = st.text_input("Search eligible players", key=f"smart_search_query_{position}", placeholder="Search by player or team…")
                results = filter_player_search(pool.loc[~pool["player"].isin(names)], query)
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
                            availability_prefix = "⚠ " if any(term in availability.casefold() for term in ("questionable", "doubtful", "out", "inactive", "ir", "did not practice")) else ""
                            details_column.markdown(
                                f'<b>{html.escape(str(result_row["player"]))}</b><br>'
                                f'{html.escape(str(result_row["team"]))} · {html.escape(str(result_row["position"]))} · {html.escape(str(result_row["venue"]))} vs {html.escape(str(result_row["next_opponent"]))}<br>'
                                f'<span class="selected-player-meta">{availability_prefix}{html.escape(availability)}</span>', unsafe_allow_html=True,
                            )
                            logo_url = team_logo_url(result_row.get("team"))
                            if logo_url:
                                logo_column.image(logo_url, width=34)
                            action_label = f"Replace · {float(result_row['median_ppr']):.1f}" if replacement_index is not None else f"Add · {float(result_row['median_ppr']):.1f}"
                            if action_column.button(action_label, key=f"choose_{position}_{result_row['player_id']}_{replacement_index}", width="stretch"):
                                if replacement_index is None:
                                    st.session_state[selection_key] = [*names, str(result_row["player"])]
                                else:
                                    updated_names = list(names)
                                    updated_names[replacement_index] = str(result_row["player"])
                                    st.session_state[selection_key] = updated_names
                                    st.session_state[replacement_key] = None
                                st.rerun()
    compare = pool.loc[pool["player"].isin(names)].sort_values("projected_ppr", ascending=False)

    if compare.empty:
        if not pool.empty:
            st.info("Choose at least one available player above to begin the comparison.")
    else:
        leader = compare.iloc[0]
        projection_spread = float(compare["median_ppr"].max() - compare["median_ppr"].min())
        if len(compare) == 1:
            edge_title = f'{leader["player"]} · {float(leader["median_ppr"]):.1f} projected PPR'
            edge_copy = "Add another player to see the projected advantage."
            edge_badge = "1 player selected"
        else:
            edge_title = f'{leader["player"]} leads by {projection_spread:.1f} PPR'
            edge_copy = "The projections are close—treat this as a lean and use the live context below to make your final call." if projection_spread < 2.5 else "We see a meaningful projected advantage, with live context below for your final decision."
            edge_badge = "Close call" if projection_spread < 2.5 else "Clearer edge"
        st.markdown(
            '<div class="decision-edge">'
            f'<div class="decision-edge-main"><div class="decision-edge-label">Week {NEXT_WEEK} decision edge</div>'
            f'<div class="decision-edge-title">{html.escape(edge_title)}</div>'
            f'<div class="decision-edge-copy">{html.escape(edge_copy)}</div></div>'
            f'<div class="decision-edge-badge">{html.escape(edge_badge)}</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="section-title">Start / Sit verdict</div><div class="section-copy">We build this ranking from current production, repeatable workload, a fading prior-season anchor, touchdown regression, and a sample-scaled matchup adjustment. The live context shown below helps you make the final call but does not change our ranking.</div>', unsafe_allow_html=True)
        outlook_columns = st.columns(len(compare))
        top_gap = 0.0 if len(compare) == 1 else float(compare.iloc[0]["median_ppr"] - compare.iloc[1]["median_ppr"])
        edge_confidence = "Solo view" if len(compare) == 1 else "Lean" if top_gap < 2.5 else "Moderate edge" if top_gap < 5 else "Strong edge"
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
                full_reason = build_player_outlook(row, index, len(compare), projection_spread, row.get("reporting_summary"))
                if len(compare) == 1:
                    reason = "Add another player to turn this into a true Start/Sit comparison."
                elif index == 0 and top_gap < 2.5:
                    reason = "Our preferred start, but only by a slim margin."
                elif index == 0:
                    reason = "Our preferred start with the strongest projection in this group."
                elif float(leader["median_ppr"] - row["median_ppr"]) < 2.5:
                    reason = "A close alternative with a nearly identical projection."
                else:
                    reason = "The riskier option relative to the other players in this comparison."
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
                logo_url = team_logo_url(row.get("team"))
                logo = f'<img class="team-logo" src="{html.escape(logo_url, quote=True)}" alt="{html.escape(str(row["team"]), quote=True)} logo">' if logo_url else ""
                player_details = f'{row.get("team")} · {row.get("position")}'
                game_details = []
                team_record = row.get("team_record")
                if team_record is not None and pd.notna(team_record) and str(team_record).strip():
                    game_details.append(f'{row.get("team")} {team_record}')
                game_details.append(f'{row.get("venue")} vs {row.get("next_opponent")}')
                kickoff = " · ".join(str(row.get(value)) for value in ("weekday", "gametime") if row.get(value) is not None and pd.notna(row.get(value)))
                if kickoff:
                    game_details.append(kickoff)
                betting_total = row.get("betting_total_live")
                if betting_total is None or pd.isna(betting_total):
                    betting_total = row.get("total_line")
                if betting_total is not None and pd.notna(betting_total):
                    game_details.append(f'{float(betting_total):.1f}-point game total')
                practice = format_injury_context(row, "Connected" in INJURY_SOURCE_STATUS)
                practice_alert = any(term in practice.casefold() for term in ("questionable", "doubtful", "out", "inactive", "ir", "did not practice"))
                quick_context = "".join([
                    f'<div class="broadcast-context-item{" context-alert" if practice_alert else ""}"><span>● Practice</span>{html.escape(practice)}</div>',
                    f'<div class="broadcast-context-item"><span>◆ Matchup</span>{html.escape(matchup_summary(row))}</div>',
                    f'<div class="broadcast-context-item"><span>↗ Role</span>{html.escape(role_summary(row))}</div>',
                    f'<div class="broadcast-context-item"><span>☁ Weather</span>{html.escape(weather_summary(row))}</div>',
                ])
                floor = float(row["floor_ppr"])
                median = float(row["median_ppr"])
                ceiling = float(row["ceiling_ppr"])
                median_position = max(5.0, min(95.0, 100 * (median - floor) / max(ceiling - floor, .1)))
                relative_note = "Sit is relative to the players in this comparison—not an automatic bench recommendation." if index > 0 and len(compare) > 1 else ""
                outlook_details = (
                    f'<details class="card-outlook-details"><summary>Expand player outlook</summary><div class="card-outlook-full">'
                    f'{html.escape(full_reason)}{reporting_links}</div></details>'
                )
                st.markdown(
                    f'<div class="verdict {card_class}"><div style="display:flex;align-items:center;gap:.45rem"><div class="tag">{verdict}</div><div class="confidence-label">{edge_confidence}</div></div><div class="player-heading">{photo}<div class="name">{html.escape(str(row["player"]))}</div></div>'
                    f'<div class="opponent team-line">{logo}<span>{html.escape(player_details)}</span></div>'
                    f'<div class="game-detail-line">{html.escape(" · ".join(game_details))}</div>'
                    f'<div class="projection-primary"><strong>{median:.1f}</strong><span>projected PPR <span class="range-help" tabindex="0" aria-label="Range definition">i<span class="range-tooltip" role="tooltip">Floor is the P10 downside outcome, projection is the median estimate, and ceiling is the P90 upside outcome. About 80% of results should fall between floor and ceiling.</span></span></span></div>'
                    f'<div class="range-track"><span class="range-marker" style="left:{median_position:.1f}%"></span></div><div class="range-labels"><span>Floor {floor:.1f}</span><span>Ceiling {ceiling:.1f}</span></div>'
                    f'<div class="outlook-label">Player outlook</div><div class="reason">{html.escape(reason)}</div><div class="broadcast-context">{quick_context}</div>'
                    f'{f"<div class=\"relative-sit-note\">{html.escape(relative_note)}</div>" if relative_note else ""}{outlook_details}</div>',
                    unsafe_allow_html=True,
                )

        st.markdown('<div class="section-title">Comparison Tool</div><div class="section-copy">Explore the selected players through calibrated projection ranges, weekly production, and repeatable usage. Hover or zoom for more detail.</div>', unsafe_allow_html=True)
        range_tab, trend_tab, usage_tab = st.tabs(["Projection range", "Weekly trend", "Usage & production"])
        chart_colors = ["#69be28", "#002244", "#a5acaf"][:len(compare)]

        detail_records = []
        for _, detail_row in compare.iterrows():
            detail_total = detail_row.get("betting_total_live")
            if detail_total is None or pd.isna(detail_total):
                detail_total = detail_row.get("total_line")
            detail_records.append({
                "Player": detail_row["player"],
                "Team": detail_row["team"],
                "Record": detail_row.get("team_record") if pd.notna(detail_row.get("team_record")) else "—",
                "Opponent": detail_row["next_opponent"],
                "Site": detail_row["venue"],
                "Kickoff": " · ".join(str(detail_row.get(value)) for value in ("weekday", "gametime") if detail_row.get(value) is not None and pd.notna(detail_row.get(value))),
                "Availability": selection_availability_summary(detail_row),
                "Game total": f"{float(detail_total):.1f}" if detail_total is not None and pd.notna(detail_total) else "—",
                "Projection": float(detail_row["median_ppr"]),
                "Range": f'{float(detail_row["floor_ppr"]):.1f}–{float(detail_row["ceiling_ppr"]):.1f}',
            })
        comparison_details = pd.DataFrame(detail_records)

        with range_tab:
            range_custom = []
            for detail in detail_records:
                range_custom.append([
                    detail["Team"], detail["Record"], detail["Opponent"], detail["Site"], detail["Kickoff"],
                    detail["Availability"], detail["Game total"], detail["Range"],
                ])
            range_fig = go.Figure(go.Scatter(
                x=compare["median_ppr"], y=compare["player"], mode="markers+text",
                text=compare["median_ppr"].map(lambda value: f"{value:.1f}"), textposition="top center",
                marker=dict(size=18, color=chart_colors, line=dict(color="#ffffff", width=2)),
                error_x=dict(type="data", symmetric=False, array=compare["ceiling_ppr"] - compare["median_ppr"], arrayminus=compare["median_ppr"] - compare["floor_ppr"], color="#69777e", thickness=4, width=8),
                customdata=range_custom,
                hovertemplate="<b>%{y}</b> · %{customdata[0]} %{customdata[1]}<br>Median %{x:.1f} PPR · range %{customdata[7]}<br>%{customdata[3]} vs %{customdata[2]} · %{customdata[4]}<br>Availability: %{customdata[5]}<br>Game total: %{customdata[6]}<extra></extra>",
            ))
            range_fig.update_layout(title=f"Week {NEXT_WEEK} P10–P90 projection range", xaxis_title="PPR points", yaxis_title="", showlegend=False)
            range_fig.update_yaxes(autorange="reversed")
            range_fig.update_xaxes(range=[max(0, float(compare["floor_ppr"].min()) - 3), float(compare["ceiling_ppr"].max()) + 3])
            st.plotly_chart(polish(range_fig, 340), width="stretch", config={"displayModeBar": True, "displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]})
            overlap = max(0.0, min(compare["ceiling_ppr"]) - max(compare["floor_ppr"]))
            st.caption(f"All selected ranges overlap by {overlap:.1f} PPR. The median gap is {projection_spread:.1f} PPR, so the ordering should be treated as {'a lean' if projection_spread < 2.5 else 'meaningful separation'}.")

        with trend_tab:
            weekly_name_column = "player_display_name" if "player_display_name" in WEEKLY.columns else "player_name"
            trend_history = WEEKLY.loc[WEEKLY[weekly_name_column].isin(compare["player"])].copy()
            if trend_history.empty:
                st.info("Weekly production history is temporarily unavailable for these players.")
            else:
                trend_history["display_ppr"] = pd.to_numeric(trend_history["fantasy_points_ppr"], errors="coerce")
                if position == "QB" and QB_PASS_TD_POINTS != 4 and "passing_tds" in trend_history:
                    trend_history["display_ppr"] += (QB_PASS_TD_POINTS - 4) * pd.to_numeric(trend_history["passing_tds"], errors="coerce").fillna(0)
                trend_fig = go.Figure()
                for color, player_name in zip(chart_colors, compare["player"]):
                    player_history = trend_history.loc[trend_history[weekly_name_column].eq(player_name)].sort_values("week")
                    hover_values = list(zip(
                        player_history.get("opponent_team", pd.Series("—", index=player_history.index)),
                        player_history.get("targets", pd.Series(0, index=player_history.index)),
                        player_history.get("carries", pd.Series(0, index=player_history.index)),
                        player_history.get("receptions", pd.Series(0, index=player_history.index)),
                        player_history.get("receiving_yards", pd.Series(0, index=player_history.index)),
                        player_history.get("rushing_yards", pd.Series(0, index=player_history.index)),
                    ))
                    trend_fig.add_trace(go.Scatter(
                        x=player_history["week"], y=player_history["display_ppr"], mode="lines+markers", name=player_name,
                        line=dict(color=color, width=4 if player_name == leader["player"] else 3), marker=dict(size=9), customdata=hover_values,
                        hovertemplate="<b>%{fullData.name}</b> · Week %{x}<br>%{y:.1f} PPR vs %{customdata[0]}<br>Targets %{customdata[1]:.0f} · carries %{customdata[2]:.0f}<br>Receptions %{customdata[3]:.0f} · receiving yards %{customdata[4]:.0f}<br>Rushing yards %{customdata[5]:.0f}<extra></extra>",
                    ))
                trend_fig.update_layout(title="Weekly PPR production", xaxis_title="NFL week", yaxis_title="PPR points", hovermode="x unified")
                trend_fig.update_xaxes(dtick=1)
                st.plotly_chart(polish(trend_fig, 380), width="stretch", config={"displayModeBar": True, "displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]})

        with usage_tab:
            metric_options = {
                "QB": {"Pass attempts": "ytd_attempts", "Passing yards": "ytd_passing_yards", "Passing TDs": "ytd_passing_tds", "Carries": "ytd_carries", "Rushing yards": "ytd_rushing_yards"},
                "RB": {"Carries": "ytd_carries", "Targets": "ytd_targets", "Rushing yards": "ytd_rushing_yards", "Receiving yards": "ytd_receiving_yards", "Total touchdowns": "ytd_total_tds"},
                "WR": {"Targets": "ytd_targets", "Receptions": "ytd_receptions", "Receiving yards": "ytd_receiving_yards", "Receiving TDs": "ytd_receiving_tds", "Snap share": "latest_snap_pct"},
                "TE": {"Targets": "ytd_targets", "Receptions": "ytd_receptions", "Receiving yards": "ytd_receiving_yards", "Receiving TDs": "ytd_receiving_tds", "Snap share": "latest_snap_pct"},
            }[position]
            usage_left, usage_right = st.columns([1, 1])
            usage_label = usage_left.selectbox("Statistic", list(metric_options), key=f"comparison_usage_metric_{position}")
            usage_mode = usage_right.radio("Display", ["Per game", "Season total"], horizontal=True, key=f"comparison_usage_mode_{position}")
            usage_column = metric_options[usage_label]
            usage_values = compare.copy()
            if usage_column == "ytd_total_tds":
                usage_values[usage_column] = usage_values.get("ytd_rushing_tds", 0) + usage_values.get("ytd_receiving_tds", 0)
            values = pd.to_numeric(usage_values.get(usage_column, pd.Series(0, index=usage_values.index)), errors="coerce").fillna(0)
            is_share = usage_column == "latest_snap_pct"
            if is_share:
                values = values * 100
                usage_mode = "Latest week"
            elif usage_mode == "Per game":
                values = values / pd.to_numeric(usage_values["games_played"], errors="coerce").clip(lower=1)
            usage_fig = go.Figure(go.Bar(
                x=values, y=usage_values["player"], orientation="h", marker_color=chart_colors,
                text=values.map(lambda value: f"{value:.1f}{'%' if is_share else ''}"), textposition="outside",
                customdata=list(zip(usage_values["team"], usage_values["next_opponent"], usage_values["games_played"])),
                hovertemplate=f"<b>%{{y}}</b> · %{{customdata[0]}}<br>{usage_label}: %{{x:.1f}}{'%' if is_share else ''}<br>%{{customdata[2]}} games played · next vs %{{customdata[1]}}<extra></extra>",
            ))
            usage_fig.update_layout(title=f"{usage_label} · {usage_mode.lower()}", xaxis_title=f"{usage_label}{' (%)' if is_share else ''}", yaxis_title="", showlegend=False)
            usage_fig.update_yaxes(autorange="reversed")
            usage_fig.update_xaxes(range=[0, max(float(values.max()) * 1.22, 1)])
            st.plotly_chart(polish(usage_fig, 330), width="stretch", config={"displayModeBar": True, "displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]})

        with st.expander("Player & team details"):
            st.dataframe(comparison_details, hide_index=True, width="stretch", column_config={
                "Projection": st.column_config.NumberColumn("Median PPR", format="%.1f"),
                "Game total": "Game total",
            })

        common = ["player", "team", "next_opponent", "games_played", "season_ppr", "recent_ppr", "recent_opportunities"]
        position_stats = {
            "QB": ["ytd_attempts", "ytd_passing_yards", "ytd_passing_tds", "ytd_rushing_yards", "ytd_rushing_tds"],
            "RB": ["ytd_carries", "ytd_targets", "ytd_rushing_yards", "ytd_receiving_yards", "ytd_rushing_tds", "ytd_receiving_tds"],
            "WR": ["ytd_targets", "ytd_receptions", "ytd_receiving_yards", "ytd_receiving_tds"],
            "TE": ["ytd_targets", "ytd_receptions", "ytd_receiving_yards", "ytd_receiving_tds"],
        }
        with st.expander("Projection Breakdown"):
            st.markdown(
                '<div class="projection-scope">'
                '<div class="projection-scope-card included"><strong>Included in our calculation</strong><span>Current-season production, repeatable workload, fading prior-season influence, touchdown regression, and a capped matchup adjustment.</span></div>'
                '<div class="projection-scope-card informational"><strong>Informational only</strong><span>Injuries, practice, weather, snap share, pace, betting totals, personnel changes, and journalism help your decision but never change our ranking.</span></div>'
                '</div>',
                unsafe_allow_html=True,
            )

            def driver_direction(delta: float) -> tuple[str, str]:
                if delta > .25:
                    return "↑", "driver-positive"
                if delta < -.25:
                    return "↓", "driver-negative"
                return "—", "driver-neutral"

            driver_cards = []
            for _, driver_row in compare.iterrows():
                games = max(1, int(driver_row.get("games_played", 1)))
                if position == "QB":
                    ytd_opportunities = float(driver_row.get("ytd_attempts", 0) or 0) + float(driver_row.get("ytd_carries", 0) or 0)
                    workload_copy = "Recent passing and rushing workload supports the current signal."
                elif position == "RB":
                    ytd_opportunities = float(driver_row.get("ytd_carries", 0) or 0) + float(driver_row.get("ytd_targets", 0) or 0)
                    workload_copy = "Recent carry and target volume supports the projection."
                else:
                    ytd_opportunities = float(driver_row.get("ytd_targets", 0) or 0)
                    workload_copy = "Recent target volume supports the projection."
                opportunity_delta = float(driver_row.get("recent_opportunities", 0) or 0) - ytd_opportunities / games

                exact_weight = driver_row.get("projection_current_weight")
                if exact_weight is None or pd.isna(exact_weight):
                    current_weight = .40 if games <= 2 else .60 if games <= 6 else .75 if games <= 10 else .90
                else:
                    current_weight = float(exact_weight)
                history_remaining = max(0.0, 1 - current_weight)
                current_signal = driver_row.get("projection_current_signal")
                history_signal = driver_row.get("projection_history_signal")
                base_signal = driver_row.get("projection_base")
                history_delta = 0.0
                if all(value is not None and pd.notna(value) for value in (current_signal, history_signal, base_signal)):
                    history_delta = float(base_signal) - float(current_signal)

                td_adjustment = driver_row.get("projection_td_adjustment")
                has_exact_td = td_adjustment is not None and pd.notna(td_adjustment)
                td_delta = float(td_adjustment) if has_exact_td else 0.0

                matchup_factor = driver_row.get("projection_matchup_factor")
                if matchup_factor is None or pd.isna(matchup_factor):
                    matchup_factor = 1.03 if str(driver_row.get("matchup_label")) == "Favorable" else .97 if str(driver_row.get("matchup_label")) == "Tough" else 1.0
                matchup_base = float(base_signal) if base_signal is not None and pd.notna(base_signal) else float(driver_row["median_ppr"]) / max(float(matchup_factor), .01)
                matchup_delta = matchup_base * (float(matchup_factor) - 1)

                rows = [
                    ("Current-season production", f'{float(driver_row["season_ppr"]):.1f} PPR/G', 0.0, "The current season establishes the starting production baseline."),
                    ("Recent repeatable workload", f'{float(driver_row["recent_opportunities"]):.1f} opp/G', opportunity_delta, workload_copy),
                    ("Prior-season influence", f'{history_remaining:.0%} remains', history_delta, "Early-season sample keeps some prior-season influence; it fades as current games accumulate."),
                    ("Touchdown regression", f'{td_delta:+.1f} PPR' if has_exact_td else "Applied", td_delta, "Touchdown production is regressed toward a sustainable opportunity-based rate."),
                    ("Matchup adjustment", f'{matchup_delta:+.1f} PPR', matchup_delta, f'The {driver_row["next_opponent"]} adjustment is evidence-scaled and capped.'),
                ]
                driver_rows_html = ""
                for label, value, delta, explanation in rows:
                    symbol, direction_class = driver_direction(delta)
                    driver_rows_html += (
                        f'<div class="driver-row"><div class="driver-row-top"><span class="driver-label">{html.escape(label)}</span>'
                        f'<span class="driver-value"><span class="driver-direction {direction_class}">{symbol}</span>{html.escape(value)}</span></div>'
                        f'<div class="driver-explanation">{html.escape(explanation)}</div></div>'
                    )
                driver_rows_html += (
                    f'<div class="driver-row driver-final"><div class="driver-row-top"><span class="driver-label">Final median projection</span>'
                    f'<span class="driver-value">{float(driver_row["median_ppr"]):.1f} PPR</span></div>'
                    f'<div class="driver-explanation">Our central estimate before the game is played.</div></div>'
                )
                driver_cards.append(
                    f'<article class="driver-card"><div class="driver-card-head"><strong>{html.escape(str(driver_row["player"]))}</strong>'
                    f'<span>{html.escape(str(driver_row["team"]))} · {html.escape(str(driver_row["position"]))} · vs {html.escape(str(driver_row["next_opponent"]))}</span></div>{driver_rows_html}</article>'
                )
            st.markdown(f'<div class="driver-grid">{"".join(driver_cards)}</div>', unsafe_allow_html=True)
            st.caption("Arrows show whether a driver nudges the outlook up, leaves it essentially unchanged, or pulls it down. They do not represent separate point totals that should be added together.")

            if st.toggle("View detailed statistics", key=f"advanced_projection_stats_{position}"):
                stat_labels = {
                    "games_played": "Games played", "season_ppr": "Season PPR/G", "recent_ppr": "Recent PPR/G",
                    "recent_opportunities": "Last 3 opportunities/G", "ytd_attempts": "Pass attempts", "ytd_carries": "Carries",
                    "ytd_targets": "Targets", "ytd_receptions": "Receptions", "ytd_passing_yards": "Passing yards",
                    "ytd_rushing_yards": "Rushing yards", "ytd_receiving_yards": "Receiving yards", "ytd_passing_tds": "Passing TDs",
                    "ytd_rushing_tds": "Rushing TDs", "ytd_receiving_tds": "Receiving TDs", "matchup_label": "Matchup",
                    "points_allowed": "Opponent PPR allowed", "projected_ppr": "Median projection", "confidence": "Sample confidence",
                }
                decimal_stats = {"season_ppr", "recent_ppr", "recent_opportunities", "points_allowed", "projected_ppr"}
                advanced_cards = []
                advanced_columns = ["games_played", "season_ppr", "recent_ppr", "recent_opportunities", *position_stats[position], "matchup_label", "points_allowed", "projected_ppr", "confidence"]
                for _, stat_row in compare.iterrows():
                    stat_rows_html = ""
                    for stat_column in advanced_columns:
                        stat_value = stat_row.get(stat_column)
                        if stat_value is None or pd.isna(stat_value):
                            display_value = "—"
                        elif stat_column in decimal_stats:
                            display_value = f"{float(stat_value):.1f}"
                        elif isinstance(stat_value, (int, float)):
                            display_value = f"{float(stat_value):.0f}"
                        else:
                            display_value = str(stat_value)
                        stat_rows_html += f'<div class="advanced-stat-row"><span>{html.escape(stat_labels[stat_column])}</span><b>{html.escape(display_value)}</b></div>'
                    advanced_cards.append(
                        f'<article class="advanced-stat-card"><div class="advanced-stat-head"><strong>{html.escape(str(stat_row["player"]))}</strong>'
                        f'<span>{html.escape(str(stat_row["team"]))} · {html.escape(str(stat_row["position"]))} · vs {html.escape(str(stat_row["next_opponent"]))}</span></div>{stat_rows_html}</article>'
                    )
                st.markdown(f'<div class="advanced-stat-grid">{"".join(advanced_cards)}</div>', unsafe_allow_html=True)

        with st.expander("More matchup context"):
            st.caption("Additional live information for your final decision. None of these details changes our ranking.")
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
    st.caption(f"Season {season} data · app checks for a new validated snapshot every 5 minutes · this snapshot loaded {REFRESHED} · supplementary provider: {PROVIDER_STATUS}")
    st.subheader("Responsible use")
    st.markdown(DISCLAIMER_LANGUAGE)

st.divider()
with st.expander("Sources, methodology & important disclaimer"):
    st.markdown(SOURCE_ATTRIBUTION)
    st.markdown(METHODOLOGY_LANGUAGE)
    st.markdown(DISCLAIMER_LANGUAGE)
