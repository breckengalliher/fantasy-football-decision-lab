"""Restricted QA weekly producer; approved model, no inferred availability.

Official schedule mapping is checked against nflverse. Missing depth/availability
blocks recommendations rather than silently inheriting last week's context.
"""
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests
from dashboard.data import (PLAYER_STATS_URL, SCHEDULES_URL, SNAP_COUNTS_URL, TEAM_STATS_URL,
    build_start_sit_board, add_live_supplementary_context, load_prior_weekly_data)
from dashboard.football_integrity import reconcile_board_identities, guard_forecasts
from dashboard.availability import kickoff_utc
from dashboard.availability_evidence import resolve_availability
from src.refresh_weekly_snapshot import build_scoring_format_boards
from src.football_qa import require_no_hard_errors, validate_weekly
from src.publication import validate_snapshot, FILES
from src.qa_current_teams import reviewed_current_teams, TRANSACTIONS


def official_games(raw, season, week):
    decoder = json.JSONDecoder()
    raw = raw.replace('\\"', '"')
    games = {}
    canonical = lambda s: {'AZ':'ARI', 'LAR':'LA', 'WSH':'WAS'}.get(s,s)
    for match in re.finditer(r'\{"id":"[^"]+","homeTeam":\{', raw):
        try:
            game, _ = decoder.raw_decode(raw[match.start():])
        except ValueError:
            continue
        if game.get('season') != season or game.get('week') != week or 'time' not in game:
            continue
        games[game['id']] = dict(game_id=game['id'],
            home=canonical(game['homeTeam']['currentLogo'].split('/')[-1]),
            away=canonical(game['awayTeam']['currentLogo'].split('/')[-1]), kickoff_at=game['time'])
    if not games:
        raise ValueError('Official schedule payload missing')
    teams = [team for game in games.values() for team in (game['home'], game['away'])]
    if len(teams) != len(set(teams)):
        raise ValueError('Conflicting official schedule')
    return list(games.values())


def build(destination, season, week):
    if (os.getenv('SDL_QA_PROVIDER_PUBLICATION') != '1'
            or os.getenv('GITHUB_REPOSITORY') != 'breckengalliher/sdl-release-qa-scheduler'):
        raise ValueError('QA-only producer')
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Use a new staging destination')
    receipts = {}
    def fetch(key, url):
        response = requests.get(url, timeout=(5,30))
        response.raise_for_status()
        receipts[key] = {'url':url, 'retrieved_at':datetime.now(timezone.utc).isoformat(),
            'sha256':hashlib.sha256(response.content).hexdigest(),
            'source_last_modified':response.headers.get('Last-Modified')}
        return response.content
    weekly = pd.read_parquet(BytesIO(fetch('weekly',PLAYER_STATS_URL.format(season=season))))
    weekly = weekly.loc[weekly.season.eq(season) & weekly.season_type.eq('REG')]
    if int(weekly.week.max()) != week-1:
        raise ValueError('Weekly statistics are not complete through the preceding week')
    require_no_hard_errors(validate_weekly(weekly, complete_team_feed=True))
    schedules = pd.read_csv(BytesIO(fetch('nflverse_schedule',SCHEDULES_URL)),low_memory=False)
    schedules = schedules.loc[schedules.season.eq(season)&schedules.game_type.eq('REG')]
    schedule_url = f'https://www.nfl.com/schedules/{season}/by-week/week-{week}'
    games = official_games(fetch('official_schedule',schedule_url).decode(),season,week)
    current = schedules.loc[schedules.week.eq(week)]
    if {(g['home'],g['away']) for g in games} != set(zip(current.home_team,current.away_team)):
        raise ValueError('Schedule providers disagree on current-week games')
    by_team = {team:game for game in games for team in (game['home'],game['away'])}
    current_teams = reviewed_current_teams(weekly,season,week,fetch)
    board, next_week = build_start_sit_board(weekly,schedules,season,current_teams=current_teams)
    if next_week != week:
        raise ValueError('Model week disagrees with requested publication')
    snaps = pd.read_parquet(BytesIO(fetch('snaps',SNAP_COUNTS_URL.format(season=season))))
    teams = pd.read_parquet(BytesIO(fetch('teams',TEAM_STATS_URL.format(season=season))))
    board = add_live_supplementary_context(board,snaps,teams)
    # Deliberately do not promote unofficial depth into the existing QB1 gate.
    board['depth_position_live'] = None
    board['depth_order_live'] = float('nan')
    prior = load_prior_weekly_data(season)
    scoring = build_scoring_format_boards(board,weekly,prior,week)
    at = datetime.now(timezone.utc)
    records = []
    for points, frame in scoring.items():
        frame = guard_forecasts(reconcile_board_identities(frame))
        frame['injury_status_live'] = 'Unknown'
        frame['injury_note_live'] = 'Official availability unverified; QA recommendations blocked.'
        frame['game_status_live'] = 'scheduled'
        frame['bye_week'] = ~frame.team.isin(by_team)
        for index, row in frame.iterrows():
            game = by_team.get(row.team)
            if game:
                kickoff = datetime.fromisoformat(game['kickoff_at'].replace('Z','+00:00'))
                opponent = game['away'] if game['home']==row.team else game['home']
                if row.next_opponent != opponent or kickoff_utc(row) != kickoff:
                    raise ValueError('Player matchup/kickoff conflicts with official schedule')
            else:
                kickoff = None
            resolved = resolve_availability([],player_id=row.player_id,team=row.team,
                game_id=game['game_id'] if game else None,kickoff_at=game['kickoff_at'] if game else None,
                now=at,game_status='scheduled',bye=not bool(game))
            frame.at[index,'injury_status_live'] = resolved['availability']
            if points==4 and row.is_roster_relevant:
                due = kickoff-timedelta(minutes=90) if kickoff else None
                records.append({k:row[k] for k in ('player_id','player','team','position')} | {
                    'identity_verified':True,'classification':'UNKNOWN','recommendation_allowed':False,
                    'events':[], 'conflicts':[], 'depth':{'classification':'unknown','confirmed_starter':False},
                    'game':{'game_id':game['game_id'] if game else None,'opponent':opponent if game else None,
                        'kickoff_at':kickoff.isoformat() if kickoff else None,'bye':not bool(game),
                        'mapping_verified':True,'source_id':'official_schedule','status':'scheduled'},
                    'inactives':{'due_at':due.isoformat() if due else None,
                        'state':'not_yet_due' if due and at<due else 'due_missing'}})
        scoring[points] = frame
    source = receipts['official_schedule'] | {'authority':'official','timestamp_basis':'undated_observation'}
    metadata = {'season':season,'completed_week':week-1,'next_week':week,
        'refreshed_at':receipts['weekly']['retrieved_at'], 'context_refreshed_at':source['retrieved_at'],
        'refreshed_qb_passing_td_formats':[4,6], 'projection_model':'Approved round-three live model',
        'refresh_scope':'Restricted QA weekly rebuild; missing depth and availability remain blocked',
        'injury_freshness_verified':False,'depth_freshness_verified':False,
        'availability_certificate':{'schema_version':2,'season':season,'week':week,'synthetic':False,
            'policy':'all_availability_actions_blocked','sources':{'official_schedule':source},'players':records},
        'qa_input_receipts':receipts,
        'qa_reviewed_transactions':list(TRANSACTIONS)}
    destination.mkdir(parents=True)
    for points, frame in scoring.items():
        frame.to_parquet(destination/f'live_start_sit_board_{points}pt_current.parquet',index=False)
    weekly.to_parquet(destination/FILES[2],index=False)
    (destination/FILES[-1]).write_text(json.dumps(metadata,indent=2))
    result = validate_snapshot(destination)
    return {'record_counts':result['record_counts'],'certification':result['availability_certification']}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--destination',required=True)
    parser.add_argument('--season',type=int,default=2026)
    parser.add_argument('--week',type=int,default=6)
    args=parser.parse_args()
    print(json.dumps(build(args.destination,args.season,args.week),indent=2))
