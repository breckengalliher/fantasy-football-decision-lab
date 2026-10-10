"""Explicit, fail-closed access configuration for the invited two-user pilot."""
import os
import re
from uuid import UUID

PAGES = ('Sunday Command Center', 'Decision Room')


def invited_accounts(environ=None):
    env = os.environ if environ is None else environ
    if env.get('SDL_RESTRICTED_PILOT') != '1':
        return None
    raw = env.get('SDL_PILOT_ACCOUNT_IDS', '').split(',')
    try:
        accounts = frozenset(str(UUID(value.strip())) for value in raw)
    except (ValueError, AttributeError) as error:
        raise ValueError('pilot-account-configuration-invalid') from error
    if len(raw) != 2 or len(accounts) != 2:
        raise ValueError('pilot-requires-two-distinct-accounts')
    base = env.get('SNAPSHOT_BASE_URL', '').rstrip('/')
    if not re.fullmatch(r'https://raw\.githubusercontent\.com/breckengalliher/fantasy-football-decision-lab/[0-9a-f]{40}/data/processed', base):
        raise ValueError('pilot-requires-immutable-publication')
    return accounts


def account_allowed(user_id, accounts):
    return accounts is None or str(user_id) in accounts
