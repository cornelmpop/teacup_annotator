"""CODEX: Image-deletion marking and loaded-project state effects."""

from __future__ import annotations

import sqlite3
from tkinter import messagebox
from typing import Protocol

import annotator.sqlite as sql_backend
from annotator.gui.audit.events import AuditEventHost
from annotator.gui.audit.events import write_audit_event
from annotator.gui.project.filtering import FilteringHost
from annotator.gui.project.navigation import current_image_name
from annotator.gui.project.status import update_buttons
from annotator.gui.project.status import update_image_status
from annotator.gui.state import ProjectState
from annotator.log.audit import save_deletion_marks


class DeletionHost(FilteringHost, AuditEventHost, Protocol):
    """CODEX: Application state and effects required by image-deletion workflows."""


def mark_current_image_for_deletion(host: DeletionHost) -> None:
    """CODEX: Mark the current image for deletion on the next confirmed Save."""

    if host.project.folder is None or not host.project.image_paths:
        return
    image_name = current_image_name(host)
    if image_name in host.project.deletion_marks:
        host.log(f"Already marked for deletion: {image_name}")
        return

    # CMP: QUESTION - Under what valid application state would this condition
    # be true? In other words, why are not failing loudly?
    if host.project.sql_connection is None:
        return
    try:
        sql_backend.persist_image_deletion_state(
            host.project.sql_connection,
            {image_name},
            marked_for_deletion=True,
            moved_to_trash=False,
        )
    except sqlite3.Error as exc:
        messagebox.showerror("Could not mark image", str(exc))
        return
    host.project.deletion_marks.add(image_name)
    host.project.session_deletion_marks.add(image_name)
    try:
        save_deletion_marks(
            host.project.folder,
            host.project.deletion_marks,
        )
    except OSError as exc:
        messagebox.showwarning(
            "Deletion backup failed",
            (
                "The mark was saved to SQLite, but "
                f"deletion_marks.json failed:\n\n{exc}"
            ),
        )
    write_audit_event(
        host,
        action="mark_image_for_deletion",
        before_state=None,
        after_state={
            "image_name": image_name,
            "marked_for_deletion": True,
            "source_table": "project_images",
        },
        details={
            "image_name": image_name,
            "image_index": host.project.current_index,
        },
        source_table="project_images",
    )
    host.log(f"Marked for deletion: {image_name}")
    update_image_status(host)
    update_buttons(host)


def restore_current_image_from_trash(host: DeletionHost) -> None:
    """CODEX: Clear the current image's pending deletion state."""

    if host.project.folder is None or not host.project.image_paths:
        return
    image_name = current_image_name(host)
    if image_name not in host.project.deletion_marks:
        host.log(f"Image is not marked for deletion: {image_name}")
        return

    if host.project.sql_connection is None:
        return
    try:
        sql_backend.persist_image_deletion_state(
            host.project.sql_connection,
            {image_name},
            marked_for_deletion=False,
            moved_to_trash=False,
        )
    except sqlite3.Error as exc:
        messagebox.showerror("Could not restore image", str(exc))
        return
    host.project.deletion_marks.discard(image_name)
    host.project.session_deletion_marks.discard(image_name)
    try:
        save_deletion_marks(
            host.project.folder,
            host.project.deletion_marks,
        )
    except OSError as exc:
        messagebox.showwarning(
            "Deletion backup failed",
            (
                "The restore was saved to SQLite, but "
                f"deletion_marks.json failed:\n\n{exc}"
            ),
        )
    write_audit_event(
        host,
        action="restore_image_from_trash",
        before_state={
            "image_name": image_name,
            "marked_for_deletion": True,
            "moved_to_trash": False,
            "source_table": "project_images",
        },
        after_state={
            "image_name": image_name,
            "marked_for_deletion": False,
            "moved_to_trash": False,
            "source_table": "project_images",
        },
        details={
            "image_name": image_name,
            "image_index": host.project.current_index,
        },
        source_table="project_images",
    )
    host.log(f"Restored from trash: {image_name}")
    update_image_status(host)
    update_buttons(host)


def remove_deleted_images_from_state(
    project: ProjectState,
    image_names: set[str],
) -> None:
    """CODEX: Remove trash-moved images from active in-memory projections.

    Remove the named images from navigation, COCO image and region projections,
    and pending deletion marks. Their SQLite image and annotation rows remain
    authoritative for manual restoration.

    Arrow entries deliberately remain in the folder-wide ``arrows_by_image``
    mapping even though moved images are not renderable. Arrow persistence
    replaces the complete folder projection, so retaining those hidden entries
    prevents a later arrow edit from deleting restorable rows.
    """

    project.deletion_marks.difference_update(image_names)
    project.session_deletion_marks.difference_update(image_names)
    project.all_image_paths = [
        image_path
        for image_path in project.all_image_paths
        if image_path.name not in image_names
    ]
    project.image_paths = [
        image_path
        for image_path in project.image_paths
        if image_path.name not in image_names
    ]
    project.coco.image_paths = list(project.all_image_paths)  # type: ignore[union-attr]
    # CODEX: Arrow persistence replaces the folder-wide projection, so hidden
    # CODEX: moved-image entries must remain available for manual restoration.
    for image_name in image_names:
        project.coco.annotations_by_image.pop(image_name, None)  # type: ignore[union-attr]
        project.coco.image_records.pop(image_name, None)  # type: ignore[union-attr]
