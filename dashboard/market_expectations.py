"""Supplemental market expectations derived from validated player-prop lines."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable

import pandas as pd


MARKET_COLUMNS = {
    "receptions": "market_receptions",
    "receiving_yards": "market_receiving_yards",
    "rushing_yards": "market_rushing_yards",
    "passing_yards": "market_passing_yards",
    "passing_tds": "market_passing_tds",
    "rushing_receiving_tds": "market_rushing_receiving_tds",
    "interceptions": "market_interceptions",
}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def american_probability(odds: Any) -> float | None:
    """Convert American odds to an implied probability before de-vigging."""
    value = _number(odds)
    if value is None or value == 0:
        return None
    return 100 / (value + 100) if value > 0 else -value / (-value + 100)


def devig_yes_no(yes_odds: Any, no_odds: Any) -> float | None:
    """Return the no-vig probability of the yes/over outcome."""
    yes = american_probability(yes_odds)
    no = american_probability(no_odds)
    if yes is None:
        return None
    if no is None:
        return yes
    total = yes + no
    return yes / total if total else None


def implied_ppr(row: Any, passing_td_points: int = 4) -> float | None:
    """Convert available consensus props into a supplemental fantasy expectation."""
    fields = {
        key: _number(row.get(column))
        for key, column in MARKET_COLUMNS.items()
    }
    if not any(value is not None for value in fields.values()):
        return None
    total = 0.0
    total += fields["receptions"] or 0.0
    total += (fields["receiving_yards"] or 0.0) / 10
    total += (fields["rushing_yards"] or 0.0) / 10
    total += (fields["passing_yards"] or 0.0) / 25
    total += (fields["passing_tds"] or 0.0) * passing_td_points
    total += (fields["rushing_receiving_tds"] or 0.0) * 6
    total -= (fields["interceptions"] or 0.0) * 2
    return round(total, 1)


def normalize_market_lines(records: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Normalize validated, flattened prop observations to one consensus row per player.

    Each input record must identify ``player``, ``team``, ``market`` and ``line``.
    Records without a real line are discarded instead of being interpreted as zero.
    Multiple books are combined by median, limiting the influence of one outlier.
    """
    rows: list[dict[str, Any]] = []
    for record in records or []:
        player = str(record.get("player") or "").strip()
        team = str(record.get("team") or "").strip().upper()
        market = str(record.get("market") or "").strip().casefold().replace(" ", "_")
        line = _number(record.get("line"))
        if not player or not team or market not in MARKET_COLUMNS or line is None:
            continue
        rows.append({
            "player_key": player.casefold(),
            "team": team,
            "market": market,
            "line": line,
            "book": str(record.get("book") or "Consensus"),
            "updated_at": record.get("updated_at"),
        })
    if not rows:
        return pd.DataFrame(columns=["player_key", "team", *MARKET_COLUMNS.values(), "market_book_count", "market_updated_at"])
    frame = pd.DataFrame(rows)
    consensus = frame.pivot_table(index=["player_key", "team"], columns="market", values="line", aggfunc="median").reset_index()
    consensus = consensus.rename(columns=MARKET_COLUMNS)
    counts = frame.groupby(["player_key", "team"])["book"].nunique().rename("market_book_count").reset_index()
    updated = frame.groupby(["player_key", "team"])["updated_at"].max().rename("market_updated_at").reset_index()
    return consensus.merge(counts, on=["player_key", "team"]).merge(updated, on=["player_key", "team"])


def enrich_with_market(board: pd.DataFrame, market: pd.DataFrame, passing_td_points: int) -> pd.DataFrame:
    """Attach supplemental market values without modifying projection columns."""
    result = board.copy()
    result["player_key"] = result["player"].astype(str).str.strip().str.casefold()
    if market is not None and not market.empty:
        result = result.merge(market, on=["player_key", "team"], how="left")
    for column in [*MARKET_COLUMNS.values(), "market_book_count", "market_updated_at"]:
        if column not in result:
            result[column] = pd.NA
    result["market_implied_ppr"] = result.apply(lambda row: implied_ppr(row, passing_td_points), axis=1)
    result["market_available"] = result["market_implied_ppr"].notna()
    result["market_checked_at"] = datetime.now(timezone.utc).isoformat()
    return result


def market_summary(row: Any) -> str:
    """Create a concise, position-aware summary of available market lines."""
    labels = [
        ("market_receptions", "rec"),
        ("market_receiving_yards", "rec yds"),
        ("market_rushing_yards", "rush yds"),
        ("market_passing_yards", "pass yds"),
        ("market_passing_tds", "pass TDs"),
        ("market_rushing_receiving_tds", "rush/rec TD probability"),
        ("market_interceptions", "INTs"),
    ]
    values = []
    for column, label in labels:
        value = _number(row.get(column))
        if value is not None:
            suffix = "%" if column == "market_rushing_receiving_tds" else ""
            shown = value * 100 if suffix else value
            values.append(f"{shown:.1f}{suffix} {label}")
    return " · ".join(values)
