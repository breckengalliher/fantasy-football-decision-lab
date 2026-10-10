"""Fail-closed access for four launch invitees or five QA capacity testers."""
import os
import re
from uuid import UUID

PAGES = ('Sunday Command Center', 'Decision Room', 'Player Trends')


def invited_accounts(environ=None):
    env = os.environ if environ is None else environ
    if env.get('SDL_RESTRICTED_PILOT') != '1':
        return None
    raw = env.get('SDL_PILOT_ACCOUNT_IDS', '').split(',')
    try:
        accounts = frozenset(str(UUID(value.strip())) for value in raw)
    except (ValueError, AttributeError) as error:
        raise ValueError('pilot-account-configuration-invalid') from error
    if len(raw) not in (4, 5) or len(accounts) != len(raw):
        raise ValueError('pilot-requires-four-or-five-distinct-accounts')
    base = env.get('SNAPSHOT_BASE_URL', '').rstrip('/')
    if not re.fullmatch(r'https://raw\.githubusercontent\.com/breckengalliher/fantasy-football-decision-lab/[0-9a-f]{40}/data/processed', base):
        raise ValueError('pilot-requires-immutable-publication')
    return accounts


def account_allowed(user_id, accounts):
    return accounts is None or str(user_id) in accounts
