"""RLS-backed team and roster persistence."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from dashboard.supabase_api import SupabaseAPI, SupabaseAPIError


class RosterRepository:
    def __init__(self, api: SupabaseAPI, access_token: str, user_id: str) -> None:
        if not access_token or not user_id:
            raise ValueError("Authenticated session required")
        self.api = api
        self.access_token = access_token
        self.user_id = user_id

    def list_teams(self) -> list[dict[str, Any]]:
        query = "select=id,name,league_id,updated_at,fantasy_leagues(name,season,scoring_type,passing_td_points)&order=updated_at.desc"
        return self.api.table(self.access_token, "fantasy_teams", query=query) or []

    def sleeper_connection(self, team_id: str) -> dict[str, Any] | None:
        rows = self.api.table(
            self.access_token,
            "sleeper_connections",
            query=f"team_id=eq.{quote(team_id, safe='')}&limit=1",
        ) or []
        return rows[0] if rows else None

    def link_sleeper(self, team_id: str, *, username: str, user_id: str, league_id: str, roster_id: str, league_name: str, team_name: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        rows = self.api.table(
            self.access_token,
            "sleeper_connections",
            method="POST",
            prefer="return=representation,resolution=merge-duplicates",
            payload={
                "team_id": team_id,
                "owner_id": self.user_id,
                "sleeper_username": username,
                "sleeper_user_id": user_id,
                "sleeper_league_id": league_id,
                "sleeper_roster_id": roster_id,
                "league_name": league_name,
                "source_team_name": team_name,
                "last_successful_sync_at": snapshot.get("fetched_at"),
                "last_attempted_sync_at": snapshot.get("fetched_at"),
                "sync_status": "PARTIAL" if snapshot.get("unmatched") else "UP_TO_DATE",
                "last_source_hash": snapshot.get("source_hash"),
                "last_source_snapshot": snapshot,
                "unmatched_players": snapshot.get("unmatched", []),
                "pending_snapshot": None,
                "pending_changes": None,
                "last_error": None,
            },
        )
        return rows[0]

    def set_sleeper_syncing(self, team_id: str) -> None:
        self.api.rpc(self.access_token, "begin_sleeper_sync", {"p_team_id": team_id})

    def record_sleeper_result(self, team_id: str, status: str, *, snapshot: dict[str, Any] | None = None, changes: dict[str, Any] | None = None, error_code: str | None = None) -> None:
        self.api.rpc(
            self.access_token,
            "record_sleeper_sync_result",
            {"p_team_id": team_id, "p_status": status, "p_snapshot": snapshot, "p_changes": changes, "p_error_code": error_code},
        )

    def resolve_sleeper_sync(self, team_id: str, decision: str, assignments: list[dict[str, str]] | None = None) -> None:
        self.api.rpc(
            self.access_token,
            "resolve_sleeper_sync",
            {"p_team_id": team_id, "p_decision": decision, "p_assignments": assignments or []},
        )

    def sleeper_sync_history(self, team_id: str, limit: int = 10) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 25))
        return self.api.table(
            self.access_token,
            "sleeper_sync_history",
            query=f"team_id=eq.{quote(team_id, safe='')}&order=attempted_at.desc&limit={safe_limit}",
        ) or []

    def team_roster(self, team_id: str) -> list[dict[str, Any]]:
        safe_id = quote(team_id, safe="")
        query = (
            "select=id,slot_type,slot_order,is_starter,"
            "roster_assignments(id,player_id,updated_at)&"
            f"team_id=eq.{safe_id}&order=is_starter.desc,slot_order.asc"
        )
        return self.api.table(self.access_token, "roster_slots", query=query) or []

    def create_league_and_team(self, name: str, team_name: str, season: int, passing_td_points: int) -> tuple[dict[str, Any], dict[str, Any]]:
        if passing_td_points not in {4, 6}:
            raise ValueError("Passing touchdowns must be worth 4 or 6 points")
        league_rows = self.api.table(
            self.access_token, "fantasy_leagues", method="POST", prefer="return=representation",
            payload={"owner_id": self.user_id, "name": name.strip(), "season": season, "scoring_type": "full_ppr", "passing_td_points": passing_td_points},
        )
        league = league_rows[0]
        team_rows = self.api.table(
            self.access_token, "fantasy_teams", method="POST", prefer="return=representation",
            payload={"owner_id": self.user_id, "league_id": league["id"], "name": team_name.strip()},
        )
        return league, team_rows[0]

    def create_roster_slots(self, team_id: str, slot_counts: dict[str, int]) -> list[dict[str, Any]]:
        allowed = {"QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "BENCH"}
        rows: list[dict[str, Any]] = []
        for slot_type, count in slot_counts.items():
            if slot_type not in allowed:
                raise ValueError(f"Unsupported roster slot: {slot_type}")
            if not 0 <= int(count) <= 20:
                raise ValueError("Roster slot counts must be between 0 and 20")
            rows.extend(
                {
                    "team_id": team_id,
                    "owner_id": self.user_id,
                    "slot_type": slot_type,
                    "slot_order": index,
                    "is_starter": slot_type != "BENCH",
                }
                for index in range(int(count))
            )
        if not rows:
            raise ValueError("Add at least one roster slot")
        return self.api.table(
            self.access_token,
            "roster_slots",
            method="POST",
            prefer="return=representation",
            payload=rows,
        ) or []

    def delete_league(self, league_id: str) -> None:
        """Remove an incomplete league; database cascades its team and slots."""
        self.api.table(
            self.access_token,
            "fantasy_leagues",
            method="DELETE",
            query=f"id=eq.{quote(league_id, safe='')}",
        )

    def update_league(self, league_id: str, *, name: str, passing_td_points: int) -> None:
        if not name.strip():
            raise ValueError("League name is required")
        if passing_td_points not in {4, 6}:
            raise ValueError("Passing touchdowns must be worth 4 or 6 points")
        self.api.table(
            self.access_token, "fantasy_leagues", method="PATCH",
            query=f"id=eq.{quote(league_id, safe='')}", prefer="return=minimal",
            payload={"name": name.strip(), "passing_td_points": passing_td_points},
        )

    def update_team_name(self, team_id: str, name: str) -> None:
        if not name.strip():
            raise ValueError("Team name is required")
        self.api.table(
            self.access_token, "fantasy_teams", method="PATCH",
            query=f"id=eq.{quote(team_id, safe='')}", prefer="return=minimal",
            payload={"name": name.strip()},
        )

    def reconcile_roster_slots(self, team_id: str, roster: list[dict[str, Any]], desired_counts: dict[str, int]) -> None:
        allowed = {"QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "BENCH"}
        grouped: dict[str, list[dict[str, Any]]] = {slot: [] for slot in allowed}
        for row in roster:
            grouped[str(row["slot_type"])].append(row)
        removals: list[dict[str, Any]] = []
        additions: list[dict[str, Any]] = []
        for slot_type, desired in desired_counts.items():
            if slot_type not in allowed or not 0 <= int(desired) <= 20:
                raise ValueError("Roster slot counts must be between 0 and 20")
            existing = sorted(grouped[slot_type], key=lambda row: int(row.get("slot_order", 0)))
            difference = int(desired) - len(existing)
            if difference < 0:
                empty = [row for row in reversed(existing) if not row.get("roster_assignments")]
                if len(empty) < abs(difference):
                    raise ValueError(f"Remove players from {slot_type} slots before reducing that slot count")
                removals.extend(empty[:abs(difference)])
            elif difference > 0:
                next_order = max((int(row.get("slot_order", -1)) for row in existing), default=-1) + 1
                additions.extend({"team_id": team_id, "owner_id": self.user_id, "slot_type": slot_type, "slot_order": next_order + offset, "is_starter": slot_type != "BENCH"} for offset in range(difference))
        for row in removals:
            self.api.table(self.access_token, "roster_slots", method="DELETE", query=f"id=eq.{quote(str(row['id']), safe='')}")
        if additions:
            self.api.table(self.access_token, "roster_slots", method="POST", prefer="return=minimal", payload=additions)

    def assign_player(self, team_id: str, slot_id: str, player_id: str) -> dict[str, Any]:
        rows = self.api.table(
            self.access_token, "roster_assignments", method="POST", prefer="return=representation,resolution=merge-duplicates",
            payload={"owner_id": self.user_id, "team_id": team_id, "slot_id": slot_id, "player_id": player_id},
        )
        return rows[0]

    @staticmethod
    def _assignment_precondition(assignment_id: str, expected: dict[str, Any]) -> str:
        """Compare-and-set in the database statement, not a racy pre-read."""
        fields = {"id": assignment_id, "slot_id": expected.get("slot_id"),
                  "player_id": expected.get("player_id"), "updated_at": expected.get("updated_at")}
        if any(not value for value in fields.values()):
            raise ValueError("Reload the roster before editing this assignment")
        return "&".join(f"{field}=eq.{quote(str(value), safe='')}" for field, value in fields.items())

    def remove_player(self, assignment_id: str, *, expected: dict[str, Any]) -> None:
        rows = self.api.table(self.access_token, "roster_assignments", method="DELETE",
                              query=self._assignment_precondition(assignment_id, expected),
                              prefer="return=representation")
        if not rows:
            raise SupabaseAPIError("Roster changed; reload before saving")

    def move_player(self, assignment_id: str, destination_slot_id: str, *, expected: dict[str, Any]) -> None:
        """Move an assignment into an empty slot owned by the current user."""
        rows = self.api.table(
            self.access_token, "roster_assignments", method="PATCH",
            query=self._assignment_precondition(assignment_id, expected), prefer="return=representation",
            payload={"slot_id": destination_slot_id},
        )
        if not rows:
            raise SupabaseAPIError("Roster changed; reload before saving")

    def swap_players(self, first: dict[str, Any], second: dict[str, Any], team_id: str) -> None:
        """One authorized transaction; stale displayed assignments are rejected."""
        self.api.rpc(self.access_token, "swap_roster_players", {
            "p_team_id": team_id,
            "p_first_id": str(first["id"]), "p_first_slot": str(first["slot_id"]), "p_first_player": str(first["player_id"]),
            "p_second_id": str(second["id"]), "p_second_slot": str(second["slot_id"]), "p_second_player": str(second["player_id"]),
        })

