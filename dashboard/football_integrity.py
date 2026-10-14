"""Shared cheap forecast contract and explicitly reviewed identity aliases.

No fuzzy merges, database writes, model fitting or external calls. Numerical
forecasts are retained for diagnosis; invalid forecasts are not actionable.
"""
from pathlib import Path
from functools import lru_cache
import numpy as np
import pandas as pd

CROSSWALK = Path(__file__).resolve().parents[1] / 'data/external/player_identity_crosswalk.csv'

def name_key(value):
    return ' '.join(str(value).strip().casefold().split())

@lru_cache(maxsize=1)
def identity_aliases():
    frame = pd.read_csv(CROSSWALK, dtype=str)
    frame['key'] = frame.alias.map(name_key)
    if frame.duplicated(['key', 'position']).any():
        raise ValueError('Ambiguous identity crosswalk')
    return {(r.key, r.position): (r.gsis_id, r.canonical_name) for r in frame.itertuples()}

def resolved_identity(name, position):
    """Only a reviewed exact alias plus position resolves an external name."""
    return identity_aliases().get((name_key(name), str(position).upper()))

def canonical_depth(depth):
    result = depth.copy()
    if result.empty:
        return result
    identities = [resolved_identity(r.player, r.depth_position_live) for r in result.itertuples()]
    # A supplied provider GSIS must agree with the reviewed mapping. Preserve
    # provider IDs as evidence; never treat an unrelated numeric GlobalID as GSIS.
    if 'provider_gsis_id' in result:
        for supplied, resolved in zip(result.provider_gsis_id, identities):
            if pd.notna(supplied) and resolved and str(supplied) != resolved[0]:
                raise ValueError('Provider GSIS disagrees with reviewed identity')
    result['canonical_player_id'] = [r[0] if r else None for r in identities]
    result['player'] = [r[1] if r else original for r, original in zip(identities, result.player)]
    result['player_key'] = result.player.map(name_key)
    return result

def reconcile_board_identities(board):
    """Collapse reviewed duplicate promotion rows; never rewrite stored rosters.

    Authoritative GSIS rows retain their statistics/projections. The promotion's
    verified depth context wins, but not its fake zero-game sample or NaN points.
    """
    result = board.copy()
    result['team'] = result.team.replace({'LAR':'LA'})
    remove = []
    for index, row in result.loc[result.player_id.astype(str).str.startswith('depth:')].iterrows():
        identity = resolved_identity(row.player, row.position)
        if not identity:
            continue
        pid, name = identity
        existing = result.index[result.player_id.eq(pid)].tolist()
        if existing:
            if len(existing) != 1 or result.loc[existing[0], 'position'] != row.position:
                raise ValueError(f'Conflicting canonical identity: {pid}')
            target = existing[0]
            if result.loc[target, 'team'] != row.team:
                raise ValueError(f'Conflicting current teams: {pid}; needs explicit trade review')
            for column in ('depth_position_live', 'depth_order_live', 'verified_qb_starter'):
                if column in result and pd.notna(row.get(column)):
                    result.loc[target, column] = row[column]
            # The provider promoted row establishes roster relevance, not history.
            result.loc[target, 'is_roster_relevant'] = True
            remove.append(index)
        else:
            result.loc[index, ['player_id','player']] = [pid, name]
    return result.drop(index=remove).reset_index(drop=True)

def forecast_valid_mask(board):
    """Legacy ranges are residual-offset bands about expected points, not medians.

    Preserve the established bracketing contract. Do not sort endpoints, clip
    negative expectations, or reinterpret fitted quantiles to pass validation.
    """
    cols = ['floor_ppr','median_ppr','ceiling_ppr','projected_ppr']
    values = board.reindex(columns=cols).apply(pd.to_numeric, errors='coerce')
    return (pd.Series(np.isfinite(values.to_numpy()).all(axis=1), index=board.index)
            & values.floor_ppr.le(values.median_ppr)
            & values.median_ppr.le(values.ceiling_ppr)
            & pd.Series(np.isclose(values.median_ppr, values.projected_ppr), index=board.index))

def guard_forecasts(board):
    result = board.copy()
    valid = forecast_valid_mask(result)
    result['forecast_valid'] = valid
    result['forecast_status'] = np.where(valid, 'Baseline available', 'Unavailable: invalid forecast; verification needed')
    result['is_roster_relevant'] = result.get('is_roster_relevant', pd.Series(False,index=result.index)).fillna(False) & valid
    return result
