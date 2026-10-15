"""Local fixtures only; preserve the producer's reviewed current-team contract."""
import json
from datetime import datetime, timezone
import pytest
import pandas as pd
from src.qa_current_teams import TRANSACTIONS, reviewed_current_teams, reviewed_transactions

NOW = datetime(2026, 10, 14, 13, tzinfo=timezone.utc)


def history():
    return pd.DataFrame([dict(player_id=e['player_id'], player_display_name=e['player'],
        position=e['position'], recent_team=e['old'], week=5, season=2026) for e in TRANSACTIONS])


def fetch(key, url):
    event = next(e for e in TRANSACTIONS if e['url'] == url)
    return ('<p>' + ' '.join(event['anchors']) + '</p>').encode()


def review(week=7):
    return {'schema_version':1, 'season':2026, 'week':week, 'status':'reviewed',
            'reviewed_at':'2026-10-14T12:00:00Z',
            'transactions':json.loads(json.dumps(TRANSACTIONS))}


def test_next_week_review_retains_mappings_source_checks_and_historical_rows():
    frame = history()
    before = frame.copy(deep=True)
    calls = []
    def getter(key, url):
        calls.append((key, url))
        return fetch(key, url)
    result = reviewed_current_teams(frame, 2026, 7, getter, at=NOW, review=review())
    assert result == {event['player_id']:event['new'] for event in TRANSACTIONS}
    assert len(calls) == len(TRANSACTIONS)
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize('fault', ['missing', 'wrong-period', 'unreviewed', 'future', 'duplicate', 'no-anchors', 'unsafe-url'])
def test_invalid_review_rejects_before_source_requests(fault):
    document = review()
    if fault == 'missing': document = None
    if fault == 'wrong-period': document['week'] = 6
    if fault == 'unreviewed': document['status'] = 'draft'
    if fault == 'future': document['reviewed_at'] = '2027-01-01T00:00:00Z'
    if fault == 'duplicate': document['transactions'].append(document['transactions'][0])
    if fault == 'no-anchors': document['transactions'][0]['anchors'] = []
    if fault == 'unsafe-url': document['transactions'][0]['url'] = 'http://example.invalid'
    def forbidden(*args): pytest.fail('Invalid review must not request sources')
    with pytest.raises(ValueError):
        reviewed_current_teams(history(), 2026, 7, forbidden, at=NOW, review=document)


def test_next_week_review_cannot_omit_still_needed_week6_correction():
    document = review()
    document['transactions'] = document['transactions'][1:]
    def forbidden(*args): pytest.fail('Missing correction must reject before sources')
    with pytest.raises(ValueError, match='omitted'):
        reviewed_current_teams(history(), 2026, 7, forbidden, at=NOW, review=document)


def test_next_week_source_conflict_still_blocks_publication():
    with pytest.raises(ValueError, match='source changed'):
        reviewed_current_teams(history(), 2026, 7, lambda *_: b'changed source', at=NOW, review=review())


def test_new_period_builder_without_review_does_not_fetch_or_create_output(tmp_path, monkeypatch):
    from src.qa_weekly_inputs import build
    monkeypatch.setenv('SDL_QA_PROVIDER_PUBLICATION', '1')
    monkeypatch.setenv('GITHUB_REPOSITORY', 'breckengalliher/sdl-release-qa-scheduler')
    def forbidden(*args, **kwargs): pytest.fail('No request before target review')
    monkeypatch.setattr('src.qa_weekly_inputs.requests.get', forbidden)
    with pytest.raises(ValueError, match='Transaction review required'):
        build(tmp_path / 'missing-review', 2026, 7)
    assert not (tmp_path / 'missing-review').exists()
