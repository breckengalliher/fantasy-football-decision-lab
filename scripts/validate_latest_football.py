"""Read-only current public-feed QA; reports do not replace published snapshots."""
from pathlib import Path
import json
import sys
from collections import Counter
from time import perf_counter
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dashboard.data import load_live_weekly_data, build_start_sit_board
from dashboard.football_integrity import guard_forecasts
from src.football_qa import validate_weekly, independent_ppr, require_no_hard_errors

def main():
    weekly,schedules=load_live_weekly_data(2026)
    flags=validate_weekly(weekly,complete_team_feed=True)
    require_no_hard_errors(flags)
    board,target=build_start_sit_board(weekly,schedules,2026)
    source=pd.read_parquet(ROOT/'data/processed/live_start_sit_board_4pt_current.parquet')
    timings=[]
    for _ in range(100):
        started=perf_counter(); guarded=guard_forecasts(source); timings.append((perf_counter()-started)*1000)
    result={'latest_public_weekly_rows':len(weekly),'weeks':sorted(weekly.week.unique().tolist()),
            'flags':dict(Counter(f.code for f in flags)), 'target_week':target,
            'pre_target_max_games':int(board.games_played.max()),
            'latest_scoring_mismatches':{str(p):int((~np.isclose(independent_ppr(weekly,p),weekly.fantasy_points_ppr+(p-4)*weekly.passing_tds)).sum()) for p in (4,6)},
            'forecast_guard_median_ms':float(np.median(timings)), 'forecast_guard_p95_ms':float(np.percentile(timings,95)),
            'board_deep_bytes_before':int(source.memory_usage(deep=True).sum()),'board_deep_bytes_after':int(guarded.memory_usage(deep=True).sum()),
            'unattributed_rows':weekly.loc[weekly.player_id.isna(),['week','team','position','fantasy_points_ppr']].to_dict('records'),
            'scope':'Current public weekly/schedule only, not a fresh live provider injury/depth snapshot or Render load test.'}
    path=ROOT/'reports/football-repair-20261009/latest-public-validation.json'
    path.write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
    print(json.dumps(result,indent=2,default=str))
if __name__=='__main__': main()
