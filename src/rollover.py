"""Explicit-period QA export and an advisory automatic-week policy.

No provider, credential, git, database or activation operations. A proposed week
is not permission to activate it. Callers must supply an explicit approved target.
"""
from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path
import shutil
import tempfile

import pandas as pd
import numpy as np

from src.publication import FILES, validate_snapshot, build_manifest
from dashboard.publication_client import read_metadata, verified_payload


@dataclass(frozen=True)
class Target:
    season: int
    week: int

    def __post_init__(self):
        if (type(self.season) is not int or type(self.week) is not int
                or not 1999 <= self.season <= 2100 or not 2 <= self.week <= 18):
            raise ValueError('Explicit regular-season target required (weeks 2–18)')


def propose_target(current, schedules, weekly):
    """Advisory only: final games AND observed stats, never weekday/midnight.

    Product review must approve the definition of complete/final (including
    postponed games). Week 1, postseason and season transitions are held.
    """
    if current.week == 18:
        return {'state': 'review-required', 'reason': 'season-transition'}
    required = {'season', 'week', 'home_team', 'away_team', 'status'}
    if not required <= set(schedules) or not {'season', 'week', 'team'} <= set(weekly):
        return {'state': 'waiting', 'reason': 'missing-source-fields'}
    games = schedules.loc[schedules.season.eq(current.season) & schedules.week.eq(current.week)]
    if games.empty or not games.status.eq('final').all():
        return {'state': 'waiting', 'reason': 'games-not-final'}
    teams = set(games.home_team) | set(games.away_team)
    stats = weekly.loc[weekly.season.eq(current.season) & weekly.week.eq(current.week)]
    if not teams <= set(stats.team) or weekly.loc[weekly.season.eq(current.season), 'week'].max() != current.week:
        return {'state': 'waiting', 'reason': 'statistics-incomplete-or-ahead'}
    following = schedules.loc[schedules.season.eq(current.season) & schedules.week.eq(current.week + 1)]
    if following.empty:
        return {'state': 'waiting', 'reason': 'next-schedule-missing'}
    return {'state': 'proposal-only', 'season': current.season, 'week': current.week + 1,
            'reason': 'requires-product-approved-timing-and-complete-publication-validation'}


def validate_target(directory, target):
    result = validate_snapshot(Path(directory))
    meta = result['metadata']
    if (meta.get('season'), meta.get('next_week')) != (target.season, target.week):
        raise ValueError('Snapshot target season/week mismatch')
    if meta.get('completed_week') != target.week - 1:
        raise ValueError('Snapshot preceding week mismatch')
    stats = pd.read_parquet(Path(directory) / FILES[2])
    if not {'season', 'week', 'season_type'} <= set(stats):
        raise ValueError('Weekly period schema missing')
    if (not stats.season.eq(target.season).all() or not stats.season_type.eq('REG').all()
            or not stats.week.isin(range(1, target.week)).all()
            or stats.week.max() != target.week - 1):
        raise ValueError('Weekly statistics disagree with target')
    for name in FILES[:2]:
        board = pd.read_parquet(Path(directory) / name)
        if (not {'publication_season', 'publication_week'} <= set(board)
                or not board.publication_season.eq(target.season).all()
                or not board.publication_week.eq(target.week).all()):
            raise ValueError('Scoring board target mismatch')
        if board[['player_id', 'player', 'team', 'position']].map(lambda v: not str(v).strip()).any().any():
            raise ValueError('Blank scoring identity')
        values = board[['floor_ppr', 'median_ppr', 'ceiling_ppr', 'projected_ppr']].apply(pd.to_numeric, errors='coerce')
        if (not np.isfinite(values.to_numpy()).all()
                or not (values.floor_ppr.le(values.median_ppr) & values.median_ppr.le(values.ceiling_ppr)).all()):
            raise ValueError('Nonfinite or unordered scoring forecasts')
    return result


class LocalReader:
    """Route the real application reader to immutable local bytes only."""
    def __init__(self, directory, manifest):
        self.directory, self.manifest = Path(directory), manifest

    def get(self, url, **kwargs):
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        filename = parsed.path.rsplit('/', 1)[-1]
        if parsed.hostname != 'raw.githubusercontent.com' or filename not in (*FILES, 'publication_manifest.json'):
            raise ValueError('Local reader route rejected')
        if filename == 'publication_manifest.json':
            body = json.dumps(self.manifest).encode()
        else:
            if f'/{self.manifest["revision"]}/data/processed/' not in parsed.path:
                raise ValueError('Local reader immutable revision mismatch')
            body = (self.directory / filename).read_bytes()
        class Response:
            status_code = 200
            content = body
            def raise_for_status(self): pass
            def json(self): return json.loads(self.content)
        return Response()


def verify_readers(directory, manifest, target):
    base = 'https://raw.githubusercontent.com/fixture/offline/' + 'b' * 40 + '/data/processed'
    transport = LocalReader(directory, manifest)
    metadata = read_metadata(transport, base)
    if (metadata['season'], metadata['next_week']) != (target.season, target.week):
        raise ValueError('Reader target mismatch')
    counts = {}
    for name in FILES:
        payload = verified_payload(transport, base, manifest, name)
        if name.endswith('.parquet'):
            frame = pd.read_parquet(BytesIO(payload))
            if len(frame) != manifest['files'][name]['record_count']:
                raise ValueError('Reader count mismatch')
            counts[name] = len(frame)
    return counts


def prepare_export(source, destination, target, revision):
    """New local review bundle, atomic directory promotion; never a live publish.

    Failure leaves last-good bytes untouched. Existing destinations are rejected,
    including duplicate runs. No operational success/publication time is emitted.
    """
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() or source == destination:
        raise ValueError('Use a new export destination; preserve last-good')
    if not destination.parent.is_dir():
        raise ValueError('Create the review parent directory first')
    # Validate and copy privately, then revalidate the exact copied bytes.
    validate_target(source, target)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='rollover-') as temporary:
        stage = Path(temporary) / 'snapshot'
        stage.mkdir()
        for name in FILES:
            shutil.copyfile(source / name, stage / name)
        validate_target(stage, target)
        manifest = build_manifest(stage, revision)
        counts = verify_readers(stage, manifest, target)
        (stage / 'publication_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        # rename fails if another run already installed the directory on Windows;
        # on other platforms the populated destination cannot be replaced either.
        stage.rename(destination)
    return {'status': 'prepared-local-only', 'season': target.season, 'week': target.week,
            'version': manifest['version'], 'reader_counts': counts,
            'production_changed': False, 'published_at': None}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--week', type=int, required=True)
    parser.add_argument('--asset-revision', required=True)
    args = parser.parse_args()
    result = prepare_export(args.source, args.destination, Target(args.season, args.week), args.asset_revision)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
