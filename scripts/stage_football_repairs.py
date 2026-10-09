"""Staged football repair evidence. Never writes published data or private rosters."""
from pathlib import Path
import hashlib
import json
import sys
from time import perf_counter
from collections import Counter
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dashboard.data import apply_approved_projection_model, load_prior_weekly_data, repair_qb_display_form
from dashboard.football_integrity import reconcile_board_identities, guard_forecasts
from src.football_qa import validate_board, validate_weekly, require_no_hard_errors

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    output = ROOT/'reports/football-repair-20261009'
    output.mkdir(exist_ok=True,parents=True)
    paths = [ROOT/f'data/processed/live_start_sit_board_{p}pt_current.parquet' for p in (4,6)]
    weekly_path = ROOT/'data/processed/live_weekly_current.parquet'
    before_hashes = {str(p.relative_to(ROOT)):sha(p) for p in paths+[weekly_path]}
    weekly = pd.read_parquet(weekly_path)
    # Existing authoritative loader: no custom historical values or inferred games.
    prior = load_prior_weekly_data(2026)
    prior.to_parquet(output/'source_player_stats_2025.parquet', index=False)
    source_hash = sha(output/'source_player_stats_2025.parquet')
    history = prior.groupby('player_id').size()
    started = perf_counter()
    evidence = {'preserved_snapshot_hashes':before_hashes,'historical_source':'nflverse stats_player_week_2025.parquet via existing loader',
                'historical_source_sha256':source_hash, 'formats':{}, 'weekly_flags':[f.to_dict() for f in validate_weekly(weekly,complete_team_feed=True)]}
    for points,path in zip((4,6),paths):
        raw = pd.read_parquet(path)
        canonical = reconcile_board_identities(raw)
        canonical['prior_recorded_games'] = canonical.player_id.map(history).fillna(0).astype(int)
        # Remove derived explanation columns; rebuild from the same raw weekly
        # stats, prior source and approved weights, not stale zero-game surrogates.
        base = canonical.drop(columns=[c for c in canonical if c.startswith('projection_')])
        rebuilt = apply_approved_projection_model(base,weekly,prior,5,points)
        original_rebuild = apply_approved_projection_model(raw.drop(columns=[c for c in raw if c.startswith('projection_')]),weekly,prior,5,points)
        original_rebuild = reconcile_board_identities(original_rebuild)
        control = original_rebuild.merge(rebuilt[['player_id','median_ppr']],on='player_id',suffixes=('_control','_repair'))
        matched_delta = control.median_ppr_control - control.median_ppr_repair
        rebuilt = repair_qb_display_form(rebuilt,weekly,points)
        rebuilt = guard_forecasts(rebuilt)
        rejected = rebuilt.loc[~rebuilt.forecast_valid]
        valid = rebuilt.loc[rebuilt.forecast_valid].copy()
        require_no_hard_errors(validate_board(valid))
        valid.to_parquet(output/f'staged_{points}pt.parquet',index=False)
        rejected.to_parquet(output/f'quarantine_{points}pt.parquet',index=False)
        matched = rebuilt.merge(raw[['player_id','median_ppr']],on='player_id',suffixes=('','_saved'))
        delta = matched.median_ppr-matched.median_ppr_saved
        failures = validate_board(rebuilt)
        limited = raw.loc[raw.games_played.lt(3)]
        fixed_history = limited.player_id.map(history).fillna(0)
        evidence['formats'][str(points)] = {
            'original_rows':len(raw),'canonical_rows':len(rebuilt),'duplicate_promotion_rows_removed':len(raw)-len(rebuilt),
            'quarantined':rejected[['player_id','player','floor_ppr','median_ppr','ceiling_ppr','forecast_status']].to_dict('records'),
            'strict_staged_hard_errors':0, 'full_rebuilt_flag_counts':dict(Counter(f.code for f in failures)),
            'staged_flag_counts':dict(Counter(f.code for f in validate_board(valid))),
            'existing_identity_forecast_changes':int((delta.abs()>1e-7).sum()),'max_existing_absolute_change':float(delta.abs().max()),
            'same_input_identity_repair_max_forecast_change':float(matched_delta.abs().max()),
            'limited_current_sample_rows':len(limited),'limited_rows_with_at_least_five_prior_records':int(fixed_history.ge(5).sum()),
            'stafford':rebuilt.loc[rebuilt.player_id.eq('00-0026498'),['player_id','player','team','games_played','prior_recorded_games','median_ppr','floor_ppr','ceiling_ppr']].to_dict('records'),
            'crosswalk_sample':rebuilt.loc[rebuilt.player_id.isin(['00-0037197','00-0035700','00-0039144','00-0039165']),['player_id','player','games_played','prior_recorded_games']].to_dict('records')}
    benchmark_path = ROOT/'reports/model-validation-audit/benchmark-predictions-2025.parquet'
    benchmark = pd.read_parquet(benchmark_path)
    metrics=[]
    for position,g in benchmark.groupby('position'):
        error = g.incumbent-g.target_ppr
        # Same-position, same-week ordering only. Ties excluded, not counted as wins.
        correct=eligible=0
        for _,week in g.groupby(['season','week']):
            actual=week.target_ppr.to_numpy(); predicted=week.incumbent.to_numpy()
            i,j=np.triu_indices(len(week),k=1)
            diff=actual[i]-actual[j]; non_tie=diff!=0
            eligible+=int(non_tie.sum())
            correct+=int(((predicted[i]-predicted[j])*diff>0)[non_tie].sum())
        metrics.append({'position':position,'n':len(g),'mae':float(error.abs().mean()),'rmse':float(np.sqrt((error**2).mean())),
                        'bias_projection_minus_actual':float(error.mean()),'eligible_ordering_pairs':eligible,'ordering_correct':correct,
                        'ordering_accuracy':correct/eligible if eligible else None})
    evidence['historical_archive']={'sha256':sha(benchmark_path),'metrics_before_and_after':metrics,
        'scope':'Identical saved predictions; reproduced metrics, not a new walk-forward backtest or proof of repaired forecast accuracy.'}
    evidence['repair_processing_seconds_excluding_source_load']=perf_counter()-started
    evidence['source_snapshots_unchanged']=all(sha(ROOT/p)==value for p,value in before_hashes.items())
    if not evidence['source_snapshots_unchanged']:
        raise AssertionError('Published snapshots changed')
    (output/'results.json').write_text(json.dumps(evidence,indent=2,default=str),encoding='utf-8')
    print(json.dumps(evidence,indent=2,default=str))

if __name__=='__main__': main()
