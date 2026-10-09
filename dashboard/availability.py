"""One availability vocabulary and schedule clock for every SDL feature."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd

UNAVAILABLE = {'out','inactive','ir','injured reserve','pup','suspended'}
def status_key(value):
    if value is None or pd.isna(value):
        return ''
    key = str(value).strip().casefold()
    return {'reserve/injured':'ir', 'reserve/pup':'pup', 'physically unable to perform':'pup'}.get(key,key)

def kickoff_utc(row):
    value = row.get('kickoff_at')
    try:
        if value is not None and pd.notna(value):
            parsed = datetime.fromisoformat(str(value).replace('Z','+00:00')) if not isinstance(value,datetime) else value
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        # nflverse gametime is Eastern (dictionary_schedules), NOT Central.
        day, clock = row.get('gameday'), row.get('gametime')
        if pd.notna(day) and pd.notna(clock) and day and clock:
            return datetime.fromisoformat(f'{day}T{clock}').replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)
    except (ValueError, TypeError):
        pass
    return None

def recommendation_restriction(row, now=None):
    if not row.get('forecast_valid', True):
        return 'Invalid forecast'
    if status_key(row.get('injury_status_live', row.get('availability'))) in UNAVAILABLE:
        return 'Unavailable'
    if row.get('bye_week', False) or status_key(row.get('next_opponent')) == 'bye':
        return 'Bye week'
    game = status_key(row.get('game_status_live'))
    if game in {'postponed','rescheduled','cancelled','canceled'}:
        return 'Verify schedule'
    kickoff = kickoff_utc(row)
    if game in {'in progress','final','closed'} or row.get('game_started',False) or (kickoff and kickoff <= (now or datetime.now(timezone.utc))):
        return 'Game locked'
    return None  # Questionable is uncertain, not confirmed unavailable.
