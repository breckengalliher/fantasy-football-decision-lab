"""Stage QA provider observations beside both approved scoring datasets.

This is context delivery, not a weekly projection rebuild or an official
availability certificate. Never advance the projection-source timestamp.
"""
import json
import os
from pathlib import Path
import pandas as pd
from dashboard.football_integrity import reconcile_board_identities, guard_forecasts
from src.publication import FILES, validate_snapshot


def stage_context(source, destination, observation, identity_matches=()):
    if (os.getenv('SDL_QA_PROVIDER_PUBLICATION') != '1'
            or os.getenv('GITHUB_REPOSITORY') != 'breckengalliher/sdl-release-qa-scheduler'):
        raise ValueError('QA provider publication is disabled outside the isolated scheduler')
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or destination.exists():
        raise ValueError('A new staging directory is required; never overwrite a snapshot')
    metadata = json.loads((source / FILES[-1]).read_text())
    if (observation.get('season'), observation.get('week')) != (metadata.get('season'), metadata.get('next_week')):
        raise ValueError('Provider and projection season/week mismatch; full approved-model rebuild required')
    if observation.get('official_freshness_verified') is not False:
        raise ValueError('Provider observations cannot certify official availability')
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    retrieved = datetime.fromisoformat(observation['source_retrieved_at'].replace('Z','+00:00'))
    validated = datetime.fromisoformat(observation['validated_at'].replace('Z','+00:00'))
    if not retrieved.tzinfo or not validated.tzinfo or not retrieved <= validated <= now or now-retrieved > timedelta(hours=2):
        raise ValueError('Stale or invalid provider observation timestamps')
    matches = [r for r in identity_matches if r.get('identity_status') == 'matched']
    if len({r['player_id'] for r in matches}) != len(matches) or len({r['bdl_id'] for r in matches}) != len(matches):
        raise ValueError('Ambiguous provider identity mapping')
    by_id = {r['player_id']:r for r in matches}
    statuses = {}
    for item in observation.get('designations', []):
        if item.get('confirmed_inactive') or item.get('confirmed_available') or item.get('recommendation_allowed'):
            raise ValueError('Unverified provider data cannot authorize recommendations')
        if item['bdl_id'] in statuses:
            raise ValueError('Ambiguous player/game observations')
        statuses[item['bdl_id']] = item
    boards = {}
    for filename in FILES[:2]:
        original = pd.read_parquet(source / filename)
        repaired = guard_forecasts(reconcile_board_identities(original))
        columns = ['floor_ppr','median_ppr','ceiling_ppr','projected_ppr']
        before, after = original.set_index('player_id'), repaired.set_index('player_id')
        common = before.index.intersection(after.index)
        pd.testing.assert_frame_equal(before.loc[common,columns],after.loc[common,columns])
        notes = []
        for row in repaired.itertuples():
            match = by_id.get(row.player_id)
            if match and (match.get('team') != row.team or match.get('position') != row.position):
                raise ValueError('Provider identity team/position conflict')
            item = statuses.get(match['bdl_id'], {}) if match else {}
            notes.append(json.dumps({'reported_status':item.get('reported_status','Unknown'),
                'source_classification':'third_party_provider',
                'provider_record_updated_at':item.get('provider_record_updated_at'),
                'official_report_at':None,'recommendation_allowed':False,
                'blockers':item.get('blockers',['unresolved_identity_or_missing_report'])}))
        repaired['qa_provider_context_json'] = notes
        boards[filename] = repaired
    # Keep all previous official evidence and its timestamps intact. Provider
    # retrieval is explicitly supplemental and cannot refresh those claims.
    metadata['qa_provider_observation'] = {
        'source_retrieved_at': observation['source_retrieved_at'],
        'validated_at': observation['validated_at'],
        'official_freshness_verified': False,
        'scope': 'QA supplemental observation; projections and official evidence unchanged',
        'counts': observation.get('counts', {}),
    }
    destination.mkdir(parents=True)
    for filename, board in boards.items():
        board.to_parquet(destination / filename, index=False)
    import shutil
    shutil.copy2(source / FILES[2], destination / FILES[2])
    (destination / FILES[-1]).write_text(json.dumps(metadata,indent=2))
    return validate_snapshot(destination)
