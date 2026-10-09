import pandas as pd

from dashboard.market_expectations import devig_yes_no, enrich_with_market, implied_ppr, normalize_market_lines


def test_multiple_books_are_combined_by_median_and_missing_is_not_zero():
    result = normalize_market_lines([
        {"player": "Example WR", "team": "SEA", "market": "receptions", "line": 5.5, "book": "A"},
        {"player": "Example WR", "team": "SEA", "market": "receptions", "line": 6.5, "book": "B"},
        {"player": "Example WR", "team": "SEA", "market": "receiving_yards", "line": None, "book": "A"},
    ])
    assert result.loc[0, "market_receptions"] == 6.0
    assert "market_receiving_yards" not in result or pd.isna(result.loc[0, "market_receiving_yards"])
    assert result.loc[0, "market_book_count"] == 2


def test_implied_ppr_uses_selected_qb_scoring_and_weighted_touchdowns():
    row = {
        "market_receptions": 6.0, "market_receiving_yards": 75.0,
        "market_rushing_yards": 10.0, "market_passing_yards": 250.0,
        "market_passing_tds": 1.5, "market_rushing_receiving_tds": .25,
        "market_interceptions": .5,
    }
    assert implied_ppr(row, 4) == 31.0
    assert implied_ppr(row, 6) == 34.0


def test_market_enrichment_never_changes_model_projection():
    board = pd.DataFrame([{"player": "Example WR", "team": "SEA", "median_ppr": 17.2}])
    market = normalize_market_lines([
        {"player": "Example WR", "team": "SEA", "market": "receptions", "line": 6.5, "book": "A"},
        {"player": "Example WR", "team": "SEA", "market": "receiving_yards", "line": 72.5, "book": "A"},
    ])
    result = enrich_with_market(board, market, 4)
    assert result.loc[0, "median_ppr"] == 17.2
    assert result.loc[0, "market_implied_ppr"] == 13.8
    assert bool(result.loc[0, "market_available"])


def test_de_vigged_touchdown_probability():
    assert round(devig_yes_no(-120, 100), 3) == 0.522
