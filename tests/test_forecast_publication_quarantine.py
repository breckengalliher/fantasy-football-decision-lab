"""Publication retains diagnosed baselines without making them actionable."""
import hashlib
import pandas as pd
import pytest
from dashboard import data
from dashboard.football_integrity import guard_forecasts
from src.football_qa import require_publishable_board
from src.refresh_weekly_snapshot import atomic_parquet


def invalid_board():
    return pd.DataFrame([dict(player_id='a', player='A', position='QB', team='SEA',
                             floor_ppr=0., median_ppr=-.1, projected_ppr=-.1,
                             ceiling_ppr=4., is_roster_relevant=True)])


def test_existing_approved_calibration_bytes_survive_release_packaging():
    assert hashlib.sha256(data.QB_RANGE_CALIBRATION_PATH.read_bytes()).hexdigest() == '5c5a839abf90a33a522ffe8d243962f67d01f836546e780e4868262d7ef8ddcd'
    assert hashlib.sha256(data.POSITION_RANGE_CALIBRATION_PATH.read_bytes()).hexdigest() == '3456ff7e723a7225e66755fa023a1f7a3ce0efe0a24d4763dc87e7f1f69a85df'


def test_missing_approved_calibration_blocks_refresh_before_calculation(monkeypatch, tmp_path):
    monkeypatch.setattr(data, 'POSITION_RANGE_CALIBRATION_PATH', tmp_path/'missing.json')
    with pytest.raises(RuntimeError, match='Approved calibration missing'):
        data.apply_approved_projection_model(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), 5)


def test_quarantined_baseline_retains_exact_numbers_and_explicit_audit(tmp_path):
    raw = invalid_board()
    guarded = guard_forecasts(raw)
    receipt = require_publishable_board(guarded)
    assert receipt['quarantined_player_count'] == 1
    assert receipt['quarantined_errors'][0]['code'] == 'invalid_interval'
    path = tmp_path/'live_start_sit_board_4pt_current.parquet'
    atomic_parquet(guarded, path)
    saved = pd.read_parquet(path)
    for c in ('floor_ppr','median_ppr','ceiling_ppr','projected_ppr'):
        pd.testing.assert_series_equal(saved[c], raw[c])
    assert not saved.is_roster_relevant.any()


@pytest.mark.parametrize('column,value', [('forecast_valid',True), ('forecast_valid','False'),
    ('forecast_valid',0), ('is_roster_relevant',True), ('is_roster_relevant','False'),
    ('forecast_status','Baseline available')])
def test_fake_or_incomplete_quarantine_cannot_replace_last_good_snapshot(tmp_path, column, value):
    path = tmp_path/'live_start_sit_board_4pt_current.parquet'
    good = invalid_board().assign(median_ppr=2., projected_ppr=2.)
    atomic_parquet(good, path)
    before = path.read_bytes()
    rejected = guard_forecasts(invalid_board()).astype({column:object})
    rejected.loc[0,column] = value
    with pytest.raises(AssertionError):
        atomic_parquet(rejected,path)
    assert path.read_bytes() == before


def test_quarantine_never_waives_duplicate_identity():
    quarantined = guard_forecasts(invalid_board())
    with pytest.raises(AssertionError, match='board_identity'):
        require_publishable_board(pd.concat([quarantined,quarantined],ignore_index=True))
