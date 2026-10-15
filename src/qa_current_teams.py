"""Reviewed Week 6 transaction evidence. No name-only joins or historical edits."""
from datetime import datetime, timezone
from html import unescape
import re
from urllib.parse import urlsplit

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


def reviewed_current_teams(weekly, season, week, fetch, at=None, *, review=None):
    """Bound reviewed corrections to this week; re-fetch evidence each build.

    This is a reviewed transaction registry, not an automatic article parser.
    Source dates are manually reviewed event dates, not guessed HTTP timestamps.
    """
    at = at or datetime.now(timezone.utc)
    events = reviewed_transactions(season, week, review, at)
    latest = weekly.sort_values('week').groupby('player_id').tail(1).set_index('player_id')
    if not latest.index.is_unique:
        raise ValueError('Reviewed transaction identity conflict')
    # A new-period document cannot silently omit an existing correction while
    # the input still assigns that player to the old team.
    by_id = {event['player_id']: event for event in events}
    for prior in TRANSACTIONS if season == 2026 and week >= 6 else ():
        if prior['player_id'] in latest.index:
            row = latest.loc[prior['player_id']]
            if row.get('recent_team', row.get('team')) == prior['old']:
                if prior['player_id'] not in by_id or by_id[prior['player_id']]['new'] != prior['new']:
                    raise ValueError('Reviewed current-team correction omitted')
    teams = {}
    for event in events:
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


def reviewed_transactions(season, week, review=None, at=None):
    """Retain Week 6 evidence; require explicit human review for another period.

    This validates a review document, not approval authority. Local fixtures are
    not real-source evidence, and timestamps never certify official availability.
    """
    if review is None:
        if (season, week) != (2026, 6):
            raise ValueError('Transaction review required for new publication period')
        return list(TRANSACTIONS)
    at = at or datetime.now(timezone.utc)
    if (not isinstance(review, dict) or type(review.get('schema_version')) is not int or review.get('schema_version') != 1
            or type(review.get('season')) is not int or type(review.get('week')) is not int
            or (review.get('season'), review.get('week')) != (season, week)
            or review.get('status') != 'reviewed'):
        raise ValueError('Transaction review period/status mismatch')
    try:
        reviewed_at = datetime.fromisoformat(review['reviewed_at'].replace('Z', '+00:00'))
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError('Transaction review timestamp invalid') from None
    if not reviewed_at.tzinfo or reviewed_at > at:
        raise ValueError('Transaction review timestamp invalid')
    events = review.get('transactions')
    if not isinstance(events, list):
        raise ValueError('Transaction review entries missing')
    ids = []
    for event in events:
        fields = ('player_id', 'player', 'position', 'old', 'new', 'date', 'url')
        if not isinstance(event, dict) or any(not isinstance(event.get(k), str) or not event[k].strip() for k in fields):
            raise ValueError('Transaction review entry invalid')
        if (not isinstance(event.get('anchors'), list) or not event['anchors']
                or any(not isinstance(v, str) or not v.strip() for v in event['anchors'])):
            raise ValueError('Transaction review source anchors missing')
        url = urlsplit(event['url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
            raise ValueError('Transaction review source URL invalid')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', event['date']):
            raise ValueError('Transaction review event date invalid')
        try:
            event_at = datetime.fromisoformat(event['date']).replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError('Transaction review event date invalid') from None
        if event_at > reviewed_at:
            raise ValueError('Transaction review predates its event')
        ids.append(event['player_id'])
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate reviewed transaction identity')
    return events
