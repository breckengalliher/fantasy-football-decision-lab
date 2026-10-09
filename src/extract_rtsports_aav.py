"""Extract the published RealTime Fantasy Sports average auction values."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
import pdfplumber


ENTRY_PATTERN = re.compile(
    r"\$(?P<market_value>\d+\.\d{2}) "
    r"(?P<player>.*?), "
    r"(?P<position>QB|RB|WR|TE|K|DEF) "
    r"(?P<team>[A-Z]{2,3}) "
    r"(?P<bye_week>\d{1,2})(?= \$|$)"
)
AS_OF_PATTERN = re.compile(r"Auctions through (?P<as_of_date>\d{1,2}-[A-Za-z]{3}-\d{4})")


def extract_aav(pdf_path: Path) -> pd.DataFrame:
    """Return one normalized row per auction-value entry in the one-page PDF."""
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    date_match = AS_OF_PATTERN.search(text)
    if not date_match:
        raise ValueError("Could not find the auction-through date in the PDF.")

    rows = [match.groupdict() for match in ENTRY_PATTERN.finditer(text)]
    if not rows:
        raise ValueError("No auction-value entries were found in the PDF.")

    result = pd.DataFrame(rows)
    result["market_value"] = pd.to_numeric(result["market_value"])
    result["bye_week"] = pd.to_numeric(result["bye_week"])
    result["season"] = 2026
    result["as_of_date"] = pd.to_datetime(
        date_match.group("as_of_date"), format="%d-%b-%Y"
    ).date().isoformat()
    result["source"] = "RealTime Fantasy Sports average auction results"
    result["source_url"] = (
        "https://www.freedraftguide.com/football/"
        "draft-guide-average-pdf.php?AAV=YES"
    )
    result["position"] = result["position"].replace({"DEF": "DST"})
    if result["player"].duplicated().any():
        raise ValueError("Extracted auction data contains duplicate player names.")
    return result.sort_values(
        ["market_value", "player"], ascending=[False, True]
    ).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("output_path", type=Path)
    args = parser.parse_args()

    result = extract_aav(args.pdf_path)
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output_path, index=False)
    print(
        f"Wrote {len(result)} values through {result['as_of_date'].iat[0]} "
        f"to {args.output_path}"
    )


if __name__ == "__main__":
    main()
