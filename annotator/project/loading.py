"""CODEX: Prepare and load non-GUI project state after folder discovery.

This module owns the project-loading domain boundary after image discovery and
before GUI state publication. It resolves project metadata and migration
readiness, opens or imports the authoritative SQLite-backed document, gathers
project records that live outside COCO, and returns one installable result.

It does not prompt users, choose folders, publish state into ``AnnotatorApp``,
load image pixels, apply filters, redraw widgets, or report final load errors.
Those effects live in ``annotator.gui.project.folder_loading`` and
``annotator.gui.project.folder_state``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import sqlite3

import annotator.sqlite as sql_backend
from annotator.arrows import Arrow
from annotator.coco import CocoDocument
from annotator.log.audit import DELETION_MARKS_FILENAME
from annotator.log.audit import load_deletion_marks
from annotator.log.audit import read_audit_events
from annotator.log.audit import save_deletion_marks
from annotator.project.discovery import ProjectDiscovery
from annotator.project.paths import project_file_path
from annotator.project_metadata import read_project_metadata

@dataclass(frozen=True, slots=True)
class ProjectLoadPlan:
    """CODEX: Immutable pre-load facts prepared after discovery.

    The GUI uses this plan to decide whether to show migration progress before
    calling ``load_project``. ``discovery`` carries the folder and ordered image
    paths, ``project_metadata`` contains README-backed metadata resolved with
    preference fallbacks, and ``migration_required`` records whether legacy
    JSON annotation files need promotion into SQLite.
    ``native_project_established`` records whether SQLite already owns project
    classes, allowing the GUI to offer ``classes.json`` only before first
    database initialization.

    ``frozen`` and ``slots`` keep this handoff explicit and stable across the
    project/GUI boundary.
    """

    discovery: ProjectDiscovery
    project_metadata: dict[str, str]
    migration_required: bool
    native_project_established: bool


@dataclass(frozen=True, slots=True)
class LoadedProject:
    """CODEX: Complete non-GUI project state returned after a successful load.

    The result includes the COCO document, open SQLite connection, arrows,
    stored annotation orders, review flags, pending deletion marks,
    authoritative ordered region-class settings, and next audit-event ID.
    Nullable SQL display colours remain nullable until GUI publication applies
    its display-only preference palette.
    Once this object is returned, the GUI folder-state layer owns installing
    the values or closing the connection if later publication fails.

    ``frozen`` and ``slots`` prevent accidental field rebinding while the
    loaded state crosses into GUI publication.
    """

    plan: ProjectLoadPlan
    document: CocoDocument
    connection: sqlite3.Connection
    arrows_by_image: dict[str, list[Arrow]]
    annotation_orders_by_uuid: dict[str, int]
    review_flags: set[str]
    deletion_marks: set[str]
    class_names: tuple[str, ...]
    class_colours: tuple[str | None, ...]
    next_audit_event_id: int


def prepare_project_load(
    discovery: ProjectDiscovery,
    preference_values: dict[str, str],
) -> ProjectLoadPlan:
    """CODEX: Read metadata and classify the native project before loading.

    The caller supplies a ``ProjectDiscovery`` result and active raw preference
    values. Project metadata is read before loading so the GUI has a stable
    plan. Read-only SQLite classification establishes whether the database
    already owns classes. JSON migration is needed only when JSON exists and
    that native project is not established. This function does not open the
    project for editing, mutate project files, or publish GUI state.
    """

    # CODEX: Class-source prompting depends on this read-only result and must run
    # CODEX: before any writable database open can create or initialize SQLite.
    native_project_established = sql_backend.native_project_established(
        discovery.folder
    )
    return ProjectLoadPlan(
        discovery=discovery,
        project_metadata=read_project_metadata(
            discovery.folder,
            preference_values,
        ),
        migration_required=(
            sql_backend.json_sources_exist(
                discovery.folder,
                discovery.image_paths,
            )
            and not native_project_established
        ),
        native_project_established=native_project_established,
    )


def load_project(
    plan: ProjectLoadPlan,
    class_colours: tuple[str, ...],
    initial_class_settings: tuple[tuple[str, ...], tuple[str, ...]] | None = None,
    progress: Callable[[int, str], None] | None = None,
) -> LoadedProject:
    """CODEX: Load all non-GUI project state and return one installable result.

    The SQLite backend owns opening the database, creating schema, importing
    legacy COCO JSON when needed, and reconstructing the COCO document. This
    function then loads project records outside the document: arrows, review
    flags, ordered class settings, legacy audit backups, and the next
    audit-event ID. SQLite deletion flags are authoritative for established
    projects; legacy deletion-mark files are migration input only before SQLite
    owns project-image rows. Authoritative SQL audit history is checked before
    the optional JSONL backup, which is recovery input only when SQL history is
    empty. ``initial_class_settings`` is passed to the SQLite initializer,
    which uses it only for an empty native document.

    If any later step fails after the database is opened, the candidate
    connection is closed before the original exception is re-raised. Successful
    results leave the connection open for GUI publication.
    """

    folder = plan.discovery.folder
    # The SQLite backend owns schema setup and any first-load JSON migration.
    document, connection = sql_backend.load_or_import_document(
        folder,
        plan.discovery.image_paths,
        class_colours,
        initial_class_settings,
        progress=progress,
    )
    try:
        arrows_by_image = sql_backend.load_arrows(connection)
        annotation_orders_by_uuid = sql_backend.load_annotation_orders(connection)
        review_flags = sql_backend.load_review_flags(connection)
        class_names, stored_class_colours = (
            sql_backend.load_region_class_settings(connection)
        )
        legacy_deletion_marks = load_deletion_marks(folder)
        legacy_deletion_marks_exists = project_file_path(
            folder,
            DELETION_MARKS_FILENAME,
        ).is_file()
        if not plan.native_project_established:
            # CODEX: Compatibility marks can seed only a newly initialized database.
            if legacy_deletion_marks and plan.discovery.restored_deletion_names:
                legacy_deletion_marks -= set(plan.discovery.restored_deletion_names)
                save_deletion_marks(folder, legacy_deletion_marks)
            if legacy_deletion_marks:
                sql_backend.persist_image_deletion_state(
                    connection,
                    legacy_deletion_marks,
                    marked_for_deletion=True,
                    moved_to_trash=False,
                )
        deletion_marks = sql_backend.load_pending_deletions(connection)
        if (
            plan.native_project_established
            and legacy_deletion_marks_exists
            and legacy_deletion_marks != deletion_marks
        ):
            # CODEX: Established projects refresh the compatibility file from SQL.
            save_deletion_marks(folder, deletion_marks)
        next_event_id = sql_backend.next_audit_event_id(connection)
        if next_event_id == 1:
            # CODEX: Optional backup parsing is relevant only to empty SQL history.
            legacy_events = read_audit_events(folder)
            if legacy_events:
                sql_backend.import_audit_events_if_empty(connection, legacy_events)
                next_event_id = sql_backend.next_audit_event_id(connection)
    except Exception:
        # A partially loaded result must not leak an open candidate connection.
        connection.close()
        raise
    return LoadedProject(
        plan=plan,
        document=document,
        connection=connection,
        arrows_by_image=arrows_by_image,
        annotation_orders_by_uuid=annotation_orders_by_uuid,
        review_flags=review_flags,
        deletion_marks=deletion_marks,
        class_names=class_names,
        class_colours=stored_class_colours,
        next_audit_event_id=next_event_id,
    )
