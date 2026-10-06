"""CODEX: Coordinate the non-GUI effects of an explicit project Save.

CODEX: The GUI save command gathers live state, user preferences, and
progress-dialog handling, then passes those values here as a
``ProjectSaveRequest``. This module owns the domain-level ordering of Save
effects: flush pending audit events, optionally refresh JSON backup/export
files from SQLite, rebuild annotation crops, write folder model settings when
the project uses them, and refresh project README metadata.

SQLite is already authoritative when this function runs. This module does not
autosave edits, create the database connection, choose backup preferences,
prompt users, catch persistence errors, or mutate GUI state; those decisions
belong to GUI save orchestration and the lower-level persistence modules.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import sqlite3

import annotator.sqlite as sql_backend
from annotator.model.configuration import save_model_conf
from annotator.project.crops import write_annotation_crops_from_database
from annotator.project.paths import project_file_path
from annotator.project_metadata import write_project_metadata


@dataclass(frozen=True, slots=True)
class ProjectSaveRequest:
    """Immutable inputs needed to complete one explicit Save.

    CODEX: ``folder``, ``connection``, and ``image_paths`` identify the loaded
    project and the authoritative SQLite state to export from.
    ``project_metadata`` is the metadata dictionary to rewrite after
    persistence effects complete.
    ``write_json_backups`` is the caller's already-resolved preference, and
    ``model_configuration`` is ``None`` unless this project should write folder
    model settings. ``crop_padding_px`` is the resolved nonnegative padding for
    every generated annotation crop.

    ``frozen`` and ``slots`` keep the GUI/domain handoff stable during the
    save: callers pass one explicit value object without accidental field
    rebinding or ad-hoc attributes.
    """

    folder: Path
    connection: sqlite3.Connection
    image_paths: list[Path]
    project_metadata: dict[str, str]
    write_json_backups: bool
    model_configuration: dict[str, str] | None
    crop_padding_px: int


@dataclass(frozen=True, slots=True)
class ProjectSaveResult:
    """Immutable summary returned to the GUI after Save effects complete.

    ``database_path`` is the canonical SQLite path used for status logging.
    ``wrote_json_backups`` records whether the optional backup/export refresh
    ran, so the GUI can report the completed save accurately without re-reading
    preferences.
    """

    database_path: Path
    wrote_json_backups: bool


def save_project(
    request: ProjectSaveRequest,
    flush_audit_events: Callable[[], None],
    progress: Callable[[float, str], None],
) -> ProjectSaveResult:
    """Run the ordered non-GUI persistence effects for explicit Save.

    ``request`` carries already-collected project state. ``flush_audit_events``
    must publish pending audit rows before exports are generated from SQLite.
    ``progress`` receives percent-like values and user-facing messages from the
    save dialog.

    CODEX: The function returns ``ProjectSaveResult`` after audit events,
    optional JSON backups, annotation crops, optional model settings, and
    README metadata have completed. It lets lower-level filesystem, SQLite,
    and image-identity errors propagate so GUI orchestration owns the single
    user-facing error path.
    """

    # Existing image rows bind annotations and arrows to exact source bytes.
    progress(8, "Verifying source image checksums")
    sql_backend.verify_project_image_hashes(request.connection, request.image_paths)
    # Pending audit rows must reach SQLite before any backup/export is generated.
    progress(12, "Finalizing SQLite audit records")
    flush_audit_events()
    # SQLite remains authoritative; this branch only refreshes optional files.
    if request.write_json_backups:
        sql_backend.save_json_backups_from_database(
            request.connection,
            request.folder,
            request.image_paths,
            # Map backup progress into the dialog range reserved for export refreshes.
            progress=lambda value, message: progress(
                15 + value * 0.7,
                message,
            ),
        )
    else:
        progress(70, "SQLite save complete")
    progress(72, "Writing annotation crops")
    write_annotation_crops_from_database(
        request.connection,
        request.folder,
        request.image_paths,
        request.crop_padding_px,
        progress=lambda completed, total: progress(
            72 + 16 * completed / max(1, total),
            f"Writing annotation crop {completed} of {total}",
        ),
    )
    # Folder model settings are written only for projects configured to own them.
    if request.model_configuration is not None:
        progress(90, "Writing folder model configuration")
        save_model_conf(request.folder, request.model_configuration)
    # README metadata is last so provenance and inventory describe completed outputs.
    progress(96, "Writing project metadata")
    write_project_metadata(
        request.folder,
        request.project_metadata,
        image_paths=request.image_paths,
        record_save=True,
    )
    return ProjectSaveResult(
        database_path=project_file_path(
            request.folder,
            sql_backend.DATABASE_FILENAME,
        ),
        wrote_json_backups=request.write_json_backups,
    )
