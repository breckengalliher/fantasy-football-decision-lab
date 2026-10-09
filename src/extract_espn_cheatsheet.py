"""Extract a normalized historical auction reference from an ESPN cheat sheet PDF."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
import pdfplumber


ENTRY_PATTERN = re.compile(
    r"\d+\.\s+\((?P<overall_rank>\d+)\)\s+"
    r"(?P<player>.+?),\s+(?P<team>[A-Z]{2,3})\s+"
    r"\$(?P<market_value>\d+)\s+(?P<bye_week>\d+)"
)

TOP300_PATTERN = re.compile(
    r"(?P<overall_rank>\d+)\.\s+\((?P<position>QB|RB|WR|TE|DST|K)(?P<position_rank>\d+)\)\s+"
    r"(?P<player>.+?),\s+(?P<team>[A-Z]{2,3})\s+"
    r"\$(?P<espn_10_team_value>\d+)\s+(?P<bye_week>\d+)"
)


def extract_entries(pdf_path: Path) -> pd.DataFrame:
    """Extract player entries and attach the visible sheet assumptions."""
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text(x_tolerance=1, y_tolerance=3) or "" for page in pdf.pages)
    entries = pd.DataFrame(match.groupdict() for match in ENTRY_PATTERN.finditer(text))
    if entries.empty:
        raise ValueError("No ESPN auction entries were found in the PDF.")
    for column in ["overall_rank", "market_value", "bye_week"]:
        entries[column] = pd.to_numeric(entries[column])
    entries = entries.sort_values("overall_rank").drop_duplicates(
        "overall_rank", keep="first"
    )
    entries["season"] = 2025
    entries["source"] = "ESPN 2025 Fantasy Football Draft Kit - PPR"
    entries["source_as_of"] = "2025-09-02"
    entries["league_teams"] = 10
    entries["budget_per_team"] = 200
    entries["passing_td_points"] = 4
    entries["reception_points"] = 1
    entries["compatible_with_portfolio_league"] = False
    return entries


def extract_top300_entries(pdf_path: Path) -> pd.DataFrame:
    """Extract ESPN's overall PPR rankings and published 10-team values."""
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text(x_tolerance=1, y_tolerance=3) or "" for page in pdf.pages)
    entries = pd.DataFrame(match.groupdict() for match in TOP300_PATTERN.finditer(text))
    if entries.empty:
        raise ValueError("No ESPN top-300 auction entries were found in the PDF.")
    numeric = ["overall_rank", "position_rank", "espn_10_team_value", "bye_week"]
    for column in numeric:
        entries[column] = pd.to_numeric(entries[column])
    return entries.sort_values("overall_rank").drop_duplicates("overall_rank", keep="first")


def calibrate_to_12_team_league(entries: pd.DataFrame) -> pd.DataFrame:
    """Reallocate ESPN prices across this league's 180-player, $2,400 draft pool."""
    offense = entries.loc[entries["position"].isin(["QB", "RB", "WR", "TE"])].nsmallest(
        168, "overall_rank"
    )
    defenses = entries.loc[entries["position"].eq("DST")].nsmallest(12, "position_rank")
    pool = pd.concat([offense, defenses], ignore_index=True).copy()
    if len(pool) != 180:
        raise ValueError(f"Expected a 180-player ESPN draft pool; found {len(pool)}.")

    minimum_budget = len(pool)
    discretionary_budget = 12 * 200 - minimum_budget
    weights = pool["espn_10_team_value"].clip(lower=0).astype(float)
    if weights.sum() <= 0:
        raise ValueError("ESPN values do not contain positive auction weights.")
    exact = weights / weights.sum() * discretionary_budget
    allocated = exact.astype(int)
    remainder = discretionary_budget - int(allocated.sum())
    priority = (exact - allocated).sort_values(ascending=False).index[:remainder]
    allocated.loc[priority] += 1
    pool["market_value"] = 1 + allocated

    pool["season"] = 2026
    pool["source"] = "ESPN 2026 PPR Top 300, calibrated to portfolio league"
    pool["source_as_of"] = "2026-08-09"
    pool["league_teams"] = 12
    pool["budget_per_team"] = 200
    pool["draft_pool_players"] = 180
    pool["passing_td_points_source"] = 4
    pool["reception_points"] = 1
    pool["calibration_method"] = (
        "$1 minimum plus proportional allocation of the remaining $2,220 "
        "using ESPN 10-team values; kickers excluded"
    )
    return pool.sort_values(["market_value", "overall_rank"], ascending=[False, True])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("output_path", type=Path)
    args = parser.parse_args()
    result = extract_entries(args.pdf_path)
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output_path, index=False)
    print(f"Wrote {len(result)} historical auction rows to {args.output_path}")


if __name__ == "__main__":
    main()
