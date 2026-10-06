"""CODEX: Prepare the Teacup-native SQLite schema and audit vocabulary.

The packaged ``Teacup.sql`` file is the schema source of truth for new
databases. This module creates missing schemas from that resource, requires
existing databases to advertise a supported schema version, probes them for the
required current tables and columns, and seeds the built-in audit action
vocabulary plus hidden internal annotation classes used by event writers and
arrow persistence.

It intentionally limits migration to app-owned internal rows needed by the
current schema contract. Callers own connection lifetime, user-facing error
handling, and any future migration workflow that changes user-owned project
semantics.
"""

from __future__ import annotations

import sqlite3

from annotator.release_identity import BACKEND_VERSION
from annotator.resources import read_schema_sql
from annotator.sqlite.internal_classes import seed_internal_annotation_classes

SUPPORTED_SCHEMA_VERSION = "1.9.4"

AUDIT_ACTION_ROWS: tuple[tuple[str, str, str], ...] = (
    ("change_class", "Change class", "Change one or more annotation classes."),
    ("close_application", "Close application", "Record application shutdown."),
    ("create_annotation", "Create annotation", "Create one editable annotation."),
    ("delete_annotation", "Delete annotation", "Delete one or more annotations."),
    ("delete_arrow", "Delete arrow", "Delete one or more arrow annotations."),
    ("delete_marked_images", "Delete marked images", "Move marked images to trash."),
    ("delete_vertex", "Delete vertex", "Delete one polygon vertex."),
    ("delete_vertices", "Delete vertices", "Delete multiple polygon vertices."),
    ("draw_arrow", "Draw arrow", "Create one arrow annotation."),
    ("edit_annotation", "Edit annotation", "Edit one annotation."),
    ("insert_vertex", "Insert vertex", "Insert one polygon vertex."),
    (
        "mark_image_for_deletion",
        "Mark image for deletion",
        "Mark one image for deletion.",
    ),
    ("merge_annotations", "Merge annotations", "Merge selected annotations."),
    ("move_arrow_endpoint", "Move arrow endpoint", "Move one arrow endpoint."),
    ("move_vertex", "Move vertex", "Move one polygon or rectangle vertex."),
    (
        "reconcile_project_images",
        "Reconcile project images",
        "Accept folder-load JPEG additions or missing-image deletion state.",
    ),
    (
        "reconcile_image_deletion_state",
        "Reconcile image deletion state",
        "Record inferred trash completion or manual restoration.",
    ),
    (
        "reorient_simplified_polygon",
        "Reorient simplified polygon",
        "Legacy automatic arrow-to-polygon alignment event.",
    ),
    (
        "resize_rectangle",
        "Resize rectangle",
        "Resize an editable rectangle annotation.",
    ),
    (
        "restore_image_from_trash",
        "Restore image from trash",
        "Clear one image's pending deletion state.",
    ),
    (
        "run_model",
        "Run model",
        "Replace model-generated regions with new model output.",
    ),
    ("select_start_vertex", "Select start vertex", "Choose a polygon starting vertex."),
    ("simplify_polygon", "Simplify polygon", "Resample or simplify polygon geometry."),
    ("undo", "Undo", "Restore a previous annotation state."),
    ("view_image", "View image", "Record image navigation or review."),
)


def ensure_schema(connection: sqlite3.Connection) -> None:
    """CODEX: Create or verify the native schema and seed internal rows.

    Existing databases must advertise ``SUPPORTED_SCHEMA_VERSION`` and provide
    the current required tables and columns. The version check rejects every
    other schema contract, while the probe queries let SQLite report malformed
    current-version schemas without this module repairing or reinterpreting
    them. App-owned audit vocabulary and the reserved arrow class row are then
    seeded in the caller's connection.
    """

    ready = connection.execute(
        """
        SELECT name
        FROM sqlite_temp_master
        WHERE type = 'table' AND name = 'annotator_schema_ready'
        """
    ).fetchone()
    if ready:
        return
    existing = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        LIMIT 1
        """
    ).fetchone()
    if existing:
        _ensure_supported_schema_version(connection)
        connection.execute("SELECT session_id FROM sessions LIMIT 0")
        connection.execute("SELECT image_id, image_md5sum FROM project_images LIMIT 0")
        connection.execute(
            "SELECT class_uuid, coco_category_id FROM annotation_classes LIMIT 0"
        )
        connection.execute(
            "SELECT model_run_class_id, model_class_index "
            "FROM model_run_classes LIMIT 0"
        )
        connection.execute(
            "SELECT annotation_uuid, annotation_order, geometry_json "
            "FROM annotations LIMIT 0"
        )
        connection.execute("SELECT action_key FROM audit_event_actions LIMIT 0")
        connection.execute(
            "SELECT audit_event_id, audit_event_action_id, duration_ms "
            "FROM audit_events LIMIT 0"
        )
        connection.execute(
            "SELECT audit_event_id, annotation_uuid, change_type, "
            "before_state_json, after_state_json "
            "FROM audit_event_annotations LIMIT 0"
        )
        connection.execute(
            "SELECT audit_event_id, class_uuid, change_type, "
            "before_state_json, after_state_json "
            "FROM audit_event_classes LIMIT 0"
        )
        connection.execute("SELECT info_json FROM coco_info LIMIT 0")
    else:
        connection.executescript(read_schema_sql())
    seed_audit_event_actions(connection)
    seed_internal_annotation_classes(connection)
    connection.execute(
        "CREATE TEMP TABLE annotator_schema_ready (ready INTEGER NOT NULL)"
    )
    connection.commit()


def _ensure_supported_schema_version(connection: sqlite3.Connection) -> None:
    """CODEX: Raise when an existing database advertises an unsupported schema."""

    schema_row = connection.execute(
        """
        SELECT schema_value
        FROM schema_metadata
        WHERE schema_key = 'schema_version'
        """
    ).fetchone()
    schema_version = _schema_version_key(schema_row[0])
    supported_version = _schema_version_key(SUPPORTED_SCHEMA_VERSION)
    if schema_version != supported_version:
        raise sqlite3.DatabaseError(
            "Unsupported Teacup SQLite schema version "
            f"{schema_row[0]}; supported version is {SUPPORTED_SCHEMA_VERSION}"
        )


def _schema_version_key(version: str) -> tuple[int, ...]:
    """CODEX: Return numeric comparison parts for schema-version text.

    The schema stores versions as text, so this helper is the comparison
    boundary. Malformed version metadata raises its natural conversion error.
    """

    version_parts = version.split(".")
    version_key = tuple(int(part) for part in version_parts)
    return version_key


def seed_audit_event_actions(connection: sqlite3.Connection) -> None:
    """CODEX: Ensure every built-in audit action has a stable database row.

    The built-in action list is application-owned vocabulary seeded into each
    prepared database. Existing rows keep their identity while labels and
    descriptions are refreshed to the current application wording. The caller
    owns transaction completion.
    """

    connection.executemany(
        """
        INSERT INTO audit_event_actions(
            action_key, action_label, action_description, introduced_app_version
        )
        VALUES(?, ?, ?, ?)
        ON CONFLICT(action_key) DO UPDATE SET
            action_label = excluded.action_label,
            action_description = excluded.action_description
        """,
        [
            (key, label, description, BACKEND_VERSION)
            for key, label, description in AUDIT_ACTION_ROWS
        ],
    )


def ensure_audit_event_action(
    connection: sqlite3.Connection,
    action_key: str,
) -> int:
    """CODEX: Return the database id for an audit action, adding it if needed.

    Known actions should normally be present from schema preparation. This
    helper supports future or externally supplied action keys by inserting a
    minimally labeled row without changing existing vocabulary rows. The caller
    owns the surrounding transaction.
    """

    label = action_key.replace("_", " ").capitalize()
    row = connection.execute(
        """
        INSERT INTO audit_event_actions(
            action_key, action_label, action_description, introduced_app_version
        )
        VALUES(?, ?, NULL, ?)
        ON CONFLICT(action_key) DO UPDATE SET action_key = excluded.action_key
        RETURNING audit_event_action_id
        """,
        (action_key, label, BACKEND_VERSION),
    ).fetchone()
    return int(row["audit_event_action_id"])
