"""CODEX: Reconcile project-root JPEG files with SQLite image rows.

This module owns the established-project load boundary where filesystem JPEG
inventory and SQLite ``project_images`` state must agree before GUI navigation
can treat an image as part of the project. It deliberately handles only root
``.jpg`` and ``.jpeg`` source images supplied by folder discovery.

Callers own user prompts, GUI publication, JSON backup refreshes, and current
project state. This module owns durable SQLite image-row additions, deletion
state for database rows whose root JPEG is already missing, and a concise audit
event recording the accepted reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from annotator.project.paths import project_file_path
from annotator.sqlite.connect import connect_database
from annotator.sqlite.constants import DATABASE_FILENAME
from annotator.sqlite.image_identity import image_md5sum
from annotator.sqlite.queries import database_has_document
from annotator.sqlite.schema import ensure_schema

@dataclass(frozen=True, slots=True)
class FolderImageReconciliation:
    """CODEX: Immutable SQLite/root-JPEG discrepancy report.

    ``folder`` and ``image_paths`` identify the folder-load candidate already
    enumerated by project discovery. ``added_image_paths`` lists root JPEGs
    missing from active SQLite rows. ``missing_image_names`` lists active
    SQLite image rows whose root JPEG is missing. The order of both collections
    follows the deterministic folder/database order used for prompts and
    writes.
    """

    folder: Path
    image_paths: tuple[Path, ...]
    added_image_paths: tuple[Path, ...]
    missing_image_names: tuple[str, ...]

    def has_changes(self) -> bool:
        """CODEX: Return whether applying this report would mutate SQLite."""

        return bool(self.added_image_paths or self.missing_image_names)


def inspect_folder_image_reconciliation(
    folder: Path,
    image_paths: list[Path],
) -> FolderImageReconciliation:
    """CODEX: Return root-JPEG discrepancies for an existing SQLite project.

    If the folder has no project database or the database has no image rows,
    return an empty report so first-time JSON/SQLite initialization remains the
    sole owner of image-row creation. For established projects, compare active
    ``project_images`` rows with the discovered root JPEG list. Matching names
    must also have matching MD5sums; a mismatch raises ``ValueError`` because a
    same-name replacement is not a safe addition or deletion.
    """

    database_path = project_file_path(folder, DATABASE_FILENAME)
    if not database_path.is_file():
        return _empty_reconciliation(folder, image_paths)
    connection = connect_database(folder)
    try:
        ensure_schema(connection)
        if not database_has_document(connection):
            return _empty_reconciliation(folder, image_paths)
        return _inspect_database_image_reconciliation(
            connection,
            folder,
            image_paths,
        )
    finally:
        connection.close()


def apply_folder_image_reconciliation(
    reconciliation: FolderImageReconciliation,
) -> None:
    """CODEX: Apply an accepted discrepancy report to SQLite.

    Added root JPEGs receive new ``project_images`` rows whose COCO IDs are
    allocated above every existing image row. Existing rows keep their COCO IDs
    while their path, dimensions, and current folder order are refreshed.
    Missing active rows are marked as already moved to trash because the source
    file is absent and cannot be moved by the normal filesystem operation.

    The image-row changes and the reconciliation audit event commit together.
    An empty report is a no-op.
    """

    if not reconciliation.has_changes():
        return
    from annotator.sqlite.image_reconciliation_apply import (
        apply_database_image_reconciliation,
    )

    connection = connect_database(reconciliation.folder)
    try:
        apply_database_image_reconciliation(connection, reconciliation)
    finally:
        connection.close()


def _empty_reconciliation(
    folder: Path,
    image_paths: list[Path],
) -> FolderImageReconciliation:
    """CODEX: Return the no-op report for a non-established project."""

    return FolderImageReconciliation(
        folder=folder,
        image_paths=tuple(image_paths),
        added_image_paths=(),
        missing_image_names=(),
    )


def _inspect_database_image_reconciliation(
    connection: sqlite3.Connection,
    folder: Path,
    image_paths: list[Path],
) -> FolderImageReconciliation:
    """CODEX: Compare active SQLite image names with discovered root JPEGs."""

    rows = _active_project_image_rows(connection)
    rows_by_name = {row["image_name"]: row for row in rows}
    discovered_by_name = {image_path.name: image_path for image_path in image_paths}

    added_image_paths = tuple(
        image_path
        for image_path in image_paths
        if image_path.name not in rows_by_name
    )
    missing_image_names = tuple(
        row["image_name"] for row in rows if row["image_name"] not in discovered_by_name
    )
    for image_path in image_paths:
        row = rows_by_name.get(image_path.name)
        if row is None:
            continue
        _verify_matching_image_hash(row, image_path)

    return FolderImageReconciliation(
        folder=folder,
        image_paths=tuple(image_paths),
        added_image_paths=added_image_paths,
        missing_image_names=missing_image_names,
    )


def _active_project_image_rows(
    connection: sqlite3.Connection,
) -> list[sqlite3.Row]:
    """CODEX: Return non-trash image rows in stored navigation order."""

    return connection.execute(
        """
        SELECT *
        FROM project_images
        WHERE moved_to_trash = 0
        ORDER BY image_sequence_index, image_id
        """
    ).fetchall()


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
