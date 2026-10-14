"""Sunday Command Center Streamlit presentation and roster onboarding."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st
from streamlit_local_storage import LocalStorage

from dashboard.auth_ui import current_session, render_auth, sign_out
from dashboard.repositories.rosters import RosterRepository
from dashboard.supabase_api import SupabaseAPI, SupabaseAPIError


DEFAULT_SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 0, "BENCH": 6}
SLOT_ELIGIBILITY = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"},
    "FLEX": {"RB", "WR", "TE"}, "SUPERFLEX": {"QB", "RB", "WR", "TE"},
    "BENCH": {"QB", "RB", "WR", "TE"},
}


def _team_setup(repository: RosterRepository, season: int) -> None:
    st.markdown(
        '<section class="cc-empty"><span>FIRST TEAM</span><h2>Build your lineup monitor</h2>'
        '<p>Add the league settings and roster shape you actually use. Player selection comes next.</p></section>',
        unsafe_allow_html=True,
    )
    with st.form("command_center_create_team"):
        left, right = st.columns(2)
        league_name = left.text_input("League name", placeholder="Sunday League")
        team_name = right.text_input("Fantasy team name", placeholder="My Team")
        pass_td = st.radio("QB passing touchdowns", [4, 6], horizontal=True, format_func=lambda value: f"{value} points")
        st.markdown("**Starting lineup and bench slots**")
        columns = st.columns(4)
        slot_counts: dict[str, int] = {}
        for index, (slot, default) in enumerate(DEFAULT_SLOTS.items()):
            slot_counts[slot] = columns[index % 4].number_input(slot, min_value=0, max_value=20, value=default, step=1)
        submitted = st.form_submit_button("Create team", type="primary", width="stretch")
    if not submitted:
        return
    if not league_name.strip() or not team_name.strip():
        st.error("Enter both a league name and fantasy team name.")
        return
    league: dict[str, Any] | None = None
    try:
        league, team = repository.create_league_and_team(league_name, team_name, season, int(pass_td))
        repository.create_roster_slots(team["id"], slot_counts)
    except (SupabaseAPIError, ValueError, KeyError) as error:
        if league and league.get("id"):
            try:
                repository.delete_league(str(league["id"]))
            except SupabaseAPIError:
                pass
        st.error(str(error))
        return
    st.session_state["cc_team_created"] = True
    st.rerun()


def _assignment(slot: dict[str, Any]) -> dict[str, Any] | None:
    value = slot.get("roster_assignments")
    if isinstance(value, list):
        return value[0] if value else None
    return value if isinstance(value, dict) else None


def _roster_manager(team: dict[str, Any], roster: list[dict[str, Any]], repository: RosterRepository, player_pool: pd.DataFrame) -> None:
    assigned_ids = {str(item["player_id"]) for slot in roster if (item := _assignment(slot))}
    lookup = {str(row["player_id"]): row.to_dict() for _, row in player_pool.iterrows()}
    with st.expander("Add or manage players", expanded=not assigned_ids):
        st.caption("Search by name, then add an eligible player to each lineup slot. Players already used on this team are hidden.")
        for slot in roster:
            slot_id = str(slot["id"])
            slot_type = str(slot["slot_type"])
            slot_number = int(slot.get("slot_order", 0)) + 1
            label = f"{slot_type} {slot_number}"
            assignment = _assignment(slot)
            left, right = st.columns([4, 1], vertical_alignment="bottom")
            if assignment:
                player_id = str(assignment["player_id"])
                player = lookup.get(player_id, {})
                player_name = str(player.get("player", player_id))
                detail = " · ".join(filter(None, [str(player.get("position", "")), str(player.get("team", ""))]))
                left.markdown(f"**{html.escape(label)}**  \\n{html.escape(player_name)} · {html.escape(detail)}")
                if right.button("Remove", key=f"cc_remove_{assignment['id']}", width="stretch"):
                    try:
                        repository.remove_player(str(assignment["id"]), expected={**assignment, "slot_id": str(slot["id"])})
                        st.rerun()
                    except (SupabaseAPIError, ValueError) as error:
                        st.error(str(error))
                continue
            eligible = SLOT_ELIGIBILITY[slot_type]
            candidates = player_pool[
                player_pool["position"].astype(str).isin(eligible)
                & ~player_pool["player_id"].astype(str).isin(assigned_ids)
            ].copy()
            sort_column = "projected_ppr" if "projected_ppr" in candidates else "median_ppr"
            candidates = candidates.sort_values(sort_column, ascending=False)
            candidate_ids = candidates["player_id"].astype(str).tolist()
            candidate_lookup = {str(row["player_id"]): row.to_dict() for _, row in candidates.iterrows()}

            def player_label(player_id: str) -> str:
                player = candidate_lookup[player_id]
                projection = float(player.get("median_ppr", player.get("projected_ppr", 0)) or 0)
                return f"{player.get('player', player_id)} · {player.get('team', 'FA')} {player.get('position', '')} · {projection:.1f} PPR"

            chosen = left.selectbox(
                label,
                candidate_ids,
                index=None,
                placeholder=f"Search eligible {slot_type} players…",
                format_func=player_label,
                key=f"cc_pick_{team['id']}_{slot_id}",
            )
            if right.button("Add", key=f"cc_add_{team['id']}_{slot_id}", disabled=chosen is None, width="stretch"):
                try:
                    repository.assign_player(str(team["id"]), slot_id, str(chosen))
                    st.rerun()
                except (SupabaseAPIError, ValueError, KeyError) as error:
                    st.error(str(error))


def _team_card(team: dict[str, Any], repository: RosterRepository, player_pool: pd.DataFrame) -> None:
    league = team.get("fantasy_leagues") or {}
    roster = repository.team_roster(str(team["id"]))
    starters = sum(1 for slot in roster if slot.get("is_starter"))
    occupied = sum(1 for slot in roster if slot.get("roster_assignments"))
    name = html.escape(str(team.get("name", "Fantasy team")))
    league_name = html.escape(str(league.get("name", "League")))
    scoring = f'Full PPR · {int(league.get("passing_td_points", 4))}-point pass TD'
    st.markdown(
        f'<article class="cc-team-card"><div><span>{league_name}</span><h3>{name}</h3><p>{html.escape(scoring)}</p></div>'
        f'<div class="cc-team-metrics"><strong>{occupied}/{len(roster)}</strong><span>roster spots filled</span>'
        f'<strong>{starters}</strong><span>starters monitored</span></div></article>',
        unsafe_allow_html=True,
    )
    if occupied == 0:
        st.info("Your roster structure is saved. Search below to add each player; no lineup status will be claimed until the required starters are filled.")
    else:
        st.warning("Lineup monitoring is being connected to the saved roster. Until that validation is complete, verify official inactives before kickoff.")
    _roster_manager(team, roster, repository, player_pool)


def render_command_center(api: SupabaseAPI, app_url: str, season: int, player_pool: pd.DataFrame) -> None:
    st.markdown(
        '<div class="cc-hero"><div><span>SUNDAY COMMAND CENTER</span><h1>Is my lineup safe?</h1>'
        '<p>One private home for starter availability, urgent lineup actions, kickoff timing, and eligible replacements.</p></div>'
        '<div class="cc-promise">No false certainty<br><b>Official status stays distinct from model estimates.</b></div></div>',
        unsafe_allow_html=True,
    )
    session = render_auth(api, app_url)
    if not session:
        return
    account_left, account_right = st.columns([4, 1], vertical_alignment="center")
    account_left.caption(f"Signed in as {session.email}")
    with account_right:
        if st.button("Sign out", key="cc_sign_out", width="stretch"):
            sign_out(api, LocalStorage(key="sdl_command_center_sign_out"))
            st.rerun()
    repository = RosterRepository(api, session.access_token, session.user_id)
    try:
        teams = repository.list_teams()
    except SupabaseAPIError as error:
        st.error(str(error))
        return
    if not teams:
        _team_setup(repository, season)
        return
    st.markdown('<div class="cc-section-label">SAVED FANTASY TEAMS</div>', unsafe_allow_html=True)
    for team in teams:
        _team_card(team, repository, player_pool)
    with st.expander("Add another fantasy team"):
        _team_setup(repository, season)

