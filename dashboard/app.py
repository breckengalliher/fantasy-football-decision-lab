"""Live weekly fantasy-football The Sunday Decision Lab."""

from __future__ import annotations

from dashboard.qa_telemetry import install as install_qa_telemetry
install_qa_telemetry()

import html
import json
import os
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

try:
    from dashboard.runtime_config import account_config
except ModuleNotFoundError:
    from runtime_config import account_config

try:
    from dashboard.publication_client import read_metadata, verified_payload
    from dashboard.live_updates import watch_publication
    from dashboard.snapshot_recovery import SnapshotRecovery
except ModuleNotFoundError:
    from publication_client import read_metadata, verified_payload
    from live_updates import watch_publication
    from snapshot_recovery import SnapshotRecovery

try:
    from dashboard.football_integrity import guard_forecasts, reconcile_board_identities
    from dashboard.availability import recommendation_restriction
except ModuleNotFoundError:
    from football_integrity import guard_forecasts, reconcile_board_identities
    from availability import recommendation_restriction
import streamlit.components.v1 as components
from urllib.parse import urlencode
from streamlit_local_storage import LocalStorage

try:
    from dashboard.providers.sportsdataio import context_freshness, format_injury_context
    from dashboard.outlooks import build_player_outlook, leader_margin
    from dashboard.injury_impact import apply_injury_scenario
    from dashboard.market_expectations import market_summary
    from dashboard.admin_refresh import authenticate as authenticate_refresh_admin, configured as admin_refresh_configured, refresh_status, trigger_refresh
    from dashboard.states import empty_player_pool_message, provider_issue_message
    from dashboard.methodology_copy import DISCLAIMER_LANGUAGE, METHODOLOGY_LANGUAGE, SOURCE_ATTRIBUTION
    from dashboard.presentation import actionable_injury_alert, eligible_positions, fantasy_game_log, player_weekly_history, matchup_summary, opponent_position_rank, player_card_stat_summary, projected_team_total, role_summary, selection_availability_summary, team_logo_url, weather_summary
    from dashboard.decision_policy import CLOSE_CALL_THRESHOLD_PPR
    from dashboard.command_center_v2 import authenticate_command_center, render_command_center
    from dashboard.product_experience import mobile_navigation, render_home
    from dashboard.supabase_api import SupabaseAPI
except ModuleNotFoundError:
    from providers.sportsdataio import context_freshness, format_injury_context
    from outlooks import build_player_outlook, leader_margin
    from injury_impact import apply_injury_scenario
    from market_expectations import market_summary
    from admin_refresh import authenticate as authenticate_refresh_admin, configured as admin_refresh_configured, refresh_status, trigger_refresh
    from states import empty_player_pool_message, provider_issue_message
    from methodology_copy import DISCLAIMER_LANGUAGE, METHODOLOGY_LANGUAGE, SOURCE_ATTRIBUTION
    from presentation import actionable_injury_alert, eligible_positions, fantasy_game_log, player_weekly_history, matchup_summary, opponent_position_rank, player_card_stat_summary, projected_team_total, role_summary, selection_availability_summary, team_logo_url, weather_summary
    from decision_policy import CLOSE_CALL_THRESHOLD_PPR
    from command_center_v2 import authenticate_command_center, render_command_center
    from product_experience import mobile_navigation, render_home
    from supabase_api import SupabaseAPI

try:
    from dashboard.data import current_nfl_season, repair_qb_display_form
except ModuleNotFoundError:
    from data import current_nfl_season, repair_qb_display_form


COLORS = {"QB": "#00529b", "RB": "#69be28", "WR": "#4b788f", "TE": "#a5acaf"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEASON = current_nfl_season()
BRAND_LOGO = PROJECT_ROOT / "dashboard" / "assets" / "sunday-decision-lab-logo-clean.png"
BRAND_ICON = PROJECT_ROOT / "dashboard" / "assets" / "sunday-decision-lab-icon-clean.png"
SNAPSHOT_BASE_URL = os.getenv(
    "SNAPSHOT_BASE_URL",
    "https://raw.githubusercontent.com/breckengalliher/fantasy-football-decision-lab/main/data/processed",
).rstrip("/")
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://thesundaydecisionlab.com/").rstrip("/") + "/"


st.set_page_config(page_title="The Sunday Decision Lab", page_icon=str(BRAND_ICON), layout="wide", initial_sidebar_state="auto")


@st.cache_resource
def command_center_api(url: str, publishable_key: str) -> SupabaseAPI:
    return SupabaseAPI(url, publishable_key)
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800&family=Bungee&family=Inter:wght@400;600;700;800&display=swap');
:root { --ink:#071b2c; --muted:#1b2730; --navy:#002244; --cream:#f3f6f7; --card:#ffffff; --line:#d7dde0; --forest:#285b16; --forest-deep:#214b13; --teal:#285b16; --gold:#69be28; --action:#69be28; --wolf:#a5acaf; }
.stApp { background:var(--cream); color:var(--ink); font-family:'Inter',Arial,sans-serif; overflow-x:hidden; }
[data-testid="stHeader"] { height:0 !important; min-height:0 !important; background:transparent !important; }
[data-testid="stToolbar"], [data-testid="stAppToolbar"], [data-testid="stAppDeployButton"], [data-testid="stDecoration"], #MainMenu { display:none !important; visibility:hidden !important; }
[data-testid="stSidebarCollapsedControl"] { position:fixed !important; top:.45rem !important; left:.45rem !important; z-index:1000001 !important; pointer-events:auto !important; }
.sr-only { position:absolute !important; width:1px !important; height:1px !important; padding:0 !important; margin:-1px !important; overflow:hidden !important; clip:rect(0,0,0,0) !important; white-space:nowrap !important; border:0 !important; }
button:focus-visible, summary:focus-visible, a:focus-visible, [tabindex="0"]:focus-visible { outline:3px solid #4b9fea !important; outline-offset:3px !important; border-radius:6px; }
[data-testid="stMain"] [data-testid="stCaptionContainer"] { color:var(--ink); }
[data-testid="stSidebar"] { background:var(--navy); }
[data-testid="stSidebar"] * { color:#f7fafb; }
[data-testid="stSidebar"] [data-baseweb="select"] * { color:var(--ink) !important; }
[data-testid="stSidebar"] button[kind="secondary"] * { color:var(--ink) !important; }
.block-container { max-width:1440px; padding-top:.35rem; }
.cc-hero { display:flex; justify-content:space-between; align-items:flex-end; gap:1.5rem; padding:1.2rem 1.35rem; margin:.5rem 0 1rem; color:#fff; background:linear-gradient(125deg,#002244 0%,#07335c 72%,#124e45 100%); border:1px solid #69be28; border-radius:22px; box-shadow:0 14px 34px rgba(0,34,68,.13); }
.cc-hero span,.cc-auth-intro span,.cc-empty span,.cc-section-label { color:#315f20; font-size:.76rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; }
.cc-hero span { color:#9ee468; }
.cc-hero h1 { color:#fff; margin:.16rem 0 .2rem; font-size:2.25rem; }
.cc-hero p { color:#eef5f8; margin:0; max-width:760px; }
.cc-promise { flex:0 0 280px; padding:.8rem 1rem; color:#d8e5eb; background:rgba(255,255,255,.08); border-radius:14px; font-size:.78rem; }
.cc-promise b { color:#fff; }
.cc-auth-intro,.cc-empty { padding:1.1rem 1.2rem; margin:.25rem 0 1rem; background:#fff; border:1px solid #d7dde0; border-left:5px solid #69be28; border-radius:16px; }
.cc-auth-intro h2,.cc-empty h2 { margin:.15rem 0 .2rem; color:#002244; }
.cc-auth-intro p,.cc-empty p { margin:0; }
.cc-section-label { margin:1rem 0 .4rem; }
.cc-team-card { display:flex; align-items:center; justify-content:space-between; gap:1.2rem; padding:1rem 1.15rem; margin:.55rem 0; background:#fff; border:1px solid #d7dde0; border-top:4px solid #69be28; border-radius:18px; }
.cc-team-card h3 { color:#002244; font-size:1.65rem; margin:.05rem 0; }
.cc-team-card p,.cc-team-card span { margin:0; color:#1b2730; }
.cc-team-metrics { display:grid; grid-template-columns:auto auto; align-items:baseline; gap:.05rem .55rem; min-width:220px; }
.cc-team-metrics strong { color:#315f20; font-size:1.15rem; text-align:right; }
.cc-brandline { color:#315f20; font-weight:900; letter-spacing:.13em; font-size:.78rem; margin:.25rem 0; }
.cc-status { display:flex; justify-content:space-between; gap:1.2rem; padding:1.05rem 1.2rem; margin:.35rem 0 1rem; background:#002244; color:#fff; border:1px solid #69be28; border-radius:18px; box-shadow:0 10px 25px rgba(0,34,68,.12); }
.cc-status>div>span,.cc-section-heading span,.cc-action>span,.cc-replacement span { font-size:.72rem; font-weight:800; letter-spacing:.1em; text-transform:uppercase; }
.cc-status h1 { color:#9ee468; font-size:2.05rem; margin:.06rem 0; }
.cc-status p { color:#eef5f8; margin:0; }
.cc-status-meta { display:flex; flex-direction:column; justify-content:center; min-width:290px; color:#dce7ec; font-size:.82rem; }
.cc-status-meta b { color:#fff; font-size:1rem; }
.cc-sync { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin:.55rem 0; padding:.72rem .85rem; border:1px solid #bed0d8; border-left:4px solid #69be28; border-radius:12px; background:#fff; }
.cc-sync div { min-width:0; }.cc-sync span,.cc-sync small { display:block; color:#596a73; font-size:.66rem; }.cc-sync span { color:#315f20; font-weight:900; letter-spacing:.05em; }.cc-sync strong { display:block; color:#002244; margin:.1rem 0; }.cc-sync>b { flex:0 0 auto; padding:.35rem .55rem; border-radius:999px; background:#edf4e8; color:#315f20; font-size:.65rem; }
.status-urgent { border-color:#d4602a; }
.status-urgent h1 { color:#ffb184; }
.status-attention,.status-verify { border-color:#d09a2c; }
.status-attention h1,.status-verify h1 { color:#f4c765; }
.cc-section-heading { margin:1rem 0 .45rem; }
.cc-section-heading span { color:#315f20; }
.cc-section-heading h2 { margin:.05rem 0; color:#002244; }
.cc-action { padding:.85rem 1rem; margin:.45rem 0; background:#fff; border:1px solid #d7dde0; border-left:5px solid #d09a2c; border-radius:14px; }
.cc-action.urgent { border-left-color:#bd431d; background:#fff8f5; }
.cc-action h3 { margin:.12rem 0; color:#002244; font-size:1.25rem; }
.cc-action p { margin:0; }
.cc-player-card { padding:.8rem 1rem; margin:.45rem 0; background:#fff; border:1px solid #d7dde0; border-radius:15px; }
.cc-player-top,.cc-player-main { display:flex; justify-content:space-between; align-items:center; gap:1rem; }
.cc-slot { color:#315f20; font-size:.72rem; font-weight:900; letter-spacing:.09em; }
.cc-availability { padding:.22rem .55rem; border-radius:999px; font-size:.72rem; font-weight:800; background:#f4ead2; color:#654708; }
.cc-availability.safe { background:#e8f3e2; color:#285b16; }
.cc-player-main h3 { margin:.16rem 0 0; color:#002244; font-size:1.35rem; }
.cc-player-main p { margin:0; font-size:.82rem; }
.cc-projection { text-align:right; min-width:110px; }
.cc-projection strong { display:block; color:#002244; font:800 1.75rem 'Barlow Condensed',sans-serif; }
.cc-projection span,.cc-range { color:#485660; font-size:.72rem; }
.cc-range { margin-top:.35rem; border-top:1px solid #e5eaec; padding-top:.35rem; }
.cc-replacement { display:flex; justify-content:space-between; align-items:center; padding:.8rem 1rem; margin:.4rem 0; background:#edf6e8; border:1px solid #b9d9a9; border-radius:14px; }
.cc-replacement h3 { color:#002244; margin:.08rem 0; }
.cc-replacement p { margin:0; }
.cc-replacement>div:last-child { text-align:right; }
.cc-replacement strong { display:block; color:#285b16; font-size:1.45rem; }
.cc-tight-heading { margin-top:.8rem; }
.cc-tight-heading h2 { display:inline-block; margin-right:.55rem; }
.cc-tight-heading p { display:inline; color:#55636c; font-size:.75rem; }
.cc-roster-row { min-height:54px; display:grid; grid-template-columns:64px minmax(0,1fr) 70px; align-items:center; gap:.7rem; padding:.45rem .65rem; margin:.18rem 0; background:#fff; border:1px solid #d7dde0; border-radius:12px; }
.cc-roster-slot { display:flex; align-items:center; justify-content:center; min-height:30px; padding:.2rem .35rem; background:#002244; color:#9ee468; border-radius:8px; font-size:.7rem; font-weight:900; }
.cc-roster-row strong { display:block; color:#002244; line-height:1.1; }
.cc-roster-row small { display:block; color:#56636b; font-size:.68rem; font-weight:600; }
.cc-roster-row>b { text-align:right; color:#285b16; font-size:1.15rem; }
.cc-roster-row>b small { text-transform:uppercase; }
.cc-roster-identity,.cc-replacement-identity,.landing-player-identity { display:flex; align-items:center; gap:.58rem; min-width:0; }
.cc-roster-identity>div,.cc-replacement-identity>div,.landing-player-identity>div { min-width:0; }
.cc-roster-identity .player-photo { width:42px; height:42px; flex-basis:42px; border-width:1px; }
.cc-replacement-identity .player-photo { width:48px; height:48px; flex-basis:48px; }
.landing-player-identity .player-photo { width:52px; height:52px; flex-basis:52px; }
.cc-roster-stats { grid-column:1/-1; display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:.32rem; padding-top:.42rem; border-top:1px solid #e1e7e9; }
.cc-stat-chip { min-width:0; padding:.35rem .42rem; border:1px solid #dce3e6; border-radius:8px; background:#f5f8f9; }
.cc-stat-chip b,.cc-stat-chip em { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.cc-stat-chip b { color:#52616a; font-size:.54rem; letter-spacing:.035em; text-transform:uppercase; }
.cc-stat-chip em { margin-top:.08rem; color:#002244; font-size:.68rem; font-style:normal; font-weight:850; }
.cc-stat-chip.projection { background:#eaf2e5; border-color:#bad5aa; }.cc-stat-chip.projection em,.cc-stat-chip.favorable em { color:#285b16; }
.cc-stat-chip.favorable { background:#edf6e8; border-color:#bfdcaf; }.cc-stat-chip.tough { background:#fff2ed; border-color:#ebc6b7; }.cc-stat-chip.tough em { color:#93401f; }.cc-stat-chip.neutral { background:#f1f4f5; }
.cc-detail-summary { display:flex; flex-direction:column; gap:.18rem; margin-bottom:.5rem; }.cc-detail-summary strong { color:#002244; font-size:.78rem; }.cc-detail-summary span { color:#53616a; font-size:.68rem; }
.cc-game-log { display:grid; gap:.3rem; }.cc-game-log-row { display:grid; grid-template-columns:42px 52px 78px minmax(0,1fr); gap:.42rem; align-items:center; padding:.42rem .5rem; border:1px solid #dce3e6; border-radius:9px; background:#fff; }.cc-game-log-row b { color:#315f20; }.cc-game-log-row span,.cc-game-log-row small { color:#53616a; font-size:.66rem; }.cc-game-log-row strong { color:#002244; font-size:.72rem; }
@media(max-width:700px) { .cc-hero { display:block; padding:1rem; } .cc-hero h1 { font-size:1.85rem; } .cc-promise { margin-top:.8rem; } .cc-team-card { display:block; } .cc-team-metrics { margin-top:.75rem; min-width:0; } }
@media(max-width:700px) { .cc-status { display:block; padding:.85rem; } .cc-status h1 { font-size:1.7rem; } .cc-status-meta { min-width:0; margin-top:.65rem; } .cc-player-card { padding:.7rem .75rem; } .cc-player-main { align-items:flex-end; } .cc-player-main h3 { font-size:1.15rem; } .cc-player-main p { font-size:.74rem; } .cc-projection { min-width:82px; } .cc-projection strong { font-size:1.45rem; } }
@media(max-width:700px) { .cc-sync { align-items:flex-start; padding:.65rem .7rem; }.cc-sync>b { max-width:38%; text-align:center; }.cc-sync small { line-height:1.35; } }
@media(max-width:700px) {
  [data-testid="stHorizontalBlock"]:has(.cc-roster-row) { flex-direction:column !important; gap:.25rem !important; }
  [data-testid="stHorizontalBlock"]:has(.cc-roster-row) > [data-testid="stColumn"] { width:100% !important; flex:1 1 100% !important; }
  [data-testid="stHorizontalBlock"]:has(.st-key-cc_v2_sign_out) > [data-testid="stColumn"]:last-child { flex:0 0 96px !important; width:96px !important; }
  .st-key-cc_v2_sign_out button { min-height:44px !important; }
}
@media(max-width:700px) { .cc-roster-row { grid-template-columns:43px minmax(0,1fr) 62px; min-height:56px; padding:.38rem .4rem; gap:.38rem; } .cc-roster-row strong { font-size:.84rem; } .cc-roster-row>b { font-size:.78rem; } .cc-roster-identity { gap:.4rem; } .cc-roster-identity .player-photo { width:38px; height:38px; flex-basis:38px; } .cc-replacement-identity .player-photo { width:42px; height:42px; flex-basis:42px; } .cc-roster-stats { grid-template-columns:repeat(2,minmax(0,1fr)); }.cc-stat-chip:last-child { grid-column:1/-1; }.cc-game-log-row { grid-template-columns:34px 44px 68px minmax(0,1fr); gap:.28rem; padding:.38rem; }.cc-game-log-row small { line-height:1.25; }.cc-tight-heading p { display:block; margin:.05rem 0; } }
.landing-hero { box-sizing:border-box; display:grid; grid-template-columns:minmax(0,1fr) 290px; gap:1.5rem; align-items:center; padding:2.2rem; margin:.35rem 0 1rem; background:linear-gradient(130deg,#002244 0%,#07375f 72%,#174b40 100%); border:1px solid #69be28; border-radius:24px; color:white; box-shadow:0 18px 38px rgba(0,34,68,.16); }
.landing-hero>div>span,.landing-section>span { color:#9ee468; font-weight:900; letter-spacing:.13em; font-size:.72rem; }
.landing-hero h1 { color:white; font:900 clamp(2.2rem,5vw,4.7rem)/.94 'Barlow Condensed',sans-serif; text-transform:uppercase; margin:.35rem 0 .75rem; }
.landing-hero h1 em { color:#9ee468; font-style:normal; }.landing-hero p { color:#e8f1f5; max-width:780px; font-size:1rem; }
.landing-hero aside { display:flex; flex-direction:column; padding:1.1rem; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.16); border-radius:16px; }
.landing-hero aside b { color:#9ee468; font-size:.68rem; letter-spacing:.1em; }.landing-hero aside strong { font-size:2rem; }.landing-hero aside span { color:#d9e5ea; font-size:.78rem; }
.trust-strip { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.45rem; margin:.75rem 0; }.trust-strip span { padding:.55rem .65rem; background:#fff; border:1px solid #d7dde0; border-radius:10px; color:#52606a; font-size:.68rem; }.trust-strip b { display:block; color:#285b16; font-size:.65rem; text-transform:uppercase; letter-spacing:.05em; }
.landing-section { margin:1.35rem 0 .5rem; }.landing-section h2 { color:#002244; margin:.12rem 0; }.landing-player { min-height:155px; padding:1rem; background:#fff; border:1px solid #d7dde0; border-top:4px solid #69be28; border-radius:15px; }.landing-player span { color:#315f20; font-size:.65rem; font-weight:900; }.landing-player h3 { color:#002244; margin:.18rem 0; }.landing-player>strong { display:block; margin-top:.55rem; color:#285b16; font-size:2rem; }.landing-player small,.landing-player p { font-size:.7rem; color:#56636b; }.landing-steps { display:grid; grid-template-columns:repeat(3,1fr); gap:.65rem; margin:1rem 0; }.landing-steps>div { display:grid; grid-template-columns:34px 1fr; gap:.1rem .55rem; padding:.85rem; background:#eaf0f2; border-radius:12px; }.landing-steps b { grid-row:1/3; display:grid; place-items:center; width:34px; height:34px; border-radius:50%; background:#002244; color:#9ee468; }.landing-steps strong { color:#002244; }.landing-steps span { color:#53616b; font-size:.7rem; }
.mobile-nav { display:none; }
@media(max-width:700px) { .landing-hero { display:block; width:100%; max-width:100%; min-width:0; padding:1.15rem; }.landing-hero p,.landing-hero span { overflow-wrap:anywhere; }.landing-hero aside { box-sizing:border-box; width:100%; min-width:0; margin-top:1rem; }.trust-strip { grid-template-columns:minmax(0,1fr) minmax(0,1fr); }.landing-steps { grid-template-columns:1fr; }.mobile-nav { box-sizing:border-box; position:fixed; z-index:999999; display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); left:8px; width:calc(100vw - 16px); bottom:8px; padding:.35rem; background:#002244; border:1px solid #69be28; border-radius:16px; box-shadow:0 8px 26px rgba(0,34,68,.28); }.mobile-nav a { min-width:0; display:flex; flex-direction:column; align-items:center; color:#fff !important; text-decoration:none; font-size:.58rem; }.mobile-nav b { color:#9ee468; font-size:1rem; }.stMainBlockContainer { box-sizing:border-box; width:100vw !important; max-width:100vw !important; padding-left:.8rem !important; padding-right:.8rem !important; padding-bottom:5.3rem !important; } }
h1,h2,h3 { font-family:'Barlow Condensed','Arial Narrow',sans-serif; letter-spacing:-.01em; font-weight:800; }
.hero { display:flex; align-items:flex-end; justify-content:space-between; gap:2rem; padding:0; margin:0; }
.hero h1 { margin:.12rem 0 .18rem; font-size:2.55rem; line-height:1.02; }
.graffiti-title { font-family:'Bungee',Impact,sans-serif; color:var(--navy); letter-spacing:.015em !important; text-transform:uppercase; text-shadow:2px 2px 0 rgba(105,190,40,.28); }
.graffiti-title span { color:var(--gold); text-shadow:2px 2px 0 rgba(0,34,68,.22); }
.hero-subtitle { color:var(--forest); font-size:.76rem; font-weight:850; letter-spacing:.13em; text-transform:uppercase; margin-bottom:.32rem; }
.sidebar-brand { font-family:'Bungee',Impact,sans-serif; color:#f7fafb; font-size:1.18rem; line-height:1.12; letter-spacing:.02em; margin:.15rem 0 .2rem; }
.sidebar-brand span { color:#9ee468; }
.st-key-sidebar_brand_mark { width:78px; margin:.05rem 0 .45rem; }
.st-key-sidebar_brand_mark [data-testid="stImage"] { width:78px; margin:0; }
.st-key-sidebar_brand_mark [data-testid="stImage"] img { display:block; width:78px; height:auto; object-fit:contain; }
.st-key-header_brand_mark { width:168px; max-width:100%; margin:0; }
.st-key-header_brand_mark [data-testid="stImage"] { width:168px; max-width:100%; margin:0; }
.st-key-header_brand_mark [data-testid="stImage"] img { display:block; width:168px; max-width:100%; height:auto; object-fit:contain; }
.hero p { color:var(--muted); margin:0; max-width:720px; }
.eyebrow { color:var(--forest); text-transform:uppercase; letter-spacing:.13em; font-size:.74rem; font-weight:800; }
.fresh { color:var(--muted); text-align:right; font-size:.78rem; white-space:nowrap; }
.app-header { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:1rem 1.15rem; margin-bottom:1rem; }
.header-details { max-width:720px; padding:.05rem 0; }
.header-details .eyebrow { margin-bottom:.14rem; }
.header-details .hero-subtitle { font-family:'Barlow Condensed','Arial Narrow',sans-serif; color:var(--navy); font-size:1.3rem; letter-spacing:.035em; margin-bottom:.08rem; }
.header-details p { color:var(--muted); margin:.08rem 0 .42rem; font-size:.8rem; line-height:1.35; }
.injury-impact-note { margin:.75rem 0 0; padding:.72rem .8rem; border-radius:10px; background:#f3f7ee; border-left:4px solid var(--gold); color:var(--ink); font-size:.76rem; line-height:1.45; }
.injury-impact-note summary { cursor:pointer; color:var(--forest); font-weight:800; letter-spacing:.035em; list-style:none; }
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
.settings-kicker { color:var(--forest); font-size:.64rem; font-weight:850; letter-spacing:.1em; text-transform:uppercase; }
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
.verdict .tag { display:inline-block; background:#edf4e8; color:var(--forest); border-radius:999px; padding:.28rem .52rem; letter-spacing:.12em; font-size:.67rem; font-weight:800; }
.verdict.start .tag { background:rgba(105,190,40,.16); color:#9ee468; }
.verdict .name { font-size:1.7rem; font-weight:750; margin:.65rem 0 .1rem; }
.player-heading { display:flex; align-items:center; gap:.75rem; margin:.65rem 0 .1rem; min-width:0; min-height:62px; }
.player-heading .name { margin:0; overflow-wrap:anywhere; }
.player-photo { width:58px; height:58px; flex:0 0 58px; border-radius:50%; background-size:cover; background-position:center top; background-repeat:no-repeat; background-color:#e8ecee; border:2px solid #d7dde0; }
.player-photo.fallback { display:grid; place-items:center; background:#e8eef1; color:#315f20; font-size:.72rem; font-weight:900; }
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
.player-stat-snapshot { margin:.72rem 0 .08rem; border:1px solid #dfe5e8; border-radius:11px; overflow:hidden; background:#f4f7f8; }
.player-stat-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); }
.player-stat { min-width:0; padding:.5rem .55rem .46rem; border-right:1px solid #dfe5e8; }
.player-stat:last-child { border-right:0; }
.player-stat-label { display:block; color:var(--muted); font-size:.53rem; font-weight:850; letter-spacing:.055em; line-height:1.2; text-transform:uppercase; }
.player-stat-value { display:block; color:var(--navy); font-size:.95rem; font-weight:850; line-height:1.05; margin-top:.16rem; }
.player-stat-unit { color:var(--muted); font-size:.52rem; font-weight:750; margin-left:.12rem; }
.player-season-line { display:flex; justify-content:space-between; gap:.55rem; padding:.4rem .55rem; border-top:1px solid #dfe5e8; color:var(--muted); font-size:.56rem; font-weight:750; line-height:1.25; }
.player-season-line strong { color:var(--forest-deep); font-size:.53rem; letter-spacing:.05em; text-transform:uppercase; white-space:nowrap; }
.verdict.start .player-stat-snapshot { background:rgba(255,255,255,.07); border-color:rgba(255,255,255,.16); }
.verdict.start .player-stat { border-right-color:rgba(255,255,255,.14); }
.verdict.start .player-stat-label,.verdict.start .player-stat-unit,.verdict.start .player-season-line { color:#c0cbd0; }
.verdict.start .player-stat-value,.verdict.start .player-season-line strong { color:#9ee468; }
.verdict.start .player-season-line { border-top-color:rgba(255,255,255,.14); }
.confidence-label { margin-left:auto; border-radius:999px; padding:.27rem .48rem; font-size:.61rem; font-weight:850; letter-spacing:.04em; text-transform:uppercase; background:#edf4e8; color:var(--forest); }
.verdict.start .confidence-label { background:rgba(105,190,40,.16); color:#9ee468; }
.label-help { position:relative; cursor:help; }
.label-help .label-tooltip { visibility:hidden; opacity:0; position:absolute; z-index:30; right:0; bottom:calc(100% + .48rem); width:240px; padding:.52rem .6rem; border-radius:8px; background:#071b2c; color:#f7fafb; font-size:.69rem; font-weight:550; letter-spacing:0; line-height:1.35; text-align:left; text-transform:none; box-shadow:0 8px 22px rgba(0,0,0,.22); transition:opacity .12s ease; }
.label-help:hover .label-tooltip,.label-help:focus .label-tooltip,.label-help:focus-within .label-tooltip { visibility:visible; opacity:1; }
.explained-term { display:inline-flex; align-items:center; gap:.18rem; border-bottom:1px dotted currentColor; line-height:1.2; }
.explained-term::after { content:'ⓘ'; font-size:.76em; opacity:.72; }
.range-help { position:relative; display:inline-flex; align-items:center; justify-content:center; width:1.05rem; height:1.05rem; border:1px solid currentColor; border-radius:50%; font-size:.68rem; font-weight:800; cursor:help; opacity:.82; }
.range-tooltip { visibility:hidden; opacity:0; position:absolute; z-index:20; left:50%; bottom:calc(100% + .5rem); transform:translateX(-50%); width:250px; padding:.55rem .65rem; border-radius:8px; background:#071b2c; color:#f7fafb; font-size:.74rem; font-weight:500; line-height:1.35; text-align:left; box-shadow:0 8px 22px rgba(0,0,0,.22); transition:opacity .12s ease; }
.range-help:hover .range-tooltip, .range-help:focus .range-tooltip, .range-help:focus-within .range-tooltip { visibility:visible; opacity:1; }
.verdict .outlook-label { color:var(--muted); text-transform:uppercase; letter-spacing:.1em; font-size:.65rem; font-weight:800; margin-top:1rem; }
.verdict.start .outlook-label { color:#9ee468; }
.verdict .reason { color:var(--ink); font-size:.84rem; line-height:1.42; margin-top:.28rem; min-height:2.4em; }
.verdict.start .reason { color:#e0e6e8; }
.actionable-alert { margin:.68rem 0 .15rem; padding:.62rem .68rem; border:1px solid #d8e0e3; border-left:4px solid #758791; border-radius:9px; background:#f3f6f7; color:var(--ink); }
.actionable-alert-head { display:flex; align-items:center; justify-content:space-between; gap:.5rem; }
.actionable-alert-label { font-size:.62rem; font-weight:850; letter-spacing:.055em; text-transform:uppercase; }
.actionable-alert-time { color:var(--muted); font-size:.59rem; text-align:right; }
.actionable-alert-title { font-size:.72rem; font-weight:800; line-height:1.32; margin-top:.28rem; }
.actionable-alert-verify { color:var(--muted); font-size:.66rem; line-height:1.38; margin-top:.24rem; }
.opportunity-details { border-top:1px solid rgba(57,127,24,.22); margin-top:.46rem; padding-top:.12rem; }
.opportunity-details summary { cursor:pointer; list-style:none; color:var(--forest); font-size:.65rem; font-weight:850; letter-spacing:.045em; text-transform:uppercase; padding:.36rem 0 .2rem; }
.opportunity-details summary::-webkit-details-marker { display:none; }
.opportunity-details summary::after { content:'+'; float:right; width:1.15rem; height:1.15rem; border:1px solid currentColor; border-radius:50%; text-align:center; line-height:1rem; font-size:.9rem; }
.opportunity-details[open] summary::after { content:'−'; }
.opportunity-details-body { color:var(--ink); font-size:.68rem; line-height:1.42; padding:.2rem 0 .18rem; }
.opportunity-details-body strong { display:block; color:var(--navy); font-size:.67rem; margin-bottom:.16rem; }
.opportunity-details-range { display:block; color:var(--muted); font-weight:700; margin-top:.22rem; }
.actionable-alert.monitor { background:#fff9e8; border-color:#ead79e; border-left-color:#d39b29; }
.actionable-alert.monitor .actionable-alert-label { color:#7a560c; }
.actionable-alert.action { background:#fff2e8; border-color:#efc4a5; border-left-color:#d46b20; }
.actionable-alert.action .actionable-alert-label { color:#94400f; }
.actionable-alert.unavailable { background:#fff0ee; border-color:#efb6ae; border-left-color:#c83c2b; }
.actionable-alert.unavailable .actionable-alert-label { color:#9f281b; }
.actionable-alert.opportunity { background:#edf6e8; border-color:#c7dfb8; border-left-color:#69be28; }
.actionable-alert.opportunity .actionable-alert-label { color:var(--forest); }
.verdict.start .actionable-alert { background:rgba(255,255,255,.09); border-color:rgba(255,255,255,.18); color:#f7fafb; }
.verdict.start .actionable-alert-time,.verdict.start .actionable-alert-verify { color:#c7d2d8; }
.verdict.start .actionable-alert-label { color:#9ee468; }
.verdict.start .opportunity-details { border-top-color:rgba(255,255,255,.16); }
.verdict.start .opportunity-details summary { color:#9ee468; }
.verdict.start .opportunity-details-body,.verdict.start .opportunity-details-body strong { color:#f7fafb; }
.verdict.start .opportunity-details-range { color:#c7d2d8; }
.decision-edge { display:flex; align-items:center; justify-content:space-between; gap:1rem; background:var(--navy); color:#f7fafb; border:1px solid rgba(105,190,40,.65); border-radius:13px; padding:.68rem .9rem; margin:.55rem 0 .5rem; box-shadow:0 7px 18px rgba(0,34,68,.10); }
.decision-edge-main { min-width:0; }
.decision-edge-label { color:#9ee468; font-size:.62rem; font-weight:850; letter-spacing:.1em; text-transform:uppercase; margin-bottom:.16rem; }
.decision-edge-title { font-size:1rem; font-weight:780; line-height:1.25; overflow-wrap:anywhere; }
.decision-edge-copy { color:#cbd5da; font-size:.76rem; line-height:1.35; margin-top:.18rem; }
.decision-edge-badge { flex:0 0 auto; background:rgba(105,190,40,.16); color:#9ee468; border:1px solid rgba(158,228,104,.42); border-radius:999px; padding:.38rem .62rem; font-size:.66rem; font-weight:850; letter-spacing:.06em; text-transform:uppercase; white-space:nowrap; }
.mobile-decision-edge { display:none; }
.desktop-decision-edge { display:block; }
.broadcast-context { display:grid; grid-template-columns:1fr; gap:.3rem; margin-top:.78rem; }
.broadcast-context-item { display:flex; align-items:flex-start; gap:.42rem; background:transparent; color:var(--ink); padding:.34rem 0; border-top:1px solid #e7eaec; min-width:0; font-size:.72rem; line-height:1.28; overflow-wrap:anywhere; }
.broadcast-context-item span { color:var(--muted); min-width:5.25rem; font-size:.62rem; font-weight:800; letter-spacing:.04em; text-transform:uppercase; }
.broadcast-context-item.context-alert { color:#a33a13; font-weight:750; }
.verdict.start .broadcast-context-item { background:rgba(255,255,255,.1); color:#f4f8fa; }
.verdict.start .broadcast-context-item { background:transparent; border-top-color:rgba(255,255,255,.13); }
.verdict.start .broadcast-context-item span { color:#9ee468; }
.card-game-log { margin-top:.72rem; border:1px solid #d8e0e4; border-radius:13px; overflow:hidden; background:#fff; }
.card-game-log summary { cursor:pointer; list-style:none; padding:.7rem .78rem; background:#062b50; color:#9ef04f; font-size:.68rem; font-weight:900; letter-spacing:.035em; text-transform:uppercase; display:flex; justify-content:space-between; align-items:center; }
.card-game-log summary::-webkit-details-marker { display:none; }
.card-game-log summary::after { content:"+"; width:1.25rem; height:1.25rem; display:grid; place-items:center; border:1px solid rgba(158,240,79,.55); border-radius:50%; font-size:.9rem; }
.card-game-log[open] summary::after { content:"−"; }
.card-game-log-body { padding:.7rem; color:var(--ink); }
.defense-rank { display:grid; grid-template-columns:auto 1fr; gap:.55rem; align-items:center; padding:.58rem .64rem; border-radius:10px; margin-bottom:.62rem; border:1px solid transparent; }
.defense-rank strong { width:2.35rem; height:2.35rem; border-radius:50%; display:grid; place-items:center; font-size:.9rem; }
.defense-rank b { display:block; font-size:.66rem; }
.defense-rank span { display:block; margin-top:.08rem; font-size:.57rem; line-height:1.25; color:#42515b; }
.defense-rank.tough { background:#fff0ed; border-color:#f0b8ac; } .defense-rank.tough strong { background:#ad351e; color:#fff; }
.defense-rank.neutral { background:#f3f1e8; border-color:#ddd5b8; } .defense-rank.neutral strong { background:#6d716d; color:#fff; }
.defense-rank.favorable { background:#edf7e8; border-color:#b9dca7; } .defense-rank.favorable strong { background:#2f7620; color:#fff; }
.fantasy-log { display:grid; gap:.28rem; }
.fantasy-log-row { display:grid; grid-template-columns:38px 36px 43px minmax(72px,1fr) minmax(68px,1fr) 28px; gap:.3rem; align-items:center; padding:.4rem .34rem; border-bottom:1px solid #e5eaec; font-size:.56rem; }
.fantasy-log-row:last-child { border-bottom:0; }
.fantasy-log-row.header { color:var(--forest); font-size:.49rem; font-weight:900; letter-spacing:.03em; text-transform:uppercase; background:#f4f7f8; border-radius:7px; }
.fantasy-log-row span:nth-child(3) { color:var(--navy); font-weight:900; }
.verdict.start .card-game-log-body { color:var(--ink); }
.game-detail-chips { display:flex; flex-wrap:wrap; align-content:flex-start; gap:.3rem; margin-top:.48rem; min-height:3.25rem; }
.game-detail-chip { display:inline-flex; align-items:center; min-height:1.45rem; border:1px solid #dce3e6; border-radius:999px; background:#f1f4f5; color:var(--muted); padding:.2rem .48rem; font-size:.61rem; font-weight:700; line-height:1.15; white-space:nowrap; cursor:help; }
.game-detail-chip.matchup { background:#edf4e8; border-color:#cfe0c5; color:var(--forest-deep); }
.game-detail-chip.team-total { background:#eaf2f6; border-color:#ccdde5; color:var(--navy); }
.game-details-legend { display:flex; justify-content:flex-end; margin:.15rem 0 .48rem; color:var(--muted); font-size:.67rem; }
.game-details-legend .explained-term { color:var(--navy); font-weight:800; }
.share-link-label { color:var(--navy); font-size:.68rem; font-weight:800; margin:.35rem 0 .18rem; }
.onboarding-intro { color:var(--muted); font-size:.82rem; line-height:1.45; margin:-.15rem 0 .75rem; }
.onboarding-steps { display:grid; gap:.55rem; margin:.25rem 0 .8rem; }
.onboarding-step { display:grid; grid-template-columns:2rem 1fr; gap:.62rem; align-items:start; padding:.68rem .72rem; border:1px solid #d7e0e4; border-radius:11px; background:#f7fafb; }
.onboarding-number { display:flex; align-items:center; justify-content:center; width:2rem; height:2rem; border-radius:50%; background:var(--navy); color:#9ee468; font-family:'Barlow Condensed','Arial Narrow',sans-serif; font-size:1.05rem; font-weight:800; }
.onboarding-step strong { display:block; color:var(--navy); font-size:.82rem; margin-bottom:.12rem; }
.onboarding-step span { color:var(--muted); font-size:.72rem; line-height:1.38; }
.onboarding-must-know { padding:.7rem .78rem; border-left:4px solid var(--gold); border-radius:9px; background:#edf4e8; }
.onboarding-must-know strong { color:var(--forest-deep); font-size:.72rem; letter-spacing:.055em; text-transform:uppercase; }
.onboarding-must-know ul { margin:.42rem 0 0; padding-left:1.1rem; color:var(--ink); font-size:.69rem; line-height:1.42; }
.onboarding-must-know li + li { margin-top:.25rem; }
.limited-sample-pill { display:inline-flex; align-items:center; border-radius:999px; background:#fff1d6; border:1px solid #e3bd70; color:#744b00; padding:.22rem .46rem; font-size:.58rem; font-weight:850; letter-spacing:.045em; text-transform:uppercase; }
.limited-sample-note { margin:.62rem 0 .12rem; padding:.62rem .68rem; border:1px solid #e3bd70; border-left:4px solid #d28a18; border-radius:9px; background:#fff8e8; color:var(--ink); font-size:.68rem; line-height:1.4; }
.limited-sample-note strong { display:block; color:#744b00; font-size:.62rem; letter-spacing:.06em; text-transform:uppercase; margin-bottom:.18rem; }
.verdict.start .game-detail-chip { background:rgba(255,255,255,.08); border-color:rgba(255,255,255,.17); color:#dbe3e6; }
.verdict.start .game-detail-chip.matchup { background:rgba(105,190,40,.14); border-color:rgba(158,228,104,.28); color:#b7ed8e; }
.verdict.start .game-detail-chip.team-total { background:rgba(75,120,143,.28); border-color:rgba(191,226,242,.24); color:#d6ecf5; }
.verdict.start .limited-sample-pill { background:rgba(255,193,77,.14); border-color:rgba(255,213,130,.38); color:#ffd582; }
.verdict.start .limited-sample-note { background:rgba(255,193,77,.10); border-color:rgba(255,213,130,.28); border-left-color:#ffd582; color:#f7fafb; }
.verdict.start .limited-sample-note strong { color:#ffd582; }
.comparison-relative-note { color:var(--muted); font-size:.7rem; line-height:1.4; margin:.45rem .1rem 0; font-style:italic; }
.card-outlook-details { border-top:1px solid #e3e8ea; margin-top:auto; padding-top:.22rem; }
.card-outlook-details summary { color:var(--navy); cursor:pointer; font-size:.74rem; font-weight:800; padding:.5rem .1rem .28rem; list-style-position:inside; }
.card-outlook-details summary:hover { color:var(--forest); }
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
.reporting-sources a { color:var(--forest); font-weight:700; text-decoration:none; }
.verdict.start .reporting-sources { color:#c0c8cc; }
.verdict.start .reporting-sources a { color:#9ee468; }
.section-title { font-size:1.16rem; font-weight:750; margin:1.2rem 0 .1rem; }
.section-copy { color:var(--muted); font-size:.87rem; margin-bottom:.65rem; }
.note { border-left:4px solid var(--gold); background:#edf4e8; color:#183515; padding:.72rem .9rem; border-radius:8px; font-size:.84rem; margin-top:1rem; }
.warning { border-left:4px solid var(--gold); background:#eef5e9; color:var(--forest-deep); padding:.72rem .9rem; border-radius:8px; font-size:.84rem; margin:.85rem 0; }
.freshness-bar { display:flex; align-items:center; gap:.35rem; background:var(--card); border:1px solid var(--line); border-radius:11px; padding:.42rem .5rem; margin:.45rem 0 .55rem; overflow:hidden; }
.freshness-item { display:flex; align-items:center; gap:.28rem; min-width:0; padding:.08rem .5rem; border-right:1px solid #e3e8ea; color:var(--ink); font-size:.66rem; line-height:1.25; white-space:nowrap; }
.freshness-item:last-of-type { border-right:0; }
.freshness-item b { color:var(--muted); font-size:.56rem; font-weight:850; letter-spacing:.055em; text-transform:uppercase; }
.freshness-item.status-caution { color:#8a5a08; }
.focused-status { display:flex; justify-content:space-between; align-items:center; gap:.75rem; background:#f7faf5; border:1px solid #dbe6d5; border-left:4px solid var(--forest); border-radius:10px; padding:.48rem .72rem; margin:.45rem 0 .55rem; color:var(--ink); font-size:.72rem; line-height:1.35; }
.focused-status > span { display:flex; align-items:center; gap:.28rem; }
.focused-status.status-caution { background:#fff8e8; border-color:#ead4a4; border-left-color:#d28a18; }
.freshness-reminder { margin-left:auto; color:var(--muted); font-size:.6rem; line-height:1.25; text-align:right; }
.freshness-alert { display:flex; align-items:center; gap:.42rem; border-left:3px solid #d39b29; background:#fbf6df; color:#76520d; border-radius:8px; padding:.48rem .65rem; margin:0 0 .55rem; font-size:.7rem; line-height:1.35; }
.player-finder { margin:.35rem 0 .8rem; }
.finder-copy { color:var(--muted); font-size:.78rem; margin:-.25rem 0 .55rem; }
.selected-player-name { font-size:.94rem; font-weight:750; line-height:1.2; margin-top:.2rem; }
.selected-player-meta { color:var(--muted); font-size:.72rem; line-height:1.3; }
.comparison-count { margin:.22rem 0 .35rem; font-size:.75rem; }
.compare-slot-kicker { color:var(--forest); font-size:.57rem; font-weight:850; letter-spacing:.09em; text-transform:uppercase; margin-bottom:.3rem; }
.compare-slot-top { display:flex; align-items:center; gap:.55rem; min-height:48px; }
.compare-slot-top .player-photo { width:46px; height:46px; flex-basis:46px; }
.compare-slot-main { min-width:0; }
.compare-slot-name { color:var(--ink); font-size:.91rem; font-weight:800; line-height:1.12; overflow-wrap:anywhere; }
.compare-slot-team { display:flex; align-items:center; gap:.3rem; color:var(--muted); font-size:.66rem; margin-top:.14rem; }
.compare-slot-team img { width:1rem; height:1rem; object-fit:contain; }
.compare-slot-game { color:var(--muted); font-size:.65rem; line-height:1.25; margin-top:.34rem; }
.compare-slot-footer { display:flex; align-items:center; justify-content:space-between; gap:.4rem; border-top:1px solid #e4e8ea; margin-top:.4rem; padding-top:.38rem; }
.compare-slot-projection { color:var(--navy); font-size:.75rem; font-weight:800; }
.st-key-mobile_selection_summary { display:none; }
.mobile-selection-row { display:flex; align-items:center; gap:.58rem; min-width:0; }
.mobile-selection-row .player-photo { width:42px; height:42px; flex:0 0 42px; }
.mobile-selection-main { min-width:0; flex:1; }
.mobile-selection-name { color:var(--ink); font-size:.82rem; font-weight:850; line-height:1.15; overflow-wrap:anywhere; }
.mobile-selection-meta { display:flex; align-items:center; gap:.3rem; color:var(--muted); font-size:.61rem; line-height:1.25; margin-top:.13rem; overflow-wrap:anywhere; }
.mobile-selection-meta img { width:.9rem; height:.9rem; object-fit:contain; flex:0 0 .9rem; }
.mobile-selection-numbers { flex:0 0 auto; text-align:right; }
.mobile-selection-projection { display:block; color:var(--navy); font-size:.88rem; font-weight:850; line-height:1; }
.mobile-selection-status { display:block; color:var(--muted); font-size:.55rem; line-height:1.2; margin-top:.2rem; max-width:92px; }
.mobile-selection-status.alert { color:#94400f; font-weight:800; }
.mobile-open-row { min-height:46px; border:1px dashed #bdc8cd; border-radius:9px; display:flex; align-items:center; justify-content:center; color:var(--muted); font-size:.68rem; }
.availability-pill { border-radius:999px; padding:.24rem .46rem; font-size:.63rem; font-weight:800; line-height:1.15; text-align:right; }
.availability-ok { background:#edf4e8; color:var(--forest); }
.availability-alert { background:#fff0e6; color:#a33a13; border:1px solid #efb79f; }
.open-slot { min-height:166px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; border:2px dashed #bdc8cd; border-radius:11px; color:var(--muted); padding:1rem; }
.open-slot-number { color:var(--forest); font-size:.62rem; font-weight:850; letter-spacing:.09em; text-transform:uppercase; }
.open-slot-title { color:var(--ink); font-size:.95rem; font-weight:780; margin:.3rem 0 .12rem; }
.open-slot-copy { font-size:.72rem; line-height:1.35; max-width:210px; }
.replacement-note { background:#edf4e8; border-left:3px solid var(--gold); color:var(--forest-deep); border-radius:8px; padding:.55rem .7rem; font-size:.76rem; margin:.35rem 0 .65rem; }
.smart-search-intro { background:var(--navy); border:1px solid #174a70; border-bottom:3px solid var(--green); border-radius:12px; color:#fff; padding:.7rem .85rem; margin:.55rem 0 .4rem; }
.smart-search-title { color:var(--green); font-size:.78rem; font-weight:900; letter-spacing:.08em; text-transform:uppercase; }
.smart-search-copy { color:#dce8f2; font-size:.78rem; line-height:1.35; margin-top:.18rem; }
.smart-search-result { background:#edf4e8; border-left:3px solid var(--green); border-radius:8px; color:var(--ink); font-size:.78rem; padding:.55rem .7rem; margin:.35rem 0 .5rem; }
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
.driver-positive { color:var(--forest); }
.driver-neutral { color:#46535a; }
.driver-negative { color:#c45a1a; }
.driver-final { background:#edf4e8; }
.driver-final .driver-value { color:var(--forest); font-size:.86rem; }
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
.detail-card-status { margin-left:auto; border-radius:999px; padding:.25rem .42rem; background:#edf4e8; color:var(--forest); font-size:.58rem; font-weight:800; text-align:center; line-height:1.15; }
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
.context-label { color:var(--forest); font-size:.56rem; font-weight:850; letter-spacing:.075em; text-transform:uppercase; line-height:1.2; margin-bottom:.15rem; }
.context-value { color:var(--ink); font-size:.69rem; font-weight:700; line-height:1.35; overflow-wrap:anywhere; }
.context-card-foot { display:flex; align-items:center; gap:.35rem; margin:0 .68rem .68rem; padding:.48rem .58rem; border-radius:8px; background:#edf4e8; color:var(--forest-deep); font-size:.64rem; line-height:1.3; }
.stPlotlyChart { background:var(--card); border:0; border-radius:12px; padding:.2rem; }
[data-baseweb="tab-list"] { gap:.32rem; background:#e6ecef; border-radius:12px; padding:.3rem; }
[data-baseweb="tab-list"] button { border-radius:8px; padding:.55rem .8rem; color:var(--ink); }
[data-baseweb="tab-list"] button[aria-selected="true"] { background:var(--navy); color:white; }
[data-baseweb="tab-highlight"] { display:none; }
[data-testid="stSegmentedControl"] { background:#e6ecef; border:1px solid #d4dde1; border-radius:12px; padding:.24rem; }
[data-testid="stSegmentedControl"] button { min-height:2.35rem; border-radius:9px !important; font-family:'Inter',Arial,sans-serif; font-weight:750; }
[data-testid="stMain"] [data-testid="stExpander"] { border:1px solid rgba(105,190,40,.62) !important; border-radius:14px !important; background:#fff !important; box-shadow:0 7px 18px rgba(0,34,68,.08); overflow:hidden; margin:.68rem 0; }
[data-testid="stMain"] [data-testid="stExpander"] details { border:0 !important; border-radius:14px !important; background:#fff; }
[data-testid="stMain"] [data-testid="stExpander"] summary { min-height:3.2rem; padding:.72rem .9rem !important; background:linear-gradient(105deg,#002244 0%,#06375c 100%) !important; color:#9ee468 !important; border-radius:13px !important; transition:background .16s ease,box-shadow .16s ease; }
[data-testid="stMain"] [data-testid="stExpander"] summary:hover { background:linear-gradient(105deg,#06375c 0%,#0b466f 100%) !important; box-shadow:inset 4px 0 0 #69be28; }
[data-testid="stMain"] [data-testid="stExpander"] summary p { color:#9ee468 !important; font-family:'Barlow Condensed','Arial Narrow',sans-serif !important; font-size:1rem !important; font-weight:800 !important; letter-spacing:.025em; }
[data-testid="stMain"] [data-testid="stExpander"] summary svg { fill:#9ee468 !important; color:#9ee468 !important; }
[data-testid="stMain"] [data-testid="stExpander"] details[open] summary { border-radius:13px 13px 0 0 !important; border-bottom:3px solid #69be28; }
[data-testid="stMain"] [data-testid="stExpander"] details[open] > div { padding-top:.38rem; }
.tool-section-head { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin:1.15rem 0 .55rem; padding:.78rem .9rem; border:1px solid var(--line); border-left:4px solid var(--gold); border-radius:12px; background:var(--card); }
.tool-section-head h2 { display:block; color:var(--navy); font-family:'Barlow Condensed','Arial Narrow',sans-serif; font-size:1.28rem; letter-spacing:.01em; line-height:1.1; margin:0; padding:0 !important; }
.tool-section-head span { display:block; color:var(--muted); font-size:.7rem; margin-top:.08rem; line-height:1.35; }
.tool-section-badge { flex:0 0 auto; border-radius:999px; background:#edf4e8; color:var(--forest) !important; padding:.34rem .58rem; font-size:.58rem !important; font-weight:850; letter-spacing:.055em; text-transform:uppercase; white-space:nowrap; }
.st-key-comparison_view [data-testid="stButtonGroup"], .st-key-deep_dive_view [data-testid="stButtonGroup"] { margin-bottom:.55rem; }
.st-key-comparison_view [role="radiogroup"], .st-key-deep_dive_view [role="radiogroup"] { display:grid !important; width:100%; gap:.32rem; padding:.34rem; border:1px solid #d4dcdf; border-radius:12px; background:#e8edef; box-sizing:border-box; }
.st-key-comparison_view [role="radiogroup"] { grid-template-columns:repeat(6,minmax(0,1fr)); }
.st-key-deep_dive_view [role="radiogroup"] { grid-template-columns:repeat(3,minmax(0,1fr)); }
.st-key-comparison_view button, .st-key-deep_dive_view button { width:100%; min-height:2.75rem; border:0 !important; border-radius:9px !important; background:transparent !important; color:var(--muted) !important; font-size:.72rem !important; font-weight:750 !important; box-shadow:none !important; }
.st-key-position_selector button, [class*="st-key-remove_"] button, [class*="st-key-replace_"] button { min-height:44px !important; }
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
.usage-player.leader .usage-fill { background:linear-gradient(90deg,var(--forest),var(--gold)); }
.trends-hero { margin:.1rem 0 .55rem; padding:.7rem .9rem; border-radius:13px; background:linear-gradient(115deg,#002244 0%,#06375c 100%); color:#fff; box-shadow:0 8px 18px rgba(0,34,68,.14); }
.trends-hero .eyebrow { color:#9ee468; font-size:.67rem; font-weight:900; letter-spacing:.11em; text-transform:uppercase; }
.trends-hero h2 { color:#fff !important; margin:.1rem 0 !important; padding:0 !important; font-family:'Barlow Condensed','Arial Narrow',sans-serif; font-size:1.45rem; }
.trends-hero p { color:#dbe6ec !important; margin:0; font-size:.72rem; }
.trend-player-card { display:grid; grid-template-columns:minmax(230px,1.2fr) repeat(4,minmax(96px,.48fr)); gap:.48rem; align-items:center; margin:.42rem 0; padding:.58rem .68rem; border:1px solid #cad4d9; border-left:5px solid #69be28; border-radius:13px; background:#fff; box-shadow:0 6px 15px rgba(0,34,68,.07); }
.trend-player-identity { display:flex; align-items:center; gap:.72rem; min-width:0; }
.trend-player-identity .player-photo { width:44px; height:44px; flex-basis:44px; }
.trend-player-name { color:var(--navy); font-family:'Barlow Condensed','Arial Narrow',sans-serif; font-size:1.1rem; font-weight:900; line-height:1.02; }
.trend-player-team { display:flex; align-items:center; gap:.26rem; color:var(--ink); font-size:.66rem; margin-top:.18rem; }
.trend-player-team img { width:1.1rem; height:1.1rem; object-fit:contain; }
.trend-stat { min-height:47px; padding:.34rem .5rem; border-radius:9px; background:#f1f5f6; }
.trend-stat span { display:block; color:var(--muted); font-size:.61rem; font-weight:800; letter-spacing:.05em; text-transform:uppercase; }
.trend-stat strong { display:block; color:var(--navy); font-size:1.02rem; line-height:1.04; margin-top:.06rem; }
.trend-stat small { color:var(--muted); font-size:.61rem; }
.trend-status { display:inline-flex; align-items:center; max-width:100%; margin-top:.25rem; padding:.18rem .42rem; border-radius:999px; background:#eef3f5; color:var(--forest); font-size:.6rem; font-weight:850; }
.trend-status.alert { background:#fff0df; color:#934f09; }
.trend-insights-title { margin:.7rem 0 .35rem; color:var(--navy); font-size:.74rem; font-weight:900; letter-spacing:.07em; text-transform:uppercase; }
.trend-insight-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.55rem; margin:.35rem 0 .7rem; }
.trend-insight-card { min-height:90px; padding:.65rem .72rem; border:1px solid #d4dcdf; border-top:3px solid #74858d; border-radius:11px; background:#fff; }
.trend-insight-card.positive { border-top-color:#397f18; background:#f4f9f1; }
.trend-insight-card.negative { border-top-color:#c3741d; background:#fff8ef; }
.trend-insight-card span { display:block; color:var(--forest); font-size:.59rem; font-weight:900; letter-spacing:.055em; text-transform:uppercase; }
.trend-insight-card strong { display:block; margin:.15rem 0; color:var(--navy); font-size:.8rem; }
.trend-insight-card p { margin:0; color:var(--ink); font-size:.65rem; line-height:1.4; }
.game-log { display:grid; gap:.35rem; }
.game-log-row { display:grid; grid-template-columns:58px minmax(80px,.7fr) repeat(4,minmax(54px,.45fr)); gap:.4rem; align-items:center; padding:.45rem .55rem; border:1px solid #dce3e6; border-radius:9px; background:#fff; color:var(--ink); font-size:.64rem; }
.game-log-row.header { border:0; background:#e9eef0; color:var(--forest); font-size:.57rem; font-weight:900; letter-spacing:.04em; text-transform:uppercase; }
.game-log-row strong { color:var(--navy); }
.trend-read { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin:.65rem 0 .9rem; padding:.78rem .9rem; border-radius:12px; background:#edf4e8; border-left:4px solid #69be28; }
.trend-read b { color:var(--forest); font-size:.68rem; letter-spacing:.07em; text-transform:uppercase; white-space:nowrap; }
.trend-read span { color:var(--ink); font-size:.76rem; }
.trend-week-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.55rem; margin:.7rem 0; }
.trend-week { min-height:92px; padding:.66rem; border:1px solid #d4dcdf; border-radius:12px; background:#fff; text-align:center; }
.trend-week.hot { border-color:#69be28; background:#f1f8ec; }
.trend-week.cool { border-color:#d68b27; background:#fff6e9; }
.trend-week .week { color:var(--muted); font-size:.61rem; font-weight:850; text-transform:uppercase; }
.trend-week strong { display:block; color:var(--navy); font-size:1.35rem; line-height:1.1; margin:.22rem 0; }
.trend-week small { color:var(--muted); font-size:.61rem; }
.trend-evidence-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.65rem; margin:.75rem 0; }
.trend-evidence { padding:.8rem; border:1px solid #d4dcdf; border-radius:12px; background:#fff; }
.trend-evidence span { color:var(--muted); font-size:.62rem; font-weight:850; text-transform:uppercase; letter-spacing:.05em; }
.trend-evidence strong { display:block; color:var(--navy); font-size:1rem; margin:.2rem 0; }
.trend-evidence p { color:var(--ink); font-size:.69rem; line-height:1.45; margin:0; }
.opportunity-summary { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.6rem; margin:.65rem 0 .75rem; }
.opportunity-kpi { padding:.7rem .78rem; border:1px solid #d4dcdf; border-radius:12px; background:#fff; }
.opportunity-kpi span { display:block; color:var(--forest); font-size:.61rem; font-weight:900; letter-spacing:.06em; text-transform:uppercase; }
.opportunity-kpi strong { display:block; margin:.12rem 0; color:var(--navy); font-size:1.18rem; }
.opportunity-kpi small { color:var(--ink); font-size:.64rem; }
.matchup-trend-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.58rem; margin:.72rem 0; }
.matchup-trend-stat { min-height:92px; padding:.7rem; border:1px solid #d4dcdf; border-radius:12px; background:#fff; }
.matchup-trend-stat span { display:block; color:var(--forest); font-size:.6rem; font-weight:900; letter-spacing:.055em; text-transform:uppercase; }
.matchup-trend-stat strong { display:block; margin:.18rem 0; color:var(--navy); font-size:1.08rem; line-height:1.1; }
.matchup-trend-stat small { display:block; color:var(--ink); font-size:.63rem; line-height:1.35; }
.matchup-verdict { margin:.65rem 0; overflow:hidden; border:1px solid #bfd0d8; border-radius:14px; background:#fff; }
.matchup-verdict-head { display:flex; align-items:center; justify-content:space-between; gap:.7rem; padding:.62rem .78rem; background:#002244; color:#fff; }
.matchup-verdict-head b { color:#9ee468; font-size:.7rem; letter-spacing:.07em; text-transform:uppercase; }
.matchup-verdict-head span { padding:.22rem .5rem; border-radius:999px; background:rgba(105,190,40,.17); color:#b8f188; font-size:.62rem; font-weight:900; text-transform:uppercase; }
.matchup-verdict p { margin:0; padding:.72rem .8rem; color:var(--ink); font-size:.73rem; line-height:1.48; }
.matchup-freshness { padding:0 .8rem .68rem; color:var(--muted); font-size:.6rem; }
.st-key-trends_position [role="radiogroup"], .st-key-trends_view [role="radiogroup"] { display:grid !important; gap:.32rem; padding:.32rem; border:1px solid #d4dcdf; border-radius:12px; background:#e8edef; }
.st-key-trends_position [role="radiogroup"] { grid-template-columns:repeat(4,minmax(0,1fr)); }
.st-key-trends_view [role="radiogroup"] { grid-template-columns:repeat(4,minmax(0,1fr)); }
.st-key-trends_position button, .st-key-trends_view button { border:0 !important; background:transparent !important; color:var(--muted) !important; font-weight:800 !important; }
.st-key-trends_position button[aria-checked="true"], .st-key-trends_view button[aria-checked="true"] { background:var(--navy) !important; color:#fff !important; }
.st-key-trends_position button[aria-checked="true"] p, .st-key-trends_view button[aria-checked="true"] p { color:#fff !important; }
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
.panel-insight b { color:var(--forest); text-transform:uppercase; letter-spacing:.06em; font-size:.6rem; white-space:nowrap; }
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
  .block-container { padding:.45rem .85rem 2rem; }
  .hero{display:block}.fresh{text-align:left;margin-top:.7rem}.hero h1{font-size:2.05rem}
  .hero, .warning, .section-copy, .note { width:calc(100vw - 1.7rem) !important; max-width:calc(100vw - 1.7rem) !important; }
  .hero > div, .hero p { width:100% !important; max-width:100% !important; min-width:0 !important; box-sizing:border-box; white-space:normal; overflow-wrap:anywhere; }
  .verdict { min-height:0; padding:1rem; }
  .verdict .name { font-size:1.45rem; }
  .range-tooltip { left:0; transform:none; width:min(250px, 75vw); }
  .label-help .label-tooltip { position:fixed; left:1rem; right:1rem; bottom:1rem; width:auto; }
  [data-testid="stSidebar"] { width:min(18.75rem, 88vw) !important; }
  .header-logo { width:min(170px,62vw); margin-bottom:.35rem; }
  .freshness-bar { flex-wrap:wrap; align-items:flex-start; }
  .freshness-item { flex:1 1 calc(50% - .35rem); border-right:0; padding:.18rem .3rem; white-space:normal; }
  .freshness-reminder { flex:1 0 100%; margin:0; padding:.18rem .3rem 0; text-align:left; border-top:1px solid #e3e8ea; }
  .freshness-item { font-size:.72rem; }
  .freshness-item b { font-size:.62rem; }
  .focused-status { align-items:flex-start; flex-direction:column; gap:.25rem; }
  .mobile-decision-edge { display:block; }
  .desktop-decision-edge { display:none; }
  .st-key-mobile_selection_summary { display:block; margin:.2rem 0 .55rem; }
  .st-key-desktop_selection_cards { display:block; }
  .st-key-desktop_selection_cards [data-testid="stHorizontalBlock"] { gap:.45rem !important; }
  .st-key-desktop_selection_cards [data-testid="stVerticalBlockBorderWrapper"] { border-radius:11px !important; }
  .st-key-desktop_selection_cards [data-testid="stVerticalBlockBorderWrapper"] > div { padding:.55rem .62rem !important; }
  .st-key-desktop_selection_cards [data-testid="stButton"] button { min-height:38px !important; padding:.28rem .5rem !important; font-size:.68rem !important; }
  .st-key-desktop_selection_cards .compare-slot-kicker { display:none; }
  .st-key-desktop_selection_cards .compare-slot-top { margin:0 !important; }
  .st-key-desktop_selection_cards .compare-slot-game { margin:.28rem 0 !important; font-size:.68rem !important; }
  .st-key-desktop_selection_cards .compare-slot-footer { margin-top:.2rem !important; }
  .st-key-mobile_selection_summary [data-testid="stVerticalBlockBorderWrapper"] { border-radius:11px !important; }
  .st-key-mobile_selection_summary [data-testid="stVerticalBlockBorderWrapper"] > div { padding:.48rem .55rem !important; }
  .st-key-mobile_selection_summary [data-testid="stHorizontalBlock"] { align-items:center !important; gap:.48rem !important; }
  .st-key-mobile_selection_summary [data-testid="stButton"] button { min-height:40px !important; padding:.3rem .58rem !important; font-size:.68rem !important; }
  [data-testid="stExpander"] summary { min-height:44px; align-items:center; }
  [data-testid="stButton"] button, [data-testid="stDownloadButton"] button, [data-testid="stLinkButton"] a { min-height:44px; }
  [data-testid="stAppViewContainer"] button { min-height:44px !important; }
  [data-testid="stHorizontalBlock"] { min-width:0 !important; }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { min-width:0 !important; }
  [data-testid="stHorizontalBlock"]:has(.compare-slot-kicker),
  [data-testid="stHorizontalBlock"]:has(.verdict) { flex-wrap:wrap !important; }
  [data-testid="stHorizontalBlock"]:has(.compare-slot-kicker) > [data-testid="stColumn"],
  [data-testid="stHorizontalBlock"]:has(.verdict) > [data-testid="stColumn"] { flex:1 1 100% !important; width:100% !important; }
  .verdict, .projection-board, .form-board, .usage-board, .detail-card-grid, .context-grid { width:100%; max-width:100%; min-width:0; }
  .card-outlook-full, .analysis-detail-section, .reporting-sources, .context-value, .detail-card-row b { overflow-wrap:anywhere; word-break:normal; }
  .reporting-sources a { display:inline-block; min-height:32px; padding:.3rem .1rem; }
  .stPlotlyChart, [data-testid="stPlotlyChart"] { width:100% !important; max-width:100% !important; overflow:hidden; }
  .st-key-comparison_view [role="radiogroup"] { grid-template-columns:repeat(3,minmax(0,1fr)); }
  .freshness-reminder { font-size:.68rem; }
  .game-detail-chip { min-height:1.65rem; font-size:.68rem; }
  .driver-grid { grid-template-columns:1fr; }
  .advanced-stat-grid { grid-template-columns:1fr; }
  .usage-player { grid-template-columns:minmax(170px,.9fr) minmax(160px,1.1fr) 78px; }
  .projection-row,.form-row { grid-template-columns:minmax(165px,.8fr) minmax(230px,1.3fr) 72px; }
  .trend-player-card { grid-template-columns:minmax(220px,1.2fr) repeat(4,minmax(86px,.5fr)); }
}
@media(max-width:520px) {
  [data-testid="stHorizontalBlock"]:has(.st-key-header_brand_mark) {
    flex-wrap:nowrap !important; align-items:center !important; gap:.75rem !important;
  }
  [data-testid="stHorizontalBlock"]:has(.st-key-header_brand_mark) > [data-testid="stColumn"]:first-child {
    flex:0 0 92px !important; width:92px !important; min-width:92px !important;
  }
  [data-testid="stHorizontalBlock"]:has(.st-key-header_brand_mark) > [data-testid="stColumn"]:last-child {
    flex:1 1 auto !important; width:auto !important; min-width:0 !important;
  }
  .st-key-sidebar_brand_mark,
  .st-key-sidebar_brand_mark [data-testid="stImage"],
  .st-key-sidebar_brand_mark [data-testid="stImage"] img { width:68px; }
  .st-key-header_brand_mark,
  .st-key-header_brand_mark [data-testid="stImage"],
  .st-key-header_brand_mark [data-testid="stImage"] img { width:88px; }
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
  .range-tooltip { position:fixed; left:1rem; right:1rem; bottom:1rem; width:auto; max-width:none; transform:none; }
  .actionable-alert-head { align-items:flex-start; flex-direction:column; gap:.18rem; }
  .actionable-alert-time { text-align:left; }
  .context-card-body { grid-template-columns:1fr; }
  .context-item.wide { grid-column:auto; }
  .trend-player-card { grid-template-columns:1fr 1fr; }
  .trend-player-identity { grid-column:1/-1; }
  .trend-stat { min-height:50px; }
  .st-key-trends_controls [data-testid="stHorizontalBlock"] { flex-direction:column !important; gap:.45rem !important; }
  .st-key-trends_controls [data-testid="stColumn"] { width:100% !important; flex:1 1 100% !important; }
  .st-key-trends_position button { min-width:0 !important; padding:.42rem .2rem !important; }
  .st-key-trends_position button p { font-size:.72rem !important; }
  .trend-insight-grid { grid-template-columns:1fr; }
  .trend-insight-card { min-height:0; padding:.52rem .62rem; }
  .game-log-row { grid-template-columns:48px minmax(72px,1fr) repeat(2,minmax(48px,.6fr)); }
  .game-log-row span:nth-child(n+5) { display:none; }
  .fantasy-log-row { grid-template-columns:34px 32px 39px minmax(68px,1fr) minmax(62px,1fr) 24px; gap:.2rem; font-size:.51rem; padding:.38rem .2rem; }
  .trend-week-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .trend-evidence-grid { grid-template-columns:1fr; }
  .opportunity-summary { grid-template-columns:1fr; }
  .matchup-trend-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .st-key-trends_view [role="radiogroup"] { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner=False)
def get_http_session() -> requests.Session:
    """Reuse HTTPS connections for immutable production snapshot downloads."""
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=10, max_retries=1)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def get_snapshot_metadata() -> dict:
    processed = PROJECT_ROOT / "data" / "processed"
    metadata_path = processed / "live_refresh_metadata.json"
    try:
        return read_metadata(get_http_session(), SNAPSHOT_BASE_URL)
    except (requests.RequestException, ValueError):
        if not metadata_path.exists():
            raise FileNotFoundError("A validated production snapshot has not been published.")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["publication_status"] = "offline-local-fallback"
        metadata["injury_freshness_verified"] = False
        metadata["depth_freshness_verified"] = False
        return metadata


def _read_snapshot_parquet(filename: str, publication: dict | None = None) -> pd.DataFrame:
    if publication:
        # No fallback to an unrelated local/current file for a pinned version.
        return pd.read_parquet(BytesIO(verified_payload(get_http_session(), SNAPSHOT_BASE_URL, publication, filename)))
    try:
        response = get_http_session().get(f"{SNAPSHOT_BASE_URL}/{filename}", timeout=(3.05, 12))
        response.raise_for_status()
        return pd.read_parquet(BytesIO(response.content))
    except (requests.RequestException, ValueError, OSError):
        path = PROJECT_ROOT / "data" / "processed" / filename
        if not path.exists():
            raise FileNotFoundError(f"Validated snapshot is missing: {filename}")
        return pd.read_parquet(path)


@st.cache_resource(ttl=300, max_entries=4, show_spinner=False)
def get_published_snapshot(season: int, passing_td_points: int, metadata_json: str) -> tuple[pd.DataFrame, pd.DataFrame, int, str, str, str | None, str]:
    """Load one immutable public snapshot shared safely by all sessions.

    Callers only select or copy rows; they never mutate these frames. Resource
    caching therefore avoids serializing and copying ~4.4 MB of public data on
    every rerun without mixing any user-specific state into the cache.
    """
    metadata = json.loads(metadata_json)
    publication = metadata.get("_publication")
    if int(metadata.get("season", -1)) != season or passing_td_points not in metadata.get("refreshed_qb_passing_td_formats", []):
        raise ValueError("The published snapshot does not match this season or scoring format.")
    # Both files belong to the same validated snapshot and are independent.
    # Downloading them concurrently removes one full network round trip on a
    # cold cache. Injury enrichment is also snapshot-scoped, so doing it here
    # prevents ~1 second of repeated Pandas work on every widget interaction.
    with ThreadPoolExecutor(max_workers=2) as executor:
        board_future = executor.submit(
            _read_snapshot_parquet,
            f"live_start_sit_board_{passing_td_points}pt_current.parquet",
            publication,
        )
        weekly_future = executor.submit(_read_snapshot_parquet, "live_weekly_current.parquet", publication)
        board = apply_injury_scenario(reconcile_board_identities(board_future.result()))
        weekly = weekly_future.result()
    board = repair_qb_display_form(board, weekly, passing_td_points)
    board = guard_forecasts(board)
    provider_status = str(metadata.get("sportsdataio_status", "Snapshot unavailable"))
    provider_refreshed_at = metadata.get("sportsdataio_refreshed_at")
    injury_sources = metadata.get("injury_source_status", {})
    injury_status = f"NFLVERSE · {injury_sources.get('nflverse', 'Unavailable')} | SLEEPER · {injury_sources.get('sleeper', 'Unavailable')}"
    checked_at = metadata.get("refreshed_at", datetime.now(timezone.utc).isoformat())
    refreshed = datetime.fromisoformat(str(checked_at).replace("Z", "+00:00")).strftime("%b %d, %Y · %H:%M UTC")
    return board, weekly, int(metadata["next_week"]), refreshed, provider_status, provider_refreshed_at, injury_status


@st.cache_resource(show_spinner=False)
def snapshot_recovery():
    # Public data references only; bounded to the two supported scoring formats.
    return SnapshotRecovery(max_entries=2)


def production_broadcast_html(
    player_name: str,
    games: list[dict],
    projection: float,
    floor: float,
    ceiling: float,
    season_average: float,
    recent_average: float,
    next_week: int,
) -> str:
    """Responsive weekly production chart with no external chart dependency."""
    payload = json.dumps(games, separators=(",", ":")).replace("</", "<\\/")
    safe_name = html.escape(player_name)
    return f"""
<div id="production-broadcast" class="broadcast-shell" aria-label="{safe_name} weekly PPR performance chart">
  <style>
    * {{ box-sizing:border-box; }}
    html,body {{ margin:0; padding:0; overflow:hidden; background:transparent; font-family:Arial,sans-serif; color:#071b2c; }}
    .broadcast-shell {{ width:100%; min-width:0; overflow:hidden; border:1px solid #cbd6db; border-radius:14px; background:#fff; box-shadow:0 8px 20px rgba(0,34,68,.08); }}
    .broadcast-top {{ display:flex; align-items:center; justify-content:space-between; gap:10px; padding:9px 11px; background:#002244; }}
    .broadcast-title b {{ display:block; color:#fff; font-size:13px; }}
    .broadcast-title span {{ display:block; margin-top:2px; color:#c9d7de; font-size:9px; }}
    .periods {{ display:flex; gap:4px; }}
    .period {{ min-height:31px; padding:5px 9px; border:1px solid rgba(255,255,255,.25); border-radius:8px; background:transparent; color:#dce8ef; font-size:10px; font-weight:800; cursor:pointer; }}
    .period.active {{ border-color:#69be28; background:#69be28; color:#002244; }}
    .chart-wrap {{ position:relative; padding:4px 7px 0; }}
    svg {{ display:block; width:100%; height:190px; overflow:visible; touch-action:manipulation; }}
    .tooltip {{ position:absolute; z-index:5; display:none; max-width:170px; padding:6px 8px; border-radius:8px; background:#002244; color:#fff; font-size:10px; line-height:1.35; pointer-events:none; box-shadow:0 5px 15px rgba(0,34,68,.22); }}
    .controls {{ display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:5px 12px; padding:6px 11px 8px; border-top:1px solid #e1e7e9; color:#50616a; font-size:9px; }}
    .reference-controls {{ display:flex; flex-wrap:wrap; gap:9px; }}
    .reference-controls label {{ display:flex; align-items:center; gap:4px; min-height:28px; cursor:pointer; }}
    .reference-controls input {{ accent-color:#285f18; }}
    .legend {{ display:flex; gap:9px; }}
    .legend span::before {{ content:''; display:inline-block; width:10px; height:3px; margin-right:4px; vertical-align:middle; background:#4b788f; }}
    .legend .projected::before {{ background:#69be28; }}
    @media(max-width:520px) {{
      .broadcast-top {{ align-items:flex-start; padding:8px; }}
      .broadcast-title span {{ max-width:155px; }}
      .period {{ min-height:34px; padding:6px 8px; }}
      svg {{ height:176px; }}
      .controls {{ padding:5px 8px 7px; }}
      .legend {{ width:100%; justify-content:flex-end; }}
    }}
  </style>
  <div class="broadcast-top">
    <div class="broadcast-title"><b>{safe_name} · weekly PPR</b><span>Actual results stay separate from the Week {next_week} projection</span></div>
    <div class="periods" role="group" aria-label="Trend time period"><button class="period active" data-period="all">Season</button><button class="period" data-period="5">Last 5</button><button class="period" data-period="3">Last 3</button></div>
  </div>
  <div class="chart-wrap"><svg id="production-chart" viewBox="0 0 720 210" role="img" aria-label="Weekly PPR results and upcoming projection"></svg><div class="tooltip" id="production-tooltip"></div></div>
  <div class="controls"><div class="reference-controls"><label><input id="season-line" type="checkbox" checked>Season avg</label><label><input id="recent-line" type="checkbox" checked>Recent avg</label><span>Missing weeks are left open</span></div><div class="legend"><span>Actual</span><span class="projected">Projection range</span></div></div>
</div>
<script>
(() => {{
  const games = {payload};
  const root = document.getElementById('production-broadcast');
  const svg = root.querySelector('#production-chart');
  const tooltip = root.querySelector('#production-tooltip');
  let period = 'all';
  const projection = {projection:.3f};
  const floor = {floor:.3f};
  const ceiling = {ceiling:.3f};
  const seasonAverage = {season_average:.3f};
  const recentAverage = {recent_average:.3f};
  const NS = 'http://www.w3.org/2000/svg';
  function node(tag, attributes={{}}, text='') {{ const element=document.createElementNS(NS,tag); Object.entries(attributes).forEach(([key,value])=>element.setAttribute(key,value)); if(text) element.textContent=text; return element; }}
  function showTooltip(event, copy) {{ tooltip.textContent=copy; tooltip.style.display='block'; const box=root.getBoundingClientRect(); tooltip.style.left=`${{Math.min(box.width-178,Math.max(5,event.clientX-box.left+8))}}px`; tooltip.style.top=`${{Math.max(5,event.clientY-box.top-46)}}px`; }}
  function hideTooltip() {{ tooltip.style.display='none'; }}
  function render() {{
    let visible = period === 'all' ? games : games.slice(-Number(period));
    svg.innerHTML=''; hideTooltip();
    const width=720, height=210, left=38, right=25, top=16, bottom=34;
    const values=visible.filter(item=>item.score!==null).map(item=>Number(item.score)).concat([projection,floor,ceiling,seasonAverage,recentAverage]);
    const max=Math.max(5,...values)*1.12;
    const xStep=(width-left-right)/Math.max(1,visible.length);
    const x=index=>left+xStep*index;
    const y=value=>top+(height-top-bottom)*(1-Number(value)/max);
    [0,.25,.5,.75,1].forEach(fraction=>{{ const value=max*fraction; const yy=y(value); svg.appendChild(node('line',{{x1:left,y1:yy,x2:width-right,y2:yy,stroke:'#e1e7e9','stroke-width':'1'}})); svg.appendChild(node('text',{{x:left-5,y:yy+3,'text-anchor':'end',fill:'#66757d','font-size':'9'}},value.toFixed(0))); }});
    const showSeason=root.querySelector('#season-line').checked;
    const showRecent=root.querySelector('#recent-line').checked;
    [[showSeason,seasonAverage,'#68777f','6 5','Season'],[showRecent,recentAverage,'#285f18','2 4','Recent']].forEach(([show,value,color,dash,label])=>{{ if(!show)return; const yy=y(value); svg.appendChild(node('line',{{x1:left,y1:yy,x2:width-right,y2:yy,stroke:color,'stroke-width':'1.5','stroke-dasharray':dash}})); svg.appendChild(node('text',{{x:width-right,y:yy-4,'text-anchor':'end',fill:color,'font-size':'9','font-weight':'700'}},`${{label}} ${{Number(value).toFixed(1)}}`)); }});
    let segment=[];
    function flush() {{ if(segment.length>1) svg.appendChild(node('polyline',{{points:segment.join(' '),fill:'none',stroke:'#4b788f','stroke-width':'4','stroke-linecap':'round','stroke-linejoin':'round'}})); segment=[]; }}
    visible.forEach((game,index)=>{{
      const xx=x(index);
      svg.appendChild(node('text',{{x:xx,y:height-11,'text-anchor':'middle',fill:'#66757d','font-size':'9'}},`W${{game.week}}`));
      if(game.score===null) {{ flush(); svg.appendChild(node('circle',{{cx:xx,cy:y(0),r:'3',fill:'#fff',stroke:'#aeb9be','stroke-width':'1.5'}})); return; }}
      const yy=y(game.score); segment.push(`${{xx}},${{yy}}`);
      const point=node('circle',{{cx:xx,cy:yy,r:'5',fill:'#fff',stroke:'#4b788f','stroke-width':'3',tabindex:'0'}});
      const context=`Week ${{game.week}} · ${{Number(game.score).toFixed(1)}} PPR${{game.opponent?' vs '+game.opponent:''}}`;
      point.addEventListener('pointerenter',event=>showTooltip(event,context)); point.addEventListener('pointerleave',hideTooltip); point.addEventListener('click',event=>showTooltip(event,context));
      svg.appendChild(point);
    }}); flush();
    const projectionX=x(visible.length);
    const range=node('line',{{x1:projectionX,y1:y(ceiling),x2:projectionX,y2:y(floor),stroke:'#69be28','stroke-width':'8','stroke-linecap':'round',opacity:'.35'}}); svg.appendChild(range);
    svg.appendChild(node('line',{{x1:projectionX-6,y1:y(ceiling),x2:projectionX+6,y2:y(ceiling),stroke:'#285f18','stroke-width':'2'}}));
    svg.appendChild(node('line',{{x1:projectionX-6,y1:y(floor),x2:projectionX+6,y2:y(floor),stroke:'#285f18','stroke-width':'2'}}));
    const projectionPoint=node('circle',{{cx:projectionX,cy:y(projection),r:'7',fill:'#69be28',stroke:'#002244','stroke-width':'3',tabindex:'0'}});
    const projectionCopy=`Week {next_week} projection · ${{projection.toFixed(1)}} PPR · floor ${{floor.toFixed(1)}} · ceiling ${{ceiling.toFixed(1)}}`;
    projectionPoint.addEventListener('pointerenter',event=>showTooltip(event,projectionCopy)); projectionPoint.addEventListener('pointerleave',hideTooltip); projectionPoint.addEventListener('click',event=>showTooltip(event,projectionCopy)); svg.appendChild(projectionPoint);
    svg.appendChild(node('text',{{x:projectionX,y:height-11,'text-anchor':'middle',fill:'#285f18','font-size':'9','font-weight':'800'}},'PROJ'));
  }}
  root.querySelectorAll('.period').forEach(button=>button.addEventListener('click',()=>{{ period=button.dataset.period; root.querySelectorAll('.period').forEach(item=>item.classList.toggle('active',item===button)); render(); }}));
  root.querySelector('#season-line').addEventListener('change',render); root.querySelector('#recent-line').addEventListener('change',render);
  render();
}})();
</script>
"""


def opportunity_tracker_html(player_name: str, games: list[dict], opportunity_label: str, season_average: float, recent_average: float, snap_share: str, role_label: str) -> str:
    """Compact, paged opportunity chart that fits without internal scrolling."""
    payload = json.dumps(games, separators=(",", ":")).replace("</", "<\\/")
    safe_name = html.escape(player_name)
    safe_metric = html.escape(opportunity_label)
    safe_role = html.escape(role_label)
    return f"""
<div id="opportunity-tracker" class="opportunity-shell" aria-label="{safe_name} weekly {safe_metric.lower()} trend">
  <style>
    * {{ box-sizing:border-box; }}
    html,body {{ margin:0; padding:0; overflow:hidden; background:transparent; font-family:Arial,sans-serif; color:#071b2c; }}
    .opportunity-shell {{ width:100%; min-width:0; overflow:hidden; border:1px solid #cbd6db; border-radius:13px; background:#fff; }}
    .opportunity-head {{ display:flex; align-items:center; justify-content:space-between; gap:10px; padding:9px 12px; background:#002244; }}
    .opportunity-head div {{ min-width:0; }}
    .opportunity-head b {{ display:block; overflow:hidden; color:#fff; font-size:14px; text-overflow:ellipsis; white-space:nowrap; }}
    .opportunity-head span {{ display:block; margin-top:2px; color:#c9d7de; font-size:10px; }}
    .role {{ flex:0 0 auto; padding:4px 8px; border-radius:999px; background:rgba(105,190,40,.18); color:#b8f188 !important; font-size:10px !important; font-weight:800; text-transform:uppercase; }}
    .chart-row {{ display:grid; grid-template-columns:34px minmax(0,1fr) 34px; align-items:center; gap:7px; padding:8px 9px 5px; }}
    .nav {{ display:grid; place-items:center; width:32px; height:38px; border:1px solid #ccd6da; border-radius:8px; background:#f0f4f5; color:#002244; font-size:20px; cursor:pointer; }}
    .nav:disabled {{ opacity:.3; cursor:default; }}
    .plot {{ position:relative; height:112px; min-width:0; border-bottom:1px solid #aebbc1; }}
    .average {{ position:absolute; left:0; right:0; border-top:2px dashed #68777f; z-index:1; }}
    .average span {{ position:absolute; top:-15px; left:2px; padding:1px 4px; background:rgba(255,255,255,.93); color:#4d5b62; font-size:9px; }}
    .bars {{ position:absolute; inset:0; display:grid; align-items:end; gap:7px; padding:10px 4px 0; z-index:2; }}
    .bar-item {{ display:flex; min-width:0; height:100%; flex-direction:column; justify-content:flex-end; align-items:center; }}
    .bar-value {{ margin-bottom:3px; color:#002244; font-size:10px; font-weight:800; }}
    .bar {{ width:min(34px,72%); min-height:3px; border-radius:5px 5px 0 0; background:#4b788f; }}
    .bar-item.latest .bar {{ background:#69be28; }}
    .bar-week {{ margin-top:3px; color:#5f6b73; font-size:9px; }}
    .summary {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1px; margin-top:5px; background:#d9e1e4; border-top:1px solid #d9e1e4; }}
    .summary div {{ min-width:0; padding:6px 8px; background:#f5f8f9; }}
    .summary span {{ display:block; color:#285f18; font-size:9px; font-weight:800; letter-spacing:.04em; text-transform:uppercase; }}
    .summary b {{ display:block; margin-top:1px; overflow:hidden; color:#002244; font-size:13px; text-overflow:ellipsis; white-space:nowrap; }}
    .hint {{ display:flex; justify-content:space-between; gap:8px; padding:5px 10px 7px; color:#65727a; font-size:9px; }}
    @media(max-width:520px) {{
      .opportunity-head {{ padding:8px 9px; }}
      .chart-row {{ grid-template-columns:32px minmax(0,1fr) 32px; gap:4px; padding:7px 6px 4px; }}
      .plot {{ height:104px; }}
      .nav {{ width:30px; height:36px; }}
      .summary div {{ padding:5px 6px; }}
    }}
  </style>
  <div class="opportunity-head"><div><b>{safe_name} · season opportunity</b><span>{safe_metric} by week · dashed line is the season average</span></div><span class="role">{safe_role}</span></div>
  <div class="chart-row" id="opportunity-swipe-zone">
    <button class="nav" id="opportunity-previous" type="button" aria-label="Show earlier weeks">&#8249;</button>
    <div class="plot"><div class="average" id="opportunity-average"><span>Avg {season_average:.1f}</span></div><div class="bars" id="opportunity-bars"></div></div>
    <button class="nav" id="opportunity-next" type="button" aria-label="Show later weeks">&#8250;</button>
  </div>
  <div class="summary"><div><span>Latest</span><b>{games[-1]['value'] if games else 0:.0f} {safe_metric}</b></div><div><span>Recent 3</span><b>{recent_average:.1f} per game</b></div><div><span>Snap share</span><b>{html.escape(snap_share)}</b></div></div>
  <div class="hint"><span>Latest week highlighted</span><span>Use arrows or swipe</span></div>
</div>
<script>
(() => {{
  const games = {payload};
  const root = document.getElementById('opportunity-tracker');
  const bars = root.querySelector('#opportunity-bars');
  const average = root.querySelector('#opportunity-average');
  const previous = root.querySelector('#opportunity-previous');
  const next = root.querySelector('#opportunity-next');
  let page = 0;
  function count() {{ return window.innerWidth <= 520 ? 4 : 6; }}
  function pages() {{ return Math.max(1, Math.ceil(games.length / count())); }}
  function render() {{
    page = Math.min(page, pages() - 1);
    const size = count();
    const start = page * size;
    const visible = games.slice(start, start + size);
    const maxValue = Math.max(1, Number({season_average:.3f}), ...games.map(game => Number(game.value))) * 1.16;
    bars.style.gridTemplateColumns = `repeat(${{Math.max(1, visible.length)}},minmax(0,1fr))`;
    average.style.bottom = `${{Math.min(94, ({season_average:.3f} / maxValue) * 100)}}%`;
    bars.innerHTML = '';
    visible.forEach((game, offset) => {{
      const item = document.createElement('div');
      const isLatest = start + offset === games.length - 1;
      item.className = `bar-item${{isLatest ? ' latest' : ''}}`;
      const height = Math.max(3, (Number(game.value) / maxValue) * 88);
      item.innerHTML = `<div class="bar-value">${{Number(game.value).toFixed(0)}}</div><div class="bar" style="height:${{height}}%"></div><div class="bar-week">W${{game.week}}</div>`;
      bars.appendChild(item);
    }});
    previous.disabled = page === 0;
    next.disabled = page >= pages() - 1;
  }}
  previous.addEventListener('click', () => {{ if (page > 0) {{ page -= 1; render(); }} }});
  next.addEventListener('click', () => {{ if (page < pages() - 1) {{ page += 1; render(); }} }});
  let startX = null;
  const zone = root.querySelector('#opportunity-swipe-zone');
  zone.addEventListener('touchstart', event => {{ startX = event.changedTouches[0].clientX; }}, {{passive:true}});
  zone.addEventListener('touchend', event => {{
    if (startX === null) return;
    const distance = event.changedTouches[0].clientX - startX;
    if (Math.abs(distance) > 38) {{
      if (distance < 0 && page < pages() - 1) page += 1;
      if (distance > 0 && page > 0) page -= 1;
      render();
    }}
    startX = null;
  }}, {{passive:true}});
  window.addEventListener('resize', render);
  render();
}})();
</script>
"""


def player_photo_html(value: object, label: object) -> str:
    """Render a safe CSS headshot with a compact initials fallback."""
    name = str(label or "Player").strip()
    initials = "".join(part[0] for part in name.split()[:2] if part)[:2].upper() or "P"
    url = "" if value is None or pd.isna(value) else str(value).strip()
    if not url.startswith("https://sleepercdn.com/content/nfl/players/") or not url.endswith(".jpg"):
        return (
            f'<span class="player-photo fallback" role="img" '
            f'aria-label="No roster photo available for {html.escape(name, quote=True)}">{html.escape(initials)}</span>'
        )
    return (
        f'<span class="player-photo" role="img" aria-label="{html.escape(name, quote=True)} roster photo" '
        f'style="background-image:url(&quot;{html.escape(url, quote=True)}&quot;)"></span>'
    )


def explained_term(label: object, explanation: object, class_name: str = "") -> str:
    """Render the shared hover, keyboard-focus, and mobile-tap help treatment."""
    classes = f"explained-term label-help {class_name}".strip()
    return (
        f'<span class="{html.escape(classes, quote=True)}" tabindex="0">{html.escape(str(label))}'
        f'<span class="label-tooltip" role="tooltip">{html.escape(str(explanation))}</span></span>'
    )


@st.cache_data(ttl=60, max_entries=24, show_spinner=False)
def build_share_image(compare: pd.DataFrame, week: int, scoring_label: str, refreshed: str) -> bytes:
    """Create a compact, social-friendly PNG for the current comparison."""
    # Pillow is only needed after the user opens sharing and requests the card.
    from PIL import Image, ImageDraw, ImageFont

    ordered = compare.sort_values("median_ppr", ascending=False).head(3).reset_index(drop=True)
    leader = ordered.iloc[0]
    margin = leader_margin(ordered["median_ppr"].tolist())
    recommendation = (
        f'{leader["player"]} is our preferred start'
        if len(ordered) == 1
        else f'{leader["player"]} leads by {margin:.1f} PPR'
    )
    if recommendation_restriction(leader):
        recommendation = 'Baseline only · verify eligibility before starting'
    image = Image.new("RGB", (1200, 630), "#002244")
    draw = ImageDraw.Draw(image)
    font_path = "C:/Windows/Fonts/arial.ttf"
    bold_path = "C:/Windows/Fonts/arialbd.ttf"
    def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        try:
            return ImageFont.truetype(bold_path if bold else font_path, size)
        except OSError:
            return ImageFont.load_default()
    draw.text((65, 48), "THE SUNDAY DECISION LAB", fill="#9ee468", font=font(32, True))
    draw.text((65, 96), f"WEEK {week} COMPARISON · {scoring_label.upper()}", fill="#cbd5da", font=font(16, True))
    draw.text((65, 145), recommendation, fill="white", font=font(31, True))
    if len(ordered) > 1:
        draw.text((65, 188), "CLOSE CALL" if margin < CLOSE_CALL_THRESHOLD_PPR else "CLEARER PROJECTED EDGE", fill="#9ee468", font=font(15, True))
    row_top = 250
    for index, row in ordered.iterrows():
        y = row_top + index * 98
        draw.rounded_rectangle((60, y, 1140, y + 78), radius=12, fill="#f7fafb" if index else "#123a59")
        primary = "white" if index == 0 else "#071b2c"
        secondary = "#cbd5da" if index == 0 else "#4a5962"
        accent = "#9ee468" if index == 0 else "#397f18"
        draw.text((88, y + 12), str(row["player"]), fill=primary, font=font(22, True))
        draw.text((88, y + 45), f'{row.get("team", "")} · {row.get("position", "")} vs {row.get("next_opponent", "")}', fill=secondary, font=font(14))
        draw.text((835, y + 15), f'{float(row["median_ppr"]):.1f} PPR', fill=accent, font=font(25, True))
        draw.text((1000, y + 48), f'{float(row["floor_ppr"]):.1f}–{float(row["ceiling_ppr"]):.1f}', fill=secondary, font=font(14, True))
    draw.text((65, 555), "Ranges use empirical residual offsets; not guaranteed individual quantiles.", fill="#cbd5da", font=font(14))
    draw.text((65, 585), f"Data snapshot: {refreshed}", fill="#a5acaf", font=font(13))
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def dismiss_onboarding() -> None:
    """Close the guide immediately and persist that choice on the next render."""
    st.session_state["onboarding_seen"] = True
    st.session_state["onboarding_force_open"] = False
    st.session_state["onboarding_pending_persist"] = True


@st.dialog("Welcome to The Sunday Decision Lab")
def show_onboarding() -> None:
    """Explain the core workflow and the interpretation rules every user needs."""
    st.markdown(
        '<div class="onboarding-intro">Build a focused lineup comparison in three quick steps.</div>'
        '<div class="onboarding-steps">'
        '<div class="onboarding-step"><div class="onboarding-number">1</div><div><strong>Choose a position</strong><span>Select QB, RB, WR, TE, or FLEX. FLEX lets you compare running backs, wide receivers, and tight ends together.</span></div></div>'
        '<div class="onboarding-step"><div class="onboarding-number">2</div><div><strong>Select up to three players</strong><span>Use the player slots and search panel. Replace any selection with one click.</span></div></div>'
        '<div class="onboarding-step"><div class="onboarding-number">3</div><div><strong>Review the recommendation</strong><span>Start with the Decision Edge and player cards, then open supporting evidence only when you want more detail.</span></div></div>'
        '</div>'
        '<div class="onboarding-must-know"><strong>Must know before making your call</strong><ul>'
        '<li><b>Start and Sit are relative only to the players you selected.</b> “Sit” is not an automatic bench recommendation for every league.</li>'
        '<li><b>Injuries, practice reports, weather, journalism, and market data are supporting context.</b> They do not change the baseline ranking.</li>'
        '<li><b>Floor and ceiling are P10 and P90 estimates—not guarantees.</b> Actual results can finish outside the displayed range.</li>'
        '<li><b>Always check the data timestamp and official inactive list before kickoff.</b> Late status changes can occur after the latest refresh.</li>'
        '</ul></div>',
        unsafe_allow_html=True,
    )
    if st.button("Got it — start comparing", type="primary", width="stretch"):
        dismiss_onboarding()
        # Dialog interactions rerun only the dialog fragment by default. Force a
        # full-app rerun so the parent visibility condition closes it at once.
        st.rerun(scope="app")


PAGE_ROUTES = {
    "home": "Home", "command-center": "Sunday Command Center", "decision-room": "Decision Room",
    "player-trends": "Player Trends", "how-it-works": "How It Works",
}
ROUTE_BY_PAGE = {value: key for key, value in PAGE_ROUTES.items()}
requested_route = str(st.query_params.get("view", "home"))
requested_page = PAGE_ROUTES.get(requested_route, "Home")
if st.session_state.get("_last_requested_route") != requested_route:
    st.session_state["main_navigation"] = requested_page
    st.session_state["_last_requested_route"] = requested_route


def _navigation_changed() -> None:
    selected = st.session_state.get("main_navigation", "Home")
    st.query_params["view"] = ROUTE_BY_PAGE.get(selected, "home")
    st.session_state["_last_requested_route"] = st.query_params["view"]


with st.sidebar:
    with st.container(key="sidebar_brand_mark"):
        st.image(str(BRAND_ICON), width=78)
    st.markdown('<div class="sidebar-brand">THE SUNDAY <span>DECISION</span> LAB</div>', unsafe_allow_html=True)
    st.caption("Your weekly lineup call")
    page = st.radio("View", ["Home", "Sunday Command Center", "Decision Room", "Player Trends", "How It Works"], key="main_navigation", on_change=_navigation_changed, label_visibility="collapsed")
    no_clutter_mode = st.toggle(
        "No-clutter mode",
        value=True,
        help="Keeps the recommendation, player cards, essential status, and comparison up front. Reporting and advanced statistics stay available on request.",
        key="no_clutter_mode",
    )
    st.caption("Answer first · deeper evidence when you want it" if no_clutter_mode else "Full dashboard view")
    if st.button("Quick start guide", width="stretch"):
        st.session_state["onboarding_seen"] = False
        st.session_state["onboarding_force_open"] = True
        if page != "Decision Room":
            st.query_params["view"] = "decision-room"
        st.rerun()

browser_storage = None
persisted_onboarding_seen = True
if page == "Decision Room":
    if "onboarding_seen" not in st.session_state:
        # Browser storage is relevant only to the Decision Room guide. Mounting
        # this custom component on every public page caused an avoidable second
        # render and delayed the mobile landing page's largest contentful paint.
        browser_storage = LocalStorage(key="sdl_browser_preferences")
        persisted_onboarding_seen = str(browser_storage.getItem("sdl_onboarding_dismissed")).casefold() == "true"
    else:
        persisted_onboarding_seen = bool(st.session_state["onboarding_seen"])
    if st.session_state.get("onboarding_pending_persist", False):
        if browser_storage is None:
            browser_storage = LocalStorage(key="sdl_browser_preferences")
        browser_storage.setItem("sdl_onboarding_dismissed", "true", key="persist_onboarding_dismissal")
        st.session_state["onboarding_pending_persist"] = False
if "onboarding_seen" not in st.session_state:
    st.session_state["onboarding_seen"] = persisted_onboarding_seen
if "onboarding_force_open" not in st.session_state:
    st.session_state["onboarding_force_open"] = False
if persisted_onboarding_seen and not st.session_state["onboarding_force_open"]:
    st.session_state["onboarding_seen"] = True
if page == "Decision Room" and (st.session_state["onboarding_force_open"] or not st.session_state["onboarding_seen"]):
    show_onboarding()
season = SEASON

# Authentication is the only data needed for a signed-out Command Center.
# Gate here so login/recovery does not download and deserialize the board and
# weekly history before the user has a private roster to view.
command_center_api_client = None
command_center_session = None
if page == "Sunday Command Center":
    supabase_url, supabase_key = account_config(st.secrets)
    if not supabase_url or not supabase_key:
        st.error("The account service has not been configured for this environment.")
        mobile_navigation()
        st.stop()
    command_center_api_client = command_center_api(supabase_url, supabase_key)
    command_center_session = authenticate_command_center(command_center_api_client, APP_BASE_URL)
    if not command_center_session:
        mobile_navigation()
        st.stop()

header_metadata = get_snapshot_metadata()
header_week = int(header_metadata.get("next_week", 0))
header_checked = datetime.fromisoformat(str(header_metadata.get("refreshed_at", datetime.now(timezone.utc).isoformat())).replace("Z", "+00:00"))
header_age_minutes = max(0, int((datetime.now(timezone.utc) - header_checked.astimezone(timezone.utc)).total_seconds() // 60))
context_checked = datetime.fromisoformat(str(header_metadata.get("context_refreshed_at", header_metadata.get("sportsdataio_refreshed_at", header_checked.isoformat()))).replace("Z", "+00:00"))
context_age_minutes = max(0, int((datetime.now(timezone.utc) - context_checked.astimezone(timezone.utc)).total_seconds() // 60))
shared_qb_points = str(st.query_params.get("qb", "4"))
shared_qb_index = 1 if shared_qb_points == "6" else 0
header_copy = {
    "Home": ("The Sunday Decision Lab", "Make a faster, evidence-backed fantasy football lineup decision."),
    "Sunday Command Center": ("Sunday Command Center", "Save your teams and see the lineup actions that matter before kickoff."),
    "Decision Room": ("Player Comparison", "Compare up to three players and make the final lineup call."),
    "Player Trends": ("Player Trends", "Track current form, repeatable opportunity, and the next-week outlook."),
    "How It Works": ("How It Works", "See what shapes our projections, what stays informational, and where the data comes from."),
}
header_title, header_description = header_copy[page]

if page == "Player Trends":
    st.markdown(
        """<style>
        .header-details p { margin:.08rem 0 .24rem !important; }
        .header-details .hero-subtitle { font-size:1.05rem !important; }
        </style>""",
        unsafe_allow_html=True,
    )

if page in {"Home", "Sunday Command Center"}:
    QB_PASS_TD_POINTS = int(shared_qb_points) if shared_qb_points in {"4", "6"} else 4
else:
    with st.container():
        st.markdown('<h1 class="sr-only">The Sunday Decision Lab</h1>', unsafe_allow_html=True)
        header_left, header_right = st.columns([.24, 1.76], gap="medium", vertical_alignment="center")
        with header_left:
            with st.container(key="header_brand_mark"):
                st.image(str(BRAND_LOGO), width=168)
        with header_right:
            st.markdown(
                f'<div class="header-details"><div class="eyebrow">Week {header_week} · {season} · Full PPR</div>'
                f'<div class="hero-subtitle">{html.escape(header_title)}</div>'
                f'<p>{html.escape(header_description)}</p>'
                '<div class="settings-kicker">QB passing touchdown scoring</div></div>',
                unsafe_allow_html=True,
            )
            qb_td_label = st.radio("QB passing touchdown scoring", ["4 points", "6 points"], index=shared_qb_index, horizontal=True, label_visibility="collapsed")
            QB_PASS_TD_POINTS = int(qb_td_label.split()[0])

try:
    with st.spinner("Updating weekly stats and matchups…"):
        snapshot, header_metadata, snapshot_restored = snapshot_recovery().load(
            season, QB_PASS_TD_POINTS, header_metadata,
            lambda snapshot_season, scoring, metadata: get_published_snapshot(
                snapshot_season, scoring, json.dumps(metadata, sort_keys=True)),
        )
        BOARD, WEEKLY, NEXT_WEEK, REFRESHED, PROVIDER_STATUS, PROVIDER_REFRESHED_AT, INJURY_SOURCE_STATUS = snapshot
        # Freshness indicators must describe the recovered data, not the failed
        # candidate whose metadata was inspected before loading the assets.
        header_week = int(header_metadata.get("next_week", NEXT_WEEK))
        header_checked = datetime.fromisoformat(str(header_metadata.get("refreshed_at", datetime.now(timezone.utc).isoformat())).replace("Z", "+00:00"))
        context_checked = datetime.fromisoformat(str(header_metadata.get("context_refreshed_at", header_metadata.get("sportsdataio_refreshed_at", header_checked.isoformat()))).replace("Z", "+00:00"))
    if snapshot_restored:
        st.warning("Update unavailable. Showing the last fully validated snapshot with its original timestamp. Verify current injuries and availability before changing your lineup.")
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
            get_snapshot_metadata.clear()
            get_published_snapshot.clear()
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

mobile_navigation()

if page == "Home":
    render_home(BOARD, header_metadata, season)

elif page == "Sunday Command Center":
    render_command_center(command_center_api_client, APP_BASE_URL, season, BOARD, WEEKLY, header_metadata, session=command_center_session)

elif page == "Decision Room":
    context_age_minutes, context_is_stale = context_freshness(PROVIDER_REFRESHED_AT)
    source_verified = header_metadata.get("injury_freshness_verified") is True and header_metadata.get("depth_freshness_verified") is True
    context_is_stale = context_is_stale or not source_verified
    context_value = "Needs confirmation" if context_is_stale else "Current"
    context_detail = "Unavailable" if context_age_minutes is None else f"Retrieved {context_age_minutes} min ago; report freshness {'verified' if source_verified else 'unverified'}"
    high_frequency_day = datetime.now().weekday() in {0, 3, 6}
    next_refresh_copy = "Game-window monitoring" if high_frequency_day else "6 AM / 5 PM Central"
    if no_clutter_mode:
        essential_status = (
            f'<span class="status-dot"></span><b>Data checked:</b> projections {header_age_minutes}m ago · '
            f'live context {context_age_minutes}m ago'
        )
        caution = '<b>Action:</b> Confirm weather, depth charts, and official inactives before kickoff.' if context_is_stale else 'Confirm official inactives before kickoff.'
        st.markdown(
            f'<div class="focused-status{" status-caution" if context_is_stale else ""}"><span>{essential_status}</span><span>{caution}</span></div>',
            unsafe_allow_html=True,
        )
    else:
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
    shared_position = str(st.query_params.get("position", "WR")).upper()
    if shared_position not in {"QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"}:
        shared_position = "WR"
    position = st.segmented_control("Position", ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"], default=shared_position, key="position_selector")
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
            shared_players = [value.strip() for value in str(st.query_params.get("players", "")).split("|") if value.strip()]
            valid_shared_players = [name for name in shared_players if name in valid_names][:3]
            # New visitors should make an intentional comparison rather than
            # inheriting demo players. Shared links remain restorable.
            st.session_state[selection_key] = valid_shared_players
        st.session_state[selection_key] = [name for name in st.session_state[selection_key] if name in valid_names][:3]
        if replacement_key not in st.session_state:
            st.session_state[replacement_key] = None
        search_version_key = f"smart_search_version_{position}"
        if search_version_key not in st.session_state:
            st.session_state[search_version_key] = 0
        names = list(st.session_state[selection_key])
        replacement_index = st.session_state[replacement_key]
        if replacement_index is not None and (replacement_index < 0 or replacement_index >= len(names)):
            replacement_index = None
            st.session_state[replacement_key] = None

        preview_compare = pool.loc[pool["player"].isin(names)].sort_values("projected_ppr", ascending=False)
        decision_edge_markup = ""
        if not preview_compare.empty:
            preview_leader = preview_compare.iloc[0]
            preview_spread = leader_margin(preview_compare["median_ppr"].tolist())
            preview_unavailable = bool(recommendation_restriction(preview_leader))
            if preview_unavailable:
                preview_title = f'{preview_leader["player"]} is unavailable · baseline comparison only'
                preview_copy = "Do not start an unavailable player. These unchanged point estimates are not an actionable lineup recommendation."
                preview_badge = "Lineup action needed"
            elif len(preview_compare) == 1:
                preview_title = f'{preview_leader["player"]} · {float(preview_leader["median_ppr"]):.1f} projected PPR'
                preview_copy = "Add another player to see the projected advantage."
                preview_badge = "1 player selected"
            else:
                preview_title = f'{preview_leader["player"]} leads by {preview_spread:.1f} PPR'
                preview_copy = "The projections are close—treat this as a lean." if preview_spread < CLOSE_CALL_THRESHOLD_PPR else "We see a meaningful projected advantage."
                preview_badge = "Close call" if preview_spread < CLOSE_CALL_THRESHOLD_PPR else "Clearer edge"
            decision_edge_markup = (
                '<div class="decision-edge">'
                f'<div class="decision-edge-main"><div class="decision-edge-label">Week {NEXT_WEEK} decision edge</div>'
                f'<div class="decision-edge-title">{html.escape(preview_title)}</div>'
                f'<div class="decision-edge-copy">{html.escape(preview_copy)}</div></div>'
                f'<div class="decision-edge-badge">{html.escape(preview_badge)}</div>'
                '</div>'
            )
            st.markdown(f'<div class="mobile-decision-edge">{decision_edge_markup}</div>', unsafe_allow_html=True)

        st.markdown(f'<div class="comparison-count">Comparison lineup · {len(names)} of 3 slots filled</div>', unsafe_allow_html=True)
        with st.container(key="desktop_selection_cards"):
            slot_columns = st.columns(3)
            for slot_index, slot_column in enumerate(slot_columns):
                with slot_column:
                    with st.container(border=True):
                        if slot_index < len(names):
                            selected_row = pool.loc[pool["player"].eq(names[slot_index])].iloc[0]
                            availability = selection_availability_summary(selected_row)
                            limited_sample = bool(selected_row.get("limited_sample_role", False)) or str(selected_row.get("confidence", "")).casefold() == "limited sample"
                            sample_badge = explained_term(
                                "Limited sample",
                                "This player lacks enough personal workload history, so the projection leans on position, team environment, and verified depth-chart role priors with a wider range.",
                                "limited-sample-pill",
                            ) if limited_sample else ""
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
                                f'<div class="compare-slot-footer"><span class="compare-slot-projection">{float(selected_row["median_ppr"]):.1f} projected PPR</span>{sample_badge}<span class="availability-pill {availability_class}">{html.escape(availability)}</span></div>',
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

        if not preview_compare.empty:
            st.markdown(
                f'<div class="desktop-decision-edge">{decision_edge_markup}</div>',
                unsafe_allow_html=True,
            )
            # Expander bodies execute even while visually closed. A toggle
            # provides the same disclosure behavior while keeping image
            # generation and the clipboard component genuinely lazy.
            if st.toggle(
                "Share this comparison",
                key=f"share_comparison_{position}",
                help="Create a restorable link or downloadable comparison card.",
            ):
                st.caption("Copy a restorable comparison link or download a ready-to-share image.")
                share_query = urlencode(
                    {
                        "position": position,
                        "players": "|".join(names),
                        "qb": QB_PASS_TD_POINTS,
                    }
                )
                share_url = f"{APP_BASE_URL}?{share_query}"
                st.markdown("**Shareable link**")
                st.code(share_url, language=None)
                safe_share_url = json.dumps(share_url)
                components.html(
                    f"""
                    <button id="copy-comparison-link" type="button">Copy link</button>
                    <script>
                    const button = document.getElementById("copy-comparison-link");
                    const shareUrl = {safe_share_url};
                    button.addEventListener("click", async () => {{
                      try {{
                        await navigator.clipboard.writeText(shareUrl);
                      }} catch (error) {{
                        const fallback = document.createElement("textarea");
                        fallback.value = shareUrl;
                        fallback.style.position = "fixed";
                        fallback.style.opacity = "0";
                        document.body.appendChild(fallback);
                        fallback.select();
                        document.execCommand("copy");
                        fallback.remove();
                      }}
                      button.textContent = "Copied!";
                      button.classList.add("copied");
                      window.setTimeout(() => {{
                        button.textContent = "Copy link";
                        button.classList.remove("copied");
                      }}, 1800);
                    }});
                    </script>
                    <style>
                    html, body {{ margin:0; padding:0; background:transparent; font-family:Inter,Arial,sans-serif; }}
                    button {{ width:100%; min-height:44px; border:1px solid #69be28; border-radius:9px; background:#002244; color:#9ee468; font-size:14px; font-weight:800; cursor:pointer; transition:background .15s ease, color .15s ease; }}
                    button:hover, button:focus-visible {{ background:#0b3658; outline:3px solid #4b9fea; outline-offset:2px; }}
                    button.copied {{ background:#397f18; color:#ffffff; }}
                    </style>
                    """,
                    height=50,
                )
                st.caption("Opening this link restores the selected players, position, and quarterback touchdown scoring format.")
                share_scoring = f"Full PPR · {QB_PASS_TD_POINTS}-point passing TDs"
                share_image = build_share_image(preview_compare, NEXT_WEEK, share_scoring, REFRESHED)
                st.download_button(
                    "Download comparison image",
                    data=share_image,
                    file_name=f"sunday-decision-lab-week-{NEXT_WEEK}-comparison.png",
                    mime="image/png",
                    width="stretch",
                )
                st.caption(f"Includes the recommendation, projection ranges, and data snapshot timestamp ({REFRESHED}).")

        available_pool = pool.loc[~pool["player"].isin(names)].sort_values(
            ["projected_ppr", "player"], ascending=[False, True]
        )
        st.markdown(
            '<div class="smart-search-intro"><div class="smart-search-title">Smart player search</div>'
            f'<div class="smart-search-copy">{"All three slots are filled. Search for any eligible player, then choose exactly who to replace." if len(names) >= 3 else "Start typing a player name or team. Relevant eligible players appear instantly."}</div></div>',
            unsafe_allow_html=True,
        )
        if replacement_index is not None:
            st.markdown(
                f'<div class="replacement-note">Replacing <b>{html.escape(names[replacement_index])}</b>. Search below and select the new player.</div>',
                unsafe_allow_html=True,
            )
        if available_pool.empty:
            st.info("Every eligible player in this position is already selected.")
        else:
            candidate_lookup = {
                str(row["player_id"]): row for _, row in available_pool.iterrows()
            }

            def format_search_candidate(player_id: str) -> str:
                row = candidate_lookup[str(player_id)]
                opponent = row.get("next_opponent")
                opponent_text = "" if opponent is None or pd.isna(opponent) else f" vs {opponent}"
                return (
                    f'{row["player"]} · {row["team"]} {row["position"]}{opponent_text}'
                    f' · {float(row["median_ppr"]):.1f} PPR'
                )

            chosen_player_id = st.selectbox(
                "Search players by name or team",
                options=list(candidate_lookup),
                index=None,
                format_func=format_search_candidate,
                placeholder="Type a player name or team…",
                key=f'smart_search_candidate_{position}_{st.session_state[search_version_key]}',
                help="Suggestions filter immediately as you type. Only eligible players for the selected position are shown.",
            )
            if chosen_player_id is not None:
                result_row = candidate_lookup[str(chosen_player_id)]
                availability = selection_availability_summary(result_row)
                st.markdown(
                    f'<div class="smart-search-result"><b>{html.escape(str(result_row["player"]))}</b> · '
                    f'{html.escape(str(result_row["team"]))} {html.escape(str(result_row["position"]))} · '
                    f'{float(result_row["median_ppr"]):.1f} projected PPR · {html.escape(availability)}</div>',
                    unsafe_allow_html=True,
                )
                if replacement_index is not None:
                    if st.button(
                        f'Replace {names[replacement_index]} with {result_row["player"]}',
                        key=f'confirm_replace_{position}_{result_row["player_id"]}_{replacement_index}',
                        type="primary",
                        width="stretch",
                    ):
                        updated_names = list(names)
                        updated_names[replacement_index] = str(result_row["player"])
                        st.session_state[selection_key] = updated_names
                        st.session_state[replacement_key] = None
                        st.session_state[search_version_key] += 1
                        st.rerun()
                elif len(names) < 3:
                    if st.button(
                        f'Add {result_row["player"]}',
                        key=f'add_search_player_{position}_{result_row["player_id"]}',
                        type="primary",
                        width="stretch",
                    ):
                        st.session_state[selection_key] = [*names, str(result_row["player"])]
                        st.session_state[search_version_key] += 1
                        st.rerun()
                else:
                    st.caption("Comparison is full. Choose which current player this result should replace.")
                    replace_columns = st.columns(3)
                    for slot_index, replace_column in enumerate(replace_columns):
                        if replace_column.button(
                            f'Replace {names[slot_index]}',
                            key=f'smart_replace_{position}_{result_row["player_id"]}_{slot_index}',
                            width="stretch",
                        ):
                            updated_names = list(names)
                            updated_names[slot_index] = str(result_row["player"])
                            st.session_state[selection_key] = updated_names
                            st.session_state[replacement_key] = None
                            st.session_state[search_version_key] += 1
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
            edge_copy = "The projections are close—treat this as a lean and use the live context below to make your final call." if projection_spread < CLOSE_CALL_THRESHOLD_PPR else "We see a meaningful projected advantage, with live context below for your final decision."
            edge_badge = "Close call" if projection_spread < CLOSE_CALL_THRESHOLD_PPR else "Clearer edge"
        verdict_intro = '<div class="section-title">Start / Sit verdict</div>'
        if not no_clutter_mode:
            verdict_intro += '<div class="section-copy">We build this ranking from current production, repeatable workload, a fading prior-season anchor, touchdown regression, and a sample-scaled matchup adjustment. When an active injury matters, an optional injury-adjusted outlook appears directly on that player’s card.</div>'
        st.markdown(verdict_intro, unsafe_allow_html=True)
        game_details_legend = explained_term(
            "Game details",
            "Record is the team’s current win-loss mark. Matchup shows home/away and opponent. Kickoff is the scheduled game time. Game is the projected combined score; Team is the implied points for that player’s team.",
        )
        st.markdown(f'<div class="game-details-legend">{game_details_legend}</div>', unsafe_allow_html=True)
        outlook_columns = st.columns(len(compare))
        top_gap = 0.0 if len(compare) == 1 else float(compare.iloc[0]["median_ppr"] - compare.iloc[1]["median_ppr"])
        for index, (column, (_, row)) in enumerate(zip(outlook_columns, compare.iterrows())):
            with column:
                limited_sample = bool(row.get("limited_sample_role", False)) or str(row.get("confidence", "")).casefold() == "limited sample"
                player_gap = 0.0 if index == 0 else float(leader["median_ppr"] - row["median_ppr"])
                if len(compare) == 1:
                    card_edge_label = "Solo view"
                    card_edge_help = "Add another player before treating this as a Start/Sit comparison."
                elif index == 0 and top_gap < CLOSE_CALL_THRESHOLD_PPR:
                    card_edge_label = "Lean edge"
                    card_edge_help = f"The preferred player leads the next-best option by {top_gap:.1f} PPR—less than our {CLOSE_CALL_THRESHOLD_PPR:.0f}-point close-call threshold."
                elif index == 0 and top_gap < 5:
                    card_edge_label = "Moderate edge"
                    card_edge_help = f"The preferred player leads the next-best option by {top_gap:.1f} PPR. This is meaningful, but not decisive."
                elif index == 0:
                    card_edge_label = "Strong edge"
                    card_edge_help = f"The preferred player leads the next-best option by {top_gap:.1f} PPR."
                elif player_gap < CLOSE_CALL_THRESHOLD_PPR:
                    card_edge_label = "Close call"
                    card_edge_help = f"This player is only {player_gap:.1f} PPR behind the leader, inside our {CLOSE_CALL_THRESHOLD_PPR:.0f}-point close-call threshold."
                elif player_gap < 5:
                    card_edge_label = "Moderate gap"
                    card_edge_help = f"This player trails the leader by {player_gap:.1f} PPR."
                else:
                    card_edge_label = "Clear gap"
                    card_edge_help = f"This player trails the leader by {player_gap:.1f} PPR."
                confidence_badge = (
                    f'<div class="confidence-label label-help explained-term" tabindex="0">{html.escape(card_edge_label)}'
                    f'<span class="label-tooltip" role="tooltip">{html.escape(card_edge_help)} This label measures separation within this comparison—not certainty that any projection will hit.</span></div>'
                )
                unavailable = bool(recommendation_restriction(row))
                if unavailable:
                    verdict = "UNAVAILABLE · BASELINE ONLY"
                    verdict_help = "Do not start this player. The unchanged forecast is retained only for research comparison."
                elif index == 0 and len(compare) > 1:
                    verdict = "START · PREFERRED"
                    verdict_help = "Highest median projection among the players you selected."
                elif len(compare) > 1 and float(leader["median_ppr"] - row["median_ppr"]) < CLOSE_CALL_THRESHOLD_PPR:
                    verdict = "SIT · CLOSE ALTERNATIVE"
                    verdict_help = f"Lower only relative to the selected leader and still inside the {CLOSE_CALL_THRESHOLD_PPR:.0f}-point close-call range—not an automatic bench recommendation."
                elif len(compare) > 1:
                    verdict = "SIT · RISKIER OPTION"
                    verdict_help = "Lower median projection than the selected leader, with a larger comparison gap—not necessarily a bench in every league."
                else:
                    verdict = "ONLY PLAYER"
                    verdict_help = "Add another player to create a true comparison."
                card_class = "start" if index == 0 else "sit"
                full_reason = build_player_outlook(row, index, len(compare), projection_spread, row.get("reporting_summary"))
                if len(compare) == 1:
                    reason = "Add another player to turn this into a true Start/Sit comparison."
                elif index == 0 and top_gap < CLOSE_CALL_THRESHOLD_PPR:
                    reason = "Our preferred start, but only by a slim margin."
                elif index == 0:
                    reason = "Our preferred start with the strongest projection in this group."
                elif float(leader["median_ppr"] - row["median_ppr"]) < CLOSE_CALL_THRESHOLD_PPR:
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
                chip_explanations = {
                    "record": "Current team win-loss record",
                    "matchup": "Home or away and this week's opponent",
                    "kickoff": "Scheduled kickoff day and time",
                    "game-total": "Projected combined points scored by both teams",
                    "team-total": "Implied points scored by this player's team",
                }
                game_chips = "".join(
                    f'<span class="game-detail-chip {chip_class}" tabindex="0" title="{html.escape(chip_explanations.get(chip_class, label), quote=True)}">{html.escape(label)}</span>'
                    for label, chip_class in game_detail_chips
                )
                practice = format_injury_context(row, "Connected" in INJURY_SOURCE_STATUS)
                practice_alert = any(term in practice.casefold() for term in ("questionable", "doubtful", "out", "inactive", "ir", "did not practice"))
                matchup_help = explained_term(
                    matchup_summary(row),
                    "Opponent difficulty after accounting for the strength of offenses already faced. The percentage is relative to this player’s baseline, and the projection adjustment is capped.",
                )
                role_help = explained_term(
                    role_summary(row),
                    "Recent snap, route, carry, or target participation compared with the player’s earlier role. ‘Role expanding’ means recent involvement has increased; this card context is informational.",
                )
                quick_context = "".join([
                    f'<div class="broadcast-context-item{" context-alert" if practice_alert else ""}"><span>● Practice</span>{html.escape(practice)}</div>',
                    f'<div class="broadcast-context-item"><span>◆ Matchup</span>{matchup_help}</div>',
                    f'<div class="broadcast-context-item"><span>↗ Role</span>{role_help}</div>',
                    f'<div class="broadcast-context-item"><span>☁ Weather</span>{html.escape(weather_summary(row))}</div>',
                ])
                injury_alert = actionable_injury_alert(row)
                actionable_alert = ""
                if injury_alert:
                    opportunity_details = ""
                    if injury_alert["classification"] == "Teammate opportunity increase":
                        opportunity_baseline = float(row.get("baseline_median_ppr", row["median_ppr"]))
                        opportunity_adjusted = float(row.get("injury_adjusted_median_ppr", opportunity_baseline))
                        opportunity_floor = float(row.get("injury_adjusted_floor_ppr", row["floor_ppr"]))
                        opportunity_ceiling = float(row.get("injury_adjusted_ceiling_ppr", row["ceiling_ppr"]))
                        opportunity_delta = opportunity_adjusted - opportunity_baseline
                        opportunity_copy = str(row.get("injury_teammate_effect", "") or injury_alert["headline"])
                        opportunity_label = explained_term(
                            "Opportunity impact",
                            "An optional scenario showing how a teammate’s reduced availability could redistribute workload. It does not change the baseline Start/Sit ranking.",
                        )
                        opportunity_details = (
                            f'<details class="opportunity-details"><summary>{opportunity_label}</summary><div class="opportunity-details-body">'
                            f'<strong>Adjusted outlook · {opportunity_adjusted:.1f} PPR ({opportunity_delta:+.1f})</strong>'
                            f'{html.escape(opportunity_copy)}'
                            f'<span class="opportunity-details-range">Adjusted range: {opportunity_floor:.1f}–{opportunity_ceiling:.1f} PPR</span>'
                            '</div></details>'
                        )
                    actionable_alert = (
                        f'<div class="actionable-alert {html.escape(injury_alert["level"], quote=True)}">'
                        f'<div class="actionable-alert-head"><span class="actionable-alert-label">{html.escape(injury_alert["classification"])}</span>'
                        f'<span class="actionable-alert-time">{html.escape(injury_alert["changed"])}</span></div>'
                        f'<div class="actionable-alert-title">{html.escape(injury_alert["headline"])}</div>'
                        f'<div class="actionable-alert-verify"><b>Verify:</b> {html.escape(injury_alert["verify"])}</div>'
                        f'{opportunity_details}</div>'
                    )
                sample_note = ""
                sample_badge = explained_term(
                    "Limited sample",
                    "Personal workload evidence is not sufficient yet. We use position, team environment, and verified role priors and intentionally widen the outcome range.",
                    "limited-sample-pill",
                ) if limited_sample else ""
                if limited_sample:
                    sample_reason = str(row.get("limited_sample_reason", "No usable current-season workload or production history"))
                    prior_weights = str(row.get("limited_sample_prior_weights", "Position, team environment, and verified depth-chart role priors"))
                    sample_note = (
                        '<div class="limited-sample-note"><strong>Why this projection is uncertain</strong>'
                        f'{html.escape(sample_reason)}. We use {html.escape(prior_weights)} instead of treating personal history as reliable. '
                        'The range is wider because route/snap share, touches or targets, efficiency, and weekly role stability are not established yet.'
                        '</div>'
                    )
                floor = float(row["floor_ppr"])
                median = float(row["median_ppr"])
                ceiling = float(row["ceiling_ppr"])
                median_position = max(5.0, min(95.0, 100 * (median - floor) / max(ceiling - floor, .1)))
                card_stats = player_card_stat_summary(row)
                stat_snapshot = (
                    '<div class="player-stat-snapshot" aria-label="Season and recent statistics">'
                    '<div class="player-stat-grid">'
                    f'<div class="player-stat" title="Average full-PPR fantasy points per game this season"><span class="player-stat-label">{html.escape(card_stats["season_label"])}</span><span class="player-stat-value">{html.escape(card_stats["season_value"])}<small class="player-stat-unit">PPR/G</small></span></div>'
                    f'<div class="player-stat" title="The recent scoring window adjusts to the available early-season sample"><span class="player-stat-label">{html.escape(card_stats["form_label"])}</span><span class="player-stat-value">{html.escape(card_stats["form_value"])}<small class="player-stat-unit">PPR/G</small></span></div>'
                    f'<div class="player-stat" title="Recent repeatable workload per game"><span class="player-stat-label">{html.escape(card_stats["workload_label"])}</span><span class="player-stat-value">{html.escape(card_stats["workload_value"])}</span></div>'
                    '</div>'
                    f'<div class="player-season-line"><strong>Season totals · {html.escape(card_stats["games_label"])}</strong><span>{html.escape(card_stats["season_line"])}</span></div>'
                    '</div>'
                )
                defense_rank = opponent_position_rank(BOARD, row)
                game_log = fantasy_game_log(WEEKLY, row, QB_PASS_TD_POINTS)
                matchup_rank_html = ""
                if defense_rank:
                    matchup_rank_html = (
                        f'<div class="defense-rank {html.escape(defense_rank["tone"], quote=True)}">'
                        f'<strong>#{defense_rank["rank"]}</strong><div><b>{html.escape(defense_rank["label"])} vs {html.escape(defense_rank["position"])}</b>'
                        f'<span>{html.escape(defense_rank["opponent"])} ranks {defense_rank["rank"]} of {defense_rank["total"]}. No. 1 is toughest; higher ranks are easier.</span></div></div>'
                    )
                game_log_html = ""
                if game_log["rows"]:
                    header_html = "".join(f'<span>{html.escape(value)}</span>' for value in game_log["headers"])
                    rows_html = "".join(
                        '<div class="fantasy-log-row">' + "".join(f'<span>{html.escape(value)}</span>' for value in values) + '</div>'
                        for values in game_log["rows"]
                    )
                    game_log_html = (
                        '<details class="card-game-log"><summary>Game log &amp; matchup</summary><div class="card-game-log-body">'
                        f'{matchup_rank_html}<div class="fantasy-log"><div class="fantasy-log-row header">{header_html}</div>{rows_html}</div>'
                        '</div></details>'
                    )
                elif matchup_rank_html:
                    game_log_html = (
                        '<details class="card-game-log"><summary>Matchup difficulty</summary><div class="card-game-log-body">'
                        f'{matchup_rank_html}<div class="analysis-detail-meta">A game log will appear after this player records a game.</div></div></details>'
                    )
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
                teammate_opportunity_alert = bool(injury_alert and injury_alert["classification"] == "Teammate opportunity increase")
                if risk != "No adjustment" or (teammate_effect and not teammate_opportunity_alert):
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
                    market_term = explained_term(
                        "Market-implied PPR",
                        "A supplemental fantasy-point expectation translated from consensus sportsbook player-prop lines. It never changes our calibrated projection or Start/Sit ranking.",
                    )
                    market_note = (
                        f'<div class="analysis-detail-section"><strong>{market_term} · {market_value:.1f} PPR ({market_delta:+.1f})</strong>'
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
                    f'<div class="verdict {card_class}"><div style="display:flex;align-items:center;gap:.45rem;flex-wrap:wrap"><div class="tag label-help" tabindex="0">{verdict}<span class="label-tooltip" role="tooltip">{html.escape(verdict_help)}</span></div>{sample_badge}{confidence_badge}</div><div class="player-heading">{photo}<div class="name">{html.escape(str(row["player"]))}</div></div>'
                    f'<div class="opponent team-line">{logo}<span>{html.escape(player_details)}</span></div>'
                    f'<div class="game-detail-chips">{game_chips}</div>'
                    f'<div class="projection-primary"><strong>{median:.1f}</strong><span>projected PPR <span class="range-help" tabindex="0" aria-label="Range definition">i<span class="range-tooltip" role="tooltip">Floor is the P10 downside outcome, projection is the median estimate, and ceiling is the P90 upside outcome. About 80% of results should fall between floor and ceiling.</span></span></span></div>'
                    f'<div class="range-track"><span class="range-marker" style="left:{median_position:.1f}%"></span></div><div class="range-labels"><span>Floor {floor:.1f}</span><span>Ceiling {ceiling:.1f}</span></div>'
                    f'{stat_snapshot}{game_log_html}<div class="outlook-label">Player outlook</div><div class="reason">{html.escape(reason)}</div>{sample_note}{actionable_alert}<div class="broadcast-context">{quick_context}</div>'
                    f'{outlook_details}</div>',
                    unsafe_allow_html=True,
                )

        if len(compare) > 1:
            st.markdown(
                '<div class="comparison-relative-note">“Sit” is relative to the other selected players—not an automatic bench recommendation in every league.</div>',
                unsafe_allow_html=True,
            )

        # Streamlit expanders execute their complete body even while closed.
        # This server-aware disclosure avoids building analysis markup until a
        # user asks for it, and its session-state key stays open across reruns.
        analysis_hub_open = st.toggle(
            "Analysis Hub",
            key="analysis_hub_open",
            help="Open projection, form, usage, matchup, market, and methodology views.",
        )
        comparison_shell = st.container(border=analysis_hub_open, key="analysis_hub_panel")
        if analysis_hub_open:
            comparison_shell.markdown(
                '<div class="tool-section-head"><div><h2>Analysis Hub</h2><span>Projection, form, usage, matchup, market context, and methodology in one place.</span></div><span class="tool-section-badge">6 analysis views</span></div>',
                unsafe_allow_html=True,
            )
            comparison_view = comparison_shell.segmented_control(
                "Analysis view", ["Projection", "Weekly form", "Usage", "Matchup", "Market", "Methodology"],
                default="Projection", width="stretch", label_visibility="collapsed",
                key="comparison_view",
            )
        else:
            comparison_view = None
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
            range_insight = f'{leader["player"]} leads by {projection_spread:.1f} PPR. The ranges overlap by {overlap:.1f}, so this is {"a close lean" if projection_spread < CLOSE_CALL_THRESHOLD_PPR else "a meaningful edge"}.'
            comparison_shell.markdown(
                f'<div class="comparison-panel-head"><div><h3>Week {NEXT_WEEK} Projection</h3><p>Floor, median projection, and ceiling shown together.</p></div><div class="panel-key">Floor ← range → Ceiling</div></div>'
                f'<div class="projection-board">{"".join(projection_rows)}</div><div class="panel-insight"><b>Quick read</b><span>{html.escape(range_insight)}</span></div>',
                unsafe_allow_html=True,
            )

        if comparison_view == "Weekly form":
            weekly_name_column = "player_display_name" if "player_display_name" in WEEKLY.columns else "player_name"
            if "player_id" in WEEKLY and "player_id" in compare:
                trend_history = WEEKLY.loc[WEEKLY["player_id"].isin(compare["player_id"])].copy()
            else:
                trend_history = WEEKLY.loc[WEEKLY[weekly_name_column].isin(compare["player"])].copy()
            if trend_history.empty:
                comparison_shell.info("Weekly production history is temporarily unavailable for these players.")
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
                comparison_shell.markdown(
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
            usage_left, usage_right = comparison_shell.columns([1, 1])
            usage_label = usage_left.selectbox(
                "Statistic", list(metric_options), key=f"comparison_usage_metric_{position}",
            )
            usage_mode = usage_right.radio(
                "Display", ["Per game", "Season total"], horizontal=True,
                key=f"comparison_usage_mode_{position}",
            )
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
            comparison_shell.markdown(
                f'<div class="usage-board">{"".join(usage_rows)}</div><div class="usage-insight"><b>Quick read</b><span>{html.escape(insight)}</span></div>',
                unsafe_allow_html=True,
            )

        if comparison_view == "Market":
            market_rows = []
            available_count = 0
            market_ppr_label = explained_term(
                "Market-implied PPR",
                "A supplemental fantasy-point expectation translated from consensus sportsbook player-prop lines. It never changes our projection or Start/Sit ranking.",
            )
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
                        f'<article class="usage-player">{identity}<div class="usage-track-wrap"><div class="usage-rank">No validated player props are currently available. Missing or suspended lines are never treated as zero.</div></div><div class="usage-score"><strong>—</strong><span>{market_ppr_label}</span></div></article>'
                    )
                    continue
                available_count += 1
                market_value = float(market_value)
                model_value = float(market_row["median_ppr"])
                delta = market_value - model_value
                lines = market_summary(market_row)
                market_rows.append(
                    f'<article class="usage-player">{identity}<div class="usage-track-wrap"><div class="usage-rank">{html.escape(lines)}</div><div class="usage-rank">Our projection: {model_value:.1f} · difference: {delta:+.1f} PPR</div></div><div class="usage-score"><strong>{market_value:.1f}</strong><span>{market_ppr_label}</span></div></article>'
                )
            market_insight = (
                f"Validated player-prop expectations are available for {available_count} of {len(compare)} selected players."
                if available_count else
                "Sportsbooks usually publish most NFL player props 72–96 hours before kickoff. Check again closer to game time."
            )
            comparison_shell.markdown(
                f'<div class="comparison-panel-head"><div><h3>Market Expectations</h3><p>Consensus receiving, rushing and passing lines translated to the selected fantasy scoring format.</p></div><div class="panel-key">Supplemental only</div></div>'
                f'<div class="usage-board">{"".join(market_rows)}</div><div class="usage-insight"><b>Important</b><span>{html.escape(market_insight)} These values never change our ranking.</span></div>',
                unsafe_allow_html=True,
            )

        deep_dive_shell = comparison_shell
        if comparison_view == "Projection":
            show_projection_drivers = comparison_shell.toggle(
                "Show projection drivers and detailed statistics",
                key=f"show_projection_drivers_{position}",
            )
            deep_dive_view = "Projection drivers" if show_projection_drivers else None
        elif comparison_view == "Matchup":
            deep_dive_view = "Matchup context"
        else:
            deep_dive_view = None
        common = ["player", "team", "next_opponent", "games_played", "season_ppr", "recent_ppr", "recent_opportunities"]
        position_stats = {
            "QB": ["ytd_attempts", "ytd_passing_yards", "ytd_passing_tds", "ytd_rushing_yards", "ytd_rushing_tds"],
            "RB": ["ytd_carries", "ytd_targets", "ytd_rushing_yards", "ytd_receiving_yards", "ytd_rushing_tds", "ytd_receiving_tds"],
            "WR": ["ytd_targets", "ytd_receptions", "ytd_receiving_yards", "ytd_receiving_tds"],
            "TE": ["ytd_targets", "ytd_receptions", "ytd_receiving_yards", "ytd_receiving_tds"],
            "FLEX": ["ytd_carries", "ytd_targets", "ytd_receptions", "ytd_rushing_yards", "ytd_receiving_yards", "ytd_rushing_tds", "ytd_receiving_tds"],
        }
        if deep_dive_view == "Projection drivers":
            deep_dive_shell.markdown(
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
            deep_dive_shell.markdown(f'<div class="driver-grid">{"".join(driver_cards)}</div>', unsafe_allow_html=True)
            deep_dive_shell.caption("Arrows show whether a driver nudges the outlook up, leaves it essentially unchanged, or pulls it down. They do not represent separate point totals that should be added together.")

            if deep_dive_shell.toggle("View detailed statistics", key=f"advanced_projection_stats_{position}"):
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
                        stat_label = html.escape(stat_labels[stat_column])
                        if stat_column == "schedule_adjusted_index":
                            stat_label = explained_term(
                                stat_labels[stat_column],
                                "Opponent difficulty adjusted for the quality of offenses previously faced. Values are interpreted relative to the player’s baseline and the projection adjustment is capped.",
                            )
                        elif stat_column == "confidence":
                            stat_label = explained_term(
                                stat_labels[stat_column],
                                "How much reliable personal workload history supports the estimate. Limited Sample means role/team/position priors carry more weight and the range is wider.",
                            )
                        stat_rows_html += f'<div class="advanced-stat-row"><span>{stat_label}</span><b>{html.escape(display_value)}</b></div>'
                    advanced_cards.append(
                        f'<article class="advanced-stat-card"><div class="advanced-stat-head"><strong>{html.escape(str(stat_row["player"]))}</strong>'
                        f'<span>{html.escape(str(stat_row["team"]))} · {html.escape(str(stat_row["position"]))} · vs {html.escape(str(stat_row["next_opponent"]))}</span></div>{stat_rows_html}</article>'
                    )
                deep_dive_shell.markdown(f'<div class="advanced-stat-grid">{"".join(advanced_cards)}</div>', unsafe_allow_html=True)

        if deep_dive_view == "Matchup context":
            deep_dive_shell.caption("Live, informational context for your final call. These details never change our ranking.")
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
                team_record = row.get("team_record") if pd.notna(row.get("team_record")) else "—"
                implied_team_total = projected_team_total(row)
                team_total = f"{implied_team_total:.1f} points" if implied_team_total is not None else "Not available"
                projection_range = f'{float(row["floor_ppr"]):.1f}–{float(row["ceiling_ppr"]):.1f} PPR'
                fields = [
                    ("Availability", availability, False),
                    ("Weather", weather_summary(row), False),
                    ("Team record", str(team_record), False),
                    ("Projected team total", team_total, False),
                    ("Expected pace", pace, True),
                    ("Scoring environment", expected_points, True),
                    ("Opponent strength", matchup_summary(row), False),
                    ("QB / O-line", personnel, False),
                    ("Projection range", projection_range, False),
                    ("Median projection", f'{float(row["median_ppr"]):.1f} PPR', False),
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
            deep_dive_shell.markdown(f'<div class="context-grid">{"".join(context_cards)}</div>', unsafe_allow_html=True)

        if comparison_view == "Methodology":
            comparison_shell.markdown(
                '<div class="comparison-panel-head"><div><h3>Sources & Methodology</h3>'
                '<p>How the projection is built, what remains informational, and the limits users should understand.</p></div>'
                '<div class="panel-key">Transparent by design</div></div>',
                unsafe_allow_html=True,
            )
            comparison_shell.markdown(SOURCE_ATTRIBUTION)
            comparison_shell.markdown(METHODOLOGY_LANGUAGE)
            comparison_shell.info("The scoring-role touchdown exception remains disabled until reliable red-zone or goal-line opportunity data is integrated and validated.")
            comparison_shell.markdown(DISCLAIMER_LANGUAGE)

elif page == "Player Trends":
    trends_controls = st.container(key="trends_controls")
    control_left, control_right = trends_controls.columns([1, 1.5])
    selected_position = control_left.segmented_control(
        "Position", ["QB", "RB", "WR", "TE"], default="WR", key="trends_position", width="stretch"
    )
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
    player_name = control_right.selectbox(
        "Find a player", pool["player"].sort_values().tolist(),
        key=f"trends_player_{selected_position}",
    )
    matches = pool.loc[pool["player"].eq(player_name)]
    if matches.empty:
        st.warning("That player record is no longer available after the latest refresh. Choose another player.")
        st.stop()
    player = matches.iloc[0]
    id_column = "player_id" if "player_id" in BOARD.columns and "player_id" in WEEKLY.columns else None
    name_column = "player_display_name" if "player_display_name" in WEEKLY.columns else "player_name"
    history = player_weekly_history(WEEKLY, player).sort_values("week")
    history = history.copy()
    history["trend_ppr"] = pd.to_numeric(history["fantasy_points_ppr"], errors="coerce")
    if selected_position == "QB" and QB_PASS_TD_POINTS != 4 and "passing_tds" in history:
        history["trend_ppr"] += (QB_PASS_TD_POINTS - 4) * pd.to_numeric(history["passing_tds"], errors="coerce").fillna(0)
    projection = float(player["projected_ppr"])
    season_average = float(player["season_ppr"])
    recent_average = float(player["recent_ppr"])
    availability = selection_availability_summary(player)
    photo = player_photo_html(player.get("headshot_url"), player_name)
    logo_url = team_logo_url(player.get("team"))
    logo = f'<img src="{html.escape(logo_url, quote=True)}" alt="{html.escape(str(player["team"]), quote=True)} logo">' if logo_url else ""
    game_line = " · ".join(
        str(player.get(value)) for value in ("weekday", "gametime")
        if player.get(value) is not None and pd.notna(player.get(value))
    ) or "Kickoff TBD"
    availability_alert = any(
        term in availability.casefold()
        for term in ("questionable", "doubtful", "out", "inactive", "ir", "did not practice")
    )
    st.markdown(
        f'<section class="trend-player-card"><div class="trend-player-identity">{photo}<div><div class="trend-player-name">{html.escape(player_name)}</div>'
        f'<div class="trend-player-team">{logo}<span>{html.escape(str(player["team"]))} · {selected_position} · {html.escape(str(player.get("venue", "")))} vs {html.escape(str(player["next_opponent"]))}</span></div>'
        f'<div class="trend-player-team"><span>{html.escape(game_line)}</span></div><span class="trend-status{" alert" if availability_alert else ""}">{html.escape(availability)}</span></div></div>'
        f'<div class="trend-stat"><span>Week {NEXT_WEEK}</span><strong>{projection:.1f}</strong><small>Projected PPR</small></div>'
        f'<div class="trend-stat"><span>Recent form</span><strong>{recent_average:.1f}</strong><small>PPR per game</small></div>'
        f'<div class="trend-stat"><span>Season baseline</span><strong>{season_average:.1f}</strong><small>PPR per game</small></div>'
        f'<div class="trend-stat"><span>Projected range</span><strong>{float(player.get("floor_ppr", projection)):.1f}–{float(player.get("ceiling_ppr", projection)):.1f}</strong><small>Floor to ceiling</small></div></section>',
        unsafe_allow_html=True,
    )

    recorded = history.dropna(subset=["trend_ppr"]).copy()
    games_played = len(recorded)
    if games_played >= 2:
        latest_score = float(recorded.iloc[-1]["trend_ppr"])
        prior_score = float(recorded.iloc[-2]["trend_ppr"])
        form_change = latest_score - prior_score
        direction = "up" if form_change > 2 else "down" if form_change < -2 else "steady"
        trend_sentence = (
            f"{player_name} is trending {direction} after scoring {latest_score:.1f} PPR last week. "
            f"We project {projection:.1f} this week, {abs(projection - season_average):.1f} points "
            f"{'above' if projection >= season_average else 'below'} the season baseline."
        )
    elif games_played == 1:
        latest_score = float(recorded.iloc[-1]["trend_ppr"])
        trend_sentence = f"Only one game is available for {player_name}. Treat the {latest_score:.1f}-point result as an early signal—not an established trend."
    else:
        trend_sentence = f"No completed-game sample is available for {player_name}. The outlook relies more heavily on the expected role, team environment, and position priors."

    if selected_position == "QB":
        recorded_opportunities = pd.to_numeric(recorded.get("attempts"), errors="coerce").fillna(0) + pd.to_numeric(recorded.get("carries"), errors="coerce").fillna(0)
        recorded_touchdowns = pd.to_numeric(recorded.get("passing_tds"), errors="coerce").fillna(0) + pd.to_numeric(recorded.get("rushing_tds"), errors="coerce").fillna(0)
        opportunity_name = "pass attempts and carries"
    elif selected_position == "RB":
        recorded_opportunities = pd.to_numeric(recorded.get("carries"), errors="coerce").fillna(0) + pd.to_numeric(recorded.get("targets"), errors="coerce").fillna(0)
        recorded_touchdowns = pd.to_numeric(recorded.get("rushing_tds"), errors="coerce").fillna(0) + pd.to_numeric(recorded.get("receiving_tds"), errors="coerce").fillna(0)
        opportunity_name = "carries and targets"
    else:
        recorded_opportunities = pd.to_numeric(recorded.get("targets"), errors="coerce").fillna(0)
        recorded_touchdowns = pd.to_numeric(recorded.get("receiving_tds"), errors="coerce").fillna(0)
        opportunity_name = "targets"
    season_opportunity_average = float(recorded_opportunities.mean()) if len(recorded_opportunities) else 0.0
    recent_opportunity_average = float(recorded_opportunities.tail(3).mean()) if len(recorded_opportunities) else 0.0
    opportunity_delta = recent_opportunity_average - season_opportunity_average
    if games_played < 2:
        role_title, role_copy, role_class = "Early role sample", "There is not enough completed-game workload to call the role growing or shrinking.", ""
    elif opportunity_delta >= 1.5:
        role_title, role_copy, role_class = "Opportunity is growing", f"Recent {opportunity_name} are {opportunity_delta:.1f} per game above the season rate.", "positive"
    elif opportunity_delta <= -1.5:
        role_title, role_copy, role_class = "Opportunity is shrinking", f"Recent {opportunity_name} are {abs(opportunity_delta):.1f} per game below the season rate.", "negative"
    else:
        role_title, role_copy, role_class = "Role is holding steady", f"Recent {opportunity_name} remain close to the season workload.", ""
    recent_touchdowns = float(recorded_touchdowns.tail(3).sum()) if len(recorded_touchdowns) else 0.0
    production_delta = recent_average - season_average
    if games_played < 2:
        sustainability_title, sustainability_copy, sustainability_class = "Sustainability unclear", "More games are needed before separating repeatable volume from scoring variance.", ""
    elif production_delta > 2 and recent_touchdowns >= 2 and opportunity_delta < 1.5:
        sustainability_title, sustainability_copy, sustainability_class = "Scoring is touchdown-led", f"{recent_touchdowns:.0f} touchdowns in the recent sample are lifting results without the same increase in workload.", "negative"
    elif opportunity_delta >= 1.5:
        sustainability_title, sustainability_copy, sustainability_class = "Production has volume support", "The recent scoring change is accompanied by a meaningful workload increase.", "positive"
    else:
        sustainability_title, sustainability_copy, sustainability_class = "Production near established role", "Recent scoring and opportunity do not show a strong divergence from the season profile.", ""
    matchup_factor = float(player.get("projection_matchup_factor", 1.0)) if pd.notna(player.get("projection_matchup_factor")) else 1.0
    if availability_alert:
        watch_title, watch_copy, watch_class = "Verify availability", f"{availability}. Check the final practice report and official inactives.", "negative"
    elif matchup_factor >= 1.02:
        watch_title, watch_copy, watch_class = "Favorable matchup signal", f"The capped matchup input adds {(matchup_factor - 1) * 100:.1f}% to the median projection.", "positive"
    elif matchup_factor <= 0.98:
        watch_title, watch_copy, watch_class = "Matchup adds resistance", f"The capped matchup input trims {(1 - matchup_factor) * 100:.1f}% from the median projection.", "negative"
    else:
        watch_title, watch_copy, watch_class = "Watch the next workload", "The matchup is near neutral, so role and opportunity should drive the next evaluation.", ""
    st.markdown(
        '<div class="trend-insights-title">Fantasy manager read</div><div class="trend-insight-grid">'
        f'<article class="trend-insight-card {role_class}"><span>Role trajectory</span><strong>{html.escape(role_title)}</strong><p>{html.escape(role_copy)}</p></article>'
        f'<article class="trend-insight-card {sustainability_class}"><span>Sustainability</span><strong>{html.escape(sustainability_title)}</strong><p>{html.escape(sustainability_copy)}</p></article>'
        f'<article class="trend-insight-card {watch_class}"><span>Watch next</span><strong>{html.escape(watch_title)}</strong><p>{html.escape(watch_copy)}</p></article></div>',
        unsafe_allow_html=True,
    )
    if "trends_hub_expanded" not in st.session_state:
        st.session_state.trends_hub_expanded = True

    def keep_trends_hub_open() -> None:
        st.session_state.trends_hub_expanded = True

    trends_shell = st.expander("Trends Analysis", expanded=st.session_state.trends_hub_expanded)
    trends_view = trends_shell.segmented_control(
        "Trend view", ["Production", "Opportunity", "Matchup", "Player profile"],
        default="Production", key="trends_view", label_visibility="collapsed", width="stretch",
        on_change=keep_trends_hub_open,
    )
    if trends_view == "Production":
        if recorded.empty:
            trends_shell.info("Weekly production is not available yet. The projection remains visible above and uncertainty is widened for the limited sample.")
        else:
            recorded_by_week = {
                int(game_row["week"]): game_row
                for _, game_row in recorded.dropna(subset=["week", "trend_ppr"]).iterrows()
            }
            final_completed_week = max(1, NEXT_WEEK - 1)
            broadcast_games = []
            for week_number in range(1, final_completed_week + 1):
                game_row = recorded_by_week.get(week_number)
                opponent_value = None if game_row is None else game_row.get("opponent_team")
                broadcast_games.append({
                    "week": week_number,
                    "score": None if game_row is None else round(float(game_row["trend_ppr"]), 1),
                    "opponent": str(opponent_value) if opponent_value is not None and pd.notna(opponent_value) else "",
                    "context": "No recorded game" if game_row is None else "Completed game",
                })
            trends_shell.markdown(
                f'<div class="comparison-panel-head"><div><h3>{html.escape(player_name)} · production broadcast</h3>'
                '<p>Review one completed week at a time against the upcoming projection.</p></div>'
                f'<div class="panel-key">{games_played} game{"s" if games_played != 1 else ""} tracked</div></div>',
                unsafe_allow_html=True,
            )
            with trends_shell:
                components.html(
                    production_broadcast_html(
                        player_name,
                        broadcast_games,
                        projection,
                        float(player.get("floor_ppr", projection)),
                        float(player.get("ceiling_ppr", projection)),
                        season_average,
                        recent_average,
                        NEXT_WEEK,
                    ),
                    height=286,
                    scrolling=False,
                )
            trends_shell.markdown(f'<div class="panel-insight"><b>How to read it</b><span>{html.escape(trend_sentence)}</span></div>', unsafe_allow_html=True)
            game_log_rows = []
            for _, game_row in recorded.sort_values("week", ascending=False).iterrows():
                opponent_value = game_row.get("opponent_team")
                opponent_display = f'vs {opponent_value}' if opponent_value is not None and pd.notna(opponent_value) else "Opponent —"
                targets = float(pd.to_numeric(pd.Series([game_row.get("targets")]), errors="coerce").fillna(0).iloc[0])
                carries = float(pd.to_numeric(pd.Series([game_row.get("carries")]), errors="coerce").fillna(0).iloc[0])
                receptions = float(pd.to_numeric(pd.Series([game_row.get("receptions")]), errors="coerce").fillna(0).iloc[0])
                touchdowns = sum(
                    float(pd.to_numeric(pd.Series([game_row.get(column)]), errors="coerce").fillna(0).iloc[0])
                    for column in ("passing_tds", "rushing_tds", "receiving_tds")
                )
                game_log_rows.append(
                    f'<div class="game-log-row"><strong>W{int(game_row["week"])}</strong><span>{html.escape(opponent_display)}</span>'
                    f'<span><strong>{float(game_row["trend_ppr"]):.1f}</strong> PPR</span><span>{targets:.0f} tgt</span><span>{carries:.0f} car</span><span>{receptions:.0f} rec · {touchdowns:.0f} TD</span></div>'
                )
            with trends_shell.expander("Weekly game log"):
                st.markdown(
                    '<div class="game-log"><div class="game-log-row header"><span>Week</span><span>Opponent</span><span>Fantasy</span><span>Targets</span><span>Carries</span><span>Receptions / TD</span></div>'
                    + "".join(game_log_rows) + "</div>",
                    unsafe_allow_html=True,
                )
    elif trends_view == "Opportunity":
        opportunity_history = recorded.copy()
        if selected_position == "QB":
            opportunity_history["opportunity"] = pd.to_numeric(opportunity_history.get("attempts"), errors="coerce").fillna(0) + pd.to_numeric(opportunity_history.get("carries"), errors="coerce").fillna(0)
            opportunity_label = "Attempts + carries"
        elif selected_position == "RB":
            opportunity_history["opportunity"] = pd.to_numeric(opportunity_history.get("carries"), errors="coerce").fillna(0) + pd.to_numeric(opportunity_history.get("targets"), errors="coerce").fillna(0)
            opportunity_label = "Carries + targets"
        else:
            opportunity_history["opportunity"] = pd.to_numeric(opportunity_history.get("targets"), errors="coerce").fillna(0)
            opportunity_label = "Targets"
        opportunity_history = opportunity_history.dropna(subset=["week", "opportunity"])
        opportunity_weeks = pd.to_numeric(opportunity_history["week"], errors="coerce").astype(int).tolist()
        opportunity_values = pd.to_numeric(opportunity_history["opportunity"], errors="coerce").fillna(0).tolist()
        season_opportunity = float(pd.Series(opportunity_values).mean()) if opportunity_values else 0.0
        recent_opportunity = float(pd.Series(opportunity_values[-3:]).mean()) if opportunity_values else 0.0
        latest_opportunity = float(opportunity_values[-1]) if opportunity_values else 0.0
        comparison_opportunity = recent_opportunity if len(opportunity_values) >= 3 else latest_opportunity
        change = comparison_opportunity - season_opportunity
        change_copy = "Role is expanding" if change >= 1.5 else "Role is contracting" if change <= -1.5 else "Role is steady"
        change_phrase = "more opportunities than" if change >= 1.5 else "fewer opportunities than" if change <= -1.5 else "about as many opportunities as"
        latest_snap = player.get("latest_snap_pct")
        latest_snap_display = "Unavailable"
        if latest_snap is not None and pd.notna(latest_snap):
            latest_snap_value = float(latest_snap)
            latest_snap_display = f"{latest_snap_value * 100 if latest_snap_value <= 1 else latest_snap_value:.0f}%"
        if opportunity_values:
            opportunity_games = [
                {"week": week, "value": round(float(value), 1)}
                for week, value in zip(opportunity_weeks, opportunity_values)
            ]
            with trends_shell:
                components.html(
                    opportunity_tracker_html(
                        player_name, opportunity_games, opportunity_label, season_opportunity,
                        recent_opportunity, latest_snap_display, change_copy,
                    ),
                    height=236,
                    scrolling=False,
                )
            trends_shell.markdown(
                f'<div class="panel-insight"><b>What changed</b><span>Over the recent sample, {html.escape(player_name)} is seeing {change_phrase} the season baseline. Opportunity describes workload—not guaranteed fantasy points.</span></div>',
                unsafe_allow_html=True,
            )
        else:
            trends_shell.info("Weekly opportunity data is not available yet. The role summary will appear after the first recorded game.")
    elif trends_view == "Matchup":
        factor = float(player.get("projection_matchup_factor", 1.0)) if pd.notna(player.get("projection_matchup_factor")) else 1.0
        adjustment = (factor - 1) * 100
        matchup_direction = "favorable" if adjustment > 1 else "unfavorable" if adjustment < -1 else "neutral"
        schedule_index = float(player.get("schedule_adjusted_index", 1.0)) if pd.notna(player.get("schedule_adjusted_index")) else 1.0
        schedule_delta = (schedule_index - 1) * 100
        defense_rank = opponent_position_rank(BOARD, player)
        opponent_record_rows = BOARD.loc[BOARD["team"].eq(player["next_opponent"]), "team_record"].dropna()
        opponent_record = str(opponent_record_rows.iloc[0]) if not opponent_record_rows.empty else "Unavailable"
        pace = player.get("combined_recent_plays")
        pace_display = f"{float(pace):.0f}" if pace is not None and pd.notna(pace) else "—"
        live_total = player.get("betting_total_live")
        total = live_total if live_total is not None and pd.notna(live_total) else player.get("total_line")
        total_display = f"{float(total):.1f}" if total is not None and pd.notna(total) else "—"
        rank_copy = f'No. {defense_rank["rank"]} of {defense_rank["total"]} available defenses · No. 1 toughest' if defense_rank is not None else "Rank unavailable"
        schedule_word = "above" if schedule_delta > 1 else "below" if schedule_delta < -1 else "near"
        pace_word = str(player.get("pace_label", "Neutral")).lower()
        rationale = (
            f"We rate {player['next_opponent']} as a {matchup_direction} matchup for {selected_position}s. "
            f"After adjusting for the opponents they have already faced, their result is {abs(schedule_delta):.0f}% {schedule_word} the league baseline. "
            f"The expected pace is {pace_word}, and the {total_display}-point game environment provides additional context. "
            f"Only a capped {adjustment:+.1f}% matchup adjustment is applied to the projection."
        )
        freshness = f"Validated data snapshot: {REFRESHED}"
        trends_shell.markdown(
            f'<div class="matchup-verdict"><div class="matchup-verdict-head"><b>{html.escape(str(player["team"]))} vs {html.escape(str(player["next_opponent"]))}</b><span>{html.escape(matchup_direction)} matchup</span></div>'
            f'<p>{html.escape(rationale)}</p><div class="matchup-freshness">{html.escape(freshness)}</div></div>'
            '<div class="matchup-trend-grid">'
            f'<article class="matchup-trend-stat"><span>Opponent record</span><strong>{html.escape(opponent_record)}</strong><small>Current season record</small></article>'
            f'<article class="matchup-trend-stat"><span>Schedule-adjusted</span><strong>{schedule_delta:+.0f}%</strong><small>{html.escape(rank_copy)} for {html.escape(selected_position)}s</small></article>'
            f'<article class="matchup-trend-stat"><span>Projection matchup effect</span><strong>{adjustment:+.1f}%</strong><small>Capped opponent adjustment applied to this player’s median projection</small></article>'
            f'<article class="matchup-trend-stat"><span>Game environment</span><strong>{total_display} pts</strong><small>{pace_display} recent combined plays · {html.escape(str(player.get("pace_label", "Neutral")))} pace</small></article>'
            '</div>'
            '<div class="panel-insight"><b>How to use this</b><span>The schedule-adjusted rating is supplemental context. The approved projection uses a separate capped, sample-scaled raw positional points-allowed adjustment. Pace, betting environment, weather, injuries, and reporting remain live decision context for you.</span></div>',
            unsafe_allow_html=True,
        )
    else:
        confidence = str(player.get("confidence", "Standard sample"))
        profile_items = [
            ("Games in sample", str(games_played), "Completed games available for current-season trend analysis."),
            ("Projection range", f'{float(player.get("floor_ppr", projection)):.1f}–{float(player.get("ceiling_ppr", projection)):.1f}', "Downside-to-upside range, not a guarantee."),
            ("Confidence", confidence, "How much reliable personal workload history supports the estimate."),
        ]
        profile = [f'<article class="trend-evidence"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong><p>{html.escape(copy)}</p></article>' for label, value, copy in profile_items]
        trends_shell.markdown(f'<div class="trend-evidence-grid">{"".join(profile)}</div>', unsafe_allow_html=True)

elif page == "How It Works":
    st.subheader("How The Sunday Decision Lab works")
    st.markdown(METHODOLOGY_LANGUAGE)
    st.info("The scoring-role touchdown exception remains disabled until reliable red-zone or goal-line opportunity data is integrated and validated.")
    st.subheader("Sources and refresh timing")
    st.markdown(SOURCE_ATTRIBUTION)
    st.caption(f"Season {season} data · active pages check a lightweight publication pointer every 60 seconds; updates pause during roster edits · this snapshot loaded {REFRESHED} · supplementary provider: {PROVIDER_STATUS}")
    st.subheader("Responsible use")
    st.markdown(DISCLAIMER_LANGUAGE)

if page != "Decision Room":
    st.divider()
    with st.expander("Sources, methodology & important disclaimer"):
        st.markdown(SOURCE_ATTRIBUTION)
        st.markdown(METHODOLOGY_LANGUAGE)
        st.markdown(DISCLAIMER_LANGUAGE)


def _prepare_idle_update(candidate):
    # Preload and integrity-check the complete data before requesting a redraw.
    # Do not clear user state, authentication, team IDs or saved assignments.
    get_snapshot_metadata.clear()
    metadata = get_snapshot_metadata()
    if metadata.get("_publication", {}).get("version") != candidate["version"]:
        raise ValueError("Publication changed while checking; retry on next tick")
    get_published_snapshot(season, QB_PASS_TD_POINTS, json.dumps(metadata, sort_keys=True))


watch_publication(SNAPSHOT_BASE_URL, header_metadata.get("_publication", {}).get("version"),
                  page == "Sunday Command Center", _prepare_idle_update)
