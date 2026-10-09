from dashboard.replacement_optimizer import optimize_replacements
from itertools import product
import random


def test_optimizer_respects_flex_eligibility_and_player_conflicts():
    slots = [
        {"slot_id": "wr", "slot_type": "WR", "current_projection": 0},
        {"slot_id": "flex", "slot_type": "FLEX", "current_projection": 0},
    ]
    bench = [
        {"player_id": "wr1", "position": "WR", "median_ppr": 18, "availability": "Healthy"},
        {"player_id": "rb1", "position": "RB", "median_ppr": 17, "availability": "Healthy"},
        {"player_id": "qb1", "position": "QB", "median_ppr": 30, "availability": "Healthy"},
    ]
    result = optimize_replacements(slots, bench)
    assert {(item.slot_id, item.player_id) for item in result} == {("wr", "wr1"), ("flex", "rb1")}


def test_optimizer_excludes_started_and_unavailable_players():
    slots = [{"slot_id": "sf", "slot_type": "SUPERFLEX", "current_projection": 12}]
    bench = [
        {"player_id": "started", "position": "QB", "median_ppr": 25, "game_started": True},
        {"player_id": "out", "position": "QB", "median_ppr": 24, "availability": "Out"},
        {"player_id": "available", "position": "RB", "median_ppr": 15, "availability": "Healthy"},
    ]
    result = optimize_replacements(slots, bench)
    assert len(result) == 1
    assert result[0].player_id == "available"
    assert result[0].difference_ppr == 3


def test_optimizer_matches_exhaustive_small_rosters():
    rng = random.Random(42)
    for _ in range(50):
        slots = [{"slot_id": str(i), "slot_type": rng.choice(["QB", "WR", "FLEX", "SUPERFLEX"])} for i in range(3)]
        bench = [{"player_id": str(i), "position": rng.choice(["QB", "RB", "WR", "TE"]), "median_ppr": rng.randint(-2, 30)} for i in range(4)]
        from dashboard.replacement_optimizer import ELIGIBLE
        best = 0
        for choices in product([None] + bench, repeat=3):
            picked = [p["player_id"] for p in choices if p]
            if len(picked) != len(set(picked)):
                continue
            if any(p and p["position"] not in ELIGIBLE[s["slot_type"]] for s, p in zip(slots, choices)):
                continue
            best = max(best, sum(p["median_ppr"] for p in choices if p))
        assert sum(r.projected_ppr for r in optimize_replacements(slots, bench)) == best


def test_large_roster_and_duplicate_bench_ids():
    slots = [{"slot_id": str(i), "slot_type": "SUPERFLEX"} for i in range(20)]
    bench = [{"player_id": str(i), "position": "QB", "median_ppr": i + 1} for i in range(20)]
    result = optimize_replacements(slots, bench + bench)
    assert len(result) == 20
    assert len({p.player_id for p in result}) == 20
    assert sum(p.projected_ppr for p in result) == 210


def test_bye_and_nonfinite_projection_are_not_recommended():
    slots = [{"slot_id": "flex", "slot_type": "FLEX"}]
    bench = [{"player_id": "bye", "position": "WR", "median_ppr": 30, "bye_week": True}, {"player_id": "missing", "position": "WR", "median_ppr": float("nan")}]
    assert optimize_replacements(slots, bench) == []

