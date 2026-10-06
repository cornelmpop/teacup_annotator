"""CODEX: Prompt and save around folder-image reconciliation."""

from __future__ import annotations

from functools import partial
from typing import Any
from typing import Protocol

from tkinter import messagebox

import annotator.sqlite as sql_backend
from annotator.dialogs import ProgressDialog
from annotator.gui.audit.events import flush_pending_audit_events
from annotator.gui.model.settings import active_model_config_values
from annotator.gui.persistence import write_json_backups_enabled
from annotator.gui.state import ProjectState
from annotator.log.audit import remove_moved_image_sidecars
from annotator.log.audit import save_deletion_marks
from annotator.preferences import Preferences
from annotator.project.loading import ProjectLoadPlan
from annotator.project.saving import ProjectSaveRequest
from annotator.project.saving import save_project

RECONCILE_PROJECT_IMAGES_TITLE = "Reconcile project images?"
RECONCILE_PROJECT_IMAGES_MESSAGE = (
    "The folder JPEG files and Teacup.sqlite3 do not match.\n\n"
    "JPEGs to add to SQLite: {added_count} ({added_names})\n"
    "Database images missing from the folder: {missing_count} ({missing_names})\n\n"
    "Accepting registers added JPEGs, records missing JPEGs through deletion/"
    "trash state where possible, opens the reconciled project, and saves "
    "project outputs.\n\n"
    "Rejecting leaves files and database unchanged and cancels this folder "
    "load. JSON and other non-JPEG files are ignored."
)
RECONCILED_SAVE_TITLE = "Saving reconciled project"
RECONCILED_SAVE_HEADING = "Saving reconciled project"
RECONCILED_SAVE_PREPARING = "Preparing {folder_name}"


class FolderImageReconciliationHost(Protocol):
    """CODEX: Host state required by reconciliation prompts and saves."""

    prefs: Preferences
    project: ProjectState
    root: Any
    session_default_class_var: Any

    def log(self, message: str) -> None:
        """CODEX: Record one project-loading message."""

        ...


def resolve_folder_image_reconciliation(
    host: FolderImageReconciliationHost,
    load_plan: ProjectLoadPlan,
) -> bool | None:
    """CODEX: Prompt for established-project JPEG/SQLite reconciliation.

    Return ``True`` when accepted reconciliation changed SQLite, ``False`` when
    no prompt was needed, and ``None`` when the user rejected the discrepancy
    and the caller must cancel folder loading before unloading current state.
    """

    if not load_plan.native_project_established:
        return False
    reconciliation = sql_backend.inspect_folder_image_reconciliation(
        load_plan.discovery.folder,
        load_plan.discovery.image_paths,
    )
    if not reconciliation.has_changes():
        return False
    confirmed = messagebox.askyesno(
        RECONCILE_PROJECT_IMAGES_TITLE,
        _folder_image_reconciliation_message(reconciliation),
    )
    if not confirmed:
        host.log("Folder load cancelled: project images were not reconciled")
        return None
    sql_backend.apply_folder_image_reconciliation(reconciliation)
    remove_moved_image_sidecars(
        load_plan.discovery.folder,
        set(reconciliation.missing_image_names),
    )
    return True


def save_reconciled_project(host: FolderImageReconciliationHost) -> None:
    """CODEX: Refresh project outputs after accepted image reconciliation.

    This uses the lower-level save boundary directly so load-time
    reconciliation does not process unrelated pending deletion marks. The
    database-backed JSON, crop, model, and metadata outputs are refreshed before
    the compatibility deletion-mark file, preserving any pending marks still
    loaded in memory.
    """

    if (
        host.project.folder is None
        or host.project.coco is None
        or host.project.sql_connection is None
    ):
        return
    dialog = ProgressDialog(
        host.root,
        RECONCILED_SAVE_TITLE,
        RECONCILED_SAVE_HEADING,
        RECONCILED_SAVE_PREPARING.format(folder_name=host.project.folder.name),
    )
    try:
        result = save_project(
            ProjectSaveRequest(
                folder=host.project.folder,
                connection=host.project.sql_connection,
                image_paths=host.project.all_image_paths,
                project_metadata=host.project.project_metadata,
                write_json_backups=write_json_backups_enabled(host),
                model_configuration=(
                    active_model_config_values(host)
                    if host.project.using_folder_model_conf
                    else None
                ),
                crop_padding_px=host.prefs.get_crop_padding_px(),
            ),
            partial(flush_pending_audit_events, host),
            dialog.update_progress,
        )
        dialog.update_progress(100, "Save complete")
    finally:
        dialog.close()
    host.project.dirty = False
    save_deletion_marks(host.project.folder, host.project.deletion_marks)
    if result.wrote_json_backups:
        host.log(f"Saved reconciled SQLite and JSON backups - {result.database_path}")
    else:
        host.log(f"Saved reconciled SQLite - {result.database_path}")


def _folder_image_reconciliation_message(
    reconciliation: sql_backend.FolderImageReconciliation,
) -> str:
    """CODEX: Format the confirmation body for JPEG/SQLite discrepancies."""

    added_names = tuple(path.name for path in reconciliation.added_image_paths)
    missing_names = reconciliation.missing_image_names
    return RECONCILE_PROJECT_IMAGES_MESSAGE.format(
        added_count=len(added_names),
        added_names=_limited_image_name_summary(added_names),
        missing_count=len(missing_names),
        missing_names=_limited_image_name_summary(missing_names),
    )


def _limited_image_name_summary(image_names: tuple[str, ...]) -> str:
    """CODEX: Return a compact prompt summary for a discrepancy name list."""

    if not image_names:
        return "none"
    shown_names = ", ".join(image_names[:5])
    hidden_count = len(image_names) - 5
    if hidden_count <= 0:
        return shown_names
    return f"{shown_names}, and {hidden_count} more"
