"""Transparent, optional injury scenarios for weekly fantasy projections."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


SKILL_POSITIONS = {"RB", "WR", "TE"}
OFFENSIVE_LINE_POSITIONS = {"OL", "OT", "LT", "RT", "OG", "LG", "RG", "G", "C"}
HIGH_RISK_AREAS = {"hamstring", "groin", "calf", "concussion", "knee", "ankle", "achilles"}


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _contains(value: Any, *terms: str) -> bool:
    text = _text(value).casefold()
    return any(term in text for term in terms)


def teammate_display_label(player: Any, position: Any) -> str:
    """Use a familiar unit label when an offensive lineman supplies context."""
    normalized_position = _text(position).upper()
    return "O-Line" if normalized_position in OFFENSIVE_LINE_POSITIONS else _text(player)


def direct_availability_factor(row: pd.Series) -> float:
    """Conservative workload factor based only on live designation and practice trend."""
    status = _text(row.get("injury_status_live")).casefold()
    practice = _text(row.get("practice_status_live")).casefold()
    if any(term in status for term in ("inactive", "injured reserve", "reserve/injured", "ir", "pup")) or status == "out":
        return 0.0
    if "doubtful" in status:
        return 0.25
    if "questionable" in status:
        if any(term in practice for term in ("did not", "dnp")):
            return 0.70
        if "limited" in practice:
            return 0.85
        if "full" in practice:
            return 0.97
        return 0.82
    if any(term in practice for term in ("did not", "dnp")):
        return 0.78
    if "limited" in practice:
        return 0.92
    return 1.0


def _recovery_outlook(row: pd.Series, factor: float) -> str:
    status = _text(row.get("injury_status_live")).casefold()
    practice = _text(row.get("practice_status_live")).casefold()
    if factor == 0:
        return "Unavailable this week; no return date is inferred."
    if "doubtful" in status:
        return "Unlikely to play this week; no return date is inferred."
    if "questionable" in status and any(term in practice for term in ("did not", "dnp")):
        return "True game-time risk; monitor the final practice report and inactives."
    if "questionable" in status:
        return "Chance to play, but workload certainty remains below normal."
    if "limited" in practice:
        return "Trending toward availability, with a possible workload limitation."
    if "full" in practice:
        return "Full practice supports normal availability."
    return "No active recovery restriction is supported by the current report."


def _risk_label(row: pd.Series, factor: float) -> str:
    body = _text(row.get("injury_body_part_live")).casefold()
    if factor == 0:
        return "Out"
    if factor <= 0.35:
        return "High risk"
    if factor < 0.80 or any(area in body for area in HIGH_RISK_AREAS) and factor < 0.95:
        return "High risk"
    if factor < 1:
        return "Monitor"
    return "No adjustment"


def _direct_summary(row: pd.Series, factor: float) -> str:
    body = _text(row.get("injury_body_part_live"))
    practice = _text(row.get("practice_status_live"))
    status = _text(row.get("injury_status_live"))
    details = [value for value in (body, practice, status) if value]
    if factor == 1:
        return "No active injury is changing this projection."
    prefix = " · ".join(details) if details else "Active availability concern"
    if factor == 0:
        return f"{prefix}. The injury-adjusted scenario removes the player from projected production."
    reduction = round((1 - factor) * 100)
    return f"{prefix}. We reduce expected workload by about {reduction}% and widen the downside risk."


def apply_injury_scenario(board: pd.DataFrame) -> pd.DataFrame:
    """Add optional injury-adjusted projections without overwriting the baseline model."""
    result = board.copy()
    result["baseline_median_ppr"] = pd.to_numeric(result["median_ppr"], errors="coerce").fillna(0.0)
    result["baseline_floor_ppr"] = pd.to_numeric(result["floor_ppr"], errors="coerce").fillna(0.0)
    result["baseline_ceiling_ppr"] = pd.to_numeric(result["ceiling_ppr"], errors="coerce").fillna(0.0)
    # Row-wise DataFrame.apply constructs hundreds of Series objects on every
    # snapshot refresh. Plain records preserve the exact rules with much lower
    # allocation and dispatch overhead.
    source_records = result.to_dict("records")
    direct_factors = [direct_availability_factor(row) for row in source_records]
    result["injury_direct_factor"] = direct_factors
    row_count = len(result)
    teammate_boost = np.zeros(row_count, dtype=float)
    team_efficiency = np.ones(row_count, dtype=float)
    teammate_effect = np.full(row_count, "", dtype=object)
    # Several unavailable teammates may contribute to one player's scenario.
    # Track the strongest individual contribution so the explanation names the
    # primary driver instead of whichever source row happened to run last.
    teammate_effect_strength = np.zeros(row_count, dtype=float)
    positions = result["position"].astype(str).to_numpy()
    players = result["player"].astype(str).to_numpy()
    factors = np.asarray(direct_factors, dtype=float)
    baselines = result["baseline_median_ppr"].to_numpy(dtype=float)
    opportunities = pd.to_numeric(result.get("recent_opportunities"), errors="coerce").fillna(0).clip(lower=1).to_numpy(dtype=float)
    skill_mask = np.isin(positions, tuple(SKILL_POSITIONS))

    # A missing skill player creates a partial opportunity pool; some team
    # volume simply disappears. NumPy position arrays avoid repeated DataFrame
    # slices and scalar .at writes while preserving the existing calculations.
    for team_positions in result.groupby("team", sort=True).indices.values():
        team_positions = np.asarray(team_positions, dtype=int)
        for source_position in team_positions:
            factor = factors[source_position]
            position = positions[source_position]
            if factor >= 0.99:
                continue
            if position == "QB":
                penalty = min(0.12, (1 - factor) * 0.12)
                candidates = team_positions[skill_mask[team_positions]]
                team_efficiency[candidates] *= 1 - penalty
                teammate_effect[candidates] = f'{players[source_position]} availability lowers the team passing outlook.'
                continue
            if position not in SKILL_POSITIONS:
                continue
            candidates = team_positions[
                (team_positions != source_position)
                & skill_mask[team_positions]
                & (factors[team_positions] >= 0.50)
            ]
            if not len(candidates):
                continue
            affinity = np.where(positions[candidates] == position, 1.2, 1.0)
            weights = opportunities[candidates] * affinity
            pool = baselines[source_position] * (1 - factor) * 0.45
            distributed = pool * weights / weights.sum()
            boosts = np.minimum(3.0, np.minimum(baselines[candidates] * 0.20, distributed))
            teammate_boost[candidates] += boosts
            primary_driver = teammate_display_label(players[source_position], position)
            stronger_effect = boosts > teammate_effect_strength[candidates]
            stronger_candidates = candidates[stronger_effect]
            teammate_effect[stronger_candidates] = f'{primary_driver} reduced availability could create additional opportunity.'
            teammate_effect_strength[stronger_candidates] = boosts[stronger_effect]

    result["injury_teammate_boost"] = teammate_boost
    result["injury_team_efficiency_factor"] = team_efficiency
    result["injury_teammate_effect"] = teammate_effect

    direct = result["injury_direct_factor"]
    team_factor = result["injury_team_efficiency_factor"]
    boost = result["injury_teammate_boost"]
    result["injury_adjusted_median_ppr"] = (result["baseline_median_ppr"] * direct * team_factor + boost).clip(lower=0)
    result["injury_adjusted_floor_ppr"] = (result["baseline_floor_ppr"] * direct * team_factor + boost * 0.50).clip(lower=0)
    result["injury_adjusted_ceiling_ppr"] = (result["baseline_ceiling_ppr"] * direct * team_factor + boost * 1.20).clip(lower=0)
    result.loc[result["injury_teammate_boost"].abs().lt(0.10) & result["injury_team_efficiency_factor"].eq(1.0), "injury_teammate_effect"] = ""
    result["injury_risk_label"] = [
        _risk_label(row, float(factor)) for row, factor in zip(source_records, direct_factors)
    ]
    result["injury_recovery_outlook"] = [
        _recovery_outlook(row, float(factor)) for row, factor in zip(source_records, direct_factors)
    ]
    result["injury_impact_summary"] = [
        _direct_summary(row, float(factor)) for row, factor in zip(source_records, direct_factors)
    ]
    return result
