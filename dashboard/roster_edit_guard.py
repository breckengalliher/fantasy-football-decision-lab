"""Keep a confirmation bound to the exact roster displayed when editing began."""
from __future__ import annotations
from typing import Any, MutableMapping


def roster_revision(roster: list[dict[str, Any]]) -> tuple:
    rows = []
    for slot in roster:
        assignments = slot.get('roster_assignments') or []
        if isinstance(assignments, dict):
            assignments = [assignments]
        rows.append((str(slot['id']), str(slot.get('slot_type', '')),
            str(slot.get('slot_order', '')), bool(slot.get('is_starter')),
            tuple(sorted((str(a.get('id', '')), str(a.get('player_id', '')),
                str(a.get('updated_at', ''))) for a in assignments))))
    return tuple(sorted(rows))


def edit_is_current(state: MutableMapping[str, Any], key: str, roster: list[dict[str, Any]]) -> bool:
    revision = roster_revision(roster)
    if key not in state:
        state[key] = revision
        return True
    return state[key] == revision
