"""CODEX: Prompt for folders and publish completely loaded projects."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import traceback
from typing import Any
from typing import Protocol
from typing import cast

from tkinter import filedialog
from tkinter import messagebox

from annotator.dialogs import ErrorDetailsDialog
from annotator.dialogs import ProgressDialog
from annotator.gui.local_class_actions import LocalClassActionHost
from annotator.gui.local_class_actions import maybe_use_local_class_settings
from annotator.gui.project.folder_image_reconciliation import (
    resolve_folder_image_reconciliation,
)
from annotator.gui.project.folder_image_reconciliation import save_reconciled_project
from annotator.gui.project.folder_state import finish_loaded_project
from annotator.gui.project.folder_state import FolderStateHost
from annotator.gui.project.folder_state import install_loaded_folder_state
from annotator.gui.project.folder_state import reset_loaded_folder_state
from annotator.gui.state import ProjectState
from annotator.preferences import Preferences
from annotator.project.discovery import discover_project
from annotator.project.loading import load_project
from annotator.project.loading import prepare_project_load


IMPORT_REPORT_FILENAME = "last_coco_import_report.txt"
IMPORT_REPORT_SAVED_TEMPLATE = (
    "Some annotations were converted or rejected during COCO import.\n\n"
    "A copy of this report was saved to:\n{report_path}"
)
IMPORT_REPORT_UNSAVED_MESSAGE = (
    "Some annotations were converted or rejected during COCO import.\n\n"
    "The report could not be written. Copy it from this dialog."
)
IMPORT_REPORT_WRITE_FAILURE_TEMPLATE = (
    "The COCO import completed, but its report could not be written.\n\n{error}"
)


class FolderLoadingHost(Protocol):
    """Application state and effects required by folder loading."""

    prefs: Preferences
    project: ProjectState
    root: Any
    session_default_class_var: Any

    def close_sql_connection(self) -> None:
        """Close the active project database connection."""

        ...

    def log(self, message: str) -> None:
        """Record one folder-loading message."""

        ...


def load_folder_dialog(host: FolderLoadingHost) -> None:
    """CODEX: Prompt for a folder containing JPEG images."""

    initial = host.prefs.get_path("image_folder")
    folder_name = filedialog.askdirectory(
        initialdir=(
            str(initial) if initial and initial.is_dir() else str(Path.home())
        )
    )
    if folder_name:
        load_folder(host, Path(folder_name))

# CMP: TODO - Docstrings should explain the steps/logic. There are a lot of
#      checks here, which means checking implementation vs design errors
#      difficult.
def load_folder(
    host: FolderLoadingHost,
    folder: Path,
    automatic: bool = False,
) -> None:
    """CODEX: Replace the current project with ``folder`` or leave it empty.

    Discover images before unloading. Then classify SQLite read-only, offer an
    existing ``classes.json`` only for a new project, and pass any accepted
    class settings into the database initializer. The complete loaded result is
    published only after every non-GUI read succeeds. Failures after unloading
    leave a clean empty state and are reported with the full traceback.

    After a successful JSON migration, write its import report beside the user
    preferences. Show the copyable report dialog only when conversions or
    rejected rows were detected. A report-write failure is warned separately
    because it does not invalidate the newly loaded SQLite project.
    """

    migration_dialog: ProgressDialog | None = None
    import_notices: list[str] | None = None
    sql_connection: sqlite3.Connection | None = None
    unloading_started = False
    error_details: str | None = None
    try:
        discovery = discover_project(folder)
        load_plan = prepare_project_load(discovery, host.prefs.values)
        reconciliation_applied = resolve_folder_image_reconciliation(
            host,
            load_plan,
        )
        if reconciliation_applied is None:
            return

        if not discovery.image_paths:
            if not automatic:
                messagebox.showwarning(
                    "No JPEG images",
                    "The selected folder does not contain .jpg or .jpeg images.",
                )
            return

        unloading_started = True
        host.close_sql_connection()
        reset_loaded_folder_state(cast(FolderStateHost, host))

        initial_class_settings = None
        if not load_plan.native_project_established:
            # CODEX: A backup class file can seed only an uninitialized project;
            # CODEX: the prompt must precede the writable open that creates SQLite.
            maybe_use_local_class_settings(
                cast(LocalClassActionHost, host),
                folder,
            )
            if host.project.using_local_class_settings:
                initial_class_settings = (
                    host.project.session_class_names,
                    host.project.session_class_colours,
                )
        if load_plan.migration_required:
            migration_dialog = ProgressDialog(
                host.root,
                "Preparing annotation database",
                "Preparing SQLite annotation database",
                f"Migrating existing JSON annotations in {folder.name}",
            )

        def report_migration_progress(value: int, message: str) -> None:
            """Forward project migration progress to the optional dialog."""

            if migration_dialog is not None:
                migration_dialog.update_progress(value, message)

        loaded = load_project(
            load_plan,
            host.prefs.get_class_colours(),
            initial_class_settings=initial_class_settings,
            progress=(
                report_migration_progress
                if load_plan.migration_required
                else None
            ),
        )
        sql_connection = loaded.connection
        install_loaded_folder_state(cast(FolderStateHost, host), folder, loaded)
        finish_loaded_project(
            cast(FolderStateHost, host),
            folder,
            load_plan.migration_required,
            load_plan.native_project_established,
            initial_class_settings is not None,
        )
        if load_plan.migration_required:
            import_notices = loaded.document.import_notices
        if reconciliation_applied:
            save_reconciled_project(host)
    except Exception:
        error_details = _load_failure_details(
            host,
            folder,
            sql_connection,
            unloading_started,
        )
    finally:
        if migration_dialog is not None:
            migration_dialog.close()
    if error_details is not None:
        ErrorDetailsDialog(host.root, "Could not load folder", error_details)
    elif import_notices is not None:
        report_lines = [
            "Teacup COCO Import Report",
            f"Project: {folder.name}",
            "",
        ]
        if import_notices:
            report_lines.extend(f"- {notice}" for notice in import_notices)
        else:
            report_lines.append(
                "No geometry conversions or rejected annotation rows were detected."
            )
        report_text = "\n".join(report_lines) + "\n"
        report_path = host.prefs.path.with_name(IMPORT_REPORT_FILENAME)
        report_written = True
        try:
            report_path.write_text(report_text, encoding="utf-8")
        except OSError as exc:
            report_written = False
            messagebox.showwarning(
                "Import report not saved",
                IMPORT_REPORT_WRITE_FAILURE_TEMPLATE.format(error=exc),
                parent=host.root,
            )
        if import_notices:
            if report_written:
                report_message = IMPORT_REPORT_SAVED_TEMPLATE.format(
                    report_path=report_path,
                )
            else:
                report_message = IMPORT_REPORT_UNSAVED_MESSAGE
            ErrorDetailsDialog(
                host.root,
                "COCO Import Report",
                f"{report_message}\n\n{report_text}",
                copy_button_text="Copy report",
            )


# CMP: TODO - Document that this is to make bug reports easier. If the
#      user starts the application without a terminal backend, the trace is
#      lost; also, simply showing the text without being able to copy/paste
#      it is not helpful.
#      QUESTION - Would it not be better to simply output to a file that can
#      be uploaded with a bug? I guess you run into issues with filesystem
#      errors.
def _load_failure_details(
    host: FolderLoadingHost,
    folder: Path,
    sql_connection: sqlite3.Connection | None,
    unloading_started: bool,
) -> str:
    """CODEX: Return the established traceback text for failed folder loads.

    Close any candidate database and reset an already-unloaded host before
    returning copyable diagnostics for the outer error dialog. Cleanup errors
    are appended without replacing the original traceback. Cleanup also closes
    an old connection retained after a failed unload commit.
    """

    failure_traceback = traceback.format_exc()
    traceback.print_exc()
    cleanup_traceback = ""
    connection_to_close = sql_connection
    if connection_to_close is None and unloading_started:
        # CODEX: A failed unload commit leaves the old connection attached for
        # CODEX: this failure boundary to close before clearing project state.
        connection_to_close = host.project.sql_connection
    if connection_to_close is not None:
        try:
            connection_to_close.close()
        except Exception:
            cleanup_traceback = (
                "\n\nAn additional error occurred while closing the "
                "candidate database:\n\n"
                f"{traceback.format_exc()}"
            )
            traceback.print_exc()
    if unloading_started:
        host.project.sql_connection = None
        reset_loaded_folder_state(cast(FolderStateHost, host))
        state_message = (
            "The selected folder was not loaded. No project is currently loaded."
        )
    elif host.project.folder is not None:
        state_message = (
            "The selected folder was not loaded. The current project remains open."
        )
    else:
        state_message = (
            "The selected folder was not loaded. No project is currently loaded."
        )
    return f"Folder: {folder}\n\n{state_message}\n\n{failure_traceback}{cleanup_traceback}"
