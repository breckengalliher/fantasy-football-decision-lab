"""Current candidate contracts adapted from preserved archived rollover tests.

Synthetic model and git doubles; no real publication evidence.
"""
import hashlib
import importlib.util
import json
import shutil
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from src.rollover import Target, prepare_export, propose_target, verify_readers

import pandas as pd
import pytest


POINTS = ["floor_ppr", "median_ppr", "ceiling_ppr", "projected_ppr"]


def review_for(week):
    # Explicit review of fabricated identities only; not real NFL evidence.
    return {'schema_version':1, 'season':2026, 'week':week, 'status':'reviewed',
            'reviewed_at':'2026-10-14T12:00:00Z', 'transactions':[]}



def fingerprint(directory):
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*") if path.is_file()}


def metadata(directory, api):
    return json.loads((directory / api.publication.FILES[-1]).read_text())


def save_metadata(directory, api, value):
    (directory / api.publication.FILES[-1]).write_text(json.dumps(value), encoding="utf-8")


def observation(week=7, season=2026):
    at = datetime.now(timezone.utc).isoformat()
    return {"season": season, "week": week, "official_freshness_verified": False,
            "source_retrieved_at": at, "validated_at": at, "designations": []}


@pytest.fixture
def feed(api, spec, monkeypatch):
    """Patch only input/model boundaries; retain producer and validator logic."""
    state = {"completed_week": 6, "official_week": 7, "official_season": 2026,
             "schedule_week": 7, "model_week": 7, "formats": [4, 6],
             "requests": [], "model_calls": []}

    def frame(points):
        rows = []
        for player in spec["players"]:
            score = player["four" if points == 4 else "six"]
            opponent = {"SEA": "DEN", "DEN": "SEA"}.get(player["team"], "BYE")
            rows.append({key: player[key] for key in ("player_id", "player", "team", "position")} | {
                "floor_ppr": score - 4, "median_ppr": score, "ceiling_ppr": score + 5,
                "projected_ppr": score, "is_roster_relevant": True,
                "next_opponent": opponent,
                "kickoff_at": spec["kickoff_at"] if opponent != "BYE" else None})
        return pd.DataFrame(rows)

    def base_model(weekly, schedule, season, *, current_teams=None):
        state["model_calls"].append(("base", season))
        state["current_teams"] = current_teams
        return frame(4), state["model_week"]

    def scoring_model(board, weekly, prior, week):
        state["model_calls"].append(("scoring", week))
        return {points: frame(points) for points in state["formats"]}

    def response(url, **kwargs):
        state["requests"].append(url)
        if url == api.weekly.PLAYER_STATS_URL.format(season=2026):
            rows = [{"season": 2026, "season_type": "REG", "week": week,
                     "player_id": p["player_id"], "team": p["team"], "position": p["position"]}
                    for week in range(1, state["completed_week"] + 1) for p in spec["players"]]
            body = pd.DataFrame(rows).to_parquet(index=False)
        elif url == api.weekly.SCHEDULES_URL:
            body = pd.DataFrame([{"season": 2026, "game_type": "REG", "week": state["schedule_week"],
                                  "home_team": "SEA", "away_team": "DEN"}]).to_csv(index=False).encode()
        elif url.startswith("https://www.nfl.com/schedules/"):
            game = {"id": spec["game"]["id"], "homeTeam": {"currentLogo": "https://example.invalid/SEA"},
                    "awayTeam": {"currentLogo": "https://example.invalid/DEN"},
                    "season": state["official_season"], "week": state["official_week"],
                    "time": spec["kickoff_at"]}
            body = json.dumps(game, separators=(",", ":")).encode()
        elif url in (api.weekly.SNAP_COUNTS_URL.format(season=2026), api.weekly.TEAM_STATS_URL.format(season=2026)):
            body = pd.DataFrame({"fixture": [True]}).to_parquet(index=False)
        else:
            pytest.fail("Unexpected input request; network remains prohibited")
        return Response(body)

    monkeypatch.setattr(api.weekly.requests, "get", response)
    monkeypatch.setattr(api.weekly, "build_start_sit_board", base_model)
    monkeypatch.setattr(api.weekly, "build_scoring_format_boards", scoring_model)
    monkeypatch.setattr(api.weekly, "add_live_supplementary_context", lambda board, *_: board)
    monkeypatch.setattr(api.weekly, "load_prior_weekly_data", lambda *_: pd.DataFrame())
    return state


class Response:
    status_code = 200
    headers = {}
    def __init__(self, body): self.content = body
    def raise_for_status(self): pass
    def json(self): return json.loads(self.content)


class LocalTransport:
    """Check immutable revision/path routing; never call an HTTP client."""
    def __init__(self, directory, manifest):
        self.directory, self.manifest, self.calls = directory, manifest, []

    def get(self, url, **kwargs):
        self.calls.append(url)
        parts = urlsplit(url).path.strip("/").split("/")
        assert urlsplit(url).hostname == "raw.githubusercontent.com"
        assert parts[:2] == ["fixture", "offline"]
        assert parts[3:5] == ["data", "processed"]
        if parts[-1] == "publication_manifest.json":
            assert parts[2] == "b" * 40
            return Response(json.dumps(self.manifest).encode())
        assert parts[2] == self.manifest["revision"]
        assert parts[-1] in self.manifest["files"]
        return Response((self.directory / parts[-1]).read_bytes())


BASE = f"https://raw.githubusercontent.com/fixture/offline/{'b' * 40}/data/processed"


@pytest.fixture
def built(tmp_path, api, feed):
    destination = tmp_path / "week7"
    api.weekly.build(destination, 2026, 7, team_review=review_for(7))
    return destination


@pytest.fixture
def last_good(tmp_path, api, feed):
    previous = dict(feed)
    feed.update(completed_week=5, official_week=6, schedule_week=6, model_week=6)
    directory = tmp_path / "last-good-week6"
    api.weekly.build(directory, 2026, 6, team_review=review_for(6))
    api.publication.write_manifest(directory, "a" * 40)
    feed.update(previous)
    return directory, fingerprint(directory)


def test_next_week_build_and_immutable_reader_agree_on_both_formats(built, api, spec, feed):
    meta = metadata(built, api)
    assert (meta["season"], meta["completed_week"], meta["next_week"]) == (2026, 6, 7)
    assert feed["model_calls"] == [("base", 2026), ("scoring", 7)]
    assert feed['current_teams'] == {}
    assert meta['qa_reviewed_transactions'] == []
    assert meta['qa_transaction_review']['week'] == 7
    manifest = api.publication.build_manifest(built, "c" * 40)
    transport = LocalTransport(built, manifest)
    loaded = api.reader.read_metadata(transport, BASE)
    assert (loaded["season"], loaded["next_week"]) == (2026, 7)
    assert loaded["_publication"]["version"] == manifest["version"]
    ids = None
    for points, field in ((4, "four"), (6, "six")):
        filename = f"live_start_sit_board_{points}pt_current.parquet"
        payload = api.reader.verified_payload(transport, BASE, manifest, filename)
        board = pd.read_parquet(BytesIO(payload)).set_index("player_id")
        identities = board[["player", "team", "position"]].sort_index()
        if ids is not None: pd.testing.assert_frame_equal(identities, ids)
        ids = identities
        for row in spec["players"]:
            assert board.loc[row["player_id"], "projected_ppr"] == row[field]
        assert len(board) == manifest["files"][filename]["record_count"]
    assert loaded["availability_certification_status"] == "restricted"
    assert manifest["source_freshness"] == {"injury": "unverified", "depth": "unverified"}
    assert manifest["projection_source_retrieved_at"] == meta["qa_input_receipts"]["weekly"]["retrieved_at"]


def test_bye_keeps_same_player_in_both_formats_without_invented_game_or_availability(built, api):
    meta = metadata(built, api)
    record = next(r for r in meta["availability_certificate"]["players"] if r["player_id"] == "fixture-bye")
    assert record["game"]["bye"] and record["game"]["kickoff_at"] is None
    assert record["game"]["game_id"] is None
    assert record["recommendation_allowed"] is False
    for filename in api.publication.FILES[:2]:
        row = pd.read_parquet(built / filename).set_index("player_id").loc["fixture-bye"]
        assert bool(row.bye_week)
        assert api.availability.recommendation_restriction(row) == "Bye week"
        assert row.injury_status_live == "Unknown"


@pytest.mark.parametrize("field,value,error", [
    ("completed_week", 5, "preceding week"),
    ("completed_week", 7, "preceding week"),
    ("official_week", 6, "schedule payload missing"),
    ("official_season", 2025, "schedule payload missing"),
    ("schedule_week", 6, "Schedule providers disagree"),
    ("model_week", 6, "Model week disagrees"),
])
def test_wrong_period_rejected_without_touching_last_good(tmp_path, api, feed, last_good, field, value, error):
    directory, before = last_good
    feed[field] = value
    output = tmp_path / "rejected"
    with pytest.raises(ValueError, match=error):
        api.weekly.build(output, 2026, 7, team_review=review_for(7))
    assert not output.exists()
    assert fingerprint(directory) == before


@pytest.mark.parametrize("formats", [[4], [6]])
def test_partial_next_week_producer_output_never_becomes_a_pointer(tmp_path, api, feed, last_good, formats):
    directory, before = last_good
    feed["formats"] = formats
    output = tmp_path / "partial"
    with pytest.raises(FileNotFoundError):
        api.weekly.build(output, 2026, 7, team_review=review_for(7))
    assert not (output / "publication_manifest.json").exists()
    assert fingerprint(directory) == before


@pytest.mark.parametrize("season,week", [(2026, 6), (2027, 7)])
def test_context_observation_cannot_relabel_existing_week(tmp_path, api, built, season, week):
    before = fingerprint(built)
    output = tmp_path / "context"
    with pytest.raises(ValueError, match="season/week mismatch"):
        api.context.stage_context(built, output, observation(week, season))
    assert not output.exists()
    assert fingerprint(built) == before


def test_unchanged_week_context_preserves_points_projection_time_and_restrictions(tmp_path, api, built):
    before = fingerprint(built)
    original = metadata(built, api)
    output = tmp_path / "context"
    api.context.stage_context(built, output, observation())
    after = metadata(output, api)
    assert after["refreshed_at"] == original["refreshed_at"]
    assert after["next_week"] == 7
    assert after["availability_certificate"] == original["availability_certificate"]
    assert after["injury_freshness_verified"] is False and after["depth_freshness_verified"] is False
    for filename in api.publication.FILES[:2]:
        first, second = [pd.read_parquet(path / filename).set_index("player_id") for path in (built, output)]
        pd.testing.assert_frame_equal(first[POINTS], second[POINTS])
        assert all(json.loads(v)["recommendation_allowed"] is False for v in second.qa_provider_context_json)
    assert fingerprint(built) == before


def test_unchanged_bytes_keep_version_independent_of_new_pointer(built, api):
    first = api.publication.build_manifest(built, "a" * 40)
    second = api.publication.build_manifest(built, "b" * 40)
    assert first["version"] == second["version"]


@pytest.mark.parametrize("fault,error", [
    ("missing_format", "Incomplete scoring formats"),
    ("missing_column", "Incomplete player schema"),
    ("identity", "disagree on player identities"),
    ("duplicate_player", "duplicate player identities"),
    ("infinite", "forecast validation failed"),
    ("reversed_range", "forecast validation failed"),
    ("merge_artifact", "merge artifacts"),
    ("old_certificate", "certificate season/week mismatch"),
    ("freshness_claim", "block all availability actions"),
    ("bye_conflict", "Board bye differs"),
])
def test_invalid_next_week_snapshot_cannot_replace_its_pointer(built, api, fault, error):
    api.publication.write_manifest(built, "a" * 40)
    pointer = built / "publication_manifest.json"
    previous = pointer.read_bytes()
    meta = metadata(built, api)
    filename = api.publication.FILES[1]
    board = pd.read_parquet(built / filename)
    if fault == "missing_format": meta["refreshed_qb_passing_td_formats"] = [4]
    elif fault == "missing_column": board = board.drop(columns="median_ppr")
    elif fault == "identity": board.loc[0, "player_id"] = "other-player"
    elif fault == "duplicate_player": board = pd.concat([board, board.iloc[[0]]], ignore_index=True)
    elif fault == "infinite": board.loc[0, "projected_ppr"] = float("inf")
    elif fault == "reversed_range": board.loc[0, "floor_ppr"] = 1000.
    elif fault == "merge_artifact": board["spread_line_live_x"] = 1.
    elif fault == "old_certificate": meta["availability_certificate"]["week"] = 6
    elif fault == "freshness_claim": meta["injury_freshness_verified"] = True
    elif fault == "bye_conflict": board.loc[board.player_id.eq("fixture-bye"), "bye_week"] = False
    board.to_parquet(built / filename, index=False)
    save_metadata(built, api, meta)
    with pytest.raises(ValueError, match=error):
        api.publication.write_manifest(built, "c" * 40)
    assert pointer.read_bytes() == previous
    assert not pointer.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize("filename", [
    "live_start_sit_board_4pt_current.parquet", "live_start_sit_board_6pt_current.parquet",
    "live_weekly_current.parquet", "live_refresh_metadata.json",
])
def test_mixed_or_tampered_immutable_assets_are_rejected(built, api, filename):
    manifest = api.publication.build_manifest(built, "c" * 40)
    (built / filename).write_bytes(b"partial-or-old-week-asset")
    with pytest.raises(ValueError, match="hash mismatch"):
        api.reader.verified_payload(LocalTransport(built, manifest), BASE, manifest, filename)


@pytest.mark.parametrize("field,value", [("week", 6), ("season", 2025)])
def test_reader_rejects_period_mismatch_even_with_valid_asset_hashes(built, api, field, value):
    manifest = api.publication.build_manifest(built, "c" * 40)
    manifest[field] = value
    with pytest.raises(ValueError, match="does not match publication"):
        api.reader.read_metadata(LocalTransport(built, manifest), BASE)


@pytest.mark.parametrize("points", [4, 6])
def test_failed_week7_read_retains_week6_and_its_real_timestamp(api, last_good, built, points):
    directory, before = last_good
    old_meta = metadata(directory, api) | {"publication_status": "validated"}
    new_meta = metadata(built, api) | {"publication_status": "validated"}
    filename = f"live_start_sit_board_{points}pt_current.parquet"
    old_board = pd.read_parquet(directory / filename)
    recovery = api.recovery.SnapshotRecovery()
    recovery.load(2026, points, old_meta, lambda *_: old_board)
    def failed(*_): raise ValueError("new week asset rejected")
    board, retained, restored = recovery.load(2026, points, new_meta, failed)
    pd.testing.assert_frame_equal(board, old_board)
    assert restored and retained["next_week"] == 6
    assert retained["refreshed_at"] == old_meta["refreshed_at"]
    assert retained["publication_status"] == "retained-validated-offline"
    assert fingerprint(directory) == before


@pytest.fixture
def git_double(tmp_path, api, last_good, monkeypatch):
    """Only emulate the ref boundary. Real staging/manifest validation still runs."""
    old, _ = last_good
    checkout = tmp_path / "disposable-checkout"
    target = checkout / "data/processed"
    shutil.copytree(old, target)
    state = {"calls": [], "head": "a" * 40, "remote": "a" * 40,
             "remote_files": fingerprint(target), "commits": 0, "target": target}

    def git(path, *args):
        assert path == checkout.resolve()
        state["calls"].append(args)
        if args == ("remote", "get-url", "origin"): return api.publisher.REMOTE
        if args == ("branch", "--show-current"): return api.publisher.BRANCH
        if args == ("status", "--porcelain"): return ""
        if args == ("rev-parse", "HEAD"): return state["head"]
        if args == ("ls-remote", "origin", "refs/heads/qa-app-data"):
            return state["remote"] + "\trefs/heads/qa-app-data"
        if args[0] == "add": return ""
        if args[0] == "commit":
            state["commits"] += 1
            assert state["commits"] <= 2
            state["head"] = ("c" if state["commits"] == 1 else "d") * 40
            return ""
        if args == ("push", "origin", "HEAD:refs/heads/qa-app-data"):
            assert state["commits"] == 2 and state["remote"] == "a" * 40
            manifest = json.loads((target / "publication_manifest.json").read_text())
            assert manifest["revision"] == "c" * 40
            for filename in api.publication.FILES:
                api.publication.verify_file((target / filename).read_bytes(), manifest, filename)
            state["remote_files"] = fingerprint(target)
            state["remote"] = state["head"]
            return ""
        pytest.fail(f"Unexpected git command in offline double: {args[0]}")

    monkeypatch.setattr(api.publisher, "git", git)
    return checkout, state


def test_week7_atomic_publication_has_two_local_commits_and_one_simulated_ref_update(built, api, git_double, last_good):
    checkout, state = git_double
    old, old_hashes = last_good
    original = fingerprint(built)
    result = api.publisher.publish(built, checkout, observation(), push=True, target=Target(2026, 7))
    # 'published' here is from a fake git boundary, NOT a real remote receipt.
    assert result["status"] == "published"
    assert result["asset_revision"] == "c" * 40 and result["pointer_revision"] == "d" * 40
    assert result["previous_revision"] == "a" * 40
    assert (result["manifest"]["season"], result["manifest"]["week"]) == (2026, 7)
    assert [c for c in state["calls"] if c[0] == "push"] == [("push", "origin", "HEAD:refs/heads/qa-app-data")]
    assert state["commits"] == 2 and state["remote"] == "d" * 40
    assert set(result["manifest"]["files"]) == set(api.publication.FILES)
    assert fingerprint(old) == old_hashes and fingerprint(built) == original


@pytest.mark.parametrize("fault", ["missing_four", "missing_six", "schema", "period", "concurrent"])
def test_invalid_rollover_never_updates_even_simulated_remote(built, api, git_double, last_good, fault):
    checkout, state = git_double
    old, old_hashes = last_good
    obs = observation()
    if fault in {"missing_four", "missing_six"}:
        (built / api.publication.FILES[0 if fault == "missing_four" else 1]).unlink()
    elif fault == "schema":
        filename = api.publication.FILES[1]
        pd.read_parquet(built / filename).drop(columns="median_ppr").to_parquet(built / filename, index=False)
    elif fault == "period": obs["week"] = 6
    elif fault == "concurrent": state["remote"] = "e" * 40
    remote_before = state["remote"]
    remote_files_before = dict(state["remote_files"])
    with pytest.raises((ValueError, FileNotFoundError, KeyError)):
        api.publisher.publish(built, checkout, obs, push=True, target=Target(2026, 7))
    assert state["remote"] == remote_before and state["remote_files"] == remote_files_before
    assert not any(c[0] in {"add", "commit", "push"} for c in state["calls"])
    assert fingerprint(old) == old_hashes




@pytest.fixture
def api(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setenv('SDL_QA_PROVIDER_PUBLICATION', '1')
    monkeypatch.setenv('GITHUB_REPOSITORY', 'breckengalliher/sdl-release-qa-scheduler')
    import importlib
    return SimpleNamespace(**{key: importlib.import_module(name) for key, name in {
        'weekly': 'src.qa_weekly_inputs', 'publication': 'src.publication',
        'publisher': 'src.qa_application_publisher', 'context': 'src.qa_provider_publication',
        'reader': 'dashboard.publication_client', 'recovery': 'dashboard.snapshot_recovery',
        'availability': 'dashboard.availability'}.items()})

@pytest.fixture
def spec():
    return json.loads((Path(__file__).parent / 'fixtures' / 'rollover_candidate.json').read_text())


def test_new_export_accepts_week7_and_preserves_all_payload_bytes(tmp_path, built, api):
    before = fingerprint(built)
    result = prepare_export(built, tmp_path / 'export', Target(2026, 7), 'c' * 40)
    assert result['status'] == 'prepared-local-only' and result['published_at'] is None
    assert result['week'] == 7
    assert {name: fingerprint(tmp_path / 'export')[name] for name in before} == before
    assert result['reader_counts'][api.publication.FILES[0]] == 3
    assert result['reader_counts'][api.publication.FILES[1]] == 3


@pytest.mark.parametrize('fault', ['wrong_target', 'mixed_board', 'old_stats', 'future_stats', 'denied'])
def test_export_failure_never_changes_last_good_or_success_timestamp(tmp_path, built, api, last_good, fault, monkeypatch):
    old, before = last_good
    target = Target(2026, 7)
    if fault == 'wrong_target': target = Target(2025, 7)
    if fault == 'mixed_board':
        name = api.publication.FILES[1]
        frame = pd.read_parquet(built / name)
        frame['publication_week'] = 6
        frame.to_parquet(built / name, index=False)
    if fault in ('old_stats', 'future_stats'):
        name = api.publication.FILES[2]
        frame = pd.read_parquet(built / name)
        frame['week'] = 5 if fault == 'old_stats' else 7
        frame.to_parquet(built / name, index=False)
    if fault == 'denied':
        import src.rollover as module
        def denied(*args): raise PermissionError('fixture access denial')
        monkeypatch.setattr(module, 'validate_target', denied)
    with pytest.raises((ValueError, PermissionError)):
        prepare_export(built, tmp_path / 'rejected-export', target, 'c' * 40)
    assert not (tmp_path / 'rejected-export').exists()
    assert fingerprint(old) == before


def test_export_duplicate_run_preserves_first_bundle(tmp_path, built):
    output = tmp_path / 'export'
    prepare_export(built, output, Target(2026, 7), 'c' * 40)
    before = fingerprint(output)
    with pytest.raises(ValueError, match='new export'):
        prepare_export(built, output, Target(2026, 7), 'd' * 40)
    assert fingerprint(output) == before


def test_reader_failure_cannot_install_export(tmp_path, built, monkeypatch):
    import src.rollover as module
    def fail(*args): raise ValueError('fixture second reader failed')
    monkeypatch.setattr(module, 'verify_readers', fail)
    with pytest.raises(ValueError, match='second reader'):
        prepare_export(built, tmp_path / 'export', Target(2026, 7), 'c' * 40)
    assert not (tmp_path / 'export').exists()


def test_restore_immediately_preceding_snapshot_through_both_real_readers(tmp_path, built, last_good, api):
    old, before = last_good
    next_output = tmp_path / 'next'
    prepare_export(built, next_output, Target(2026, 7), 'c' * 40)
    recovery = tmp_path / 'restore'
    prepare_export(old, recovery, Target(2026, 6), 'a' * 40)
    manifest = json.loads((recovery / 'publication_manifest.json').read_text())
    assert len(verify_readers(recovery, manifest, Target(2026, 6))) == 3
    assert manifest['week'] == 6
    assert fingerprint(old) == before
    assert metadata(recovery, api)['refreshed_at'] == metadata(old, api)['refreshed_at']


@pytest.mark.parametrize('fault,reason', [
    ('not-final', 'games-not-final'), ('postponed', 'games-not-final'),
    ('missing-stats', 'statistics-incomplete-or-ahead'), ('no-next', 'next-schedule-missing'),
    ('ready', 'requires-product-approved-timing-and-complete-publication-validation')])
def test_automatic_policy_is_advisory_and_requires_source_readiness(fault, reason):
    schedule = pd.DataFrame([
        {'season':2026, 'week':6, 'home_team':'SEA', 'away_team':'DEN', 'status':'final'},
        {'season':2026, 'week':7, 'home_team':'SEA', 'away_team':'CHI', 'status':'scheduled'}])
    stats = pd.DataFrame([{'season':2026, 'week':6, 'team':team} for team in ('SEA','DEN')])
    if fault in ('not-final', 'postponed'): schedule.loc[0, 'status'] = fault
    if fault == 'missing-stats': stats = stats.iloc[:1]
    if fault == 'no-next': schedule = schedule.iloc[:1]
    result = propose_target(Target(2026, 6), schedule, stats)
    assert result['reason'] == reason
    assert result['state'] == ('proposal-only' if fault == 'ready' else 'waiting')


@pytest.mark.parametrize('season,week', [(2026, 0), (2026, 1), (2026, 19), (2026, True), ('2026', 7)])
def test_invalid_or_unsupported_targets_reject_before_input_or_output(season, week):
    with pytest.raises(ValueError): Target(season, week)


def test_end_of_season_requires_separate_review():
    assert propose_target(Target(2026, 18), pd.DataFrame(), pd.DataFrame())['state'] == 'review-required'


def test_targeted_qa_publisher_checks_both_readers_before_simulated_activation(built, api, git_double):
    checkout, state = git_double
    result = api.publisher.publish(built, checkout, observation(), push=True, target=Target(2026, 7))
    assert result['status'] == 'published' and state['remote'] == 'd' * 40


def test_targeted_qa_reader_failure_preserves_remote_pointer(built, api, git_double, monkeypatch):
    import src.rollover as module
    checkout, state = git_double
    previous = dict(state['remote_files'])
    def fail(*args): raise ValueError('fixture actual reader failed')
    monkeypatch.setattr(module, 'verify_readers', fail)
    with pytest.raises(ValueError, match='actual reader'):
        api.publisher.publish(built, checkout, observation(), push=True, target=Target(2026, 7))
    assert state['remote'] == 'a' * 40 and state['remote_files'] == previous
    assert not any(c[0] == 'push' for c in state['calls'])


def test_export_competing_writer_cannot_replace_existing_bundle(tmp_path, built, monkeypatch):
    import src.rollover as module
    original = module.verify_readers
    destination = tmp_path / 'competing'
    def competing(*args):
        result = original(*args)
        destination.mkdir()
        (destination / 'prior-receipt').write_text('other validated run')
        return result
    monkeypatch.setattr(module, 'verify_readers', competing)
    with pytest.raises(OSError):
        prepare_export(built, destination, Target(2026, 7), 'c' * 40)
    assert (destination / 'prior-receipt').read_text() == 'other validated run'
    assert not (destination / 'publication_manifest.json').exists()


def test_retained_prior_week_notice_separates_failed_attempt_from_source_time(api):
    from dashboard.snapshot_recovery import retained_notice
    recovery = api.recovery.SnapshotRecovery()
    original = {'next_week':6, 'publication_status':'validated', 'refreshed_at':'original-time'}
    recovery.load(2026, 4, original, lambda *_: 'old-bytes')
    def fail(*args): raise ValueError('fixture download failure')
    value, meta, retained = recovery.load(2026, 4, {'next_week':7, 'publication_status':'validated'}, fail)
    assert retained and value == 'old-bytes' and meta['refreshed_at'] == 'original-time'
    assert 'prior-week data: Week 6; Week 7' in retained_notice(meta)
    assert 'failed_target_week' not in original
