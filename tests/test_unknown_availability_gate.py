from datetime import datetime, timedelta, timezone
import pytest
from dashboard.lineup_rules import lineup_status
from dashboard.replacement_optimizer import optimize_replacements

NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
FRESH = {'refreshed_at': NOW.isoformat(), 'context_refreshed_at': NOW.isoformat(),
         'injury_freshness_verified': True, 'depth_freshness_verified': True}

@pytest.mark.parametrize('status', [None, '', 'UNKNOWN', 'UNSPECIFIED', 'Active',
    'Not listed', 'Verify availability · no provider designation'])
def test_global_freshness_cannot_promote_unknown_player(status):
    player = {'player_id': 'p', 'position': 'WR', 'slot_type': 'WR',
              'availability': status, 'median_ppr': 50,
              'kickoff_at': (NOW + timedelta(hours=5)).isoformat()}
    assert lineup_status([player], FRESH, NOW) == 'VERIFY DATA'
    assert optimize_replacements([{'slot_id': 's', 'slot_type': 'WR'}], [player]) == []

def test_unknown_high_projection_cannot_displace_known_eligible_replacement():
    bench = [{'player_id': 'unknown', 'position': 'WR', 'median_ppr': 50},
             {'player_id': 'eligible', 'position': 'WR', 'median_ppr': 10, 'availability': 'Available'}]
    assert [r.player_id for r in optimize_replacements([{'slot_id': 's', 'slot_type': 'WR'}], bench)] == ['eligible']

def test_questionable_remains_uncertain_and_confirmed_out_remains_unavailable():
    player = {'player_id': 'p', 'position': 'WR', 'slot_type': 'WR',
              'kickoff_at': (NOW + timedelta(hours=5)).isoformat()}
    assert lineup_status([{**player, 'availability': 'Questionable'}], FRESH, NOW) == 'INJURY CONCERN'
    assert lineup_status([{**player, 'availability': 'Out'}], FRESH, NOW) == 'ACTION REQUIRED'
