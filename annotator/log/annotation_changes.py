"""CODEX: Derive audit annotation changes with required row snapshots.

SQLite audit rows need one association per affected annotation plus enough
before/after state to interpret creates, updates, and deletes after the live
annotation row changes or disappears. This module compares JSON-friendly audit
states produced by GUI helpers; it does not inspect live annotation objects,
write SQLite, validate action details, or decide event-level metadata such as
the resampling method used by a polygon edit.
"""

from __future__ import annotations

from typing import Any

AuditChange = tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]

# CODEX: These fields describe storage/session position rather than annotation
# CODEX: meaning, so they do not create update associations by themselves.
_NON_SEMANTIC_FIELDS = {
    "annotation_index",
    "component_id",
    "illustration_id",
    "session_id",
    "entry_time",
}
_NON_SEMANTIC_ARROW_FIELDS = {"arrow_index"}


def affected_annotation_changes(
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
) -> list[AuditChange]:
    """CODEX: Return changed region annotation UUIDs and row snapshots.

    Accept ``None``, a single-image state with an ``annotations`` list, or a
    global state with an ``images`` collection. Rows are indexed by the generic
    ``annotation_uuid``. The returned tuples are UUID-sorted and use the schema
    change types ``created``, ``updated``, and ``deleted``.
    """

    before = _annotations_by_uuid(before_state)
    after = _annotations_by_uuid(after_state)
    changes: list[AuditChange] = []
    for annotation_uuid in sorted(before.keys() | after.keys()):
        if annotation_uuid not in before:
            change_type = "created"
            before_snapshot = None
            after_snapshot = after[annotation_uuid]
        elif annotation_uuid not in after:
            change_type = "deleted"
            before_snapshot = before[annotation_uuid]
            after_snapshot = None
        elif before[annotation_uuid] != after[annotation_uuid]:
            change_type = "updated"
            before_snapshot = before[annotation_uuid]
            after_snapshot = after[annotation_uuid]
        else:
            continue
        changes.append((annotation_uuid, change_type, before_snapshot, after_snapshot))
    return changes


def affected_arrow_changes(
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
) -> list[AuditChange]:
    """CODEX: Return changed arrow annotation UUIDs and row snapshots.

    Arrows are stored as generic annotation rows in SQLite, but GUI audit state
    still presents them in an ``arrows`` list. The durable arrow UUID is used as
    the annotation UUID for audit associations.
    """

    before = _arrows_by_uuid(before_state)
    after = _arrows_by_uuid(after_state)
    changes: list[AuditChange] = []
    for annotation_uuid in sorted(before.keys() | after.keys()):
        if annotation_uuid not in before:
            change_type = "created"
            before_snapshot = None
            after_snapshot = after[annotation_uuid]
        elif annotation_uuid not in after:
            change_type = "deleted"
            before_snapshot = before[annotation_uuid]
            after_snapshot = None
        elif before[annotation_uuid] != after[annotation_uuid]:
            change_type = "updated"
            before_snapshot = before[annotation_uuid]
            after_snapshot = after[annotation_uuid]
        else:
            continue
        changes.append((annotation_uuid, change_type, before_snapshot, after_snapshot))
    return changes


def _annotations_by_uuid(
    state: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """CODEX: Return semantic region rows keyed by durable annotation UUID."""

    indexed: dict[str, dict[str, Any]] = {}
    for annotation in _annotation_rows(state):
        annotation_uuid = _row_uuid(annotation, "annotation_uuid")
        semantic_state = _semantic_state(annotation, _NON_SEMANTIC_FIELDS)
        semantic_state["annotation_uuid"] = annotation_uuid
        indexed[annotation_uuid] = semantic_state
    return indexed


def _annotation_rows(
    state: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """CODEX: Return region rows from ``state`` as a flat list."""

    if state is None:
        return []
    images = state.get("images")
    if images is not None:
        return [
            annotation
            for image_state in images
            for annotation in image_state.get("annotations", [])
        ]
    return list(state.get("annotations", []))


def _arrows_by_uuid(
    state: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """CODEX: Return semantic arrow rows keyed by durable annotation UUID."""

    indexed: dict[str, dict[str, Any]] = {}
    for arrow in _arrow_rows(state):
        annotation_uuid = _row_uuid(arrow, "annotation_uuid", "arrow_uuid")
        semantic_state = _semantic_state(arrow, _NON_SEMANTIC_ARROW_FIELDS)
        semantic_state["annotation_uuid"] = annotation_uuid
        semantic_state["arrow_uuid"] = annotation_uuid
        semantic_state.setdefault("annotation_type", "keypoints")
        semantic_state.setdefault("annotation_role", "arrow")
        indexed[annotation_uuid] = semantic_state
    return indexed


def _arrow_rows(
    state: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """CODEX: Return arrow rows from ``state`` as a flat list."""

    if state is None:
        return []
    images = state.get("images")
    if images is not None:
        return [
            arrow for image_state in images for arrow in image_state.get("arrows", [])
        ]
    return list(state.get("arrows", []))


def _row_uuid(row: dict[str, Any], *keys: str) -> str:
    """CODEX: Return the first non-empty durable UUID from an audit row."""

    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    raise KeyError(keys[0])


def _semantic_state(
    row: dict[str, Any],
    ignored_fields: set[str],
) -> dict[str, Any]:
    """CODEX: Return row state with non-semantic bookkeeping removed."""

    return {key: value for key, value in row.items() if key not in ignored_fields}
