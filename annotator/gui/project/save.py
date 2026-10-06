"""Explicit Save workflow for an authoritative annotation project."""

from __future__ import annotations

from functools import partial
import sqlite3
import tkinter as tk
from tkinter import messagebox
from typing import Protocol

from annotator.dialogs import ProgressDialog
from annotator.gui.audit.events import flush_pending_audit_events
from annotator.gui.model.settings import active_model_config_values
from annotator.gui.model.settings import ModelSettingsHost
from annotator.gui.persistence import BackupPreferenceHost
from annotator.gui.persistence import write_json_backups_enabled
from annotator.gui.project.delete_marked import maybe_delete_marked_images_on_save
from annotator.gui.project.deletion import DeletionHost
from annotator.gui.project.status import update_buttons
from annotator.gui.project.status import update_image_status
from annotator.preferences import Preferences
from annotator.project.saving import ProjectSaveRequest
from annotator.project.saving import save_project


class SaveHost(
    DeletionHost,
    BackupPreferenceHost,
    ModelSettingsHost,
    Protocol,
):
    """Application state and effects required by the explicit Save workflow."""

    root: tk.Tk
    prefs: Preferences

    def log(self, message: str) -> None: ...


def save_annotations(host: SaveHost) -> bool:
    """CODEX: Export authoritative state and crops, reporting complete success."""

    if host.project.coco is None or host.project.folder is None:
        return False
    if host.project.sql_connection is None:
        return False
    dialog = ProgressDialog(
        host.root,
        "Saving annotations",
        "Saving annotation project",
        f"Preparing {host.project.folder.name}",
    )
    host.interaction.worker_running = True
    update_buttons(host)
    try:
        dialog.update_progress(5, "Checking images marked for deletion")
        maybe_delete_marked_images_on_save(host)
        write_json_backups = write_json_backups_enabled(host)
        result = save_project(
            ProjectSaveRequest(
                folder=host.project.folder,
                connection=host.project.sql_connection,
                image_paths=host.project.all_image_paths,
                project_metadata=host.project.project_metadata,
                write_json_backups=write_json_backups,
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
    except (OSError, sqlite3.Error, ValueError) as exc:
        messagebox.showerror("Could not complete save", str(exc))
        return False
    finally:
        dialog.close()
        host.interaction.worker_running = False
        update_buttons(host)
    host.project.dirty = False
    if result.wrote_json_backups:
        host.log(f"Saved SQLite and JSON backups - {result.database_path}")
    else:
        host.log(f"Saved SQLite - {result.database_path}")
    update_image_status(host)
    return True
