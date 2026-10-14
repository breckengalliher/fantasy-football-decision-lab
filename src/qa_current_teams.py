"""Reviewed Week 6 transaction evidence. No name-only joins or historical edits."""
from datetime import datetime, timezone
from html import unescape
import re

TRANSACTIONS = (
    dict(player_id='00-0039849', player='Marvin Harrison Jr.', position='WR', old='ARI', new='HOU',
         date='2026-10-12', url='https://www.houstontexans.com/news/houston-texans-transactions-10-12-2026',
         anchors=('Marvin Harrison Jr.', 'via trade with the Arizona Cardinals')),
    dict(player_id='00-0038728', player='Jared Wayne', position='WR', old='HOU', new='MIA',
         date='2026-10-13', url='https://www.miamidolphins.com/news/dolphins-make-roster-moves-x9196',
         anchors=('Jared Wayne', 'off waivers from Houston')),
    dict(player_id='00-0041096', player='Kaytron Allen', position='RB', old='WAS', new='MIA',
         date='2026-10-09', url='https://www.miamidolphins.com/team/transactions/',
         anchors=('10/09', 'Kaytron Allen', 'off waivers from Washington')),
)


def reviewed_current_teams(weekly, season, week, fetch, at=None):
    """Bound reviewed corrections to this week; re-fetch evidence each build.

    This is a reviewed transaction registry, not an automatic article parser.
    Source dates are manually reviewed event dates, not guessed HTTP timestamps.
    """
    if (season, week) != (2026, 6):
        raise ValueError('Transaction review required for new publication period')
    at = at or datetime.now(timezone.utc)
    latest = weekly.sort_values('week').groupby('player_id').tail(1).set_index('player_id')
    teams = {}
    for event in TRANSACTIONS:
        if datetime.fromisoformat(event['date']).replace(tzinfo=timezone.utc) > at:
            raise ValueError('Future transaction evidence')
        row = latest.loc[event['player_id']]
        name = row.get('player_display_name', row.get('player_name'))
        current = row.get('recent_team', row.get('team'))
        if name != event['player'] or row['position'] != event['position'] or current not in (event['old'],event['new']):
            raise ValueError('Reviewed transaction identity conflict')
        raw = fetch('transaction_'+event['player_id'],event['url']).decode()
        text = ' '.join(unescape(re.sub('<[^>]+>', ' ', raw)).split())
        if not all(anchor in text for anchor in event['anchors']):
            raise ValueError('Reviewed transaction source changed; manual review required')
        teams[event['player_id']] = event['new']
    return teams
