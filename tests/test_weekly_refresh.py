import pandas as pd

from src.refresh_weekly_snapshot import api_key, build_scoring_format_boards


def test_weekly_refresh_recalculates_both_qb_scoring_formats(monkeypatch):
    calls = []

    def fake_projection(board, weekly, prior_weekly, next_week, passing_td_points):
        calls.append(passing_td_points)
        result = board.copy()
        result["median_ppr"] = passing_td_points
        result["qb_passing_td_points"] = passing_td_points
        return result

    def fake_gate(board):
        result = board.copy()
        result["verified_qb_starter"] = True
        return result

    monkeypatch.setattr("src.refresh_weekly_snapshot.apply_approved_projection_model", fake_projection)
    monkeypatch.setattr("src.refresh_weekly_snapshot.apply_verified_starter_gate", fake_gate)

    boards = build_scoring_format_boards(
        pd.DataFrame([{"player": "Quarterback"}]),
        pd.DataFrame(),
        pd.DataFrame(),
        next_week=5,
    )

    assert calls == [4, 6]
    assert set(boards) == {4, 6}
    assert boards[4].loc[0, "median_ppr"] == 4
    assert boards[6].loc[0, "median_ppr"] == 6
    assert boards[4] is not boards[6]


def test_api_key_tolerates_duplicate_local_assignment(monkeypatch, tmp_path):
    streamlit = tmp_path / ".streamlit"
    streamlit.mkdir()
    secrets = streamlit / "secrets.toml"
    secrets.write_text(
        'SPORTSDATAIO_API_KEY = "old"\nSPORTSDATAIO_API_KEY = "current"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("SPORTSDATAIO_API_KEY", raising=False)
    monkeypatch.setattr("src.refresh_weekly_snapshot.ROOT", tmp_path)

    assert api_key() == "current"
