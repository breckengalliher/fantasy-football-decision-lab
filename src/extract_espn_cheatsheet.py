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
