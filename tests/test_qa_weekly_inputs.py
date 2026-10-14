import json
import pytest
from src.qa_weekly_inputs import official_games, build


def game(identifier='one', week=6):
    return {'id':identifier,'homeTeam':{'currentLogo':'https://example/SEA'},
            'awayTeam':{'currentLogo':'https://example/DEN'},'season':2026,'week':week,
            'time':'2026-10-16T00:15:00Z'}


def test_official_schedule_exact_period_and_stable_identity():
    raw = json.dumps(game(),separators=(',',':'))
    rows = official_games(raw+raw,2026,6)
    assert len(rows)==1
    assert rows[0]['home']=='SEA' and rows[0]['away']=='DEN'
    assert rows[0]['game_id']=='one'


def test_missing_or_wrong_week_cannot_imply_byes():
    with pytest.raises(ValueError,match='missing'):
        official_games(json.dumps(game(week=5),separators=(',',':')),2026,6)


def test_conflicting_schedule_blocks_snapshot():
    raw = ''.join(json.dumps(game(identifier=i),separators=(',',':')) for i in ('a','b'))
    with pytest.raises(ValueError,match='Conflicting'):
        official_games(raw,2026,6)


def test_production_cannot_run_qa_producer(tmp_path,monkeypatch):
    monkeypatch.setenv('SDL_QA_PROVIDER_PUBLICATION','1')
    monkeypatch.setenv('GITHUB_REPOSITORY','breckengalliher/fantasy-football-decision-lab')
    with pytest.raises(ValueError,match='QA-only'):
        build(tmp_path/'output',2026,6)
    assert not (tmp_path/'output').exists()
