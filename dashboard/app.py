"""Live weekly fantasy-football The Sunday Decision Lab."""

from __future__ import annotations

import base64
import html
import json
import os
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

try:
    from dashboard.providers.sportsdataio import context_freshness, format_injury_context
    from dashboard.outlooks import build_player_outlook, leader_margin
    from dashboard.injury_impact import apply_injury_scenario
    from dashboard.market_expectations import market_summary
    from dashboard.admin_refresh import authenticate as authenticate_refresh_admin, configured as admin_refresh_configured, refresh_status, trigger_refresh
    from dashboard.states import empty_player_pool_message, provider_issue_message
    from dashboard.methodology_copy import DISCLAIMER_LANGUAGE, METHODOLOGY_LANGUAGE, SOURCE_ATTRIBUTION
    from dashboard.presentation import eligible_positions, filter_player_search, matchup_summary, projected_team_total, role_summary, selection_availability_summary, team_logo_url, weather_summary
except ModuleNotFoundError:
    from providers.sportsdataio import context_freshness, format_injury_context
    from outlooks import build_player_outlook, leader_margin
    from injury_impact import apply_injury_scenario
    from market_expectations import market_summary
    from admin_refresh import authenticate as authenticate_refresh_admin, configured as admin_refresh_configured, refresh_status, trigger_refresh
    from states import empty_player_pool_message, provider_issue_message
    from methodology_copy import DISCLAIMER_LANGUAGE, METHODOLOGY_LANGUAGE, SOURCE_ATTRIBUTION
    from presentation import eligible_positions, filter_player_search, matchup_summary, projected_team_total, role_summary, selection_availability_summary, team_logo_url, weather_summary

try:
    from dashboard.data import current_nfl_season
except ModuleNotFoundError:
    from data import current_nfl_season


COLORS = {"QB": "#00529b", "RB": "#69be28", "WR": "#4b788f", "TE": "#a5acaf"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEASON = current_nfl_season()
BRAND_LOGO = PROJECT_ROOT / "dashboard" / "assets" / "sunday-decision-lab-logo.png"
BRAND_ICON = PROJECT_ROOT / "dashboard" / "assets" / "sunday-decision-lab-icon.png"
SNAPSHOT_BASE_URL = os.getenv(
    "SNAPSHOT_BASE_URL",
    "https://raw.githubusercontent.com/breckengalliher/fantasy-football-decision-lab/main/data/processed",
).rstrip("/")

st.set_page_config(page_title="The Sunday Decision Lab", page_icon=str(BRAND_ICON), layout="wide", initial_sidebar_state="auto")
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800&family=Bungee&family=Inter:wght@400;600;700;800&display=swap');
:root { --ink:#071b2c; --muted:#1b2730; --navy:#002244; --cream:#f3f6f7; --card:#ffffff; --line:#d7dde0; --teal:#397f18; --gold:#69be28; --action:#69be28; --wolf:#a5acaf; }
.stApp { background:var(--cream); color:var(--ink); font-family:'Inter',Arial,sans-serif; }
[data-testid="stMain"] [data-testid="stCaptionContainer"] { color:var(--ink); }
[data-testid="stSidebar"] { background:var(--navy); }
[data-testid="stSidebar"] * { color:#f7fafb; }
[data-testid="stSidebar"] [data-baseweb="select"] * { color:var(--ink) !important; }
[data-testid="stSidebar"] button[kind="secondary"] * { color:var(--ink) !important; }
.block-container { max-width:1440px; padding-top:.85rem; }
h1,h2,h3 { font-family:'Barlow Condensed','Arial Narrow',sans-serif; letter-spacing:-.01em; font-weight:800; }
.hero { display:flex; align-items:flex-end; justify-content:space-between; gap:2rem; padding:0; margin:0; }
.hero h1 { margin:.12rem 0 .18rem; font-size:2.55rem; line-height:1.02; }
.graffiti-title { font-family:'Bungee',Impact,sans-serif; color:var(--navy); letter-spacing:.015em !important; text-transform:uppercase; text-shadow:2px 2px 0 rgba(105,190,40,.28); }
.graffiti-title span { color:var(--gold); text-shadow:2px 2px 0 rgba(0,34,68,.22); }
.hero-subtitle { color:#397f18; font-size:.76rem; font-weight:850; letter-spacing:.13em; text-transform:uppercase; margin-bottom:.32rem; }
.sidebar-brand { font-family:'Bungee',Impact,sans-serif; color:#f7fafb; font-size:1.18rem; line-height:1.12; letter-spacing:.02em; margin:.15rem 0 .2rem; }
.sidebar-brand span { color:#9ee468; }
.sidebar-logo { text-align:center; margin:.1rem 0 .35rem; }
.sidebar-logo img { width:88px; height:88px; border-radius:22px; object-fit:cover; }
.header-logo { display:block; width:min(225px,100%); height:auto; margin:0; mix-blend-mode:multiply; }
.hero p { color:var(--muted); margin:0; max-width:720px; }
.eyebrow { color:#397f18; text-transform:uppercase; letter-spacing:.13em; font-size:.74rem; font-weight:800; }
.fresh { color:var(--muted); text-align:right; font-size:.78rem; white-space:nowrap; }
.app-header { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:1rem 1.15rem; margin-bottom:1rem; }
.header-details { max-width:720px; padding:.05rem 0; }
.header-details .eyebrow { margin-bottom:.14rem; }
.header-details .hero-subtitle { font-family:'Barlow Condensed','Arial Narrow',sans-serif; color:var(--navy); font-size:1.3rem; letter-spacing:.035em; margin-bottom:.08rem; }
.header-details p { color:var(--muted); margin:.08rem 0 .42rem; font-size:.8rem; line-height:1.35; }
.injury-impact-note { margin:.75rem 0 0; padding:.72rem .8rem; border-radius:10px; background:#f3f7ee; border-left:4px solid var(--gold); color:var(--ink); font-size:.76rem; line-height:1.45; }
.injury-impact-note summary { cursor:pointer; color:#397f18; font-weight:800; letter-spacing:.035em; list-style:none; }
.injury-impact-note summary::-webkit-details-marker { display:none; }
.injury-impact-note summary::after { content:'+'; float:right; font-size:1rem; }
.injury-impact-note[open] summary::after { content:'–'; }
.injury-impact-body { padding-top:.55rem; }
.injury-impact-range { display:block; margin-top:.35rem; font-weight:700; color:var(--navy); }
.market-note { margin:.65rem 0 0; padding:.68rem .78rem; border-radius:10px; background:#eef4f7; border-left:4px solid #4b788f; color:var(--ink); font-size:.74rem; line-height:1.42; }
.market-note summary { cursor:pointer; color:var(--navy); font-weight:800; letter-spacing:.025em; list-style:none; }
.market-note summary::-webkit-details-marker { display:none; }
.market-note summary::after { content:'+'; float:right; font-size:1rem; }
.market-note[open] summary::after { content:'–'; }
.market-note-body { padding-top:.5rem; }
.market-note-lines { display:block; margin-top:.28rem; font-weight:700; }
.market-note-meta { display:block; margin-top:.34rem; color:var(--muted); font-size:.67rem; }
.verdict.start .market-note { background:rgba(75,120,143,.2); border-left-color:#9fc5d8; color:#f4f8fa; }
.verdict.start .market-note summary { color:#bfe2f2; }
.verdict.start .market-note-meta { color:#c0c8cc; }
.settings-kicker { color:#397f18; font-size:.64rem; font-weight:850; letter-spacing:.1em; text-transform:uppercase; }
.status-dot { display:inline-block; width:.48rem; height:.48rem; border-radius:50%; background:var(--gold); }
[data-testid="stHorizontalBlock"]:has(.verdict) { align-items:stretch !important; }
[data-testid="stHorizontalBlock"]:has(.verdict) > [data-testid="stColumn"] { display:flex !important; }
[data-testid="stHorizontalBlock"]:has(.verdict) > [data-testid="stColumn"] > div,
[data-testid="stHorizontalBlock"]:has(.verdict) > [data-testid="stColumn"] [data-testid="stVerticalBlock"],
[data-testid="stHorizontalBlock"]:has(.verdict) > [data-testid="stColumn"] [data-testid="stElementContainer"],
[data-testid="stHorizontalBlock"]:has(.verdict) > [data-testid="stColumn"] [data-testid="stMarkdown"],
[data-testid="stHorizontalBlock"]:has(.verdict) > [data-testid="stColumn"] [data-testid="stMarkdown"] > div,
[data-testid="stHorizontalBlock"]:has(.verdict) > [data-testid="stColumn"] [data-testid="stMarkdownContainer"] { width:100%; height:100%; box-sizing:border-box; }
.verdict { background:#fbfcfc; color:var(--ink); border:1px solid #dfe4e6; border-radius:16px; padding:1.15rem 1.25rem; min-height:100%; height:100%; display:flex; flex-direction:column; box-sizing:border-box; }
.verdict.start { background:var(--navy); color:white; border-color:var(--gold); box-shadow:0 12px 28px rgba(0,34,68,.18); }
.verdict .tag { display:inline-block; background:#edf4e8; color:#397f18; border-radius:999px; padding:.28rem .52rem; letter-spacing:.12em; font-size:.67rem; font-weight:800; }
.verdict.start .tag { background:rgba(105,190,40,.16); color:#9ee468; }
.verdict .name { font-size:1.7rem; font-weight:750; margin:.65rem 0 .1rem; }
.player-heading { display:flex; align-items:center; gap:.75rem; margin:.65rem 0 .1rem; min-width:0; min-height:62px; }
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
.decision-edge { display:flex; align-items:center; justify-content:space-between; gap:1rem; background:var(--navy); color:#f7fafb; border:1px solid rgba(105,190,40,.65); border-radius:13px; padding:.68rem .9rem; margin:.55rem 0 .5rem; box-shadow:0 7px 18px rgba(0,34,68,.10); }
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
.game-detail-chips { display:flex; flex-wrap:wrap; align-content:flex-start; gap:.3rem; margin-top:.48rem; min-height:3.25rem; }
.game-detail-chip { display:inline-flex; align-items:center; min-height:1.45rem; border:1px solid #dce3e6; border-radius:999px; background:#f1f4f5; color:var(--muted); padding:.2rem .48rem; font-size:.61rem; font-weight:700; line-height:1.15; white-space:nowrap; }
.game-detail-chip.matchup { background:#edf4e8; border-color:#cfe0c5; color:#315f1e; }
.game-detail-chip.team-total { background:#eaf2f6; border-color:#ccdde5; color:var(--navy); }
.verdict.start .game-detail-chip { background:rgba(255,255,255,.08); border-color:rgba(255,255,255,.17); color:#dbe3e6; }
.verdict.start .game-detail-chip.matchup { background:rgba(105,190,40,.14); border-color:rgba(158,228,104,.28); color:#b7ed8e; }
.verdict.start .game-detail-chip.team-total { background:rgba(75,120,143,.28); border-color:rgba(191,226,242,.24); color:#d6ecf5; }
.comparison-relative-note { color:var(--muted); font-size:.7rem; line-height:1.4; margin:.45rem .1rem 0; font-style:italic; }
.card-outlook-details { border-top:1px solid #e3e8ea; margin-top:auto; padding-top:.22rem; }
.card-outlook-details summary { color:var(--navy); cursor:pointer; font-size:.74rem; font-weight:800; padding:.5rem .1rem .28rem; list-style-position:inside; }
.card-outlook-details summary:hover { color:#397f18; }
.card-outlook-full { color:var(--ink); font-size:.79rem; line-height:1.5; padding:.42rem .2rem .15rem; }
.analysis-detail-section { border-top:1px solid #e3e8ea; margin-top:.65rem; padding-top:.6rem; }
.analysis-detail-section strong { display:block; color:var(--navy); font-size:.68rem; letter-spacing:.055em; text-transform:uppercase; margin-bottom:.2rem; }
.analysis-detail-meta { display:block; color:var(--muted); font-size:.68rem; margin-top:.28rem; }
.verdict.start .card-outlook-details { border-top-color:rgba(255,255,255,.16); }
.verdict.start .card-outlook-details summary { color:#9ee468; }
.verdict.start .card-outlook-full { color:#e0e6e8; }
.verdict.start .analysis-detail-section { border-top-color:rgba(255,255,255,.16); }
.verdict.start .analysis-detail-section strong { color:#9ee468; }
.verdict.start .analysis-detail-meta { color:#c0c8cc; }
.reporting-sources { margin-top:.65rem; font-size:.72rem; color:var(--muted); line-height:1.35; }
.reporting-sources a { color:#397f18; font-weight:700; text-decoration:none; }
.verdict.start .reporting-sources { color:#c0c8cc; }
.verdict.start .reporting-sources a { color:#9ee468; }
.section-title { font-size:1.16rem; font-weight:750; margin:1.2rem 0 .1rem; }
.section-copy { color:var(--muted); font-size:.87rem; margin-bottom:.65rem; }
.note { border-left:4px solid var(--gold); background:#edf4e8; color:#183515; padding:.72rem .9rem; border-radius:8px; font-size:.84rem; margin-top:1rem; }
.warning { border-left:4px solid var(--gold); background:#eef5e9; color:#29451f; padding:.72rem .9rem; border-radius:8px; font-size:.84rem; margin:.85rem 0; }
.freshness-bar { display:flex; align-items:center; gap:.35rem; background:var(--card); border:1px solid var(--line); border-radius:11px; padding:.42rem .5rem; margin:.45rem 0 .55rem; overflow:hidden; }
.freshness-item { display:flex; align-items:center; gap:.28rem; min-width:0; padding:.08rem .5rem; border-right:1px solid #e3e8ea; color:var(--ink); font-size:.66rem; line-height:1.25; white-space:nowrap; }
.freshness-item:last-of-type { border-right:0; }
.freshness-item b { color:var(--muted); font-size:.56rem; font-weight:850; letter-spacing:.055em; text-transform:uppercase; }
.freshness-item.status-caution { color:#8a5a08; }
.freshness-reminder { margin-left:auto; color:var(--muted); font-size:.6rem; line-height:1.25; text-align:right; }
.freshness-alert { display:flex; align-items:center; gap:.42rem; border-left:3px solid #d39b29; background:#fbf6df; color:#76520d; border-radius:8px; padding:.48rem .65rem; margin:0 0 .55rem; font-size:.7rem; line-height:1.35; }
.player-finder { margin:.35rem 0 .8rem; }
.finder-copy { color:var(--muted); font-size:.78rem; margin:-.25rem 0 .55rem; }
.selected-player-name { font-size:.94rem; font-weight:750; line-height:1.2; margin-top:.2rem; }
.selected-player-meta { color:var(--muted); font-size:.72rem; line-height:1.3; }
.comparison-count { margin:.22rem 0 .35rem; font-size:.75rem; }
.compare-slot-kicker { color:#397f18; font-size:.57rem; font-weight:850; letter-spacing:.09em; text-transform:uppercase; margin-bottom:.3rem; }
.compare-slot-top { display:flex; align-items:center; gap:.55rem; min-height:48px; }
.compare-slot-top .player-photo { width:46px; height:46px; flex-basis:46px; }
.compare-slot-main { min-width:0; }
.compare-slot-name { color:var(--ink); font-size:.91rem; font-weight:800; line-height:1.12; overflow-wrap:anywhere; }
.compare-slot-team { display:flex; align-items:center; gap:.3rem; color:var(--muted); font-size:.66rem; margin-top:.14rem; }
.compare-slot-team img { width:1rem; height:1rem; object-fit:contain; }
.compare-slot-game { color:var(--muted); font-size:.65rem; line-height:1.25; margin-top:.34rem; }
.compare-slot-footer { display:flex; align-items:center; justify-content:space-between; gap:.4rem; border-top:1px solid #e4e8ea; margin-top:.4rem; padding-top:.38rem; }
.compare-slot-projection { color:var(--navy); font-size:.75rem; font-weight:800; }
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
.detail-card-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.75rem; margin:.2rem 0 .35rem; }
.detail-card { background:var(--card); border:1px solid var(--line); border-radius:13px; overflow:hidden; min-width:0; box-shadow:0 7px 18px rgba(0,34,68,.055); }
.detail-card-head { display:flex; align-items:center; gap:.58rem; padding:.72rem .78rem; background:var(--navy); border-bottom:3px solid var(--gold); }
.detail-card-head .player-photo { width:44px; height:44px; flex-basis:44px; border-width:1px; }
.detail-card-name { color:white; font-family:'Barlow Condensed','Arial Narrow',sans-serif; font-size:1.02rem; font-weight:800; line-height:1.05; overflow-wrap:anywhere; }
.detail-card-team { display:flex; align-items:center; gap:.3rem; color:#c7d2d8; font-size:.64rem; margin-top:.16rem; }
.detail-card-team img { width:1rem; height:1rem; object-fit:contain; }
.detail-card-status { margin-left:auto; border-radius:999px; padding:.25rem .42rem; background:#edf4e8; color:#397f18; font-size:.58rem; font-weight:800; text-align:center; line-height:1.15; }
.detail-card-status.alert { background:#fff0e6; color:#a33a13; }
.detail-card-body { padding:.35rem .78rem .72rem; }
.detail-card-row { display:flex; justify-content:space-between; align-items:flex-start; gap:.65rem; padding:.42rem 0; border-bottom:1px solid #e8ecee; font-size:.68rem; line-height:1.3; }
.detail-card-row:last-child { border-bottom:0; }
.detail-card-row span { color:var(--muted); font-weight:700; }
.detail-card-row b { color:var(--ink); text-align:right; font-weight:750; }
.detail-card-projection { display:grid; grid-template-columns:1fr auto; gap:.5rem; align-items:end; margin-top:.65rem; padding:.62rem .68rem; border-radius:9px; background:var(--navy); }
.detail-card-projection span { color:#c7d2d8; font-size:.59rem; text-transform:uppercase; letter-spacing:.06em; }
.detail-card-projection strong { color:#9ee468; font-size:1.35rem; line-height:1; }
.detail-card-projection small { display:block; color:#f7fafb; font-size:.62rem; margin-top:.15rem; }
.context-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.85rem; width:100%; }
.context-card { background:var(--card); border:1px solid var(--line); border-radius:14px; overflow:hidden; min-width:0; box-shadow:0 7px 18px rgba(0,34,68,.055); }
.context-card-head { display:flex; align-items:center; gap:.62rem; padding:.72rem .78rem; background:var(--navy); border-bottom:3px solid var(--gold); }
.context-card-head .player-photo { width:46px; height:46px; flex:0 0 46px; border-width:1px; border-color:#8da0aa; background-color:#173854; }
.context-card-name { color:white; font-family:'Barlow Condensed','Arial Narrow',sans-serif; font-size:1.08rem; font-weight:800; line-height:1.08; overflow-wrap:anywhere; }
.context-card-game { display:flex; align-items:center; gap:.3rem; color:#c7d2d8; font-size:.62rem; margin-top:.17rem; }
.context-card-game img { width:1rem; height:1rem; object-fit:contain; }
.context-card-body { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.48rem; padding:.68rem; }
.context-item { background:#f4f7f8; border:1px solid #e1e7e9; border-radius:9px; padding:.52rem .58rem; min-width:0; }
.context-item.wide { grid-column:1/-1; }
.context-label { color:#397f18; font-size:.56rem; font-weight:850; letter-spacing:.075em; text-transform:uppercase; line-height:1.2; margin-bottom:.15rem; }
.context-value { color:var(--ink); font-size:.69rem; font-weight:700; line-height:1.35; overflow-wrap:anywhere; }
.context-card-foot { display:flex; align-items:center; gap:.35rem; margin:0 .68rem .68rem; padding:.48rem .58rem; border-radius:8px; background:#edf4e8; color:#29451f; font-size:.64rem; line-height:1.3; }
.stPlotlyChart { background:var(--card); border:0; border-radius:12px; padding:.2rem; }
[data-baseweb="tab-list"] { gap:.32rem; background:#e6ecef; border-radius:12px; padding:.3rem; }
[data-baseweb="tab-list"] button { border-radius:8px; padding:.55rem .8rem; color:var(--ink); }
[data-baseweb="tab-list"] button[aria-selected="true"] { background:var(--navy); color:white; }
[data-baseweb="tab-highlight"] { display:none; }
[data-testid="stSegmentedControl"] { background:#e6ecef; border:1px solid #d4dde1; border-radius:12px; padding:.24rem; }
[data-testid="stSegmentedControl"] button { min-height:2.35rem; border-radius:9px !important; font-family:'Inter',Arial,sans-serif; font-weight:750; }
.tool-section-head { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin:1.15rem 0 .55rem; padding:.78rem .9rem; border:1px solid var(--line); border-left:4px solid var(--gold); border-radius:12px; background:var(--card); }
.tool-section-head strong { display:block; color:var(--navy); font-family:'Barlow Condensed','Arial Narrow',sans-serif; font-size:1.28rem; letter-spacing:.01em; }
.tool-section-head span { display:block; color:var(--muted); font-size:.7rem; margin-top:.08rem; line-height:1.35; }
.tool-section-badge { flex:0 0 auto; border-radius:999px; background:#edf4e8; color:#397f18 !important; padding:.34rem .58rem; font-size:.58rem !important; font-weight:850; letter-spacing:.055em; text-transform:uppercase; white-space:nowrap; }
.st-key-comparison_view [data-testid="stButtonGroup"], .st-key-deep_dive_view [data-testid="stButtonGroup"] { margin-bottom:.55rem; }
.st-key-comparison_view [role="radiogroup"], .st-key-deep_dive_view [role="radiogroup"] { display:grid !important; width:100%; gap:.32rem; padding:.34rem; border:1px solid #d4dcdf; border-radius:12px; background:#e8edef; box-sizing:border-box; }
.st-key-comparison_view [role="radiogroup"] { grid-template-columns:repeat(4,minmax(0,1fr)); }
.st-key-deep_dive_view [role="radiogroup"] { grid-template-columns:repeat(3,minmax(0,1fr)); }
.st-key-comparison_view button, .st-key-deep_dive_view button { width:100%; min-height:2.45rem; border:0 !important; border-radius:9px !important; background:transparent !important; color:var(--muted) !important; font-size:.72rem !important; font-weight:750 !important; box-shadow:none !important; }
.st-key-comparison_view button:hover, .st-key-deep_dive_view button:hover { background:#f8fafb !important; color:var(--navy) !important; }
.st-key-comparison_view button[aria-checked="true"], .st-key-deep_dive_view button[aria-checked="true"] { background:var(--navy) !important; color:#fff !important; box-shadow:0 4px 10px rgba(0,34,68,.18) !important; }
.st-key-comparison_view button[aria-checked="true"] p, .st-key-deep_dive_view button[aria-checked="true"] p { color:#fff !important; }
.usage-board { display:grid; gap:.58rem; margin:.7rem 0 .35rem; }
.usage-player { display:grid; grid-template-columns:minmax(180px,.8fr) minmax(220px,1.45fr) 92px; gap:.9rem; align-items:center; background:var(--card); border:1px solid var(--line); border-radius:13px; padding:.72rem .82rem; }
.usage-player.leader { border-color:var(--gold); box-shadow:0 7px 18px rgba(0,34,68,.08); }
.usage-identity { display:flex; align-items:center; gap:.62rem; min-width:0; }
.usage-identity .player-photo { width:46px; height:46px; flex-basis:46px; }
.usage-name { color:var(--ink); font-size:.82rem; font-weight:850; line-height:1.18; overflow-wrap:anywhere; }
.usage-team { display:flex; align-items:center; gap:.28rem; color:var(--muted); font-size:.65rem; margin-top:.16rem; }
.usage-team img { width:1rem; height:1rem; object-fit:contain; }
.usage-track-wrap { min-width:0; }
.usage-track { height:10px; border-radius:999px; background:#dfe5e7; overflow:hidden; }
.usage-fill { height:100%; border-radius:999px; background:var(--wolf); }
.usage-player.leader .usage-fill { background:linear-gradient(90deg,#397f18,var(--gold)); }
.usage-rank { color:var(--muted); font-size:.63rem; margin-top:.28rem; }
.usage-score { text-align:right; }
.usage-score strong { display:block; color:var(--navy); font-size:1.55rem; line-height:1; letter-spacing:-.03em; }
.usage-score span { color:var(--muted); font-size:.62rem; }
.usage-insight { border-left:4px solid var(--gold); background:#edf4e8; color:var(--ink); padding:.66rem .8rem; border-radius:9px; font-size:.75rem; line-height:1.4; margin-top:.65rem; }
.comparison-panel-head { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin:.72rem 0 .65rem; padding:.68rem .78rem; border:1px solid var(--line); border-radius:11px; background:var(--card); }
.comparison-panel-head h3 { margin:0; color:var(--navy); font-size:1.05rem; }
.comparison-panel-head p { margin:.12rem 0 0; color:var(--muted); font-size:.68rem; }
.panel-key { flex:0 0 auto; border-radius:999px; background:#eef2f3; color:var(--muted); padding:.3rem .5rem; font-size:.58rem; font-weight:800; white-space:nowrap; }
.panel-key { color:var(--muted); font-size:.62rem; white-space:nowrap; }
.projection-board,.form-board { display:grid; gap:.58rem; }
.projection-row,.form-row { display:grid; grid-template-columns:minmax(180px,.85fr) minmax(310px,1.55fr) 82px; align-items:center; gap:.9rem; padding:.72rem .82rem; background:var(--card); border:1px solid var(--line); border-radius:13px; }
.projection-row.preferred,.form-row.preferred { border-color:var(--action); box-shadow:0 7px 18px rgba(0,34,68,.07); }
.projection-lane { position:relative; height:38px; margin:0 .2rem; }
.projection-lane-base { position:absolute; top:16px; left:0; right:0; height:7px; border-radius:999px; background:#e0e6e8; }
.projection-lane-range { position:absolute; top:16px; height:7px; border-radius:999px; background:linear-gradient(90deg,#8b999f,#466574); }
.projection-lane-range::before,.projection-lane-range::after { content:""; position:absolute; top:-4px; width:2px; height:15px; background:#53666f; }
.projection-lane-range::before { left:0; }.projection-lane-range::after { right:0; }
.projection-dot { position:absolute; top:9px; width:21px; height:21px; border:3px solid white; border-radius:50%; background:var(--navy); box-shadow:0 1px 5px rgba(0,0,0,.22); transform:translateX(-50%); }
.projection-row.preferred .projection-dot { background:var(--action); }
.projection-labels { display:flex; justify-content:space-between; color:var(--muted); font-size:.6rem; margin-top:25px; }
.projection-score { text-align:right; }.projection-score strong { display:block; color:var(--navy); font-size:1.55rem; line-height:1; }.projection-score span { color:var(--muted); font-size:.62rem; }
.panel-insight { display:flex; align-items:center; gap:.65rem; margin-top:.65rem; padding:.62rem .75rem; border-radius:10px; background:#edf4e8; color:var(--ink); font-size:.72rem; }
.panel-insight b { color:#397f18; text-transform:uppercase; letter-spacing:.06em; font-size:.6rem; white-space:nowrap; }
.form-weeks { display:grid; grid-template-columns:repeat(4,minmax(45px,1fr)); gap:.38rem; }
.week-chip { text-align:center; border-radius:9px; background:#eef2f3; padding:.34rem .2rem; border:1px solid #e0e5e7; }
.week-chip span { display:block; color:var(--muted); font-size:.55rem; text-transform:uppercase; letter-spacing:.05em; }.week-chip strong { display:block; color:var(--navy); font-size:.82rem; margin-top:.05rem; }
.week-chip.high { background:#edf6e8; border-color:#b9d9a7; }.week-chip.low { background:#f7eee6; border-color:#e5c9ad; }
.trend-summary { text-align:right; }.trend-summary strong { display:block; font-size:.78rem; color:var(--navy); }.trend-summary span { display:block; color:var(--muted); font-size:.6rem; margin-top:.12rem; }
@media(max-width:1100px) {
  .context-grid { grid-template-columns:1fr; }
  .detail-card-grid { grid-template-columns:1fr; }
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
  .header-logo { width:min(170px,62vw); margin-bottom:.35rem; }
  .freshness-bar { flex-wrap:wrap; align-items:flex-start; }
  .freshness-item { flex:1 1 calc(50% - .35rem); border-right:0; padding:.18rem .3rem; white-space:normal; }
  .freshness-reminder { flex:1 0 100%; margin:0; padding:.18rem .3rem 0; text-align:left; border-top:1px solid #e3e8ea; }
  .driver-grid { grid-template-columns:1fr; }
  .advanced-stat-grid { grid-template-columns:1fr; }
  .usage-player { grid-template-columns:minmax(170px,.9fr) minmax(160px,1.1fr) 78px; }
  .projection-row,.form-row { grid-template-columns:minmax(165px,.8fr) minmax(230px,1.3fr) 72px; }
}
@media(max-width:520px) {
  div[data-baseweb="select"] > div { flex-wrap:wrap; }
  .freshness-item { flex-basis:100%; }
  .decision-edge { align-items:flex-start; flex-direction:column; }
  .projection-scope { grid-template-columns:1fr; }
  .usage-player { grid-template-columns:1fr 72px; }
  .usage-track-wrap { grid-column:1/-1; grid-row:2; }
  .comparison-panel-head { align-items:flex-start; flex-direction:column; gap:.25rem; }
  .projection-row,.form-row { grid-template-columns:1fr 68px; gap:.55rem; }
  .projection-lane,.form-weeks { grid-column:1/-1; grid-row:2; }
  .panel-insight { align-items:flex-start; flex-direction:column; gap:.2rem; }
  .tool-section-head { align-items:flex-start; }
  .tool-section-badge { display:none; }
  .st-key-comparison_view [role="radiogroup"] { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .st-key-deep_dive_view [role="radiogroup"] { grid-template-columns:1fr; }
}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=300, show_spinner=False)
def get_snapshot_metadata() -> dict:
    processed = PROJECT_ROOT / "data" / "processed"
    metadata_path = processed / "live_refresh_metadata.json"
    try:
        response = requests.get(f"{SNAPSHOT_BASE_URL}/live_refresh_metadata.json", timeout=12)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        if not metadata_path.exists():
            raise FileNotFoundError("A validated production snapshot has not been published.")
        return json.loads(metadata_path.read_text(encoding="utf-8"))


def _read_snapshot_parquet(filename: str) -> pd.DataFrame:
    try:
        response = requests.get(f"{SNAPSHOT_BASE_URL}/{filename}", timeout=20)
        response.raise_for_status()
        return pd.read_parquet(BytesIO(response.content))
    except (requests.RequestException, ValueError, OSError):
        path = PROJECT_ROOT / "data" / "processed" / filename
        if not path.exists():
            raise FileNotFoundError(f"Validated snapshot is missing: {filename}")
        return pd.read_parquet(path)


@st.cache_data(ttl=300, show_spinner=False)
def get_published_snapshot(season: int, passing_td_points: int) -> tuple[pd.DataFrame, pd.DataFrame, int, str, str, str | None, str]:
    metadata = get_snapshot_metadata()
    if int(metadata.get("season", -1)) != season or passing_td_points not in metadata.get("refreshed_qb_passing_td_formats", []):
        raise ValueError("The published snapshot does not match this season or scoring format.")
    board = _read_snapshot_parquet(f"live_start_sit_board_{passing_td_points}pt_current.parquet")
    weekly = _read_snapshot_parquet("live_weekly_current.parquet")
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
    st.markdown(
        f'<div class="sidebar-logo"><img src="data:image/png;base64,{base64.b64encode(BRAND_ICON.read_bytes()).decode("ascii")}" '
        'alt="The Sunday Decision Lab SDL logo"></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="sidebar-brand">THE SUNDAY <span>DECISION</span> LAB</div>', unsafe_allow_html=True)
    st.caption("Your weekly lineup call")
    page = st.radio("View", ["Decision Room", "Player Trends", "How It Works"], label_visibility="collapsed")
season = SEASON

header_metadata = get_snapshot_metadata()
header_week = int(header_metadata.get("next_week", 0))
header_checked = datetime.fromisoformat(str(header_metadata.get("refreshed_at", datetime.now(timezone.utc).isoformat())).replace("Z", "+00:00"))
header_age_minutes = max(0, int((datetime.now(timezone.utc) - header_checked.astimezone(timezone.utc)).total_seconds() // 60))
context_checked = datetime.fromisoformat(str(header_metadata.get("context_refreshed_at", header_metadata.get("sportsdataio_refreshed_at", header_checked.isoformat()))).replace("Z", "+00:00"))
context_age_minutes = max(0, int((datetime.now(timezone.utc) - context_checked.astimezone(timezone.utc)).total_seconds() // 60))

with st.container():
    header_left, header_right = st.columns([.48, 1.52], gap="medium", vertical_alignment="center")
    with header_left:
        brand_logo_uri = "data:image/png;base64," + base64.b64encode(BRAND_LOGO.read_bytes()).decode("ascii")
        st.markdown(
            f'<img class="header-logo" src="{brand_logo_uri}" alt="The Sunday Decision Lab logo">',
            unsafe_allow_html=True,
        )
    with header_right:
        st.markdown(
            f'<div class="header-details"><div class="eyebrow">Week {header_week} · {season} · Full PPR</div>'
            '<div class="hero-subtitle">Player Comparison</div>'
            '<p>Compare up to three players and make the final lineup call.</p>'
            '<div class="settings-kicker">QB passing touchdown scoring</div></div>',
            unsafe_allow_html=True,
        )
        qb_td_label = st.radio("QB passing touchdown scoring", ["4 points", "6 points"], horizontal=True, label_visibility="collapsed")
        QB_PASS_TD_POINTS = int(qb_td_label.split()[0])

try:
    with st.spinner("Updating weekly stats and matchups…"):
        BOARD, WEEKLY, NEXT_WEEK, REFRESHED, PROVIDER_STATUS, PROVIDER_REFRESHED_AT, INJURY_SOURCE_STATUS = get_published_snapshot(season, QB_PASS_TD_POINTS)
        BOARD = apply_injury_scenario(BOARD)
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
        if st.button("Check for latest updates", width="stretch"):
            st.cache_data.clear()
            st.rerun()
        st.caption("Loads the newest validated cloud snapshot. It does not call providers or consume API quota.")
        st.divider()
        if st.toggle("Admin refresh center", key="show_admin_refresh"):
            if not admin_refresh_configured():
                st.info("Admin controls will activate after the protected refresh password and GitHub workflow token are added to the production environment.")
            elif not st.session_state.get("refresh_admin_authenticated", False):
                admin_password = st.text_input("Admin password", type="password", key="refresh_admin_password")
                if st.button("Unlock refresh controls", width="stretch"):
                    if authenticate_refresh_admin(admin_password):
                        st.session_state["refresh_admin_authenticated"] = True
                        st.session_state["refresh_admin_password"] = ""
                        st.rerun()
                    else:
                        st.error("That admin password is not valid.")
            else:
                st.success("Admin controls unlocked")
                st.caption("Refreshes run in the cloud, reject overlapping jobs, and enforce a 15-minute cooldown.")
                refresh_actions = [
                    ("injuries", "Refresh injuries / practice"),
                    ("context", "Refresh live context"),
                    ("market", "Refresh market expectations"),
                    ("projections", "Recalculate projections"),
                    ("all", "Run everything"),
                ]
                for refresh_kind, refresh_label in refresh_actions:
                    if st.button(refresh_label, key=f"admin_refresh_{refresh_kind}", width="stretch"):
                        try:
                            st.session_state["admin_refresh_message"] = trigger_refresh(refresh_kind)
                            st.session_state["admin_refresh_kind"] = refresh_kind
                        except Exception:
                            st.session_state["admin_refresh_message"] = {"state": "error", "message": "The cloud refresh could not be requested. Confirm the protected GitHub token and try again."}
                message = st.session_state.get("admin_refresh_message")
                if message:
                    if message["state"] in {"requested", "already_running"}:
                        st.info(message["message"])
                    elif message["state"] == "cooldown":
                        st.warning(message["message"])
                    elif message["state"] == "error":
                        st.error(message["message"])
                if st.button("Check refresh progress", width="stretch"):
                    kind = st.session_state.get("admin_refresh_kind", "all")
                    try:
                        st.session_state["admin_refresh_message"] = refresh_status(kind)
                        st.rerun()
                    except Exception:
                        st.error("Refresh status is temporarily unavailable.")
                if st.button("Lock admin controls", width="stretch"):
                    st.session_state["refresh_admin_authenticated"] = False
                    st.rerun()

if page == "Decision Room":
    context_age_minutes, context_is_stale = context_freshness(PROVIDER_REFRESHED_AT)
    context_value = "Needs confirmation" if context_is_stale else "Current"
    context_detail = "Unavailable" if context_age_minutes is None else f"Checked {context_age_minutes} min ago"
    high_frequency_day = datetime.now().weekday() in {0, 3, 6}
    next_refresh_copy = "Game-window monitoring" if high_frequency_day else "6 AM / 5 PM Central"
    st.markdown(
        '<div class="freshness-bar">'
        f'<div class="freshness-item"><span class="status-dot"></span><b>Projections</b><span>{header_age_minutes}m ago</span></div>'
        f'<div class="freshness-item"><span class="status-dot"></span><b>Context</b><span>{context_age_minutes}m ago</span></div>'
        f'<div class="freshness-item{" status-caution" if context_is_stale else ""}"><span class="status-dot"></span><b>Weather / depth</b><span>{context_value} · {context_detail}</span></div>'
        f'<div class="freshness-item"><b>Next</b><span>{next_refresh_copy}</span></div>'
        '<div class="freshness-reminder">Confirm official inactives before kickoff.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    provider_issue = provider_issue_message(PROVIDER_STATUS)
    if provider_issue:
        st.warning(provider_issue)
    position = st.segmented_control("Position", ["QB", "RB", "WR", "TE", "FLEX"], default="WR")
    selected_positions = eligible_positions(position)
    pool = BOARD.loc[
        BOARD["position"].isin(selected_positions)
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

        st.markdown(f'<div class="comparison-count">Comparison lineup · {len(names)} of 3 slots filled</div>', unsafe_allow_html=True)
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

        preview_compare = pool.loc[pool["player"].isin(names)].sort_values("projected_ppr", ascending=False)
        if not preview_compare.empty:
            preview_leader = preview_compare.iloc[0]
            preview_spread = leader_margin(preview_compare["median_ppr"].tolist())
            if len(preview_compare) == 1:
                preview_title = f'{preview_leader["player"]} · {float(preview_leader["median_ppr"]):.1f} projected PPR'
                preview_copy = "Add another player to see the projected advantage."
                preview_badge = "1 player selected"
            else:
                preview_title = f'{preview_leader["player"]} leads by {preview_spread:.1f} PPR'
                preview_copy = "The projections are close—treat this as a lean." if preview_spread < 2.5 else "We see a meaningful projected advantage."
                preview_badge = "Close call" if preview_spread < 2.5 else "Clearer edge"
            st.markdown(
                '<div class="decision-edge">'
                f'<div class="decision-edge-main"><div class="decision-edge-label">Week {NEXT_WEEK} decision edge</div>'
                f'<div class="decision-edge-title">{html.escape(preview_title)}</div>'
                f'<div class="decision-edge-copy">{html.escape(preview_copy)}</div></div>'
                f'<div class="decision-edge-badge">{html.escape(preview_badge)}</div>'
                '</div>',
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
        projection_spread = leader_margin(compare["median_ppr"].tolist())
        if len(compare) == 1:
            edge_title = f'{leader["player"]} · {float(leader["median_ppr"]):.1f} projected PPR'
            edge_copy = "Add another player to see the projected advantage."
            edge_badge = "1 player selected"
        else:
            edge_title = f'{leader["player"]} leads by {projection_spread:.1f} PPR'
            edge_copy = "The projections are close—treat this as a lean and use the live context below to make your final call." if projection_spread < 2.5 else "We see a meaningful projected advantage, with live context below for your final decision."
            edge_badge = "Close call" if projection_spread < 2.5 else "Clearer edge"
        st.markdown('<div class="section-title">Start / Sit verdict</div><div class="section-copy">We build this ranking from current production, repeatable workload, a fading prior-season anchor, touchdown regression, and a sample-scaled matchup adjustment. When an active injury matters, an optional injury-adjusted outlook appears directly on that player’s card.</div>', unsafe_allow_html=True)
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
                game_detail_chips = []
                team_record = row.get("team_record")
                if team_record is not None and pd.notna(team_record) and str(team_record).strip():
                    game_detail_chips.append((f'{row.get("team")} {team_record}', "record"))
                game_detail_chips.append((f'{row.get("venue")} vs {row.get("next_opponent")}', "matchup"))
                kickoff = " · ".join(str(row.get(value)) for value in ("weekday", "gametime") if row.get(value) is not None and pd.notna(row.get(value)))
                if kickoff:
                    game_detail_chips.append((kickoff, "kickoff"))
                betting_total = row.get("betting_total_live")
                if betting_total is None or pd.isna(betting_total):
                    betting_total = row.get("total_line")
                if betting_total is not None and pd.notna(betting_total):
                    game_detail_chips.append((f'Game {float(betting_total):.1f}', "game-total"))
                team_total = projected_team_total(row)
                if team_total is not None:
                    game_detail_chips.append((f'Team {team_total:.1f}', "team-total"))
                game_chips = "".join(
                    f'<span class="game-detail-chip {chip_class}">{html.escape(label)}</span>'
                    for label, chip_class in game_detail_chips
                )
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
                injury_note = ""
                baseline = float(row.get("baseline_median_ppr", median))
                adjusted = float(row.get("injury_adjusted_median_ppr", baseline))
                adjusted_floor = float(row.get("injury_adjusted_floor_ppr", floor))
                adjusted_ceiling = float(row.get("injury_adjusted_ceiling_ppr", ceiling))
                delta = adjusted - baseline
                risk = str(row.get("injury_risk_label", "No adjustment"))
                teammate_effect = str(row.get("injury_teammate_effect", "") or "").strip()
                if risk == "No adjustment" and abs(delta) < 0.10:
                    teammate_effect = ""
                if risk != "No adjustment" or teammate_effect:
                    impact_parts = []
                    if risk != "No adjustment":
                        impact_parts.append(str(row.get("injury_impact_summary", "")))
                        impact_parts.append(str(row.get("injury_recovery_outlook", "")))
                    if teammate_effect:
                        impact_parts.append(teammate_effect)
                    impact_label = f"Injury impact · {risk}" if risk != "No adjustment" else "Team opportunity shift"
                    injury_note = (
                        f'<div class="analysis-detail-section"><strong>{html.escape(impact_label)} · {adjusted:.1f} PPR ({delta:+.1f})</strong>'
                        f'{html.escape(" ".join(part for part in impact_parts if part))}'
                        f'<span class="analysis-detail-meta">Adjusted range: {adjusted_floor:.1f}–{adjusted_ceiling:.1f} PPR</span></div>'
                    )
                market_note = ""
                market_value = row.get("market_implied_ppr")
                if market_value is not None and pd.notna(market_value):
                    market_value = float(market_value)
                    market_delta = market_value - median
                    market_lines = market_summary(row)
                    book_count = row.get("market_book_count")
                    book_text = ""
                    if book_count is not None and pd.notna(book_count):
                        count = int(book_count)
                        book_text = f"Median across {count} sportsbook{'s' if count != 1 else ''}. "
                    updated = row.get("market_updated_at")
                    updated_text = f"Last line update: {updated}." if updated is not None and pd.notna(updated) else ""
                    comparison = "above" if market_delta > .05 else "below" if market_delta < -.05 else "in line with"
                    market_note = (
                        f'<div class="analysis-detail-section"><strong>Market expectation · {market_value:.1f} PPR ({market_delta:+.1f})</strong>'
                        f'The market-implied total is {comparison} our {median:.1f} PPR projection. '
                        f'This is supplemental and does not change the Start/Sit ranking.'
                        f'{f"<span class=\"market-note-lines\">{html.escape(market_lines)}</span>" if market_lines else ""}'
                        f'<span class="analysis-detail-meta">{html.escape(book_text + updated_text)}</span></div>'
                    )
                outlook_details = (
                    f'<details class="card-outlook-details"><summary>Full player analysis</summary><div class="card-outlook-full">'
                    f'{html.escape(full_reason)}{injury_note}{market_note}{reporting_links}</div></details>'
                )
                st.markdown(
                    f'<div class="verdict {card_class}"><div style="display:flex;align-items:center;gap:.45rem"><div class="tag">{verdict}</div><div class="confidence-label">{edge_confidence}</div></div><div class="player-heading">{photo}<div class="name">{html.escape(str(row["player"]))}</div></div>'
                    f'<div class="opponent team-line">{logo}<span>{html.escape(player_details)}</span></div>'
                    f'<div class="game-detail-chips">{game_chips}</div>'
                    f'<div class="projection-primary"><strong>{median:.1f}</strong><span>projected PPR <span class="range-help" tabindex="0" aria-label="Range definition">i<span class="range-tooltip" role="tooltip">Floor is the P10 downside outcome, projection is the median estimate, and ceiling is the P90 upside outcome. About 80% of results should fall between floor and ceiling.</span></span></span></div>'
                    f'<div class="range-track"><span class="range-marker" style="left:{median_position:.1f}%"></span></div><div class="range-labels"><span>Floor {floor:.1f}</span><span>Ceiling {ceiling:.1f}</span></div>'
                    f'<div class="outlook-label">Player outlook</div><div class="reason">{html.escape(reason)}</div><div class="broadcast-context">{quick_context}</div>'
                    f'{outlook_details}</div>',
                    unsafe_allow_html=True,
                )

        if len(compare) > 1:
            st.markdown(
                '<div class="comparison-relative-note">“Sit” is relative to the other selected players—not an automatic bench recommendation in every league.</div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<div class="tool-section-head"><div><strong>Comparison Tool</strong><span>Compare projection range, weekly form, repeatable usage, and supplemental market expectations.</span></div><span class="tool-section-badge">4 comparison views</span></div>',
            unsafe_allow_html=True,
        )
        comparison_view = st.segmented_control(
            "Comparison view", ["Projection", "Weekly form", "Usage", "Market"],
            default="Projection", width="stretch", label_visibility="collapsed",
            key="comparison_view",
        )
        if comparison_view == "Projection":
            range_min = max(0.0, float(compare["floor_ppr"].min()) - 2.0)
            range_max = float(compare["ceiling_ppr"].max()) + 2.0
            range_span = max(range_max - range_min, 1.0)
            projection_rows = []
            for _, range_row in compare.iterrows():
                floor = float(range_row["floor_ppr"])
                median = float(range_row["median_ppr"])
                ceiling = float(range_row["ceiling_ppr"])
                left = (floor - range_min) / range_span * 100
                width = (ceiling - floor) / range_span * 100
                dot = (median - range_min) / range_span * 100
                photo = player_photo_html(range_row.get("headshot_url"), range_row["player"])
                logo_url = team_logo_url(range_row.get("team"))
                logo = f'<img src="{html.escape(logo_url, quote=True)}" alt="{html.escape(str(range_row["team"]), quote=True)} logo">' if logo_url else ""
                identity = (
                    f'<div class="usage-identity">{photo}<div><div class="usage-name">{html.escape(str(range_row["player"]))}</div>'
                    f'<div class="usage-team">{logo}<span>{html.escape(str(range_row["team"]))} · {html.escape(str(range_row.get("position", position)))} vs {html.escape(str(range_row["next_opponent"]))}</span></div></div></div>'
                )
                projection_rows.append(
                    f'<article class="projection-row{" preferred" if range_row["player"] == leader["player"] else ""}">{identity}'
                    f'<div class="projection-lane" title="Floor is the downside estimate, projection is the median, and ceiling is the upside estimate.">'
                    f'<div class="projection-lane-base"></div><div class="projection-lane-range" style="left:{left:.1f}%;width:{width:.1f}%"></div>'
                    f'<div class="projection-dot" style="left:{dot:.1f}%"></div><div class="projection-labels"><span>Floor {floor:.1f}</span><span>Ceiling {ceiling:.1f}</span></div></div>'
                    f'<div class="projection-score"><strong>{median:.1f}</strong><span>Projected PPR</span></div></article>'
                )
            overlap = max(0.0, min(compare["ceiling_ppr"]) - max(compare["floor_ppr"]))
            range_insight = f'{leader["player"]} leads by {projection_spread:.1f} PPR. The ranges overlap by {overlap:.1f}, so this is {"a close lean" if projection_spread < 2.5 else "a meaningful edge"}.'
            st.markdown(
                f'<div class="comparison-panel-head"><div><h3>Week {NEXT_WEEK} Projection</h3><p>Floor, median projection, and ceiling shown together.</p></div><div class="panel-key">Floor ← range → Ceiling</div></div>'
                f'<div class="projection-board">{"".join(projection_rows)}</div><div class="panel-insight"><b>Quick read</b><span>{html.escape(range_insight)}</span></div>',
                unsafe_allow_html=True,
            )

        if comparison_view == "Weekly form":
            weekly_name_column = "player_display_name" if "player_display_name" in WEEKLY.columns else "player_name"
            trend_history = WEEKLY.loc[WEEKLY[weekly_name_column].isin(compare["player"])].copy()
            if trend_history.empty:
                st.info("Weekly production history is temporarily unavailable for these players.")
            else:
                trend_history["display_ppr"] = pd.to_numeric(trend_history["fantasy_points_ppr"], errors="coerce")
                if position == "QB" and QB_PASS_TD_POINTS != 4 and "passing_tds" in trend_history:
                    trend_history["display_ppr"] += (QB_PASS_TD_POINTS - 4) * pd.to_numeric(trend_history["passing_tds"], errors="coerce").fillna(0)
                form_rows = []
                recent_leaders = []
                displayed_weeks = sorted(pd.to_numeric(trend_history["week"], errors="coerce").dropna().astype(int).unique().tolist())
                max_weeks = max(len(displayed_weeks), 1)
                for _, form_player in compare.iterrows():
                    player_name = form_player["player"]
                    player_history = trend_history.loc[trend_history[weekly_name_column].eq(player_name)].sort_values("week")
                    scores = player_history["display_ppr"].dropna().tolist()
                    recent_average = sum(scores[-2:]) / max(len(scores[-2:]), 1)
                    recent_leaders.append((recent_average, player_name))
                    chips = []
                    history_by_week = {int(game["week"]): game for _, game in player_history.iterrows()}
                    for week_number in displayed_weeks:
                        game = history_by_week.get(week_number)
                        if game is None:
                            chips.append(f'<div class="week-chip" title="No recorded game"><span>W{week_number}</span><strong>—</strong></div>')
                            continue
                        score = float(game["display_ppr"])
                        chip_class = " high" if score >= 25 else " low" if score < 15 else ""
                        opponent = game.get("opponent_team")
                        opponent_text = f' vs {opponent}' if opponent is not None and pd.notna(opponent) else ""
                        chips.append(f'<div class="week-chip{chip_class}" title="Week {week_number}{html.escape(opponent_text)}"><span>W{week_number}</span><strong>{score:.1f}</strong></div>')
                    photo = player_photo_html(form_player.get("headshot_url"), player_name)
                    logo_url = team_logo_url(form_player.get("team"))
                    logo = f'<img src="{html.escape(logo_url, quote=True)}" alt="{html.escape(str(form_player["team"]), quote=True)} logo">' if logo_url else ""
                    identity = (
                        f'<div class="usage-identity">{photo}<div><div class="usage-name">{html.escape(str(player_name))}</div>'
                        f'<div class="usage-team">{logo}<span>{html.escape(str(form_player["team"]))} · {html.escape(str(form_player.get("position", position)))}</span></div></div></div>'
                    )
                    if len(scores) >= 2:
                        change = scores[-1] - scores[-2]
                        trend_word = "Trending up" if change > 2 else "Trending down" if change < -2 else "Holding steady"
                        trend_detail = f'{change:+.1f} from prior game'
                    else:
                        trend_word, trend_detail = "Early sample", "One result available"
                    form_rows.append(
                        f'<article class="form-row{" preferred" if player_name == leader["player"] else ""}">{identity}'
                        f'<div class="form-weeks" style="grid-template-columns:repeat({max_weeks},minmax(45px,1fr))">{"".join(chips)}</div>'
                        f'<div class="trend-summary"><strong>{html.escape(trend_word)}</strong><span>{html.escape(trend_detail)}</span></div></article>'
                    )
                recent_leaders.sort(reverse=True)
                form_insight = f'{recent_leaders[0][1]} has the strongest two-game form at {recent_leaders[0][0]:.1f} PPR per game.'
                st.markdown(
                    f'<div class="comparison-panel-head"><div><h3>Weekly Form</h3><p>Every current-season result, with recent direction at a glance.</p></div><div class="panel-key">Green 25+ · Orange under 15</div></div>'
                    f'<div class="form-board">{"".join(form_rows)}</div><div class="panel-insight"><b>Quick read</b><span>{html.escape(form_insight)}</span></div>',
                    unsafe_allow_html=True,
                )

        if comparison_view == "Usage":
            metric_options = {
                "QB": {"Pass attempts": "ytd_attempts", "Passing yards": "ytd_passing_yards", "Passing TDs": "ytd_passing_tds", "Carries": "ytd_carries", "Rushing yards": "ytd_rushing_yards"},
                "RB": {"Carries": "ytd_carries", "Targets": "ytd_targets", "Rushing yards": "ytd_rushing_yards", "Receiving yards": "ytd_receiving_yards", "Total touchdowns": "ytd_total_tds"},
                "WR": {"Targets": "ytd_targets", "Receptions": "ytd_receptions", "Receiving yards": "ytd_receiving_yards", "Receiving TDs": "ytd_receiving_tds", "Snap share": "latest_snap_pct"},
                "TE": {"Targets": "ytd_targets", "Receptions": "ytd_receptions", "Receiving yards": "ytd_receiving_yards", "Receiving TDs": "ytd_receiving_tds", "Snap share": "latest_snap_pct"},
                "FLEX": {"Opportunities": "recent_opportunities", "Carries": "ytd_carries", "Targets": "ytd_targets", "Receptions": "ytd_receptions", "Rushing yards": "ytd_rushing_yards", "Receiving yards": "ytd_receiving_yards", "Total touchdowns": "ytd_total_tds"},
            }[position]
            usage_left, usage_right = st.columns([1, 1])
            usage_label = usage_left.selectbox("Statistic", list(metric_options), key=f"comparison_usage_metric_{position}")
            usage_mode = usage_right.radio("Display", ["Per game", "Season total"], horizontal=True, key=f"comparison_usage_mode_{position}")
            usage_column = metric_options[usage_label]
            usage_values = compare.copy()
            if usage_column == "recent_opportunities":
                usage_mode = "Per game"
            elif usage_column == "ytd_total_tds":
                usage_values[usage_column] = usage_values.get("ytd_rushing_tds", 0) + usage_values.get("ytd_receiving_tds", 0)
            values = pd.to_numeric(usage_values.get(usage_column, pd.Series(0, index=usage_values.index)), errors="coerce").fillna(0)
            is_share = usage_column == "latest_snap_pct"
            if is_share:
                values = values * 100
                usage_mode = "Latest week"
            elif usage_mode == "Per game" and usage_column != "recent_opportunities":
                values = values / pd.to_numeric(usage_values["games_played"], errors="coerce").clip(lower=1)
            usage_values["display_value"] = values
            ranked_usage = usage_values.sort_values(["display_value", "player"], ascending=[False, True]).reset_index(drop=True)
            max_value = max(float(ranked_usage["display_value"].max()), 1.0)
            usage_rows = []
            ordinal = {1: "1st", 2: "2nd", 3: "3rd"}
            for rank, (_, usage_row) in enumerate(ranked_usage.iterrows(), start=1):
                value = float(usage_row["display_value"])
                width = max(4.0, min(100.0, value / max_value * 100))
                photo = player_photo_html(usage_row.get("headshot_url"), usage_row["player"])
                logo_url = team_logo_url(usage_row.get("team"))
                logo = (
                    f'<img src="{html.escape(logo_url, quote=True)}" alt="{html.escape(str(usage_row["team"]), quote=True)} logo">'
                    if logo_url else ""
                )
                game_detail = f'{usage_row.get("position", position)} · {usage_row["team"]} vs {usage_row["next_opponent"]}'
                display_value = f"{value:.1f}{'%' if is_share else ''}"
                usage_rows.append(
                    f'<article class="usage-player{" leader" if rank == 1 else ""}">'
                    f'<div class="usage-identity">{photo}<div><div class="usage-name">{html.escape(str(usage_row["player"]))}</div>'
                    f'<div class="usage-team">{logo}<span>{html.escape(game_detail)}</span></div></div></div>'
                    f'<div class="usage-track-wrap"><div class="usage-track"><div class="usage-fill" style="width:{width:.1f}%"></div></div>'
                    f'<div class="usage-rank">{ordinal.get(rank, f"#{rank}")} of {len(ranked_usage)} · {html.escape(usage_label.lower())}</div></div>'
                    f'<div class="usage-score"><strong>{display_value}</strong><span>{html.escape(usage_mode)}</span></div></article>'
                )
            leader_usage = ranked_usage.iloc[0]
            if len(ranked_usage) > 1:
                runner_up = ranked_usage.iloc[1]
                gap = float(leader_usage["display_value"] - runner_up["display_value"])
                if gap < 0.05:
                    insight = f'{leader_usage["player"]} and {runner_up["player"]} are essentially tied in {usage_label.lower()}.'
                else:
                    suffix = " percentage points" if is_share else ""
                    insight = f'{leader_usage["player"]} leads this comparison by {gap:.1f}{suffix} in {usage_label.lower()} ({usage_mode.lower()}).'
            else:
                insight = f'{leader_usage["player"]} is shown at {float(leader_usage["display_value"]):.1f}{"%" if is_share else ""} for {usage_label.lower()}.'
            st.markdown(
                f'<div class="usage-board">{"".join(usage_rows)}</div><div class="usage-insight"><b>Quick read</b><span>{html.escape(insight)}</span></div>',
                unsafe_allow_html=True,
            )

        if comparison_view == "Market":
            market_rows = []
            available_count = 0
            for _, market_row in compare.iterrows():
                market_value = market_row.get("market_implied_ppr")
                photo = player_photo_html(market_row.get("headshot_url"), market_row["player"])
                logo_url = team_logo_url(market_row.get("team"))
                logo = f'<img src="{html.escape(logo_url, quote=True)}" alt="{html.escape(str(market_row["team"]), quote=True)} logo">' if logo_url else ""
                identity = (
                    f'<div class="usage-identity">{photo}<div><div class="usage-name">{html.escape(str(market_row["player"]))}</div>'
                    f'<div class="usage-team">{logo}<span>{html.escape(str(market_row["team"]))} · {html.escape(str(market_row.get("position", position)))} vs {html.escape(str(market_row["next_opponent"]))}</span></div></div></div>'
                )
                if market_value is None or pd.isna(market_value):
                    market_rows.append(
                        f'<article class="usage-player">{identity}<div class="usage-track-wrap"><div class="usage-rank">No validated player props are currently available. Missing or suspended lines are never treated as zero.</div></div><div class="usage-score"><strong>—</strong><span>Market PPR</span></div></article>'
                    )
                    continue
                available_count += 1
                market_value = float(market_value)
                model_value = float(market_row["median_ppr"])
                delta = market_value - model_value
                lines = market_summary(market_row)
                market_rows.append(
                    f'<article class="usage-player">{identity}<div class="usage-track-wrap"><div class="usage-rank">{html.escape(lines)}</div><div class="usage-rank">Our projection: {model_value:.1f} · difference: {delta:+.1f} PPR</div></div><div class="usage-score"><strong>{market_value:.1f}</strong><span>Market PPR</span></div></article>'
                )
            market_insight = (
                f"Validated player-prop expectations are available for {available_count} of {len(compare)} selected players."
                if available_count else
                "Sportsbooks usually publish most NFL player props 72–96 hours before kickoff. Check again closer to game time."
            )
            st.markdown(
                f'<div class="comparison-panel-head"><div><h3>Market Expectations</h3><p>Consensus receiving, rushing and passing lines translated to the selected fantasy scoring format.</p></div><div class="panel-key">Supplemental only</div></div>'
                f'<div class="usage-board">{"".join(market_rows)}</div><div class="usage-insight"><b>Important</b><span>{html.escape(market_insight)} These values never change our ranking.</span></div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<div class="tool-section-head"><div><strong>Deep Dive</strong><span>Explore the player profile, projection logic, and live matchup context behind the decision.</span></div><span class="tool-section-badge">3 analysis lenses</span></div>',
            unsafe_allow_html=True,
        )
        deep_dive_view = st.segmented_control(
            "Deep dive view", ["Player details", "Projection drivers", "Matchup context"],
            default="Player details", width="stretch", label_visibility="collapsed",
            key="deep_dive_view",
        )
        if deep_dive_view == "Player details":
            detail_cards = []
            for _, detail_row in compare.iterrows():
                detail_total = detail_row.get("betting_total_live")
                if detail_total is None or pd.isna(detail_total):
                    detail_total = detail_row.get("total_line")
                availability = selection_availability_summary(detail_row)
                availability_alert = any(label in availability.casefold() for label in ("questionable", "doubtful", "out", "inactive", "ir", "pup"))
                kickoff = " · ".join(
                    str(detail_row.get(value)) for value in ("weekday", "gametime")
                    if detail_row.get(value) is not None and pd.notna(detail_row.get(value))
                ) or "TBD"
                team_record = detail_row.get("team_record") if pd.notna(detail_row.get("team_record")) else "—"
                photo = player_photo_html(detail_row.get("headshot_url"), detail_row["player"])
                logo_url = team_logo_url(detail_row.get("team"))
                logo = f'<img src="{html.escape(logo_url, quote=True)}" alt="{html.escape(str(detail_row["team"]), quote=True)} logo">' if logo_url else ""
                game_total = f"{float(detail_total):.1f} points" if detail_total is not None and pd.notna(detail_total) else "Not available"
                detail_team_total = projected_team_total(detail_row)
                team_total = f"{detail_team_total:.1f} points" if detail_team_total is not None else "Not available"
                detail_cards.append(
                    f'<article class="detail-card"><div class="detail-card-head">{photo}<div><div class="detail-card-name">{html.escape(str(detail_row["player"]))}</div>'
                    f'<div class="detail-card-team">{logo}<span>{html.escape(str(detail_row["team"]))} · {html.escape(str(detail_row.get("position", position)))}</span></div></div>'
                    f'<div class="detail-card-status{" alert" if availability_alert else ""}">{html.escape(availability)}</div></div>'
                    f'<div class="detail-card-body"><div class="detail-card-row"><span>Matchup</span><b>{html.escape(str(detail_row["venue"]))} vs {html.escape(str(detail_row["next_opponent"]))}</b></div>'
                    f'<div class="detail-card-row"><span>Kickoff</span><b>{html.escape(kickoff)}</b></div>'
                    f'<div class="detail-card-row"><span>Team record</span><b>{html.escape(str(team_record))}</b></div>'
                    f'<div class="detail-card-row"><span>Game total</span><b>{html.escape(game_total)}</b></div>'
                    f'<div class="detail-card-row"><span>Projected team total</span><b>{html.escape(team_total)}</b></div>'
                    f'<div class="detail-card-projection"><div><span>Floor–ceiling</span><small>{float(detail_row["floor_ppr"]):.1f}–{float(detail_row["ceiling_ppr"]):.1f} PPR</small></div>'
                    f'<div><span>Median</span><strong>{float(detail_row["median_ppr"]):.1f}</strong></div></div></div></article>'
                )
            st.markdown(f'<div class="detail-card-grid">{"".join(detail_cards)}</div>', unsafe_allow_html=True)

        common = ["player", "team", "next_opponent", "games_played", "season_ppr", "recent_ppr", "recent_opportunities"]
        position_stats = {
            "QB": ["ytd_attempts", "ytd_passing_yards", "ytd_passing_tds", "ytd_rushing_yards", "ytd_rushing_tds"],
            "RB": ["ytd_carries", "ytd_targets", "ytd_rushing_yards", "ytd_receiving_yards", "ytd_rushing_tds", "ytd_receiving_tds"],
            "WR": ["ytd_targets", "ytd_receptions", "ytd_receiving_yards", "ytd_receiving_tds"],
            "TE": ["ytd_targets", "ytd_receptions", "ytd_receiving_yards", "ytd_receiving_tds"],
            "FLEX": ["ytd_carries", "ytd_targets", "ytd_receptions", "ytd_rushing_yards", "ytd_receiving_yards", "ytd_rushing_tds", "ytd_receiving_tds"],
        }
        if deep_dive_view == "Projection drivers":
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
                player_position = str(driver_row.get("position", position))
                limited_sample = bool(driver_row.get("limited_sample_role", False))
                games_played = int(driver_row.get("games_played", 0) or 0)
                games = max(1, games_played)
                if player_position == "QB":
                    ytd_opportunities = float(driver_row.get("ytd_attempts", 0) or 0) + float(driver_row.get("ytd_carries", 0) or 0)
                    workload_copy = "Recent passing and rushing workload supports the current signal."
                elif player_position == "RB":
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

                if limited_sample:
                    depth_position = str(driver_row.get("depth_position_live", player_position))
                    depth_order = driver_row.get("depth_order_live")
                    role_label = f'{depth_position}{int(depth_order)}' if depth_order is not None and pd.notna(depth_order) else "Verified role"
                    rows = [
                        ("Verified depth-chart role", role_label, 0.0, "The live depth chart confirms a fantasy-relevant offensive role."),
                        ("Current-season sample", "0 games", 0.0, "No usable game sample is available yet, so we do not manufacture recent production."),
                        ("Position / role baseline", f'{float(driver_row["median_ppr"]):.1f} PPR', 0.0, "Comparable current-season players provide a conservative starting estimate."),
                        ("Outcome uncertainty", "Wider range", 0.0, "The floor-to-ceiling range is intentionally wider until real usage arrives."),
                        ("Matchup adjustment", "Neutral", 0.0, "We wait for real workload evidence before applying a player-specific matchup adjustment."),
                    ]
                else:
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
                    "schedule_adjusted_index": "Schedule-adjusted matchup", "projected_ppr": "Median projection", "confidence": "Sample confidence",
                }
                decimal_stats = {"season_ppr", "recent_ppr", "recent_opportunities", "projected_ppr"}
                advanced_cards = []
                advanced_columns = ["games_played", "season_ppr", "recent_ppr", "recent_opportunities", *position_stats[position], "matchup_label", "schedule_adjusted_index", "projected_ppr", "confidence"]
                for _, stat_row in compare.iterrows():
                    stat_rows_html = ""
                    for stat_column in advanced_columns:
                        stat_value = stat_row.get(stat_column)
                        if stat_column == "schedule_adjusted_index":
                            display_value = matchup_summary(stat_row)
                        elif stat_value is None or pd.isna(stat_value):
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

        if deep_dive_view == "Matchup context":
            st.caption("Live, informational context for your final call. These details never change our ranking.")
            context_cards = []
            for _, row in compare.iterrows():
                provider_total = row.get("betting_total_live")
                if provider_total is None or pd.isna(provider_total):
                    provider_total = row.get("total_line")
                if provider_total is not None and pd.notna(provider_total):
                    total_value = float(provider_total)
                    scoring_label = "Higher-scoring environment" if total_value >= 48 else "Lower-scoring environment" if total_value <= 42 else "Typical scoring environment"
                    expected_points = f"{scoring_label} · {total_value:.1f}-point total"
                else:
                    expected_points = "Game total is not available"
                pace = f"{row['pace_label']} expected tempo · {row['combined_recent_plays']:.0f} recent combined plays" if pd.notna(row.get("combined_recent_plays")) else "Recent pace is not available"
                if pd.notna(row.get("qb_changed")):
                    changes = []
                    if bool(row.get("qb_changed")): changes.append("Starting QB changed")
                    if bool(row.get("ol_changed")): changes.append("Starting O-line changed")
                    personnel = " · ".join(changes) if changes else "No changes reported"
                else:
                    personnel = "No changes reported" if PROVIDER_STATUS.startswith("Connected") else "Personnel status unavailable"
                kickoff = " · ".join(
                    str(row.get(value)) for value in ("weekday", "gametime")
                    if row.get(value) is not None and pd.notna(row.get(value))
                ) or "Kickoff TBD"
                availability = selection_availability_summary(row)
                fields = [
                    ("Availability", availability, False),
                    ("Weather", weather_summary(row), False),
                    ("Expected pace", pace, True),
                    ("Scoring environment", expected_points, True),
                    ("Opponent strength", matchup_summary(row), False),
                    ("QB / O-line", personnel, False),
                ]
                rows_html = "".join(
                    f'<div class="context-item{" wide" if wide else ""}"><div class="context-label">{html.escape(label)}</div><div class="context-value">{html.escape(value)}</div></div>'
                    for label, value, wide in fields
                )
                photo = player_photo_html(row.get("headshot_url"), row["player"])
                logo_url = team_logo_url(row.get("team"))
                logo = f'<img src="{html.escape(logo_url, quote=True)}" alt="{html.escape(str(row["team"]), quote=True)} logo">' if logo_url else ""
                context_cards.append(
                    f'<article class="context-card"><div class="context-card-head">{photo}<div><div class="context-card-name">{html.escape(str(row["player"]))}</div>'
                    f'<div class="context-card-game">{logo}<span>{html.escape(str(row["team"]))} · {html.escape(str(row.get("venue", "")))} vs {html.escape(str(row["next_opponent"]))} · {html.escape(kickoff)}</span></div></div></div>'
                    f'<div class="context-card-body">{rows_html}</div><div class="context-card-foot"><b>Context only:</b> use this alongside the projection, not as a ranking adjustment.</div></article>'
                )
            st.markdown(f'<div class="context-grid">{"".join(context_cards)}</div>', unsafe_allow_html=True)

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
    st.subheader("How The Sunday Decision Lab works")
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
