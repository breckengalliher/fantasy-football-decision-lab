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


def clear_team_edit_state(state: MutableMapping[str, Any], team_id: str) -> None:
    """Close pending editors before their widgets render on the next run."""
    manage_prefix = f"cc_edit_revision_{team_id}_"
    add_prefix = f"cc_add_revision_{team_id}_"
    for key in list(state):
        if key.startswith(manage_prefix):
            assignment = key[len(manage_prefix):]
            state[f"cc_manage_{assignment}"] = False
            state.pop(f"cc_target_{assignment}", None)
            state.pop(f"cc_confirm_remove_{assignment}", None)
            state.pop(key, None)
        elif key.startswith(add_prefix):
            slot = key[len(add_prefix):]
            state[f"cc_add_panel_{team_id}_{slot}"] = False
            state.pop(f"cc_slot_pick_{team_id}_{slot}", None)
            state.pop(f"cc_compact_pick_{team_id}_{slot}", None)
            state.pop(key, None)
        elif key.startswith("cc_confirm_swap_"):
            state.pop(key, None)
    state.pop(f"cc_replacement_revision_{team_id}", None)


def reject_changed_editors(state: MutableMapping[str, Any], team_id: str, roster: list[dict[str, Any]]) -> bool:
    revision = roster_revision(roster)
    prefixes = (f"cc_edit_revision_{team_id}_", f"cc_add_revision_{team_id}_")
    replacement_key = f"cc_replacement_revision_{team_id}"
    if not any((key.startswith(prefixes) or key == replacement_key) and state[key] != revision for key in list(state)):
        return False
    clear_team_edit_state(state, team_id)
    return True
