"""Dashboard data access with an explicit demo fallback."""

from __future__ import annotations

import pandas as pd
from pathlib import Path


DEMO_PLAYERS = pd.DataFrame(
    [
        {
            "player": "Demo RB Alpha",
            "position": "RB",
            "team": "ATL",
            "projected_points": 287.4,
            "floor": 245.0,
            "ceiling": 329.0,
            "model_value": 61,
            "market_value": 52,
            "confidence": "High",
            "opportunity_score": 94,
            "efficiency_score": 86,
            "risk_score": 24,
            "target_share": 0.13,
            "air_yard_share": 0.01,
            "red_zone_share": 0.61,
            "weekly_projection": 18.2,
            "opponent": "CAR",
            "matchup": "Favorable",
        },
        {
            "player": "Demo WR Bravo",
            "position": "WR",
            "team": "CIN",
            "projected_points": 301.8,
            "floor": 256.0,
            "ceiling": 348.0,
            "model_value": 58,
            "market_value": 62,
            "confidence": "High",
            "opportunity_score": 96,
            "efficiency_score": 91,
            "risk_score": 18,
            "target_share": 0.29,
            "air_yard_share": 0.38,
            "red_zone_share": 0.31,
            "weekly_projection": 19.4,
            "opponent": "CLE",
            "matchup": "Neutral",
        },
        {
            "player": "Demo WR Charlie",
            "position": "WR",
            "team": "SEA",
            "projected_points": 252.6,
            "floor": 208.0,
            "ceiling": 302.0,
            "model_value": 42,
            "market_value": 31,
            "confidence": "Medium",
            "opportunity_score": 88,
            "efficiency_score": 83,
            "risk_score": 36,
            "target_share": 0.25,
            "air_yard_share": 0.36,
            "red_zone_share": 0.22,
            "weekly_projection": 16.8,
            "opponent": "LAR",
            "matchup": "Favorable",
        },
        {
            "player": "Demo RB Delta",
            "position": "RB",
            "team": "MIA",
            "projected_points": 241.3,
            "floor": 192.0,
            "ceiling": 295.0,
            "model_value": 39,
            "market_value": 44,
            "confidence": "Medium",
            "opportunity_score": 82,
            "efficiency_score": 95,
            "risk_score": 48,
            "target_share": 0.11,
            "air_yard_share": -0.01,
            "red_zone_share": 0.44,
            "weekly_projection": 15.1,
            "opponent": "BUF",
            "matchup": "Difficult",
        },
        {
            "player": "Demo TE Echo",
            "position": "TE",
            "team": "ARI",
            "projected_points": 216.7,
            "floor": 183.0,
            "ceiling": 255.0,
            "model_value": 31,
            "market_value": 25,
            "confidence": "High",
            "opportunity_score": 89,
            "efficiency_score": 88,
            "risk_score": 22,
            "target_share": 0.23,
            "air_yard_share": 0.21,
            "red_zone_share": 0.28,
            "weekly_projection": 14.0,
            "opponent": "SF",
            "matchup": "Neutral",
        },
        {
            "player": "Demo QB Foxtrot",
            "position": "QB",
            "team": "BUF",
            "projected_points": 438.2,
            "floor": 385.0,
            "ceiling": 492.0,
            "model_value": 37,
            "market_value": 34,
            "confidence": "High",
            "opportunity_score": 92,
            "efficiency_score": 93,
            "risk_score": 20,
            "target_share": 0.0,
            "air_yard_share": 0.0,
            "red_zone_share": 0.71,
            "weekly_projection": 27.1,
            "opponent": "NYJ",
            "matchup": "Neutral",
        },
        {
            "player": "Demo RB Golf",
            "position": "RB",
            "team": "DEN",
            "projected_points": 198.5,
            "floor": 151.0,
            "ceiling": 249.0,
            "model_value": 22,
            "market_value": 14,
            "confidence": "Low",
            "opportunity_score": 76,
            "efficiency_score": 79,
            "risk_score": 57,
            "target_share": 0.08,
            "air_yard_share": 0.0,
            "red_zone_share": 0.39,
            "weekly_projection": 13.2,
            "opponent": "LV",
            "matchup": "Favorable",
        },
        {
            "player": "Demo DST Hotel",
            "position": "DST",
            "team": "PHI",
            "projected_points": 142.0,
            "floor": 106.0,
            "ceiling": 178.0,
            "model_value": 4,
            "market_value": 2,
            "confidence": "Medium",
            "opportunity_score": 85,
            "efficiency_score": 87,
            "risk_score": 31,
            "target_share": 0.0,
            "air_yard_share": 0.0,
            "red_zone_share": 0.0,
            "weekly_projection": 9.3,
            "opponent": "NYG",
            "matchup": "Favorable",
        },
    ]
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_BOARD_PATH = PROJECT_ROOT / "data" / "processed" / "draft_board_2026_current.csv"
RECENT_GAMES_PATH = PROJECT_ROOT / "data" / "processed" / "recent_games_2026.csv"
DEFAULT_MARKET_PATH = (
    PROJECT_ROOT / "data" / "external" / "espn_2026_ppr_12_team_auction.csv"
)


def add_injury_context(players: pd.DataFrame) -> pd.DataFrame:
    """Make missing injury coverage explicit without inferring players are healthy."""
    result = players.copy()
    result["injury_status"] = "Unavailable"
    result["injury_detail"] = "No reviewed 2026 injury feed"
    result["injury_as_of"] = pd.NA
    return result


def load_dashboard_players() -> tuple[pd.DataFrame, str]:
    """Load the pipeline output, falling back visibly when it is unavailable."""
    if REAL_BOARD_PATH.exists():
        frame = add_injury_context(pd.read_csv(REAL_BOARD_PATH))
        if DEFAULT_MARKET_PATH.exists():
            frame, matched = apply_market_values(
                frame,
                pd.read_csv(DEFAULT_MARKET_PATH),
                source_label="ESPN PPR calibrated to 12 teams (Aug 9, 2026)",
                unmatched_value=float("nan"),
                unmatched_source="No ESPN 12-team match",
            )
            return frame, f"Historical model + {matched} ESPN 12-team matches"
        return frame, "Historical model"
    return add_injury_context(DEMO_PLAYERS), "Illustrative fallback"


def apply_market_values(
    players: pd.DataFrame,
    market_values: pd.DataFrame,
    source_label: str = "Uploaded 2026 market file",
    unmatched_value: float | None = None,
    unmatched_source: str | None = None,
) -> tuple[pd.DataFrame, int]:
    """Apply reviewed player auction values using exact normalized names."""
    required = {"player", "market_value", "season"}
    missing = required.difference(market_values.columns)
    if missing:
        raise ValueError("Market file is missing: " + ", ".join(sorted(missing)))
    market = market_values[list(required)].copy()
    market["season"] = pd.to_numeric(market["season"], errors="raise")
    if not market["season"].eq(2026).all():
        raise ValueError("Market file must contain only 2026 values.")
    market["player_key"] = market["player"].astype(str).str.strip().str.casefold()
    if market["player_key"].duplicated().any():
        raise ValueError("Market file contains duplicate player names.")
    market["market_value"] = pd.to_numeric(market["market_value"], errors="raise")
    if market["market_value"].lt(0).any():
        raise ValueError("Market values cannot be negative.")

    result = players.copy()
    if "comparison_source" not in result:
        result["comparison_source"] = "Internal baseline"
    result["market_value"] = pd.to_numeric(
        result["market_value"], errors="raise"
    ).astype(float)
    result["player_key"] = result["player"].astype(str).str.strip().str.casefold()
    incoming = market.set_index("player_key")["market_value"]
    matched = result["player_key"].isin(incoming.index)
    if unmatched_value is not None:
        result.loc[~matched, "market_value"] = unmatched_value
    if unmatched_source is not None:
        result.loc[~matched, "comparison_source"] = unmatched_source
    result.loc[matched, "market_value"] = result.loc[matched, "player_key"].map(incoming)
    result.loc[matched, "comparison_source"] = source_label
    return result.drop(columns="player_key"), int(matched.sum())


def prepare_draft_board(players: pd.DataFrame) -> pd.DataFrame:
    """Add portfolio-facing draft signals."""

    board = players.copy()
    if "comparison_source" not in board:
        board["comparison_source"] = "Illustrative comparison"
    board["auction_edge"] = board["model_value"] - board["market_value"]
    board["value_signal"] = pd.cut(
        board["auction_edge"],
        bins=[float("-inf"), -4, 3, float("inf")],
        labels=["Overpriced", "Fair", "Target"],
    )
    return board.sort_values(["auction_edge", "projected_points"], ascending=[False, False])


def player_history(player_name: str, players: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return actual recent games when available, otherwise demo history."""

    if RECENT_GAMES_PATH.exists() and players is not None:
        history = pd.read_csv(RECENT_GAMES_PATH)
        selected = history.loc[history["player"].eq(player_name)].copy()
        if not selected.empty:
            return selected[
                [
                    "game",
                    "opponent_team",
                    "ppr_points",
                    "target_share",
                    "air_yard_share",
                    "targets",
                    "carries",
                ]
            ]

    source = DEMO_PLAYERS if players is None else players
    player_index = source.index[source["player"].eq(player_name)][0]
    base_projection = source.loc[player_index, "weekly_projection"]
    multipliers = [0.76, 1.05, 0.89, 1.18, 0.97]
    target_share = source.loc[player_index, "target_share"]
    air_yard_share = source.loc[player_index, "air_yard_share"]
    return pd.DataFrame(
        {
            "game": ["Game -5", "Game -4", "Game -3", "Game -2", "Game -1"],
            "ppr_points": [round(base_projection * value, 1) for value in multipliers],
            "target_share": [
                max(0.0, round(target_share * value, 3)) for value in [0.91, 1.08, 0.95, 1.11, 0.98]
            ],
            "air_yard_share": [
                round(air_yard_share * value, 3) for value in [0.82, 1.17, 0.88, 1.21, 0.96]
            ],
        }
    )
