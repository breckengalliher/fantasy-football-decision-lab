"""Offline, read-only football validation. Never changes a forecast.

Hard rules are accounting/scoring/identity constraints. Statistical flags are
reviewable, not caps. Team identities require callers to assert complete feeds.
Scoring independently follows nflfastR calculate_stats.R (Full PPR, 4/6 pass TD).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

POSITIONS = ("QB", "RB", "WR", "TE")
SCORING = {
    "passing_yards": .04, "passing_tds": 4, "passing_interceptions": -2,
    "rushing_yards": .1, "receiving_yards": .1, "receptions": 1,
    "rushing_tds": 6, "receiving_tds": 6, "special_teams_tds": 6,
    "passing_2pt_conversions": 2, "rushing_2pt_conversions": 2,
    "receiving_2pt_conversions": 2, "sack_fumbles_lost": -2,
    "rushing_fumbles_lost": -2, "receiving_fumbles_lost": -2,
}
ELIGIBLE = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"},
            "FLEX": {"RB", "WR", "TE"}, "SUPERFLEX": set(POSITIONS), "BENCH": set(POSITIONS)}


@dataclass(frozen=True)
class FootballFlag:
    code: str
    severity: str
    entity: str
    week: Any
    calculation: str
    expected: str
    observed: str
    evidence: str
    code_location: str
    recommendation: str

    def to_dict(self) -> dict:
        return asdict(self)


def independent_ppr(games: pd.DataFrame, passing_td_points: int = 4) -> pd.Series:
    """Explicit offline fixture scorer; validator requires complete scoring columns."""
    if passing_td_points not in (4, 6):
        raise ValueError("Only Full PPR with four- or six-point passing TD is supported")
    points = pd.Series(0.0, index=games.index)
    for column, weight in SCORING.items():
        if column in games:
            coefficient = passing_td_points if column == "passing_tds" else weight
            points += pd.to_numeric(games[column], errors="coerce").fillna(0) * coefficient
    return points


def validate_weekly(games: pd.DataFrame, *, complete_team_feed: bool = False) -> list[FootballFlag]:
    flags = []
    def add(row, code, severity, calculation, expected, observed, location, recommendation):
        flags.append(FootballFlag(code, severity, str(row.get("player_id", row.get("team", "dataset"))), row.get("week"), calculation, expected, str(observed), f"Observed input row: {row.get('player_display_name', row.get('team', 'dataset'))}", location, recommendation))
    keys = [c for c in ("season", "season_type", "week", "player_id", "team") if c in games]
    if "player_id" in games:
        for _, row in games.loc[games["player_id"].isna() | games["player_id"].astype(str).str.strip().eq("")].iterrows():
            # nflverse includes unattributed/non-player records. They belong in
            # team accounting but must never become selectable player identities.
            severity = "hard_error" if row.get("position") in POSITIONS else "modeling_warning"
            add(row, "missing_identity", severity, "player identity", "Stable ID present for supported player positions", "Missing ID", "dashboard/data.py:build_start_sit_board", "Exclude unattributed rows from player features; retain team accounting")
        for _, row in games.loc[games.duplicated(keys, keep=False)].iterrows():
            add(row, "duplicate_game", "hard_error", "game aggregation", "One row per player/team/week/type", "Duplicate key", "dashboard/data.py:build_start_sit_board", "Deduplicate source, not player names")
    for left, right in (("completions", "attempts"), ("receptions", "targets")):
        if {left, right}.issubset(games):
            for _, row in games.loc[pd.to_numeric(games[left], errors="coerce") > pd.to_numeric(games[right], errors="coerce")].iterrows():
                add(row, "count_identity", "hard_error", f"{left}/{right}", f"{left} <= {right}", f"{row[left]} > {row[right]}", "src/football_qa.py:validate_weekly", "Verify official stat corrections and target attribution")
    counts = [c for c in SCORING if c in games and not c.endswith("yards")]
    for column in counts:
        for _, row in games.loc[pd.to_numeric(games[column], errors="coerce") < 0].iterrows():
            add(row, "negative_count", "hard_error", column, "Nonnegative count (negative yards are legal)", row[column], "src/football_qa.py:validate_weekly", "Repair malformed feed")
    missing = set(SCORING) - set(games)
    if missing:
        add({}, "incomplete_scoring", "modeling_warning", "independent scoring", "All scoring categories available", sorted(missing), "dashboard/data.py:_position_fantasy_points", "Do not certify a partial reconstruction as complete")
    elif "fantasy_points_ppr" in games:
        expected = independent_ppr(games)
        observed = pd.to_numeric(games["fantasy_points_ppr"], errors="coerce")
        for _, row in games.loc[observed.isna() | ~np.isclose(observed, expected, atol=1e-7)].iterrows():
            add(row, "scoring_mismatch", "hard_error", "Full PPR raw scoring", f"{expected.loc[row.name]:.8f}", row["fantasy_points_ppr"], "dashboard/data.py:_position_fantasy_points", "Reconcile raw categories with authoritative upstream formula")
    if complete_team_feed and {"season", "week", "team", "passing_tds", "receiving_tds", "attempts", "targets"}.issubset(games):
        for key, team in games.groupby(["season", "week", "team"]):
            td_pass, td_rec = team.passing_tds.sum(), team.receiving_tds.sum()
            if not np.isclose(td_pass, td_rec):
                add({"team": key[2], "week": key[1]}, "team_td_identity", "hard_error", "team passing/receiving TD", "Equal for complete team-game feed", f"{td_pass} pass vs {td_rec} rec", "src/football_qa.py:validate_weekly", "Reconcile complete team roster including nonstandard positions")
            if team.targets.sum() > team.attempts.sum():
                add({"team": key[2], "week": key[1]}, "team_targets", "high_priority", "targets/pass attempts", "Targets should not exceed attempts in a reconciled feed", f"{team.targets.sum()} targets vs {team.attempts.sum()} attempts", "src/football_qa.py:validate_weekly", "Investigate feed target attribution; do not cap a forecast")
    return flags


def validate_board(board: pd.DataFrame, reference: pd.DataFrame | None = None) -> list[FootballFlag]:
    flags = []
    def add(row, code, severity, calculation, expected, observed, recommendation):
        flags.append(FootballFlag(code, severity, str(row.get("player_id", "dataset")), row.get("next_week"), calculation, expected, str(observed), str(row.get("player", "Board coverage")), "dashboard/data.py:apply_approved_projection_model", recommendation))
    for _, row in board.iterrows():
        values = pd.to_numeric(pd.Series([row.get(c) for c in ("floor_ppr", "median_ppr", "ceiling_ppr")]), errors="coerce")
        if not np.isfinite(values).all() or not values.iloc[0] <= values.iloc[1] <= values.iloc[2]:
            add(row, "invalid_interval", "hard_error", "projection range", "Finite floor <= median <= ceiling", values.tolist(), "Reject invalid interval; do not silently reorder")
        projected = pd.to_numeric(pd.Series([row.get('projected_ppr', np.nan)]), errors='coerce').iloc[0]
        if not np.isfinite(projected) or not np.isclose(projected, values.iloc[1]):
            add(row, "projection_disagreement", "hard_error", "comparison/rank median", "projected_ppr == median_ppr", row.get("projected_ppr"), "Use one approved expected-points field")
        if bool(row.get("is_roster_relevant", False)) and str(row.get("injury_status_live", "")).strip().casefold() in {"out", "inactive", "ir", "injured reserve", "pup", "suspended"}:
            add(row, "unavailable_in_pool", "high_priority", "start/sit availability", "Unavailable baseline explicitly distinguished from actionable start", row.get("injury_status_live"), "Retain baseline but gate actionable recommendation and show status")
        if row.get("games_played", 0) < 3:
            add(row, "limited_sample", "modeling_warning", "personal-history reliability", "Disclose limited history and priors", f"{row.get('games_played', 0)} games", "Review role evidence; no arbitrary rejection")
        if str(row.get("player_id", "")).startswith("depth:"):
            add(row, "name_based_promoted_id", "high_priority", "promoted-player identity", "Persistent provider/GSIS crosswalk, not a name-generated ID", row.get("player_id"), "Verify aliases, suffixes, and trades before roster persistence")
        if reference is not None and {"position", "fantasy_points_ppr"}.issubset(reference):
            peers = pd.to_numeric(reference.loc[reference.position.eq(row.get("position")), "fantasy_points_ppr"], errors="coerce").dropna()
            if len(peers) >= 100 and values.iloc[1] > peers.quantile(.995):
                add(row, "empirical_tail", "modeling_warning", "historical tail screen", "Review, not cap, medians above reference 99.5th percentile", f"{values.iloc[1]:.2f}; n={len(peers)}; q995={peers.quantile(.995):.2f}", "Confirm role, reference eligibility, and cutoff before judging realism")
    if "player_id" in board:
        for _, row in board.loc[board.player_id.duplicated(keep=False) | board.player_id.isna()].iterrows():
            add(row, "board_identity", "hard_error", "player identity", "Unique nonmissing player ID", row.get("player_id"), "Repair identity join")
    if {"verified_qb_starter", "position", "team"}.issubset(board):
        starters = board.loc[board.position.eq("QB") & board.verified_qb_starter.eq(True)]
        for team, group in starters.groupby("team"):
            if len(group) > 1:
                add(group.iloc[0], "conflicting_qb_depth", "high_priority", "verified QB1 depth", "One unambiguous QB1 per team", f"{team}: {group.player_id.tolist()}", "Resolve conflicting reports; do not treat both as verified starters")
    if not {"projected_attempts", "projected_carries", "projected_targets", "projected_passing_tds", "projected_receiving_tds"}.issubset(board):
        add({}, "no_team_forecast_accounting", "modeling_warning", "team forecast constraints", "Reconciled stat forecasts required to audit forecast accounting", "Point forecasts and historical usage only", "Propose team-level forecasting as a separate model experiment")
    return flags


def validate_assignments(assignments: list[dict]) -> list[FootballFlag]:
    flags, players, slots = [], set(), set()
    for row in assignments:
        player, slot = row.get("player_id"), row.get("slot_id")
        if not player:
            continue  # Empty setup slots are legal, not a football error.
        if player in players or slot in slots or row.get("position") not in ELIGIBLE.get(str(row.get("slot_type", "")).upper(), set()):
            flags.append(FootballFlag("illegal_roster", "hard_error", str(player), row.get("week"), "roster eligibility/uniqueness", "One legal player per slot and one slot per player", str(row), "Assignment fixture or caller-provided roster", "dashboard/repositories/rosters.py", "Reject invalid assignment server-side and in database"))
        players.add(player); slots.add(slot)
    return flags


def require_no_hard_errors(flags: list[FootballFlag]) -> None:
    hard = [f for f in flags if f.severity == "hard_error"]
    if hard:
        raise AssertionError(f"{len(hard)} hard football errors: " + "; ".join(f.code for f in hard[:10]))
