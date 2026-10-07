import pandas as pd

from dashboard.data import apply_player_pool_guardrails, audit_player_pool


def test_player_pool_removes_duplicates_invalid_records_and_excess_depth():
    rows = []
    for index in range(38):
        rows.append({
            "player_id": f"te-{index}", "player": f"Tight End {index}", "position": "TE",
            "team": "SEA", "next_opponent": "SF", "is_roster_relevant": True,
            "recent_opportunities": 40 - index, "season_ppr": 20 - index / 10, "games_played": 4,
        })
    rows.extend([
        {"player_id": "duplicate-a", "player": "Same Player", "position": "WR", "team": "SEA", "next_opponent": "SF", "is_roster_relevant": True, "recent_opportunities": 8, "season_ppr": 10, "games_played": 4},
        {"player_id": "duplicate-b", "player": "Same Player", "position": "WR", "team": "SF", "next_opponent": "SEA", "is_roster_relevant": True, "recent_opportunities": 4, "season_ppr": 5, "games_played": 4},
        {"player_id": "bad-team", "player": "Missing Team", "position": "RB", "team": "", "next_opponent": "SEA", "is_roster_relevant": True, "recent_opportunities": 9, "season_ppr": 8, "games_played": 4},
    ])
    guarded = apply_player_pool_guardrails(pd.DataFrame(rows))
    audit = audit_player_pool(guarded)

    assert audit["eligible_by_position"]["TE"] == 36
    assert audit["eligible_by_position"]["WR"] == 1
    assert audit["duplicate_player_ids"] == 0
    assert audit["duplicate_player_names_by_position"] == 0
    assert audit["missing_teams"] == 0
    assert not guarded.loc[guarded["player_id"].eq("bad-team"), "is_roster_relevant"].iloc[0]
