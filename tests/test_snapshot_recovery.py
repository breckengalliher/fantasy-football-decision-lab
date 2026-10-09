import pytest
from dashboard.snapshot_recovery import SnapshotRecovery


def test_failed_candidate_retains_complete_old_version_and_actual_timestamp():
    recovery = SnapshotRecovery()
    old = {"publication_status": "validated", "_publication": {"version": "v1"},
           "refreshed_at": "original-time", "injury_freshness_verified": True,
           "depth_freshness_verified": True}
    public_frames = object()
    recovery.load(2026, 4, old, lambda *args: public_frames)
    def failure(*args):
        raise ValueError("hash mismatch")
    snapshot, metadata, restored = recovery.load(2026, 4, {"publication_status": "validated"}, failure)
    assert snapshot is public_frames and restored
    assert metadata["_publication"]["version"] == "v1"
    assert metadata["refreshed_at"] == "original-time"
    assert metadata["injury_freshness_verified"] is False
    assert old["injury_freshness_verified"] is True


def test_recovery_never_substitutes_another_scoring_format():
    recovery = SnapshotRecovery()
    recovery.load(2026, 4, {"publication_status": "validated"}, lambda *args: "4pt")
    def failure(*args):
        raise TimeoutError()
    with pytest.raises(TimeoutError):
        recovery.load(2026, 6, {}, failure)


def test_recovery_is_bounded_and_legacy_is_not_last_validated():
    recovery = SnapshotRecovery(max_entries=2)
    for season in (2024, 2025, 2026):
        recovery.load(season, 4, {"publication_status": "validated"}, lambda *args: "public")
    assert list(recovery._entries) == [(2025, 4), (2026, 4)]
    recovery.load(2026, 6, {"publication_status": "legacy-unverified"}, lambda *args: "legacy")
    assert (2026, 6) not in recovery._entries


def test_unverified_metadata_does_not_replace_validated_snapshot():
    recovery = SnapshotRecovery()
    recovery.load(2026, 4, {"publication_status": "validated"}, lambda *args: "public")
    def must_not_load(*args):
        pytest.fail("Should retain previously validated data")
    snapshot, metadata, restored = recovery.load(2026, 4, {"publication_status": "offline-local-fallback"}, must_not_load)
    assert snapshot == "public" and restored
