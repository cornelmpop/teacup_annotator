"""CODEX: Apply accepted folder-image reconciliation to SQLite rows.

This module owns the mutating half of load-time image reconciliation. The
public inspection and prompt-facing dataclass live in
``annotator.sqlite.image_reconciliation``; this file keeps row insertion,
missing-image deletion state, and the audit event together as one SQLite
transaction.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3

from annotator.log.audit import TRASH_FOLDER_NAME
from annotator.sqlite.audit import append_audit_event
from annotator.sqlite.image_identity import image_md5sum
from annotator.sqlite.image_reconciliation import FolderImageReconciliation
from annotator.sqlite.json import _json_dumps
from annotator.sqlite.queries import _image_size
from annotator.sqlite.schema import ensure_schema

RECONCILE_PROJECT_IMAGES_ACTION = "reconcile_project_images"


def apply_database_image_reconciliation(
    connection: sqlite3.Connection,
    reconciliation: FolderImageReconciliation,
) -> None:
    """CODEX: Mutate image rows and append the accepted reconciliation event."""

    ensure_schema(connection)
    rows = connection.execute("SELECT * FROM project_images").fetchall()
    rows_by_name = {row["image_name"]: row for row in rows}
    next_coco_image_id = _next_coco_image_id(rows)
    added_names: list[str] = []

    with connection:
        _mark_missing_images_moved(connection, reconciliation.missing_image_names)
        for image_index, image_path in enumerate(reconciliation.image_paths):
            row = rows_by_name.get(image_path.name)
            if row is None:
                _insert_project_image_row(
                    connection,
                    image_path,
                    image_index,
                    next_coco_image_id,
                )
                added_names.append(image_path.name)
                next_coco_image_id += 1
            elif not row["moved_to_trash"]:
                _verify_matching_image_hash(row, image_path)
                _refresh_project_image_row(connection, row, image_path, image_index)
        append_audit_event(
            connection,
            {
                "action": RECONCILE_PROJECT_IMAGES_ACTION,
                "event_summary": "Reconcile project images",
                "details_json": _json_dumps(
                    {
                        "added_image_names": added_names,
                        "missing_image_names": list(
                            reconciliation.missing_image_names
                        ),
                        "missing_images_recorded_as_moved_to_trash": True,
                        "source_table": "project_images",
                        "trash_folder": f"teacup/{TRASH_FOLDER_NAME}",
                    }
                ),
            },
            commit=False,
        )


def _next_coco_image_id(rows: list[sqlite3.Row]) -> int:
    """CODEX: Return the next never-used COCO image ID for new rows."""

    used_ids = [
        row["coco_image_id"] for row in rows if row["coco_image_id"] is not None
    ]
    return max(used_ids, default=0) + 1


def _mark_missing_images_moved(
    connection: sqlite3.Connection,
    image_names: tuple[str, ...],
) -> None:
    """CODEX: Record accepted missing root JPEGs as completed deletions."""

    if not image_names:
        return
    connection.executemany(
        """
        UPDATE project_images
        SET marked_for_deletion = 0, moved_to_trash = 1
        WHERE image_name = ?
          AND moved_to_trash = 0
        """,
        [(image_name,) for image_name in image_names],
    )


def _insert_project_image_row(
    connection: sqlite3.Connection,
    image_path: Path,
    image_index: int,
    coco_image_id: int,
) -> None:
    """CODEX: Insert one accepted root JPEG into ``project_images``."""

    width, height = _image_size(image_path)
    current_md5sum = image_md5sum(image_path)
    metadata = _image_metadata(image_path.name, coco_image_id)
    # CODEX: SQLite stores project paths as text at the filesystem boundary.
    image_path_text = str(image_path)
    connection.execute(
        """
        INSERT INTO project_images(
            image_name, image_path, image_md5sum, width, height,
            coco_image_id, image_sequence_index, metadata_json
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            image_path.name,
            image_path_text,
            current_md5sum,
            width,
            height,
            coco_image_id,
            image_index,
            metadata,
        ),
    )


def _refresh_project_image_row(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    image_path: Path,
    image_index: int,
) -> None:
    """CODEX: Refresh path, dimensions, and folder order for one active row."""

    width, height = _image_size(image_path)
    # CODEX: SQLite stores project paths as text at the filesystem boundary.
    image_path_text = str(image_path)
    connection.execute(
        """
        UPDATE project_images
        SET image_path = ?,
            width = ?,
            height = ?,
            image_sequence_index = ?
        WHERE image_id = ?
        """,
        (
            image_path_text,
            width,
            height,
            image_index,
            row["image_id"],
        ),
    )


def _image_metadata(image_name: str, coco_image_id: int) -> str:
    """CODEX: Return metadata matching normal Teacup image-row creation."""

    return _json_dumps(
        {
            "source": "Teacup image folder",
            "coco_image_record": {
                "id": coco_image_id,
                "file_name": image_name,
            },
        }
    )


def _verify_matching_image_hash(row: sqlite3.Row, image_path: Path) -> None:
    """CODEX: Reject same-name source files whose bytes no longer match."""

    current_md5sum = image_md5sum(image_path)
    stored_md5sum = row["image_md5sum"]
    if current_md5sum != stored_md5sum:
        raise ValueError(
            "Image content mismatch for "
            f"{image_path.name}: stored MD5 {stored_md5sum} does not "
            f"match current MD5 {current_md5sum}. The project database "
            "may belong to a different image folder, or the image file "
            "may have been replaced."
        )
