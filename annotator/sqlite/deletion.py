"""CODEX: Reconcile SQLite image-deletion flags with filesystem state.

This module owns recovery of ``project_images`` deletion state after an
interrupted trash move or manual restoration. It compares each source path with
its exact ``teacup/trash`` target, verifies restored bytes against stored MD5,
and commits flag changes with their audit event. Image rows, annotations,
confirmation, file moves, and JSON-backup cleanup stay outside this module.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from annotator.log.audit import TRASH_FOLDER_NAME
from annotator.project.paths import project_file_path
from annotator.sqlite.audit import append_audit_event
from annotator.sqlite.connect import connect_database
from annotator.sqlite.constants import DATABASE_FILENAME
from annotator.sqlite.image_identity import verify_project_image_hashes
from annotator.sqlite.json import _json_dumps
from annotator.sqlite.schema import ensure_schema

RECONCILE_IMAGE_DELETION_ACTION = "reconcile_image_deletion_state"


def reconcile_folder_image_deletions(folder: Path) -> tuple[set[str], set[str]]:
    """CODEX: Reconcile an existing folder database before image discovery.

    Return empty sets if no database exists. Otherwise, open a writable
    connection, delegate to ``reconcile_image_deletions``, and close the
    connection whether reconciliation returns or raises. Running before
    source-image enumeration lets the last image's interrupted move complete
    even when no loadable root JPEG remains.
    """

    database_path = project_file_path(folder, DATABASE_FILENAME)
    # CODEX: Discovery must not create a database solely to ask whether an
    # CODEX: interrupted move needs recovery.
    if not database_path.is_file():
        return set(), set()
    connection = connect_database(folder)
    try:
        return reconcile_image_deletions(connection, folder)
    finally:
        connection.close()


def reconcile_image_deletions(
    connection: sqlite3.Connection,
    folder: Path,
) -> tuple[set[str], set[str]]:
    """CODEX: Reconcile recorded deletion state against exact image paths.

    Return ``(completed_names, restored_names)``. Pending rows stay pending when
    only the source exists, become moved when only the exact trash target
    exists, and fail when both paths or neither path exist. Moved rows become
    restored when a matching-MD5 source reappears. All paths and restored bytes
    are checked before SQL updates, then changed flags and one audit event
    commit together. The function reads filesystem state but never changes
    files; schema, filesystem, identity, and SQLite errors propagate unchanged.
    """

    ensure_schema(connection)
    rows = connection.execute(
        """
        SELECT image_name, marked_for_deletion, moved_to_trash
        FROM project_images
        WHERE marked_for_deletion = 1 OR moved_to_trash = 1
        ORDER BY image_name
        """
    ).fetchall()
    completed_names: set[str] = set()
    restored_names: set[str] = set()
    restored_paths: list[Path] = []
    rows_by_name = {row["image_name"]: row for row in rows}
    # CODEX: Classify every candidate before issuing updates so one ambiguous
    # CODEX: pending row cannot leave earlier candidates partially reconciled.
    for row in rows:
        image_name = str(row["image_name"])
        source_path = folder / image_name
        trash_path = project_file_path(folder, TRASH_FOLDER_NAME) / image_name
        source_exists = source_path.is_file()
        trash_exists = trash_path.is_file()
        if int(row["moved_to_trash"]):
            if source_exists:
                restored_names.add(image_name)
                restored_paths.append(source_path)
            continue
        if source_exists and trash_exists:
            raise FileExistsError(
                f"Both the project image and trash target exist for {image_name}"
            )
        if not source_exists and not trash_exists:
            raise FileNotFoundError(
                f"Neither the project image nor trash target exists for {image_name}"
            )
        if trash_exists:
            completed_names.add(image_name)
    if restored_paths:
        # CODEX: An exact filename alone does not establish restoration; verify
        # CODEX: every source before committing any inferred flag changes.
        verify_project_image_hashes(connection, restored_paths)
    if completed_names or restored_names:
        changed_names = sorted(completed_names | restored_names)
        before_state = {"images": _deletion_state_images(rows_by_name, changed_names)}
        after_state = {
            "images": [
                {
                    "image_name": image_name,
                    "marked_for_deletion": False,
                    "moved_to_trash": image_name in completed_names,
                }
                for image_name in changed_names
            ]
        }
        with connection:
            for image_names, moved_to_trash in (
                (completed_names, 1),
                (restored_names, 0),
            ):
                if not image_names:
                    continue
                connection.executemany(
                    """
                    UPDATE project_images
                    SET marked_for_deletion = 0, moved_to_trash = ?
                    WHERE image_name = ?
                    """,
                    [
                        (moved_to_trash, image_name)
                        for image_name in sorted(image_names)
                    ],
                )
            append_audit_event(
                connection,
                {
                    "action": RECONCILE_IMAGE_DELETION_ACTION,
                    "event_summary": "Reconcile image deletion state",
                    "before_state_json": _json_dumps(before_state),
                    "after_state_json": _json_dumps(after_state),
                    "details_json": _json_dumps(
                        {
                            "completed_image_names": sorted(completed_names),
                            "restored_image_names": sorted(restored_names),
                            "source_table": "project_images",
                            "trash_folder": f"teacup/{TRASH_FOLDER_NAME}",
                        }
                    ),
                },
                commit=False,
            )
    return completed_names, restored_names


def _deletion_state_images(
    rows_by_name: dict[str, sqlite3.Row],
    image_names: list[str],
) -> list[dict[str, bool | str]]:
    """CODEX: Return audit snapshots for current image deletion flags."""

    return [
        {
            "image_name": image_name,
            "marked_for_deletion": rows_by_name[image_name]["marked_for_deletion"]
            == 1,
            "moved_to_trash": rows_by_name[image_name]["moved_to_trash"] == 1,
        }
        for image_name in image_names
    ]


def moved_image_names(connection: sqlite3.Connection) -> set[str]:
    """CODEX: Return image names SQLite records as already moved to trash.

    This query trusts SQLite: it does not inspect source/trash paths, reconcile
    deletion flags, or remove JSON backups. Callers use it after reconciliation
    to limit backup cleanup to known completed moves.
    """

    ensure_schema(connection)
    rows = connection.execute(
        """
        SELECT image_name
        FROM project_images
        WHERE moved_to_trash = 1
        """
    ).fetchall()
    return {str(row["image_name"]) for row in rows}
