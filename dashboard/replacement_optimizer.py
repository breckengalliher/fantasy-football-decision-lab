"""Roster-wide legal replacement assignment for Command Center actions."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable
from dashboard.availability import status_key, UNAVAILABLE


ELIGIBLE = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"},
    "FLEX": {"RB", "WR", "TE"}, "SUPERFLEX": {"QB", "RB", "WR", "TE"},
}


@dataclass(frozen=True)
class Replacement:
    slot_id: str
    slot_type: str
    player_id: str
    projected_ppr: float
    difference_ppr: float


def optimize_replacements(
    open_slots: Iterable[dict[str, Any]], bench: Iterable[dict[str, Any]],
) -> list[Replacement]:
    """Maximize total median PPR while assigning each bench player at most once."""
    slots = list(open_slots)
    candidates = [
        player for player in bench
        if not player.get("game_started", False)
        and not player.get("bye_week", False)
        and not player.get("data_unavailable", False)
        and player.get("forecast_valid", True)
        and player.get("player_id")
        and status_key(player.get("availability", "")) not in UNAVAILABLE
    ]
    if not slots or not candidates:
        return []
    # One column per stable player ID, plus an empty option per slot.
    candidates = list({str(p["player_id"]): p for p in candidates}.values())
    projections = [float(p.get("median_ppr", p.get("projected_ppr", 0)) or 0) for p in candidates]
    costs = []
    for slot in slots:
        eligible = ELIGIBLE.get(str(slot["slot_type"]).upper(), set())
        costs.append([
            -score if isfinite(score) and str(p.get("position", "")).upper() in eligible else float("inf")
            for p, score in zip(candidates, projections)
        ] + [0.0] * len(slots))
    assignment = _minimum_assignment(costs)
    result = []
    for slot, column in zip(slots, assignment):
        if column >= len(candidates):
            continue
        player, projection = candidates[column], projections[column]
        result.append(Replacement(str(slot["slot_id"]), str(slot["slot_type"]).upper(), str(player["player_id"]), projection, projection - float(slot.get("current_projection", 0) or 0)))
    return result


def _minimum_assignment(costs: list[list[float]]) -> list[int]:
    """Rectangular Hungarian solver: exact optimum in O(rows² × columns).

    Empty columns guarantee a finite solution without optional dependencies.
    """
    n, m = len(costs), len(costs[0])
    u, v = [0.0] * (n + 1), [0.0] * (m + 1)
    matched, previous = [0] * (m + 1), [0] * (m + 1)
    for row in range(1, n + 1):
        matched[0] = row
        column = 0
        minimum, used = [float("inf")] * (m + 1), [False] * (m + 1)
        while True:
            used[column] = True
            current = matched[column]
            delta, next_column = float("inf"), 0
            for candidate in range(1, m + 1):
                if used[candidate]:
                    continue
                reduced = costs[current - 1][candidate - 1] - u[current] - v[candidate]
                if reduced < minimum[candidate]:
                    minimum[candidate], previous[candidate] = reduced, column
                if minimum[candidate] < delta:
                    delta, next_column = minimum[candidate], candidate
            for candidate in range(m + 1):
                if used[candidate]:
                    u[matched[candidate]] += delta
                    v[candidate] -= delta
                else:
                    minimum[candidate] -= delta
            column = next_column
            if not matched[column]:
                break
        while column:
            parent = previous[column]
            matched[column] = matched[parent]
            column = parent
    result = [m] * n
    for column in range(1, m + 1):
        if matched[column]:
            result[matched[column] - 1] = column - 1
    return result

