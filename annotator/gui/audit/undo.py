"""CODEX: Orchestrate scoped Undo capture, restoration, persistence, and audit."""

from __future__ import annotations

from tkinter import messagebox
from typing import Any, Protocol, cast
import sqlite3
import time

import annotator.sqlite as sql_backend
from annotator.gui.audit.events import flush_pending_audit_events
from annotator.gui.audit.state import annotation_uuid_at
from annotator.gui.audit.state import audit_state_from_snapshot
from annotator.gui.audit.state import current_audit_state
from annotator.gui.audit.undo_snapshot import capture_undo_snapshot
from annotator.gui.audit.undo_snapshot import restore_undo_snapshot
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.persistence import AnnotationPersistenceHost
from annotator.gui.persistence import BackupPreferenceHost
from annotator.gui.persistence import autosave_current_image
from annotator.gui.persistence import persist_all_annotations
from annotator.gui.persistence import persist_arrows
from annotator.gui.persistence import persist_image_annotations
from annotator.gui.persistence import write_json_backups_enabled
from annotator.gui.project.navigation import current_image_name
from annotator.gui.recovery import RecoveryHost
from annotator.gui.recovery import restore_arrows_from_sql
from annotator.gui.recovery import restore_document_from_sql
from annotator.gui.render_state import RenderStateHost
from annotator.gui.render_state import mark_annotations_changed
from annotator.gui.selection import clear_annotation_selection
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.preferences import Preferences


class UndoSnapshotHost(Protocol):
    """Project state required to stage Undo snapshots."""

    project: ProjectState


class UndoHost(UndoSnapshotHost, Protocol):
    """Application state and effects required by Undo operations."""

    interaction: InteractionState
    prefs: Preferences

    def log(self, message: str) -> None:
        """Record one Undo persistence or recovery message."""

        ...

# CMP: QUESTION - Is it really justified to have a default action for such
# an important function?
def push_undo(
    host: UndoSnapshotHost,
    action: str = "edit_annotation",
    annotation_index: int | None = None,
    details: dict[str, Any] | None = None,
    all_images: bool = False,
    started_monotonic_ns: int | None = None,
    source_uuid: str | None = None,
    source_table: str | None = None,
) -> None:
    """CODEX: Stage the declared Undo scope and its matching audit event."""

    if host.project.coco is None:
        return
    image_name = None if all_images else current_image_name(host)
    snapshot = capture_undo_snapshot(host.project, image_name, all_images, action)
    host.project.undo_stack.append(snapshot)

    # CMP: TODO - justify why we are doing this.
    if len(host.project.undo_stack) > 50:
        del host.project.undo_stack[0]

    audit_details = dict(details or {})
    if host.project.image_paths:
        audit_details.setdefault("image_name", current_image_name(host))
        audit_details.setdefault("image_index", host.project.current_index)
    if annotation_index is not None:
        audit_details.setdefault("annotation_index", annotation_index)
    event = {
        "action": action,
        "source_uuid": (
            source_uuid
            if source_uuid is not None
            else annotation_uuid_at(host, annotation_index)
        ),
        "before_state": audit_state_from_snapshot(host, snapshot, all_images),
        "all_images": all_images,
        "details": audit_details,
        "started_monotonic_ns": (
            started_monotonic_ns
            if started_monotonic_ns is not None
            else time.monotonic_ns()
        ),
        "undo_snapshot": snapshot,
    }
    if image_name is not None:
        event["image_name"] = image_name
    # CMP: TODO - so what if the source_table IS None?
    if source_table is not None:
        event["source_table"] = source_table
    host.project.pending_audit_events.append(event)

# CMP: TODO - Hm, that's a lot of stuff to keep track of. Can't this
# boilerplate resetting be delegated to a centralized place?
def undo(host: UndoHost) -> None:
    """CODEX: Restore, persist, and audit the latest chronological Undo entry.

    CODEX: Local entries retain owners; failed writes reload authoritative SQLite.
    """

    if host.project.coco is None or not host.project.undo_stack:
        return
    snapshot = host.project.undo_stack.pop()
    all_images = bool(snapshot.get("all_images"))
    target_image_name = snapshot.get("image_name")
    before_state = current_audit_state(host, all_images, target_image_name)
    target_image_name, arrows_changed = restore_undo_snapshot(host.project, snapshot)
    clear_annotation_selection(host.interaction)
    host.interaction.selected_arrow_index = None
    host.interaction.selected_arrow_indices.clear()
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    host.interaction.mode = None
    host.interaction.temp_polygon = []
    host.interaction.temp_edge_insertions = []
    host.interaction.drag_vertex_original_point = None
    host.interaction.drag_shared_vertex_refs = []
    mark_annotations_changed(cast(RenderStateHost, host))
    host.project.dirty = True

    undo_event = {
        "action": "undo",
        "source_uuid": None,
        "before_state": before_state,
        "all_images": all_images,
        "details": {"undo_stack_depth": len(host.project.undo_stack)},
        "undo_of_audit_event_id": snapshot["audit_event_id"],
    }
    if target_image_name is not None:
        undo_event["image_name"] = target_image_name
    host.project.pending_audit_events.append(undo_event)

    try:
        if arrows_changed:
            persist_arrows(cast(AnnotationPersistenceHost, host), commit=False)
        if all_images:
            persist_all_annotations(cast(AnnotationPersistenceHost, host), commit=False)
        else:
            persist_image_annotations(
                cast(AnnotationPersistenceHost, host),
                target_image_name,
                commit=False,
            )
        flush_pending_audit_events(host)
    except sqlite3.Error as exc:
        host.project.pending_audit_events.pop()
        host.project.undo_stack.append(snapshot)
        restore_arrows_from_sql(cast(RecoveryHost, host))
        restore_document_from_sql(cast(RecoveryHost, host))
        messagebox.showerror("Could not save undo", str(exc))
        return

    backup_path = None
    backup_failed = False
    if (
        write_json_backups_enabled(cast(BackupPreferenceHost, host))
        and host.project.sql_connection is not None
        and host.project.folder is not None
    ):
        try:
            if all_images:
                sql_backend.save_json_backups_from_database(
                    host.project.sql_connection, host.project.folder,
                    host.project.all_image_paths,
                )
            else:
                backup_path = host.project.coco.save_image(target_image_name)
        except OSError as exc:
            backup_failed = True
            messagebox.showerror("JSON backup failed", str(exc))
    if target_image_name is not None:
        if target_image_name != current_image_name(host):
            # CODEX: Name the off-screen owner because the canvas intentionally
            # CODEX: stays on the image the user is currently viewing.
            host.log(f"Undid {snapshot['action']} on {target_image_name}")
        elif not backup_failed:
            saved_name = (
                backup_path.name
                if backup_path is not None
                else sql_backend.DATABASE_FILENAME
            )
            host.log(f"Autosaved {saved_name}")
    redraw_canvas(cast(CanvasRenderHost, host))
