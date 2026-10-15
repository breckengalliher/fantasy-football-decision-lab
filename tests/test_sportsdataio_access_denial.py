"""Offline access-denial regression tests; never use real provider credentials."""
import json
import traceback

import pytest
import requests

from dashboard.providers import sportsdataio as provider
from src import refresh_live_context, refresh_market_snapshot


def denied(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError("unsafe key=TEST_SECRET", response=response)


@pytest.mark.parametrize("status", [401, 403])
def test_request_uses_header_and_redacts_exception(monkeypatch, status):
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        raise denied(status)
    monkeypatch.setattr(provider.requests, "get", get)
    client = provider.SportsDataIOClient("TEST_SECRET")
    with pytest.raises(requests.HTTPError) as caught:
        client._get("scores/json/Teams")
    assert len(calls) == 1
    assert "TEST_SECRET" not in calls[0][0]
    assert "params" not in calls[0][1]
    assert calls[0][1]["headers"] == {"Ocp-Apim-Subscription-Key": "TEST_SECRET"}
    assert caught.value.response.status_code == status
    assert "TEST_SECRET" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("status", [401, 403])
def test_prop_denial_aborts_even_after_partial_success(monkeypatch, status):
    client = provider.SportsDataIOClient("TEST_SECRET")
    calls = []
    def get(path):
        calls.append(path)
        if len(calls) == 2:
            raise denied(status)
        return []
    monkeypatch.setattr(client, "_get", get)
    with pytest.raises(requests.HTTPError):
        client._market_lines([{"ScoreID": n, "Status": "Scheduled"} for n in [1, 2, 3]])
    assert len(calls) == 2  # no repeated denied calls or partial publication


@pytest.mark.parametrize("module", [refresh_live_context, refresh_market_snapshot])
@pytest.mark.parametrize("status", [401, 403])
def test_denial_preserves_both_formats_and_all_timestamps(monkeypatch, tmp_path, module, status):
    metadata = {"season": 2026, "next_week": 6, "market_refreshed_at": "2026-10-14T00:00:00Z"}
    (tmp_path / "live_refresh_metadata.json").write_text(json.dumps(metadata))
    for points in (4, 6):
        (tmp_path / f"live_start_sit_board_{points}pt_current.parquet").write_bytes(b"last-good")
    (tmp_path / "publication_manifest.json").write_bytes(b"last-good-manifest")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    monkeypatch.setattr(module, "PROCESSED", tmp_path)
    monkeypatch.setattr(module, "api_key", lambda: "TEST_SECRET")
    monkeypatch.setattr("sys.argv", ["refresh"])
    def get(*args, **kwargs):
        raise denied(status)
    monkeypatch.setattr(provider.requests, "get", get)
    with pytest.raises(requests.HTTPError):
        module.main()
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_successful_empty_props_remain_distinct_from_denial(monkeypatch):
    client = provider.SportsDataIOClient("TEST_SECRET")
    monkeypatch.setattr(client, "_get", lambda path: [])
    lines, status = client._market_lines([{"ScoreID": 1}])
    assert lines.empty
    assert status == "No player props currently published"


def test_market_prop_denial_does_not_rewrite_snapshot(monkeypatch, tmp_path):
    module = refresh_market_snapshot
    metadata = {"season": 2026, "next_week": 6}
    (tmp_path / "live_refresh_metadata.json").write_text(json.dumps(metadata))
    for points in (4, 6):
        (tmp_path / f"live_start_sit_board_{points}pt_current.parquet").write_bytes(b"unchanged")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    monkeypatch.setattr(module, "PROCESSED", tmp_path)
    monkeypatch.setattr(module, "api_key", lambda: "TEST_SECRET")
    monkeypatch.setattr("sys.argv", ["refresh"])
    def get(self, path):
        if "ScoresByWeek" in path:
            return [{"ScoreID": 1}]
        raise denied(403)
    monkeypatch.setattr(provider.SportsDataIOClient, "_get", get)
    with pytest.raises(requests.HTTPError):
        module.main()
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
