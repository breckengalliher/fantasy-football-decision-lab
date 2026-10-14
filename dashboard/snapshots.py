"""Weekly snapshot and personnel-change helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


OFFENSIVE_LINE_POSITIONS = {"C", "G", "LG", "RG", "T", "OT", "LT", "RT"}


def build_personnel_context(
    current: pd.DataFrame, previous: pd.DataFrame | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare current and previous depth charts without affecting projections."""
    current = current.copy()
    previous = pd.DataFrame() if previous is None else previous.copy()
    required = {"player_key", "team", "depth_position_live", "depth_order_live"}
    if not required.issubset(current.columns):
        return pd.DataFrame(), pd.DataFrame()

    player = current[list(required)].drop_duplicates(["player_key", "team"])
    if required.issubset(previous.columns):
        prior = previous[list(required)].drop_duplicates(["player_key", "team"]).rename(
            columns={
                "depth_position_live": "previous_depth_position",
                "depth_order_live": "previous_depth_order",
            }
        )
        player = player.merge(prior, on=["player_key", "team"], how="left")
    else:
        player["previous_depth_position"] = pd.NA
        player["previous_depth_order"] = pd.NA
    current_order = pd.to_numeric(player["depth_order_live"], errors="coerce")
    previous_order = pd.to_numeric(player["previous_depth_order"], errors="coerce")
    player["depth_order_changed"] = (
        previous_order.notna() & current_order.ne(previous_order)
    ).fillna(False)

    def team_summary(frame: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for team, group in frame.groupby("team"):
            qb = group.loc[
                group["depth_position_live"].eq("QB")
                & pd.to_numeric(group["depth_order_live"], errors="coerce").eq(1),
                "player_key",
            ].tolist()
            line = sorted(
                group.loc[
                    group["depth_position_live"].isin(OFFENSIVE_LINE_POSITIONS)
                    & pd.to_numeric(group["depth_order_live"], errors="coerce").eq(1),
                    "player_key",
                ].tolist()
            )
            rows.append({"team": team, "starting_qb": qb[0] if qb else pd.NA, "starting_ol": "|".join(line)})
        return pd.DataFrame(rows)

    current_team = team_summary(current)
    if required.issubset(previous.columns) and not previous.empty:
        previous_team = team_summary(previous).rename(
            columns={"starting_qb": "previous_starting_qb", "starting_ol": "previous_starting_ol"}
        )
        team = current_team.merge(previous_team, on="team", how="left")
    else:
        team = current_team.copy()
        team["previous_starting_qb"] = pd.NA
        team["previous_starting_ol"] = pd.NA
    team["qb_changed"] = (
        team["previous_starting_qb"].notna()
        & team["starting_qb"].astype("string").ne(team["previous_starting_qb"].astype("string"))
    ).fillna(False)
    team["ol_changed"] = (
        team["previous_starting_ol"].notna()
        & team["starting_ol"].astype("string").ne(team["previous_starting_ol"].astype("string"))
    ).fillna(False)
    return player, team


def load_personnel_snapshot(project_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    processed = project_root / "data" / "processed"
    player_path = processed / "personnel_players_current.parquet"
    team_path = processed / "personnel_teams_current.parquet"
    players = pd.read_parquet(player_path) if player_path.exists() else pd.DataFrame()
    teams = pd.read_parquet(team_path) if team_path.exists() else pd.DataFrame()
    return players, teams
