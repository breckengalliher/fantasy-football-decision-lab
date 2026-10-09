"""Reproducible offline audit of checked-in snapshots; never calls providers."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from dashboard.data import repair_qb_display_form
from dashboard.presentation import fantasy_game_log, opponent_position_rank
from src.football_qa import independent_ppr, require_no_hard_errors, validate_board, validate_weekly


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "reports/football-audit-20261009/evidence.json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    started = perf_counter()
    weekly = pd.read_parquet(ROOT / "data/processed/live_weekly_current.parquet")
    historical_path = ROOT / "reports/model-validation-audit/benchmark-predictions-2025.parquet"
    history = pd.read_parquet(historical_path) if historical_path.exists() else pd.DataFrame()
    all_flags = validate_weekly(weekly, complete_team_feed=True)
    evidence = {"as_of": datetime.now(timezone.utc).isoformat(), "weekly_rows": len(weekly), "weekly_seasons": sorted(weekly.season.unique().tolist()), "weekly_weeks": sorted(weekly.week.unique().tolist()), "snapshot_metadata": json.loads((ROOT / "data/processed/live_refresh_metadata.json").read_text()), "scoring": {}, "boards": {}, "historical": []}
    for points in (4, 6):
        raw = pd.read_parquet(ROOT / f"data/processed/live_start_sit_board_{points}pt_current.parquet")
        eligible = raw.loc[raw.is_roster_relevant.eq(True)]
        board = repair_qb_display_form(raw, weekly, points)
        board["next_week"] = evidence["snapshot_metadata"]["next_week"]
        flags = validate_board(board)
        all_flags += flags
        expected = independent_ppr(weekly, points)
        source = weekly.fantasy_points_ppr + (points - 4) * weekly.passing_tds
        evidence["scoring"][str(points)] = {"rows": len(weekly), "mismatches": int((~np.isclose(expected, source, atol=1e-7)).sum()), "max_absolute_difference": float((expected-source).abs().max())}
        protected = [c for c in raw if c.startswith("projection_")] + ["projected_ppr", "median_ppr", "floor_ppr", "ceiling_ppr"]
        qbs = board.position.eq("QB")
        sample = []
        for position in ("QB", "RB", "WR", "TE"):
            row = board.loc[board.position.eq(position) & board.is_roster_relevant.eq(True)].sort_values("median_ppr", ascending=False).iloc[0]
            sample.append({"player_id": row.player_id, "player": row.player, "position": position, "team": row.team, "opponent": row.next_opponent, "median": float(row.median_ppr), "floor": float(row.floor_ppr), "ceiling": float(row.ceiling_ppr), "last_two_ppr": float(row.last_two_ppr), "rank": opponent_position_rank(board, row), "game_log": fantasy_game_log(weekly, row, points)})
        latency = []
        for _ in range(20):
            t = perf_counter(); repair_qb_display_form(raw, weekly, points); latency.append((perf_counter()-t)*1000)
        evidence["boards"][str(points)] = {"rows": len(raw), "eligible": len(eligible), "qb_last_two_changed": int((~np.isclose(raw.loc[qbs, "last_two_ppr"], board.loc[qbs, "last_two_ppr"], equal_nan=True)).sum()), "all_forecasts_unchanged": raw[protected].equals(board[protected]), "display_repair_median_ms": float(np.median(latency)), "representative_players": sample, "flags": [f.to_dict() for f in flags]}
    for position, group in (history.groupby("position") if not history.empty else []):
        error = group.target_ppr - group.incumbent
        evidence["historical"].append({"position": position, "samples": len(group), "mae": float(error.abs().mean()), "bias_actual_minus_projection": float(error.mean()), "challenger_mae": float((group.target_ppr-group.regularized_opportunity_efficiency).abs().mean()), "test_season": 2025})
    evidence["historical_scope"] = "Recomputed saved 2025 benchmark predictions, not a new backtest or prospective injury validation. No timestamped historical injury/route/depth evidence is present in this file." if not history.empty else "Optional historical benchmark archive not present; snapshot hard-rule validation still ran."
    evidence["flags"] = [f.to_dict() for f in all_flags]
    evidence["severity_counts"] = {s: sum(f.severity == s for f in all_flags) for s in ("hard_error", "high_priority", "modeling_warning")}
    evidence["elapsed_seconds"] = perf_counter() - started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: evidence[k] for k in ("weekly_rows", "scoring", "severity_counts", "elapsed_seconds")}))
    if args.strict:
        require_no_hard_errors(all_flags)


if __name__ == "__main__":
    main()
