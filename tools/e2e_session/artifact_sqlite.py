"""CODEX: Project authoritative SQLite classes, image state, and arrows for E2E comparison.

The final artifact golden complements action-level output deltas with the
SQLite values required to reopen a project. It deliberately omits raw database
bytes, sessions, logs, audit history, and region rows already covered by the
workflow golden. Callers own the read-only connection and canonicalization of
paths, UUIDs, and geometry precision.
"""

from __future__ import annotations

from collections.abc import Callable
import json
import sqlite3
from typing import Any


def sqlite_artifact_state(
    connection: sqlite3.Connection,
    canonicalize: Callable[[Any], Any],
) -> dict[str, Any]:
    """CODEX: Return deterministic resumable state from authoritative SQLite rows.

    Region classes retain SQL order and nullable colours. Project images expose
    navigation, content identity, their recorded source path, and workflow state.
    Arrows retain image ownership, order, source, and decoded geometry. The
    supplied canonicalizer normalizes only established E2E nondeterminism.
    """

    # CODEX: SQLite owns these values even when a readable backup such as
    # CODEX: classes.json is also present; the file is projected independently.
    state = {
        "arrows": _arrow_rows(connection),
        "classes": _class_rows(connection),
        "images": _image_rows(connection),
    }
    return canonicalize(state)


def _class_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """CODEX: Return ordered region-class identity and display settings."""

    rows = connection.execute(
        """
        SELECT class_name, class_list_order, coco_category_id, supercategory,
               display_color, class_source
        FROM annotation_classes
        WHERE annotation_family = 'region'
        ORDER BY class_list_order, class_id
        """
    ).fetchall()
    return [
        {
            "coco_category_id": row["coco_category_id"],
            "colour": row["display_color"],
            "name": row["class_name"],
            "order": row["class_list_order"],
            "source": row["class_source"],
            "supercategory": row["supercategory"],
        }
        for row in rows
    ]


def _image_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """CODEX: Return ordered image identity, navigation, and workflow state."""

    rows = connection.execute(
        """
        SELECT image_name, image_path, image_md5sum, image_sequence_index,
               pending_review, marked_for_deletion, moved_to_trash
        FROM project_images
        ORDER BY image_sequence_index, image_name, image_id
        """
    ).fetchall()
    return [
        {
            "image_path": row["image_path"],
            "image_md5sum": row["image_md5sum"],
            "marked_for_deletion": row["marked_for_deletion"],
            "moved_to_trash": row["moved_to_trash"],
            "name": row["image_name"],
            "order": row["image_sequence_index"],
            "pending_review": row["pending_review"],
        }
        for row in rows
    ]


def _arrow_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """CODEX: Return ordered arrow identity, source, and decoded geometry."""

    rows = connection.execute(
        """
        SELECT ann.annotation_uuid, ann.annotation_order,
               ann.annotation_source, ann.geometry_json, img.image_name
        FROM annotations AS ann
        JOIN project_images AS img ON img.image_id = ann.image_id
        WHERE ann.annotation_type = 'keypoints'
          AND ann.annotation_role = 'arrow'
        ORDER BY img.image_sequence_index, img.image_name,
                 ann.annotation_order, ann.annotation_id
        """
    ).fetchall()
    return [
        {
            "geometry": json.loads(row["geometry_json"]),
            "image": row["image_name"],
            "order": row["annotation_order"],
            "source": row["annotation_source"],
            "uuid": row["annotation_uuid"],
        }
        for row in rows
    ]
