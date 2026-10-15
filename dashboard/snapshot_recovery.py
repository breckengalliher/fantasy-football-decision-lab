"""Bounded, public-only last-validated snapshot recovery within one process.

This is not durable storage: after restart the immutable published revision must
be fetched again. No account, roster, token or user preference belongs here.
"""
from collections import OrderedDict
from copy import deepcopy
from threading import Lock


def retained_notice(metadata):
    week = metadata.get('next_week', 'unknown')
    target = metadata.get('failed_target_week')
    period = f'Retaining prior-week data: Week {week}; Week {target} could not be validated.' if isinstance(target, int) and isinstance(week, int) and target > week else f'Showing the last fully validated Week {week} snapshot.'
    return ('Update unavailable. ' + period + ' Original source timestamps are unchanged. '
            'Verify current injuries and availability before changing your lineup.')


class SnapshotRecovery:
    def __init__(self, max_entries=2):
        self._entries = OrderedDict()
        self._lock = Lock()
        self.max_entries = max_entries

    def load(self, season, scoring, metadata, loader):
        key = (season, scoring)
        with self._lock:
            previous = self._entries.get(key)
        try:
            if previous and metadata.get("publication_status") != "validated":
                raise ValueError("Latest publication could not be verified")
            snapshot = loader(season, scoring, metadata)
        except Exception:
            if previous is None:
                raise
            snapshot, retained_metadata = previous
            recovered = deepcopy(retained_metadata)
            recovered["publication_status"] = "retained-validated-offline"
            recovered['failed_target_week'] = metadata.get('next_week')
            # A valid file is not proof of current availability during outage.
            recovered["injury_freshness_verified"] = False
            recovered["depth_freshness_verified"] = False
            return snapshot, recovered, True
        if metadata.get("publication_status") == "validated":
            with self._lock:
                self._entries[key] = (snapshot, deepcopy(metadata))
                self._entries.move_to_end(key)
                while len(self._entries) > self.max_entries:
                    self._entries.popitem(last=False)
        return snapshot, metadata, False
