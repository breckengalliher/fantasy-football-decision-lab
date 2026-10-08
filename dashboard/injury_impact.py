"""Transparent, optional injury scenarios for weekly fantasy projections."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


SKILL_POSITIONS = {"RB", "WR", "TE"}
HIGH_RISK_AREAS = {"hamstring", "groin", "calf", "concussion", "knee", "ankle", "achilles"}


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _contains(value: Any, *terms: str) -> bool:
    text = _text(value).casefold()
    return any(term in text for term in terms)


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
    result["injury_direct_factor"] = result.apply(direct_availability_factor, axis=1)
    result["injury_teammate_boost"] = 0.0
    result["injury_team_efficiency_factor"] = 1.0
    result["injury_teammate_effect"] = ""

    # A missing skill player creates a partial opportunity pool; some team volume simply disappears.
    for team, team_rows in result.groupby("team"):
        for source_index, source in team_rows.iterrows():
            factor = float(source["injury_direct_factor"])
            position = _text(source.get("position"))
            if factor >= 0.99:
                continue
            if position == "QB":
                penalty = min(0.12, (1 - factor) * 0.12)
                candidate_index = team_rows.index[team_rows["position"].isin(SKILL_POSITIONS)]
                result.loc[candidate_index, "injury_team_efficiency_factor"] *= 1 - penalty
                for index in candidate_index:
                    result.at[index, "injury_teammate_effect"] = f'{source["player"]} availability lowers the team passing outlook.'
                continue
            if position not in SKILL_POSITIONS:
                continue
            candidates = team_rows.loc[
                (team_rows.index != source_index)
                & team_rows["position"].isin(SKILL_POSITIONS)
                & team_rows["injury_direct_factor"].ge(0.50)
            ].copy()
            if candidates.empty:
                continue
            usage = pd.to_numeric(candidates.get("recent_opportunities"), errors="coerce").fillna(0).clip(lower=1)
            affinity = candidates["position"].map(lambda value: 1.2 if value == position else 1.0)
            weights = usage * affinity
            pool = float(source["baseline_median_ppr"]) * (1 - factor) * 0.45
            for index, weight in weights.items():
                baseline = float(result.at[index, "baseline_median_ppr"])
                boost = min(3.0, baseline * 0.20, pool * float(weight / weights.sum()))
                result.at[index, "injury_teammate_boost"] += boost
                result.at[index, "injury_teammate_effect"] = f'{source["player"]} reduced availability could create additional opportunity.'

    direct = result["injury_direct_factor"]
    team_factor = result["injury_team_efficiency_factor"]
    boost = result["injury_teammate_boost"]
    result["injury_adjusted_median_ppr"] = (result["baseline_median_ppr"] * direct * team_factor + boost).clip(lower=0)
    result["injury_adjusted_floor_ppr"] = (result["baseline_floor_ppr"] * direct * team_factor + boost * 0.50).clip(lower=0)
    result["injury_adjusted_ceiling_ppr"] = (result["baseline_ceiling_ppr"] * direct * team_factor + boost * 1.20).clip(lower=0)
    result.loc[result["injury_teammate_boost"].abs().lt(0.10), "injury_teammate_effect"] = ""
    result["injury_risk_label"] = result.apply(lambda row: _risk_label(row, float(row["injury_direct_factor"])), axis=1)
    result["injury_recovery_outlook"] = result.apply(lambda row: _recovery_outlook(row, float(row["injury_direct_factor"])), axis=1)
    result["injury_impact_summary"] = result.apply(lambda row: _direct_summary(row, float(row["injury_direct_factor"])), axis=1)
    return result
