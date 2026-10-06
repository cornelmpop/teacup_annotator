"""Functional writes for authoritative annotation project state."""

# CMP: TODO - expand the module docstring. Too terse.

from __future__ import annotations

from pathlib import Path
import sqlite3
from tkinter import messagebox
from typing import Protocol

import annotator.sqlite as sql_backend
from annotator.gui.model.settings import active_class_colours
from annotator.gui.model.settings import ModelSettingsHost
from annotator.gui.project.navigation import current_image_name
from annotator.gui.recovery import RecoveryHost
from annotator.gui.recovery import restore_document_from_sql
from annotator.gui.state import ProjectState
from annotator.preferences import Preferences


class ProjectPersistenceHost(Protocol):
    """Project state required by storage functions."""

    project: ProjectState


class BackupPreferenceHost(Protocol):
    """Preference state required to select optional JSON backups."""

    prefs: Preferences


class AnnotationPersistenceHost(
    ProjectPersistenceHost,
    BackupPreferenceHost,
    ModelSettingsHost,
    Protocol,
):
    """Application values required by annotation storage functions."""


class AutosaveHost(AnnotationPersistenceHost, RecoveryHost, Protocol):
    """Application effects required to complete or recover one autosave."""

    def log(self, message: str) -> None: ...


def write_json_backups_enabled(host: BackupPreferenceHost) -> bool:
    """Return whether SQL saves should also refresh COCO JSON backups."""

    return host.prefs.get_bool("write_json_backups", True)

# CMP: TODO - clarify docstring.
# CODEX: mixed_selection_region_delete_reorders_arrows_2026-08-26 adds the
# CODEX: project order map so arrow saves preserve sparse annotation order.
def persist_arrows(
    host: ProjectPersistenceHost,
    commit: bool = True,
) -> None:
    """CODEX: Reconcile SQLite arrows from the project's complete mapping."""

    if host.project.folder is None or host.project.sql_connection is None:
        return
    sql_backend.persist_arrows(
        host.project.sql_connection,
        host.project.arrows_by_image,
        commit=commit,
        annotation_orders_by_uuid=host.project.annotation_orders_by_uuid,
    )

# CMP: TODO - clarify docstring, expanding on what global actions may be expected.
#      Also document why write_json_backups is off by default for this (e.g., JSON
#      backups are written only on intentional save operations to minimize unnecessary
#      I/O)
# CODEX: mixed_selection_region_delete_reorders_arrows_2026-08-26 threads sparse
# CODEX: annotation order through global region synchronization.
def persist_all_annotations(
    host: AnnotationPersistenceHost,
    commit: bool = True,
) -> None:
    """CODEX/CMP: Synchronize active-image regions after a global action."""

    if host.project.coco is None:
        return
    if host.project.sql_connection is None:
        raise sqlite3.ProgrammingError("No SQLite database is open")
    sql_backend.persist_document(
        host.project.sql_connection,
        host.project.coco,
        write_json_backups=False,
        class_colours=active_class_colours(host),
        commit=commit,
        annotation_orders_by_uuid=host.project.annotation_orders_by_uuid,
    )

def persist_image_annotations(
    host: AnnotationPersistenceHost,
    image_name: str,
    annotation_indices: list[int] | None = None,
    commit: bool = True,
    human_edit: bool = False,
) -> Path | None:
    """CODEX: Persist one named image with explicit human-edit semantics.

    CODEX: ``human_edit`` reaches SQLite's changed-row boundary so surviving
    CODEX: model-linked annotations become manual only when this write actually
    CODEX: changes them. Model installation and Undo restoration leave it false.
    CODEX: Callers own transaction composition when ``commit`` is false.
    """

    if host.project.coco is None:
        return None
    if host.project.sql_connection is None:
        if not commit:
            raise sqlite3.ProgrammingError("No SQLite database is open")
        return host.project.coco.save_image(image_name)
    if annotation_indices:
        return sql_backend.persist_annotations(
            host.project.sql_connection,
            host.project.coco,
            image_name,
            annotation_indices,
            write_json_backup=commit and write_json_backups_enabled(host),
            class_colours=active_class_colours(host),
            commit=commit,
            annotation_orders_by_uuid=host.project.annotation_orders_by_uuid,
            human_edit=human_edit,
        )
    return sql_backend.persist_image(
        host.project.sql_connection,
        host.project.coco,
        image_name,
        write_json_backup=commit and write_json_backups_enabled(host),
        class_colours=active_class_colours(host),
        commit=commit,
        annotation_orders_by_uuid=host.project.annotation_orders_by_uuid,
        human_edit=human_edit,
    )


# CMP: TODO - Clarify docstring. Replace 'persist' and 'active backend'
# with something more immediately meaningful.
# CODEX: mixed_selection_region_delete_reorders_arrows_2026-08-26 preserves the
# CODEX: database order stream when current-image region rows are rewritten.
def persist_current_image_annotations(
    host: AnnotationPersistenceHost,
    annotation_indices: list[int] | None = None,
    commit: bool = True,
    human_edit: bool = False,
) -> Path | None:
    """CODEX: Persist the displayed image through the named-image boundary."""

    if host.project.coco is None or not host.project.image_paths:
        return None
    return persist_image_annotations(
        host,
        current_image_name(host),
        annotation_indices,
        commit,
        human_edit,
    )

# CMP: TODO - clarify docstring - we are not editing the image per-se, and
# this is important for safety reasons (i.e., we don't want an application
# crash to delete a lot of in-memory operations during a long session).
def autosave_current_image(
    host: AutosaveHost,
    annotation_indices: list[int] | None = None,
    human_edit: bool = True,
) -> bool:
    """CODEX: Persist one completed human edit or exact source restoration.

    Normal GUI operations use the default human-edit policy. Undo passes false
    because its snapshot, including a restored model source, is authoritative.
    """

    if host.project.coco is None or not host.project.image_paths:
        return False
    try:
        from annotator.gui.audit.events import flush_pending_audit_events

        persist_current_image_annotations(
            host,
            annotation_indices,
            commit=False,
            human_edit=human_edit,
        )
        # CODEX: Source promotion is now reflected in memory, so audit
        # CODEX: after-state records the same provenance committed to SQLite.
        flush_pending_audit_events(host)
    except sqlite3.Error as exc:
        restore_document_from_sql(host)
        host.log(f"Autosave failed: {exc}")
        messagebox.showerror("Autosave failed", str(exc))
        return False
    path = None

    # CMP: No special handling of these failures is needed, since the individual
    # JSON files do not get automatically imported. If they are out of sync, it's
    # not great, but it's also not a show stopper, as these are effectively backups
    # of backups.
    if write_json_backups_enabled(host):
        try:
            path = host.project.coco.save_image(current_image_name(host))
        except OSError as exc:
            host.log(f"JSON backup failed after SQLite autosave: {exc}")
            messagebox.showerror("JSON backup failed", str(exc))
            return True
    saved_name = path.name if path is not None else sql_backend.DATABASE_FILENAME
    host.log(f"Autosaved {saved_name}")
    return True
