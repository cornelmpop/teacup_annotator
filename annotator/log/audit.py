"""CODEX: Legacy backup, deletion-state, and audit-state helpers.

SQLite is the authoritative audit store for current projects. This module owns
folder-level JSON backup/export compatibility, persisted deletion marks,
project-local trash movement for deleted images, sidebar edit-summary helpers,
and JSON-friendly row builders used before SQLite audit events are written.

It does not allocate authoritative SQLite audit IDs, write audit association
tables, commit annotation state, or decide action-specific event details such
as the polygon resampling method.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from annotator.arrows import Arrow
from annotator.coco.io import image_annotation_path
from annotator.geom.polygon import bbox_for_polygon
from annotator.project.json_identity_migration import migrate_audit_jsonl_file
from annotator.project.paths import project_data_folder
from annotator.project.paths import project_file_path

AUDIT_EVENTS_FILENAME = "audit_events.jsonl"
DELETION_MARKS_FILENAME = "deletion_marks.json"
TRASH_FOLDER_NAME = "trash"
VIEW_AUDIT_ACTION = "view_image"
CLOSE_AUDIT_ACTION = "close_application"
# CODEX: These action groups are the shared source of truth for sidebar edit
# CODEX: summaries and per-session timing counts.
SUMMARY_NEW_ACTIONS = {"create_annotation", "draw_arrow"}
SUMMARY_EDIT_ACTIONS = {
    "delete_arrow",
    "move_vertex",
    "move_arrow_endpoint",
    "resize_rectangle",
    "insert_vertex",
    "delete_vertex",
    "delete_vertices",
    "simplify_polygon",
    "select_start_vertex",
    "merge_annotations",
    "reorient_simplified_polygon",
}
SUMMARY_CLASS_CHANGE_ACTIONS = {"change_class"}
SUMMARY_EDIT_COUNT_ACTIONS = (
    SUMMARY_NEW_ACTIONS | SUMMARY_EDIT_ACTIONS | SUMMARY_CLASS_CHANGE_ACTIONS
)


def next_audit_event_id(folder: Path) -> int:
    """CODEX: Return the next JSONL-compatible audit event id for ``folder``.

    Current projects allocate authoritative audit IDs in SQLite. This helper is
    retained for legacy JSONL backup/export compatibility and for importing old
    projects. Blank lines are ignored, valid rows advance to one greater than
    their stored ``audit_event_id``, and malformed rows still consume one
    position so later appends do not reuse an order slot from the readable log.
    """

    path = project_file_path(folder, AUDIT_EVENTS_FILENAME)
    if not path.is_file():
        return 1
    next_id = 1
    with path.open("r", encoding="utf-8") as audit_file:
        for line in audit_file:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
                next_id = max(next_id, int(event.get("audit_event_id", 0)) + 1)
            except (json.JSONDecodeError, TypeError, ValueError):
                # CODEX: Preserve append-order spacing even when a legacy row is unreadable.
                next_id += 1
    return next_id


def append_audit_event(folder: Path, event: dict[str, Any]) -> Path:
    """CODEX: Append one newline-delimited JSON audit backup row.

    The SQLite audit table remains authoritative for current projects. This
    writer preserves the caller-supplied event, including its complete nested
    session record, for database reconstruction. Sorted keys keep generated
    rows stable in reviews and regression tests.
    """

    path = project_file_path(folder, AUDIT_EVENTS_FILENAME)
    path.parent.mkdir(exist_ok=True)
    with path.open("a", encoding="utf-8") as audit_file:
        json.dump(event, audit_file, sort_keys=True)
        audit_file.write("\n")
    return path


def load_deletion_marks(folder: Path) -> set[str]:
    """CODEX: Load image basenames currently marked for deletion.

    Deletion marks are stored under ``teacup/deletion_marks.json``. The current
    payload is a dictionary with ``marked_images`` and ``updated_at`` keys, but
    legacy list-shaped files are still accepted. Only basenames are returned so
    callers cannot persist paths outside the project folder.
    """

    path = project_file_path(folder, DELETION_MARKS_FILENAME)
    if not path.is_file():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if isinstance(payload, dict):
        values = payload.get("marked_images", [])
    else:
        # CODEX: Older deletion-mark files stored the image-name list directly.
        values = payload
    if not isinstance(values, list):
        return set()
    return {Path(str(value)).name for value in values if str(value).strip()}


def save_deletion_marks(folder: Path, image_names: set[str]) -> Path:
    """CODEX: Persist deletion marks as a sorted project-local JSON payload.

    The payload records image basenames and an update timestamp. The write goes
    through a temporary file in the project data folder and then replaces the
    destination so callers do not leave a partially written deletion-mark file.
    """

    project_folder = project_data_folder(folder)
    project_folder.mkdir(exist_ok=True)
    path = project_folder / DELETION_MARKS_FILENAME
    payload = {
        "marked_images": sorted(image_names),
        "updated_at": int(time.time()),
    }
    temp_path = project_folder / f".{DELETION_MARKS_FILENAME}.tmp"
    with temp_path.open("w", encoding="utf-8") as marks_file:
        json.dump(payload, marks_file, indent=2)
        marks_file.write("\n")
    temp_path.replace(path)
    return path


def move_image_to_trash(folder: Path, image_name: str) -> Path:
    """CODEX: Move one image into trash and remove its JSON backup file.

    The exact image filename is preserved so SQLite and manual restoration can
    reconcile the move without a separate filesystem manifest.
    """

    trash_folder = project_file_path(folder, TRASH_FOLDER_NAME)
    trash_folder.mkdir(exist_ok=True)
    image_path = folder / Path(image_name).name
    trash_path = trash_folder / image_path.name
    if not image_path.is_file():
        raise FileNotFoundError(f"Image is missing: {image_path}")
    if trash_path.exists():
        raise FileExistsError(
            f"Trash already contains {trash_path.name}; restore, rename, or "
            "remove that file before deleting this image"
        )
    image_annotation_path(folder, image_path.name).unlink(missing_ok=True)
    shutil.move(str(image_path), str(trash_path))
    return trash_path


def remove_moved_image_sidecars(folder: Path, image_names: set[str]) -> set[Path]:
    """CODEX: Remove per-image JSON backups after images were moved.

    SQLite records which image basenames were actually trash-moved. This helper
    only removes a matching backup file when the source image is already absent,
    so it does not delete backup files for images still present in the folder.
    """

    removed_paths: set[Path] = set()
    for image_name in sorted(image_names):
        image_path = folder / Path(image_name).name
        if image_path.is_file():
            continue
        sidecar_path = image_annotation_path(folder, image_path.name)
        if sidecar_path.is_file():
            sidecar_path.unlink()
            removed_paths.add(sidecar_path)
    return removed_paths


def read_audit_events(folder: Path) -> list[dict[str, Any]]:
    """CODEX: Read valid object rows from the JSONL audit backup.

    Current project code reads authoritative audit history from SQLite. This
    helper supports JSONL imports and optional readable backups. The explicit
    identity migration runs before decoding so this reader only returns current
    field names. Blank lines are ignored, while unsupported nonblank rows fail
    during migration.
    """

    path = project_file_path(folder, AUDIT_EVENTS_FILENAME)
    if not path.is_file():
        return []
    migrate_audit_jsonl_file(path)
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as audit_file:
        for line in audit_file:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                # CODEX: A malformed backup row should not hide later readable rows.
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def empty_image_edit_summary() -> dict[str, Any]:
    """CODEX: Return default GUI image edit summary values."""

    return {
        "views": 0,
        "new": 0,
        "edited": 0,
        "class_changes": 0,
        "last_edit": None,
    }


def image_edit_summary(folder: Path, image_name: str) -> dict[str, Any]:
    """CODEX: Summarize JSONL backup events for one image.

    Current GUI status code usually passes SQLite rows directly to
    ``image_edit_summary_from_events``. This folder-based helper remains useful
    for legacy JSONL-only projects and tests around readable backup files.
    """

    return image_edit_summary_from_events(read_audit_events(folder), image_name)


def image_edit_summary_from_events(
    events: list[dict[str, Any]],
    image_name: str,
) -> dict[str, Any]:
    """CODEX: Summarize view/new/edit/class-change counts for one image.

    ``events`` may come from SQLite rows or decoded JSONL backup rows. The
    action buckets in this module classify which counters advance; ``last_edit``
    tracks the latest positive millisecond timestamp from non-view edit actions.
    """

    summary = empty_image_edit_summary()
    for event in events:
        if audit_event_image_name(event) != image_name:
            continue
        action = str(event.get("action", ""))
        if action == VIEW_AUDIT_ACTION:
            summary["views"] += 1
        elif action in SUMMARY_NEW_ACTIONS:
            summary["new"] += 1
            summary["last_edit"] = latest_event_time(summary["last_edit"], event)
        elif action in SUMMARY_EDIT_ACTIONS:
            summary["edited"] += 1
            summary["last_edit"] = latest_event_time(summary["last_edit"], event)
        elif action in SUMMARY_CLASS_CHANGE_ACTIONS:
            summary["class_changes"] += 1
            summary["last_edit"] = latest_event_time(summary["last_edit"], event)
    return summary


def latest_event_time(current: int | None, event: dict[str, Any]) -> int | None:
    """CODEX: Return the later valid millisecond timestamp.

    Missing, non-numeric, and non-positive event timestamps are ignored so a
    malformed compatibility row does not erase a previously known edit time.
    """

    try:
        event_time = int(event.get("event_time", 0))
    except (TypeError, ValueError):
        return current
    if event_time <= 0:
        return current
    if current is None or event_time > current:
        return event_time
    return current


def audit_event_image_name(event: dict[str, Any]) -> str | None:
    """CODEX: Return the image name associated with an audit event.

    ``details_json`` is preferred because direct event writers put the current
    image there even when before/after state is absent. Before/after state is
    then checked for older rows and for actions whose image identity is only
    present in captured annotation state.
    """

    details = audit_json_field(event, "details_json")
    if isinstance(details, dict) and details.get("image_name"):
        return str(details["image_name"])
    # CODEX: Details are explicit metadata; state fields are compatibility lookup.
    for field_name in ("after_state_json", "before_state_json"):
        state = audit_json_field(event, field_name)
        if isinstance(state, dict) and state.get("image_name"):
            return str(state["image_name"])
    return None


def audit_json_field(event: dict[str, Any], field_name: str) -> Any:
    """CODEX: Return one decoded JSON audit field, or ``None`` when unavailable.

    SQLite readers and legacy JSONL readers may hand callers either already
    decoded dictionaries/lists or JSON strings. Unsupported scalar values and
    malformed JSON are treated as absent because callers use this helper for
    optional metadata extraction, not schema validation.
    """

    value = event.get(field_name)
    if value in (None, ""):
        return None
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def format_image_edit_summary(summary: dict[str, Any]) -> str:
    """CODEX: Return the two-line edit-summary table shown under the GUI log."""

    header = "Views | New | Edited | class changes | Last edit"
    values = (
        f"{summary['views']} | {summary['new']} | {summary['edited']} | "
        f"{summary['class_changes']} | {format_summary_timestamp(summary['last_edit'])}"
    )
    return f"{header}\n{values}"


def format_summary_timestamp(timestamp: int | None) -> str:
    """CODEX: Format a millisecond timestamp using the user's local timezone."""

    if not timestamp:
        return "-"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp / 1000))


def annotation_audit_state(
    annotation: Any,
    annotation_index: int,
    categories: list[dict[str, Any]],
) -> dict[str, Any]:
    """CODEX: Return one JSON-friendly region-annotation audit snapshot.

    The returned keys describe the native generic annotation table. This is not
    a persistence row writer: callers still own Undo staging, SQLite commits,
    and action-specific audit details.
    """

    polygon = annotation.polygons[0] if annotation.polygons else []
    annotation_uuid_value = annotation.raw.get("annotation_uuid")
    annotation_uuid = annotation_uuid_value.strip() if annotation_uuid_value else ""
    # CODEX: Category lookup mirrors COCO metadata, with "object" as the legacy default.
    category_name = next(
        (
            str(category.get("name", "object"))
            for category in categories
            if int(category.get("id", -1)) == annotation.category_id
        ),
        "object",
    )
    return {
        "annotation_uuid": annotation_uuid,
        "annotation_index": annotation_index,
        "annotation_id": annotation.annotation_id,
        "component_id": None,
        "source_table": "annotations",
        "illustration_id": None,
        "session_id": None,
        "entry_time": annotation.raw.get("entry_time"),
        "annotation_role": "",
        "polygon_coords": [[x_coord, y_coord] for x_coord, y_coord in polygon],
        "bbox_coords": bbox_for_polygon(polygon),
        "obj_class": annotation.raw.get("obj_class", category_name),
        "class_id": annotation.raw.get("class_id", annotation.category_id),
        "category_id": annotation.category_id,
        "category_name": category_name,
        "model_confidence": annotation.score,
        "imprecise": int(annotation.raw.get("imprecise", 0) or 0),
        "annotation_type": annotation.raw.get("annotation_type", "polygon"),
        "entry_type": annotation.raw.get("entry_type", "manual"),
    }


def arrow_audit_state(
    arrow: Arrow,
    arrow_index: int,
) -> dict[str, Any]:
    """CODEX: Return one JSON-friendly arrow-annotation audit snapshot.

    Arrow snapshots use the durable arrow UUID plus endpoint coordinates so
    before/after comparison can classify created, updated, and deleted arrows.
    The bounding box is derived metadata for readers; SQLite persistence and
    audit-event insertion live outside this helper.
    """

    return {
        "annotation_uuid": arrow.arrow_uuid,
        "arrow_uuid": arrow.arrow_uuid,
        "arrow_index": arrow_index,
        "annotation_type": "keypoints",
        "annotation_role": "arrow",
        "start_x": arrow.start_x,
        "start_y": arrow.start_y,
        "end_x": arrow.end_x,
        "end_y": arrow.end_y,
        "bbox_coords": [
            min(arrow.start_x, arrow.end_x),
            min(arrow.start_y, arrow.end_y),
            abs(arrow.end_x - arrow.start_x),
            abs(arrow.end_y - arrow.start_y),
        ],
    }
