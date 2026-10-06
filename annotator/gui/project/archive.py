"""Distribution-archive GUI orchestration."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from tkinter import filedialog
from tkinter import messagebox
import traceback
from typing import cast
from typing import Protocol

from annotator.archive import create_archive
from annotator.dialogs import ErrorDetailsDialog
from annotator.dialogs import ProgressDialog
from annotator.gui.project.save import SaveHost
from annotator.gui.project.save import save_annotations
from annotator.gui.project.status import update_buttons
from annotator.project.archiving import inspect_archive_readiness
from annotator.project_metadata import PROJECT_METADATA_LABELS
from annotator.sqlite.constants import DATABASE_FILENAME


class ArchiveHost(SaveHost, Protocol):
    """Application state and effects required by the archive workflow."""

    def open_config_window(self) -> None: ...

# CMP: TODO - Clarify docstring - snapshot as a term doesn't show up in the
#      code itself. Clarify delegation and ownership clearly.
# CMP: QUESTION: Is a dialog potentially raised mid-archive? If so, that's no
#      sound behaviour. Checks should be conducted before commits.
def archive_folder(host: ArchiveHost) -> None:
    """Validate, save, snapshot, and package the active annotation folder."""

    if host.project.folder is None or not host.project.all_image_paths:
        return
    readiness = inspect_archive_readiness(
        host.project.folder,
        host.project.project_metadata,
    )
    if not readiness.class_definitions_present:
        messagebox.showerror(
            "Class definitions required",
            (
                "Archive was stopped because the required class-definition "
                "file does not exist:\n\n"
                f"{readiness.class_definitions_path}\n\n"
                "Create this file at the path shown before exporting."
            ),
        )
        return
    if readiness.missing_metadata_keys:
        labels = "\n".join(
            f"- {PROJECT_METADATA_LABELS[key]}"
            for key in readiness.missing_metadata_keys
        )
        messagebox.showerror(
            "Archive metadata required",
            (
                "Archive was stopped. Fill in these fields under "
                f"Configuration > Project:\n\n{labels}\n\n"
                "Any nonempty value, including TODO, is accepted."
            ),
        )
        host.open_config_window()
        return

    # CMP: TODO - This list should live outside this code, since
    #      this creates a synchronization problem if the code that
    #      actually implements the archival changes (e.g., a new
    #      file is added.
    confirmed = messagebox.askokcancel(
        "Create distribution archive",
        (
            "The archive will contain only:\n\n"
            "- README.txt\n"
            f"- {DATABASE_FILENAME}\n"
            "- annotations.json\n"
            "- class_definitions.txt\n"
            "- checksums.txt\n"
            "- all loaded JPG/JPEG images\n\n"
            "Before distributing it, review the FAIR Distribution section "
            "in USER_MANUAL.md.\n\n"
            "Continue?"
        ),
    )
    if not confirmed:
        return
    filename = filedialog.asksaveasfilename(
        title="Save annotation archive",
        initialdir=str(host.project.folder.parent),
        initialfile=f"{host.project.folder.name}.zip",
        defaultextension=".zip",
        filetypes=(("ZIP archive", "*.zip"),),
    )
    if not filename or not save_annotations(host):
        return

    output_path = Path(filename)
    host.interaction.worker_running = True
    update_buttons(host)
    dialog = ProgressDialog(
        host.root,
        "Creating archive",
        "Creating distribution archive",
        f"Preparing {output_path.name}",
    )
    try:
        create_archive(
            host.project.folder,
            host.project.all_image_paths,
            cast(sqlite3.Connection, host.project.sql_connection),
            output_path,
            progress=dialog.update_progress,
        )
    except Exception:
        details = traceback.format_exc()
        traceback.print_exc()
        ErrorDetailsDialog(host.root, "Could not create archive", details)
        host.log(f"Archive failed: {details}")
        return
    finally:
        dialog.close()
        host.interaction.worker_running = False
        update_buttons(host)
        
    messagebox.showinfo(
        "Archive created",
        (
            f"Created:\n{output_path}\n\n"
            "Before distributing it, review the FAIR Distribution section "
            "in USER_MANUAL.md."
        ),
    )
    host.log(f"Created distribution archive: {output_path}")
