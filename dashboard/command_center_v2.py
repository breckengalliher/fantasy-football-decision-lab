"""Premium, mobile-first Sunday Command Center presentation."""
from __future__ import annotations

import html
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from streamlit_local_storage import LocalStorage

from dashboard.auth_ui import render_auth, sign_out
from dashboard.availability import kickoff_utc, status_key
from dashboard.lineup_rules import LineupAction, build_lineup_actions, lineup_status
from dashboard.presentation import fantasy_game_log, opponent_position_rank, opponent_position_ranks, player_card_stat_summary, player_photo_html, projected_team_total
from dashboard.replacement_optimizer import optimize_replacements
from dashboard.repositories.rosters import RosterRepository
from dashboard.roster_edit_guard import edit_is_current
from dashboard.sleeper_client import SleeperClient, SleeperError, map_player_records, map_players, passing_td_points, roster_shape
from dashboard.sleeper_sync import build_snapshot, detect_changes, external_name, local_starter_ids
from dashboard.supabase_api import SupabaseAPI, SupabaseAPIError
from dashboard.trust_layer import render_trust_strip

DEFAULT_SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 0, "BENCH": 6}
ELIGIBLE = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "FLEX": {"RB", "WR", "TE"}, "SUPERFLEX": {"QB", "RB", "WR", "TE"}, "BENCH": {"QB", "RB", "WR", "TE"}}
CENTRAL = ZoneInfo("America/Chicago")
SLOT_RANK = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "FLEX": 4, "SUPERFLEX": 5, "BENCH": 6}


def _sleeper_public_use_allowed() -> bool:
    """Local development stays testable; Render requires written permission flag."""
    on_render = bool(os.getenv("RENDER_SERVICE_ID") or os.getenv("RENDER_EXTERNAL_URL"))
    permission = os.getenv("SLEEPER_COMMERCIAL_PERMISSION_CONFIRMED", "").strip().casefold() == "true"
    return not on_render or permission


@st.cache_data(ttl=900, show_spinner=False)
def _sleeper_account(username: str, season: int) -> tuple[dict[str, Any], list[Any]]:
    client = SleeperClient()
    user = client.user(username)
    return user, client.leagues(str(user["user_id"]), season)


@st.cache_data(ttl=86400, max_entries=1, show_spinner=False)
def _sleeper_players() -> dict[str, dict[str, Any]]:
    return SleeperClient().players()


def _text(value: Any, fallback: str = "—") -> str:
    if value is None or pd.isna(value) or not str(value).strip() or str(value).casefold() == "none":
        return fallback
    return str(value).strip()


def _assignment(slot: dict[str, Any]) -> dict[str, Any] | None:
    value = slot.get("roster_assignments")
    return (value[0] if value else None) if isinstance(value, list) else (value if isinstance(value, dict) else None)


def _kickoff(player: dict[str, Any]) -> datetime | None:
    return kickoff_utc(player)


def _availability(player: dict[str, Any]) -> str:
    status = status_key(player.get("injury_status_live"))
    return status.title() if status else "No reported designation"


def _player_locked(player: dict[str, Any], now: datetime | None = None) -> bool:
    status = _text(player.get("game_status_live"), "").casefold()
    if status in {"postponed", "rescheduled", "cancelled", "canceled"}:
        return False
    kickoff = _kickoff(player)
    return status in {"in progress", "final", "closed"} or bool(kickoff and kickoff <= (now or datetime.now(timezone.utc)))


def _entry(slot: dict[str, Any], lookup: dict[str, dict[str, Any]], now: datetime) -> dict[str, Any]:
    assignment = _assignment(slot)
    player_id = str(assignment["player_id"]) if assignment else None
    player = lookup.get(player_id or "", {})
    kickoff = _kickoff(player)
    game_status = _text(player.get("game_status_live"), "").casefold()
    return {**player, "slot_id": str(slot["id"]), "assignment_id": str(assignment["id"]) if assignment else None, "slot_type": str(slot["slot_type"]), "slot_order": int(slot.get("slot_order", 0)), "is_starter": bool(slot.get("is_starter")), "player_id": player_id, "availability": _availability(player) if player_id else "Empty", "kickoff_at": kickoff, "game_started": _player_locked(player, now), "bye_week": bool(player.get("bye_week", False)) or _text(player.get("next_opponent"), "").casefold() == "bye", "data_unavailable": bool(player_id and (not player or pd.isna(player.get("median_ppr"))))}


def _assign_imported_roster(repo: RosterRepository, team_id: str, slots: list[dict[str, Any]], starters: list[str], players: list[str], pool: pd.DataFrame) -> None:
    positions = {str(row.player_id): str(row.position) for row in pool.itertuples()}
    available = list(slots)
    assigned: set[str] = set()
    for player_id in starters:
        position = positions.get(player_id, "")
        candidates = [slot for slot in available if slot.get("is_starter") and position in ELIGIBLE[str(slot["slot_type"])]]
        candidates.sort(key=lambda slot: (str(slot["slot_type"]) != position, SLOT_RANK.get(str(slot["slot_type"]), 99)))
        if candidates:
            slot = candidates[0]; repo.assign_player(team_id, str(slot["id"]), player_id); available.remove(slot); assigned.add(player_id)
    bench = [slot for slot in available if not slot.get("is_starter")]
    for player_id in (pid for pid in players if pid not in assigned):
        if not bench: break
        slot = bench.pop(0); repo.assign_player(team_id, str(slot["id"]), player_id)


def _snapshot_assignment_plan(slots: list[dict[str, Any]], snapshot: dict[str, Any], pool: pd.DataFrame) -> list[dict[str, str]]:
    mapped = {str(row.get("external_player_id")): str(row.get("player_id")) for row in snapshot.get("mappings", []) if row.get("matched") and row.get("player_id")}
    starters = [mapped[value] for value in snapshot.get("starters", []) if value in mapped]
    players = [mapped[value] for value in snapshot.get("players", []) if value in mapped]
    positions = {str(row.player_id): str(row.position) for row in pool.itertuples()}
    available, assigned, plan = list(_ordered_slots(slots)), set(), []
    for player_id in starters:
        position = positions.get(player_id, "")
        candidates = [slot for slot in available if slot.get("is_starter") and position in ELIGIBLE[str(slot["slot_type"])]]
        candidates.sort(key=lambda slot: (str(slot["slot_type"]) != position, SLOT_RANK.get(str(slot["slot_type"]), 99)))
        if candidates:
            slot = candidates[0]
            plan.append({"slot_id": str(slot["id"]), "player_id": player_id})
            available.remove(slot); assigned.add(player_id)
    bench = [slot for slot in available if not slot.get("is_starter")]
    for player_id in (value for value in players if value not in assigned):
        if not bench:
            break
        plan.append({"slot_id": str(bench.pop(0)["id"]), "player_id": player_id})
    return plan


def _sleeper_import(repo: RosterRepository, season: int, pool: pd.DataFrame) -> None:
    st.markdown("#### Import from Sleeper")
    st.caption("Read-only import: SDL never asks for your Sleeper password and cannot change your Sleeper lineup.")
    if not _sleeper_public_use_allowed():
        st.warning("Sleeper import is awaiting written integration permission and is not available on the public service yet.")
        return
    username = st.text_input("Sleeper username", key="cc_sleeper_username", placeholder="Enter your public Sleeper username")
    if st.button("Find my Sleeper leagues", disabled=not username.strip(), width="stretch"):
        try:
            user, leagues = _sleeper_account(username, season)
            st.session_state["cc_sleeper_user"] = user
            st.session_state["cc_sleeper_leagues"] = leagues
        except SleeperError as error:
            st.error(str(error))
    user, leagues = st.session_state.get("cc_sleeper_user"), st.session_state.get("cc_sleeper_leagues", [])
    if not user or not leagues:
        return
    league_ids = [league.league_id for league in leagues]
    selected_id = st.selectbox("Sleeper league", league_ids, format_func=lambda value: next(league.name for league in leagues if league.league_id == value))
    league = next(item for item in leagues if item.league_id == selected_id)
    counts, ignored = roster_shape(league.roster_positions)
    td_points, scoring_warning = passing_td_points(league.scoring_settings)
    st.caption("Roster detected · " + " · ".join(f"{count} {slot}" for slot, count in counts.items() if count))
    if ignored:
        st.warning("Not imported because SDL does not project these slots: " + ", ".join(sorted(set(ignored))))
    if scoring_warning:
        st.warning(scoring_warning)
    if st.button("Import this roster", type="primary", width="stretch"):
        created = None
        try:
            sleeper_roster = SleeperClient().roster(league.league_id, str(user["user_id"]))
            source_players = _sleeper_players()
            mappings = map_player_records([str(value) for value in sleeper_roster.get("players") or []], source_players, pool)
            snapshot = build_snapshot(sleeper_roster, league, mappings)
            player_ids, unmatched = map_players([str(value) for value in sleeper_roster.get("players") or []], source_players, pool)
            starter_ids, _ = map_players([str(value) for value in sleeper_roster.get("starters") or [] if value], source_players, pool)
            created, team = repo.create_league_and_team(league.name, str(sleeper_roster.get("metadata", {}).get("team_name") or f"{username}'s team"), league.season, td_points)
            slots = repo.create_roster_slots(str(team["id"]), counts)
            _assign_imported_roster(repo, str(team["id"]), slots, starter_ids, player_ids, pool)
            repo.link_sleeper(
                str(team["id"]), username=username.strip(), user_id=str(user["user_id"]), league_id=league.league_id,
                roster_id=str(sleeper_roster.get("roster_id") or ""), league_name=league.name,
                team_name=str(sleeper_roster.get("metadata", {}).get("team_name") or f"{username}'s team"), snapshot=snapshot,
            )
            if unmatched:
                st.session_state["cc_import_notice"] = f"Imported {len(player_ids)} players. {len(unmatched)} could not be matched and remain open for manual selection."
            st.rerun()
        except (SleeperError, SupabaseAPIError, ValueError, KeyError) as error:
            if created:
                try: repo.delete_league(str(created["id"]))
                except SupabaseAPIError: pass
            st.error(str(error))


def _team_setup(repo: RosterRepository, season: int, pool: pd.DataFrame) -> None:
    st.markdown('<section class="cc-empty"><span>FIRST TEAM</span><h2>Build your lineup monitor</h2><p>Add league settings and your roster shape. Player selection follows immediately.</p></section>', unsafe_allow_html=True)
    import_tab, manual_tab = st.tabs(["Import from Sleeper", "Create manually"])
    with import_tab:
        _sleeper_import(repo, season, pool)
    with manual_tab:
        _manual_team_setup(repo, season)


def _manual_team_setup(repo: RosterRepository, season: int) -> None:
    with st.form("cc_create_team_v2"):
        left, right = st.columns(2)
        league_name, team_name = left.text_input("League name"), right.text_input("Fantasy team name")
        pass_td = st.radio("QB passing touchdowns", [4, 6], horizontal=True, format_func=lambda n: f"{n} points")
        cols, counts = st.columns(4), {}
        for index, (slot, default) in enumerate(DEFAULT_SLOTS.items()):
            counts[slot] = cols[index % 4].number_input(slot, 0, 20, default, key=f"cc_v2_new_{slot}")
        submit = st.form_submit_button("Create team", type="primary", width="stretch")
    if not submit:
        return
    if not league_name.strip() or not team_name.strip():
        st.error("Enter both a league and team name."); return
    league = None
    try:
        league, team = repo.create_league_and_team(league_name, team_name, season, int(pass_td))
        repo.create_roster_slots(team["id"], counts); st.rerun()
    except (SupabaseAPIError, ValueError, KeyError) as error:
        if league:
            try: repo.delete_league(str(league["id"]))
            except SupabaseAPIError: pass
        st.error(str(error))


def _edit_team_settings(team: dict[str, Any], repo: RosterRepository) -> None:
    league = team.get("fantasy_leagues") or {}
    roster = repo.team_roster(str(team["id"]))
    current_counts = {slot: sum(1 for row in roster if str(row["slot_type"]) == slot) for slot in DEFAULT_SLOTS}
    st.markdown("#### Edit league settings")
    with st.form(f"cc_edit_team_{team['id']}"):
        left, right = st.columns(2)
        league_name = left.text_input("League name", value=str(league.get("name", "")))
        team_name = right.text_input("Fantasy team name", value=str(team.get("name", "")))
        passing_td = st.radio("QB passing touchdowns", [4, 6], index=1 if int(league.get("passing_td_points", 4)) == 6 else 0, horizontal=True, format_func=lambda value: f"{value} points")
        st.caption("Roster format · reductions remove empty slots only")
        columns, desired = st.columns(4), {}
        for index, slot_type in enumerate(DEFAULT_SLOTS):
            desired[slot_type] = columns[index % 4].number_input(slot_type, 0, 20, current_counts[slot_type], key=f"cc_edit_{team['id']}_{slot_type}")
        submitted = st.form_submit_button("Save league settings", type="primary", width="stretch")
    if not submitted:
        return
    try:
        repo.reconcile_roster_slots(str(team["id"]), roster, desired)
        repo.update_league(str(team["league_id"]), name=league_name, passing_td_points=int(passing_td))
        repo.update_team_name(str(team["id"]), team_name)
        st.success("League settings saved.")
        st.rerun()
    except (SupabaseAPIError, ValueError) as error:
        st.error(str(error))


def _roster_editor(team: dict[str, Any], roster: list[dict[str, Any]], repo: RosterRepository, pool: pd.DataFrame) -> None:
    used = {str(item["player_id"]) for slot in roster if (item := _assignment(slot))}
    lookup = {str(row["player_id"]): row.to_dict() for _, row in pool.iterrows()}
    st.caption("Search by name. Eligibility and duplicate-player rules are enforced automatically.")
    for slot in roster:
        slot_id, slot_type = str(slot["id"]), str(slot["slot_type"])
        label = f"{slot_type} {int(slot.get('slot_order', 0)) + 1}"
        current = _assignment(slot)
        left, right = st.columns([4, 1], vertical_alignment="bottom")
        if current:
            player = lookup.get(str(current["player_id"]), {})
            left.markdown(f"**{label}**  \\n{html.escape(_text(player.get('player'), str(current['player_id'])))} · {html.escape(_text(player.get('team')))} {_text(player.get('position'), '')}")
            if right.button("Remove", key=f"cc_v2_remove_{current['id']}", width="stretch"):
                try:
                    repo.remove_player(str(current["id"]), expected={**current, "slot_id": slot_id}); st.rerun()
                except (SupabaseAPIError, ValueError) as error:
                    st.error(str(error))
            continue
        candidates = pool[pool["position"].astype(str).isin(ELIGIBLE[slot_type]) & ~pool["player_id"].astype(str).isin(used)].sort_values("median_ppr", ascending=False)
        options, rows = candidates["player_id"].astype(str).tolist(), {str(row["player_id"]): row.to_dict() for _, row in candidates.iterrows()}
        chosen = left.selectbox(label, options, index=None, placeholder=f"Search eligible {slot_type} players…", format_func=lambda pid: f"{rows[pid]['player']} · {rows[pid]['team']} {rows[pid]['position']} · {float(rows[pid]['median_ppr']):.1f} PPR", key=f"cc_v2_pick_{team['id']}_{slot_id}")
        if right.button("Add", key=f"cc_v2_add_{team['id']}_{slot_id}", disabled=chosen is None, width="stretch"):
            try: repo.assign_player(str(team["id"]), slot_id, str(chosen)); st.rerun()
            except SupabaseAPIError as error: st.error(str(error))


def _ordered_slots(roster: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(roster, key=lambda slot: (0 if slot.get("is_starter") else 1, SLOT_RANK.get(str(slot["slot_type"]), 99), int(slot.get("slot_order", 0))))


def _player_lookup(pool: pd.DataFrame, player_ids: set[str] | None = None) -> dict[str, dict[str, Any]]:
    # Batch conversion avoids creating a Pandas Series for every player on
    # every full rerun. Duplicate IDs retain the previous last-row-wins behavior.
    if player_ids is not None:
        pool = pool.loc[pool["player_id"].astype(str).isin(player_ids)]
    return {str(row["player_id"]): row for row in pool.to_dict(orient="records")}


def _matchup_chip(pool: pd.DataFrame, player: dict[str, Any], ranks=None) -> str:
    rank = (ranks.get((str(player.get("position", "")).upper(), str(player.get("next_opponent", "")).upper()))
            if ranks is not None else opponent_position_rank(pool, player))
    if not rank:
        return '<span class="cc-stat-chip neutral"><b>Matchup</b><em>Rank unavailable</em></span>'
    return (
        f'<span class="cc-stat-chip {html.escape(str(rank["tone"]))}"><b>Vs {html.escape(str(rank["opponent"]))}</b>'
        f'<em>{html.escape(str(rank["label"]))} · #{int(rank["rank"])} of {int(rank["total"])}</em></span>'
    )


def _toggle_fantasy_details(open_key: str) -> None:
    """Update state before rendering so the button matches the visible content."""
    st.session_state[open_key] = not st.session_state.get(open_key, False)


@st.fragment
def _fantasy_details(player: dict[str, Any], pool: pd.DataFrame, weekly: pd.DataFrame, passing_td_points: int, key: str) -> None:
    open_key = f"{key}-open"
    st.button(
        "Hide fantasy details" if st.session_state.get(open_key, False) else "Fantasy details & game log",
        key=f"{key}-toggle",
        width="stretch",
        on_click=_toggle_fantasy_details,
        args=(open_key,),
    )
    if st.session_state.get(open_key, False):
        summary = player_card_stat_summary(player)
        game_total = player.get("betting_total_live")
        if game_total is None or pd.isna(game_total):
            game_total = player.get("total_line")
        team_total = projected_team_total(player)
        context = [
            f'{_text(player.get("team"))} {_text(player.get("team_record"), "record unavailable")}',
            f'{_text(player.get("venue"), "Site unavailable").title()} vs {_text(player.get("next_opponent"), "opponent unavailable")}',
        ]
        if game_total is not None and not pd.isna(game_total):
            context.append(f"{float(game_total):.1f}-point game total")
        if team_total is not None:
            context.append(f"{team_total:.1f} implied team points")
        st.markdown(
            f'<div class="cc-detail-summary"><strong>{html.escape(summary["season_line"])}</strong><span>{html.escape(" · ".join(context))}</span></div>',
            unsafe_allow_html=True,
        )
        log = fantasy_game_log(weekly, player, passing_td_points=passing_td_points, limit=5)
        if not log["rows"]:
            st.caption("Fantasy-relevant game log is not available for this player yet.")
            return
        rows = "".join(
            f'<div class="cc-game-log-row"><b>{html.escape(row[0])}</b><span>vs {html.escape(row[1])}</span><strong>{html.escape(row[2])} PPR</strong><small>{html.escape(row[3])} · {html.escape(row[4])} · {html.escape(row[5])} TD</small></div>'
            for row in log["rows"]
        )
        st.markdown(f'<div class="cc-game-log" id="{html.escape(key, quote=True)}">{rows}</div>', unsafe_allow_html=True)


def _compact_roster_editor(team: dict[str, Any], all_roster: list[dict[str, Any]], visible_slots: list[dict[str, Any]], repo: RosterRepository, pool: pd.DataFrame, weekly: pd.DataFrame, passing_td_points: int, lookup: dict[str, dict[str, Any]] | None = None, ranks=None) -> None:
    used = {str(item["player_id"]) for slot in all_roster if (item := _assignment(slot))}
    lookup = lookup if lookup is not None else _player_lookup(pool)
    for slot in _ordered_slots(visible_slots):
        slot_id, slot_type = str(slot["id"]), str(slot["slot_type"])
        label = f"{slot_type} {int(slot.get('slot_order', 0)) + 1}"
        current = _assignment(slot)
        left, right = st.columns([5, 1], vertical_alignment="center")
        if current:
            player = lookup.get(str(current["player_id"]), {})
            projection = float(player.get("median_ppr", 0) or 0)
            photo = player_photo_html(player.get("headshot_url"), player.get("player"))
            summary = player_card_stat_summary(player)
            game_total = player.get("betting_total_live")
            if game_total is None or pd.isna(game_total):
                game_total = player.get("total_line")
            team_total = projected_team_total(player)
            context_parts = [
                f'{_text(player.get("team"))} {_text(player.get("team_record"), "")}'.strip(),
                f'{_text(player.get("venue"), "Site TBD").title()} vs {_text(player.get("next_opponent"), "BYE")}',
            ]
            if game_total is not None and not pd.isna(game_total):
                context_parts.append(f"Game {float(game_total):.1f}")
            if team_total is not None:
                context_parts.append(f"Team {team_total:.1f}")
            stats = (
                f'<div class="cc-roster-stats"><span class="cc-stat-chip projection"><b>Week projection</b><em>{projection:.1f} PPR</em></span>'
                f'<span class="cc-stat-chip"><b>{html.escape(summary["season_label"])}</b><em>{html.escape(summary["season_value"])} PPR</em></span>'
                f'<span class="cc-stat-chip"><b>{html.escape(summary["form_label"])}</b><em>{html.escape(summary["form_value"])} PPR</em></span>'
                f'<span class="cc-stat-chip"><b>{html.escape(summary["workload_label"])}</b><em>{html.escape(summary["workload_value"])}</em></span>'
                f'{_matchup_chip(pool, player, ranks)}</div>'
            )
            left.markdown(
                f'<article class="cc-roster-row"><span class="cc-roster-slot">{html.escape(label)}</span>'
                f'<div class="cc-roster-identity">{photo}<div><strong>{html.escape(_text(player.get("player"), str(current["player_id"])))}</strong>'
                f'<small>{html.escape(" · ".join(context_parts))}</small></div></div>'
                f'<b>{float(player.get("floor_ppr", 0) or 0):.1f}–{float(player.get("ceiling_ppr", 0) or 0):.1f}<small>RANGE</small></b>{stats}</article>',
                unsafe_allow_html=True,
            )
            if right.button("Manage", key=f"cc_compact_manage_{current['id']}", width="stretch", help="Compare, move, swap, or remove this player."):
                key = f"cc_manage_{current['id']}"
                st.session_state[key] = not st.session_state.get(key, False)
                st.session_state.pop(f"cc_edit_revision_{team['id']}_{current['id']}", None)
            if st.session_state.get(f"cc_manage_{current['id']}", False):
                _manage_player(team, all_roster, slot, current, repo, pool, lookup)
            _fantasy_details(player, pool, weekly, passing_td_points, f"cc-log-{current['id']}")
            continue
        candidates = pool[pool["position"].astype(str).isin(ELIGIBLE[slot_type]) & ~pool["player_id"].astype(str).isin(used)].sort_values("median_ppr", ascending=False)
        options = candidates["player_id"].astype(str).tolist()
        rows = {str(row["player_id"]): row.to_dict() for _, row in candidates.iterrows()}
        chosen = left.selectbox(label, options, index=None, placeholder=f"Search and add an eligible {slot_type}…", format_func=lambda pid: f"{rows[pid]['player']} · {rows[pid]['team']} {rows[pid]['position']} · {float(rows[pid]['median_ppr']):.1f} PPR", key=f"cc_compact_pick_{team['id']}_{slot_id}")
        if right.button("Add", key=f"cc_compact_add_{team['id']}_{slot_id}", disabled=chosen is None, width="stretch"):
            try: repo.assign_player(str(team["id"]), slot_id, str(chosen)); st.rerun()
            except SupabaseAPIError as error: st.error(str(error))


def _manage_player(team: dict[str, Any], roster: list[dict[str, Any]], source_slot: dict[str, Any], current: dict[str, Any], repo: RosterRepository, pool: pd.DataFrame, lookup: dict[str, dict[str, Any]] | None = None) -> None:
    revision_key = f"cc_edit_revision_{team['id']}_{current['id']}"
    if not edit_is_current(st.session_state, revision_key, roster):
        st.warning("Your lineup changed in another visit. Review the updated lineup and reopen Manage before saving.")
        st.session_state[f"cc_manage_{current['id']}"] = False
        st.session_state.pop(revision_key, None)
        st.session_state.pop(f"cc_target_{current['id']}", None)
        st.session_state.pop(f"cc_confirm_remove_{current['id']}", None)
        return
    lookup = lookup or {str(row["player_id"]): row.to_dict() for _, row in pool.iterrows()}
    player = lookup.get(str(current["player_id"]), {})
    position = str(player.get("position") or "")
    locked = _player_locked(player)
    target_slots = []
    for slot in _ordered_slots(roster):
        if str(slot["id"]) == str(source_slot["id"]) or position not in ELIGIBLE[str(slot["slot_type"])]:
            continue
        other = _assignment(slot)
        if other:
            other_player = lookup.get(str(other["player_id"]), {})
            if _player_locked(other_player):
                continue
            if str(other_player.get("position") or "") not in ELIGIBLE[str(source_slot["slot_type"])]:
                continue
        target_slots.append(slot)
    st.caption("Lineup management")
    c1, c2 = st.columns(2)
    if c1.button("Compare player", key=f"cc_compare_{current['id']}", width="stretch"):
        st.session_state["cc_return_team"] = str(team["id"])
        st.query_params["team"] = str(team["id"])
        st.query_params["view"] = "decision-room"
        st.query_params["position"] = position if position in {"QB", "RB", "WR", "TE"} else "FLEX"
        st.query_params["players"] = str(player.get("player") or "")
        st.query_params["qb"] = str((team.get("fantasy_leagues") or {}).get("passing_td_points", 4))
        st.rerun()
    confirmed_remove = st.checkbox("Confirm removal from this SDL roster", key=f"cc_confirm_remove_{current['id']}", disabled=locked)
    if c2.button("Remove", key=f"cc_remove_{current['id']}", width="stretch", disabled=locked or not confirmed_remove):
        try:
            repo.remove_player(str(current["id"]), expected={**current, "slot_id": str(source_slot["id"])})
            st.session_state.pop(revision_key, None)
            st.rerun()
        except (SupabaseAPIError, ValueError) as error:
            st.error(str(error))
    if locked:
        st.caption("Game started — lineup moves and removal are locked. Research remains available.")
    if target_slots and not locked:
        target_id = st.selectbox("Move or swap with", [str(slot["id"]) for slot in target_slots], format_func=lambda value: next(f"{slot['slot_type']} {int(slot.get('slot_order', 0)) + 1}" + (" · swap" if _assignment(slot) else " · empty") for slot in target_slots if str(slot["id"]) == value), key=f"cc_target_{current['id']}")
        if st.button("Confirm lineup move", type="primary", key=f"cc_move_{current['id']}", width="stretch"):
            target = next(slot for slot in target_slots if str(slot["id"]) == target_id)
            try:
                other = _assignment(target)
                if other:
                    repo.swap_players({**current, "slot_id": str(source_slot["id"])}, {**other, "slot_id": str(target["id"])}, str(team["id"]))
                else:
                    repo.move_player(str(current["id"]), str(target["id"]), expected={**current, "slot_id": str(source_slot["id"])})
                st.session_state.pop(revision_key, None)
                st.rerun()
            except (SupabaseAPIError, ValueError) as error:
                st.error(str(error))


def _add_player_slot(team: dict[str, Any], all_roster: list[dict[str, Any]], slot: dict[str, Any], repo: RosterRepository, pool: pd.DataFrame, *, title: str | None = None) -> None:
    slot_id, slot_type = str(slot["id"]), str(slot["slot_type"])
    slot_number = int(slot.get("slot_order", 0)) + 1
    used = {str(item["player_id"]) for existing in all_roster if (item := _assignment(existing))}
    candidates = pool[pool["position"].astype(str).isin(ELIGIBLE[slot_type]) & ~pool["player_id"].astype(str).isin(used)].sort_values("median_ppr", ascending=False)
    options = candidates["player_id"].astype(str).tolist()
    rows = {str(row["player_id"]): row.to_dict() for _, row in candidates.iterrows()}
    expander_title = title or f"{slot_type} {slot_number} · + Add player"
    with st.expander(expander_title, expanded=False):
        left, right = st.columns([5, 1], vertical_alignment="bottom")
        chosen = left.selectbox("Find a player", options, index=None, placeholder=f"Search eligible {slot_type} players…", format_func=lambda pid: f"{rows[pid]['player']} · {rows[pid]['team']} {rows[pid]['position']} · {float(rows[pid]['median_ppr']):.1f} PPR", key=f"cc_slot_pick_{team['id']}_{slot_id}")
        if right.button("Add", key=f"cc_slot_add_{team['id']}_{slot_id}", disabled=chosen is None, width="stretch"):
            try: repo.assign_player(str(team["id"]), slot_id, str(chosen)); st.rerun()
            except SupabaseAPIError as error: st.error(str(error))


def _countdown(kickoff: datetime | None, now: datetime) -> str:
    if kickoff is None: return "Kickoff unavailable"
    seconds = int((kickoff - now).total_seconds())
    if seconds <= 0: return "Game started"
    days, rem = divmod(seconds, 86400); hours, rem = divmod(rem, 3600)
    return f"{days}d {hours}h to kickoff" if days else f"{hours}h {max(1, rem // 60)}m to kickoff"


def _player_card(entry: dict[str, Any], compact: bool = False) -> str:
    name = _text(entry.get("player"), "Empty lineup slot")
    status = _text(entry.get("availability"), "Verify status")
    projection = float(entry.get("median_ppr", 0) or 0)
    kickoff = entry.get("kickoff_at")
    when = kickoff.astimezone(CENTRAL).strftime("%a %I:%M %p CT").replace(" 0", " ") if kickoff else "Kickoff unavailable"
    css = "safe" if status == "No reported designation" else "warn"
    return f'<article class="cc-player-card {"compact" if compact else ""}"><div class="cc-player-top"><span class="cc-slot">{entry["slot_type"]} {entry["slot_order"] + 1}</span><span class="cc-availability {css}">{html.escape(status)}</span></div><div class="cc-player-main"><div><h3>{html.escape(name)}</h3><p>{html.escape(_text(entry.get("team")))} · {html.escape(_text(entry.get("position"), entry["slot_type"]))} vs {html.escape(_text(entry.get("next_opponent"), "BYE / unavailable"))} · {html.escape(when)}</p></div><div class="cc-projection"><strong>{projection:.1f}</strong><span>projected PPR</span></div></div><div class="cc-range">{float(entry.get("floor_ppr", 0) or 0):.1f}–{float(entry.get("ceiling_ppr", 0) or 0):.1f} projection range</div></article>'


def _action_card(action: LineupAction, starters: list[dict[str, Any]], now: datetime) -> None:
    entry = next((e for e in starters if e.get("player_id") == action.player_id and e["slot_type"] == action.slot_type), {})
    name, label = _text(entry.get("player"), f"Empty {action.slot_type} slot"), ("MANDATORY FIX" if action.mandatory else "REVIEW")
    headline = action.headline if name.casefold() == action.headline.casefold() else f"{name} · {action.headline}"
    st.markdown(f'<article class="cc-action {action.severity}"><span>{label} · {html.escape(_countdown(action.kickoff_at, now))}</span><h3>{html.escape(headline)}</h3><p>{html.escape(action.explanation)}</p></article>', unsafe_allow_html=True)


def _replacements(team: dict[str, Any], repo: RosterRepository, actions: list[LineupAction], starters: list[dict[str, Any]], bench: list[dict[str, Any]], lookup: dict[str, dict[str, Any]]) -> None:
    open_slots = []
    for action in actions:
        if action.mandatory or action.severity == "urgent":
            entry = next((e for e in starters if e["slot_type"] == action.slot_type and e.get("player_id") == action.player_id), None)
            if entry and not entry.get("game_started"): open_slots.append({"slot_id": entry["slot_id"], "slot_type": entry["slot_type"], "current_projection": float(entry.get("median_ppr", 0) or 0)})
    results = optimize_replacements(open_slots, bench)
    if not results: return
    st.markdown('<div class="cc-section-heading"><span>RECOMMENDED REPLACEMENTS</span><h2>Best eligible bench options</h2></div>', unsafe_allow_html=True)
    for result in results:
        player, edge = lookup.get(result.player_id, {}), result.difference_ppr
        current = next((entry for entry in starters if entry["slot_id"] == result.slot_id), None)
        replacement = next((entry for entry in bench if entry.get("player_id") == result.player_id), None)
        label = "Close call" if abs(edge) < 2 else ("Projected upgrade" if edge > 0 else "Availability fallback")
        photo = player_photo_html(player.get("headshot_url"), player.get("player"))
        st.markdown(f'<article class="cc-replacement"><div class="cc-replacement-identity">{photo}<div><span>{result.slot_type} · {label}</span><h3>{html.escape(_text(player.get("player"), result.player_id))}</h3><p>{html.escape(_text(player.get("team")))} {_text(player.get("position"), "")} vs {html.escape(_text(player.get("next_opponent")))}</p></div></div><div><strong>{result.projected_ppr:.1f}</strong><span>{edge:+.1f} PPR</span></div></article>', unsafe_allow_html=True)
        apply_col, compare_col = st.columns(2)
        can_apply = bool(current and replacement and current.get("assignment_id") and replacement.get("assignment_id"))
        confirmed = st.checkbox("Confirm this swap in SDL only", key=f"cc_confirm_swap_{result.slot_id}_{result.player_id}", help="This saves your SDL lineup; it never changes Sleeper.")
        if apply_col.button("Apply lineup swap", key=f"cc_apply_replacement_{result.slot_id}_{result.player_id}", disabled=not can_apply or not confirmed, type="primary", width="stretch"):
            try:
                repo.swap_players(
                    {"id": current["assignment_id"], "slot_id": current["slot_id"], "player_id": current["player_id"]},
                    {"id": replacement["assignment_id"], "slot_id": replacement["slot_id"], "player_id": replacement["player_id"]},
                    str(team["id"]),
                )
                st.rerun()
            except SupabaseAPIError as error:
                st.error(str(error))
        current_player = lookup.get(str(current.get("player_id")), {}) if current else {}
        if compare_col.button("Compare players", key=f"cc_compare_replacement_{result.slot_id}_{result.player_id}", width="stretch"):
            st.session_state["cc_return_team"] = str(team["id"])
            st.query_params["team"] = str(team["id"])
            st.query_params["view"] = "decision-room"
            positions = {str(player.get("position") or ""), str(current_player.get("position") or "")}
            st.query_params["position"] = (str(player.get("position") or "FLEX") if len(positions) == 1 else ("SUPERFLEX" if "QB" in positions else "FLEX"))
            st.query_params["players"] = "|".join(filter(None, [str(current_player.get("player") or ""), str(player.get("player") or "")]))
            st.query_params["qb"] = str((team.get("fantasy_leagues") or {}).get("passing_td_points", 4))
            st.rerun()


def _sync_time(value: Any) -> str:
    if not value:
        return "Not yet"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(CENTRAL).strftime("%b %d · %I:%M %p CT").replace(" 0", " ")
    except ValueError:
        return "Unavailable"


def _render_sync_review(team: dict[str, Any], repo: RosterRepository, connection: dict[str, Any], roster: list[dict[str, Any]], pool: pd.DataFrame) -> None:
    snapshot = connection.get("pending_snapshot") or {}
    changes = connection.get("pending_changes") or {}
    if not snapshot or not changes:
        return
    st.markdown("#### Sleeper changes detected")
    if changes.get("roster_changed"):
        added = ", ".join(external_name(snapshot, value) for value in changes.get("roster_added", [])) or "None"
        removed = ", ".join(external_name(connection.get("last_source_snapshot") or {}, value) for value in changes.get("roster_removed", [])) or "None"
        st.info(f"**Roster refresh** · Added: {added} · Removed: {removed}")
    else:
        st.caption("Roster membership did not change.")
    if changes.get("lineup_changed"):
        promoted = ", ".join(external_name(snapshot, value) for value in changes.get("starters_added", [])) or "None"
        benched = ", ".join(external_name(connection.get("last_source_snapshot") or {}, value) for value in changes.get("starters_removed", [])) or "None"
        st.warning(f"**Sleeper lineup change** · Moved into starters: {promoted} · Moved to bench: {benched}")
    if changes.get("local_lineup_conflict"):
        st.warning("Your SDL saved lineup differs from Sleeper. Syncing has not changed it. Choose explicitly which lineup SDL should keep.")
    unmatched = snapshot.get("unmatched") or []
    if unmatched:
        names = ", ".join(str(row.get("name") or row.get("external_player_id")) for row in unmatched)
        st.error(f"Unmatched Sleeper players: {names}. No projection or automatic assignment will be created for them.")
    left, right = st.columns(2)
    if left.button("Keep my SDL lineup", key=f"keep_sdl_{team['id']}", width="stretch", help="Acknowledge the Sleeper changes without replacing your saved SDL lineup."):
        try:
            repo.resolve_sleeper_sync(str(team["id"]), "KEEP_SDL_LINEUP")
            st.success("Your SDL lineup was kept. Sleeper remains connected as a read-only source.")
            st.rerun()
        except SupabaseAPIError as error:
            st.error(str(error))
    plan = _snapshot_assignment_plan(roster, snapshot, pool)
    if right.button("Apply Sleeper lineup", key=f"apply_sleeper_{team['id']}", width="stretch", disabled=bool(unmatched), help="Explicitly replace SDL slot assignments with the reviewed Sleeper lineup."):
        try:
            repo.resolve_sleeper_sync(str(team["id"]), "APPLY_SLEEPER_LINEUP", plan)
            st.success("The reviewed Sleeper lineup was applied to SDL.")
            st.rerun()
        except SupabaseAPIError as error:
            st.error(str(error))


def _sleeper_sync_panel(team: dict[str, Any], repo: RosterRepository, roster: list[dict[str, Any]], pool: pd.DataFrame) -> None:
    try:
        connection = repo.sleeper_connection(str(team["id"]))
    except SupabaseAPIError:
        return
    if not connection:
        return
    public_allowed = _sleeper_public_use_allowed()
    status = str(connection.get("sync_status") or "CONNECTED")
    last_success = _sync_time(connection.get("last_successful_sync_at"))
    last_attempt = _sync_time(connection.get("last_attempted_sync_at"))
    pending = bool(connection.get("pending_snapshot"))
    st.markdown(
        f'<section class="cc-sync"><div><span>SLEEPER · {html.escape(status.replace("_", " "))}</span>'
        f'<strong>{html.escape(str(connection.get("league_name") or "Connected league"))}</strong>'
        f'<small>Last successful sync: {html.escape(last_success)} · Latest attempt: {html.escape(last_attempt)}</small></div>'
        f'<b>{"Review changes" if pending else "SDL lineup protected"}</b></section>',
        unsafe_allow_html=True,
    )
    if status == "FAILED":
        st.warning("Couldn't refresh Sleeper. Your last saved SDL roster and lineup are still shown.")
    previous_attempt = connection.get("last_attempted_sync_at")
    cooldown = False
    if previous_attempt:
        try:
            cooldown = datetime.now(timezone.utc) - datetime.fromisoformat(str(previous_attempt).replace("Z", "+00:00")) < timedelta(seconds=60)
        except ValueError:
            pass
    if not public_allowed:
        st.info("Public Sleeper refresh is paused until written integration permission is confirmed. Your SDL lineup remains available.")
    if st.button("Sync with Sleeper", key=f"sync_sleeper_{team['id']}", width="stretch", disabled=not public_allowed or cooldown or st.session_state.get(f"syncing_{team['id']}", False), help="Read-only refresh. SDL will show differences for review and will not replace your saved lineup."):
        sync_key = f"syncing_{team['id']}"
        st.session_state[sync_key] = True
        try:
            repo.set_sleeper_syncing(str(team["id"]))
            with st.spinner("Checking Sleeper for roster and lineup changes…"):
                client = SleeperClient()
                league = client.league(str(connection["sleeper_league_id"]))
                source = client.roster(league.league_id, str(connection["sleeper_user_id"]))
                mappings = map_player_records([str(value) for value in source.get("players") or []], _sleeper_players(), pool)
                snapshot = build_snapshot(source, league, mappings)
                diff = detect_changes(connection.get("last_source_snapshot"), snapshot, local_starter_ids(roster))
                if diff.has_changes:
                    result_status = "PARTIAL" if diff.unmatched else "CHANGES_DETECTED"
                    repo.record_sleeper_result(str(team["id"]), result_status, snapshot=snapshot, changes=diff.as_dict())
                    st.session_state["cc_import_notice"] = "Sleeper changes found. Review them before anything changes in SDL."
                else:
                    repo.record_sleeper_result(str(team["id"]), "UP_TO_DATE", snapshot=snapshot, changes=diff.as_dict())
                    st.session_state["cc_import_notice"] = "Sleeper roster checked. No new source changes were found."
        except (SleeperError, SupabaseAPIError, ValueError, KeyError) as error:
            try:
                repo.record_sleeper_result(str(team["id"]), "FAILED", error_code=type(error).__name__)
            except SupabaseAPIError:
                pass
            st.error(str(error))
        finally:
            st.session_state[sync_key] = False
        st.rerun()
    _render_sync_review(team, repo, connection, roster, pool)


def _dashboard(team: dict[str, Any], repo: RosterRepository, pool: pd.DataFrame, weekly: pd.DataFrame, metadata: dict[str, Any], now: datetime) -> None:
    league, roster = team.get("fantasy_leagues") or {}, _ordered_slots(repo.team_roster(str(team["id"])))
    # Entries, replacements, and management only need saved roster identities.
    # Add/search controls still receive the complete eligible player pool.
    roster_ids = {str(item["player_id"]) for slot in roster if (item := _assignment(slot))}
    lookup = _player_lookup(pool, roster_ids)
    ranks = opponent_position_ranks(pool)
    entries = [_entry(slot, lookup, now) for slot in roster]
    starters, bench = [e for e in entries if e["is_starter"]], [e for e in entries if not e["is_starter"] and e.get("player_id")]
    all_actions = build_lineup_actions(starters, now)
    actions = [action for action in all_actions if action.player_id is not None]
    has_empty_starters = any(not entry.get("player_id") for entry in starters)
    status = lineup_status(starters, metadata, now)
    next_kickoff = min((e["kickoff_at"] for e in starters if e.get("kickoff_at") and e["kickoff_at"] > now), default=None)
    occupied_starters = [entry for entry in starters if entry.get("player_id")]
    starter_projection = sum(float(entry.get("median_ppr", 0) or 0) for entry in occupied_starters)
    bench_count = sum(1 for entry in entries if not entry["is_starter"] and entry.get("player_id"))
    copy = {"INCOMPLETE SETUP": "Add players to your open starting positions. Empty setup slots are not treated as injury warnings.", "READY": "No actionable lineup issues detected based on the latest available information. This is not a performance guarantee.", "INJURY CONCERN": "One or more starters have uncertain availability. Check official inactives before kickoff.", "ACTION REQUIRED": "A starter is unavailable or on bye. Review an eligible replacement; games already started may be locked.", "VERIFY DATA": "Essential information is missing or stale. Verify before making a decision.", "GAME IN PROGRESS": "At least one starter's game has begun. Started players cannot be moved."}[status]
    refreshed = _text(metadata.get("context_refreshed_at") or metadata.get("refreshed_at"), "Unavailable")
    if refreshed != "Unavailable":
        try: refreshed = datetime.fromisoformat(refreshed.replace("Z", "+00:00")).astimezone(CENTRAL).strftime("%b %d · %I:%M %p CT").replace(" 0", " ")
        except ValueError: pass
    st.markdown(f'<section class="cc-status status-{status.lower().replace(" ", "-")}"><div><span>LINEUP STATUS</span><h1>{html.escape(status)}</h1><p>{html.escape(copy)}</p></div><div class="cc-status-meta"><b>{html.escape(str(team["name"]))}</b><span>{html.escape(_text(league.get("name"), "Saved league"))} · Week {_text(metadata.get("next_week"))} · Full PPR · {int(league.get("passing_td_points", 4))}-pt pass TD</span><span>{len(occupied_starters)}/{len(starters)} starters filled · {bench_count} bench · {starter_projection:.1f} projected starter PPR</span><span>{len(actions)} requiring attention · {_countdown(next_kickoff, now)}</span><span>Updated {html.escape(refreshed)}</span></div></section>', unsafe_allow_html=True)
    render_trust_strip(metadata)
    _sleeper_sync_panel(team, repo, roster, pool)
    if actions:
        st.markdown('<div class="cc-section-heading"><span>ACTION CENTER</span><h2>Handle these first</h2></div>', unsafe_allow_html=True)
        for action in actions:
            _action_card(action, starters, now)
    elif status == "READY": st.success("YOUR LINEUP LOOKS READY — No actionable lineup issues detected based on the latest available information.")
    _replacements(team, repo, actions, starters, bench, lookup)
    starter_slots = [slot for slot in roster if slot.get("is_starter")]
    bench_slots = [slot for slot in roster if not slot.get("is_starter")]
    passing_td_points = int(league.get("passing_td_points", 4))
    st.markdown('<div class="cc-section-heading cc-tight-heading"><span>STARTING LINEUP</span><h2>Build your starters</h2><p>QB · RB · RB · WR · WR · TE · FLEX / SUPERFLEX</p></div>', unsafe_allow_html=True)
    for slot in _ordered_slots(starter_slots):
        if _assignment(slot):
            _compact_roster_editor(team, roster, [slot], repo, pool, weekly, passing_td_points, lookup, ranks)
        else:
            _add_player_slot(team, roster, slot, repo, pool)
    st.markdown(f'<div class="cc-section-heading cc-tight-heading"><span>BENCH</span><h2>{len(bench_slots)} roster spots</h2></div>', unsafe_allow_html=True)
    for slot in _ordered_slots(bench_slots):
        if _assignment(slot):
            _compact_roster_editor(team, roster, [slot], repo, pool, weekly, passing_td_points, lookup, ranks)
        else:
            _add_player_slot(team, roster, slot, repo, pool)


def authenticate_command_center(api: SupabaseAPI, app_url: str):
    """Restore or render authentication before loading public NFL datasets."""
    return render_auth(api, app_url)


def render_command_center(api: SupabaseAPI, app_url: str, season: int, player_pool: pd.DataFrame, weekly: pd.DataFrame, metadata: dict[str, Any], session=None) -> None:
    # Invalid saved forecasts remain in audit files, never in add/compare/swap pools.
    if "forecast_valid" in player_pool:
        player_pool = player_pool.loc[player_pool.forecast_valid.eq(True)].copy()
    session = session or render_auth(api, app_url)
    if not session: return
    repo = RosterRepository(api, session.access_token, session.user_id)
    try: teams = repo.list_teams()
    except SupabaseAPIError as error: st.error(str(error)); return
    left, right = st.columns([3, 1], vertical_alignment="center")
    left.markdown('<div class="cc-brandline">SUNDAY COMMAND CENTER</div>', unsafe_allow_html=True)
    if right.button("Sign out", key="cc_v2_sign_out", width="stretch"):
        sign_out(api); st.rerun()
    if not teams: _team_setup(repo, season, player_pool); return
    if notice := st.session_state.pop("cc_import_notice", None):
        st.info(notice)
    ids = [str(t["id"]) for t in teams]
    requested_team = str(st.query_params.get("team", st.session_state.get("cc_return_team", "")))
    selected_id = st.selectbox("Fantasy team", ids, index=ids.index(requested_team) if requested_team in ids else 0, key="cc_selected_team", format_func=lambda tid: next(str(t["name"]) for t in teams if str(t["id"]) == tid), label_visibility="collapsed")
    st.query_params["team"] = selected_id
    selected_team = next(t for t in teams if str(t["id"]) == selected_id)
    scoring = str((selected_team.get("fantasy_leagues") or {}).get("passing_td_points", 4))
    if str(st.query_params.get("qb", "4")) != scoring:
        st.query_params["qb"] = scoring
        st.rerun()
    _dashboard(selected_team, repo, player_pool, weekly, metadata, datetime.now(timezone.utc))
    settings_key = "cc_team_settings_open"
    if st.button(
        "Close team settings" if st.session_state.get(settings_key, False) else "Team settings and additional teams",
        key="cc_team_settings_toggle",
        width="stretch",
    ):
        st.session_state[settings_key] = not st.session_state.get(settings_key, False)
    if st.session_state.get(settings_key, False):
        selected_team = next(t for t in teams if str(t["id"]) == selected_id)
        st.caption(f"Signed in as {session.email}")
        _edit_team_settings(selected_team, repo)
        st.divider()
        _team_setup(repo, season, player_pool)
