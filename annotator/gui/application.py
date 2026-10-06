"""Application-level startup, connection, close, and logging effects."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import time
import tkinter as tk
from tkinter import messagebox
from typing import Any
from typing import Protocol

import annotator.sqlite as sql_backend
from annotator.gui.audit.events import finalize_committed_audit_events
from annotator.gui.audit.events import write_audit_event
from annotator.gui.project.folder_loading import load_folder
from annotator.gui.project.navigation import current_image_name
from annotator.gui.project.navigation import persist_current_image_position
from annotator.gui.session_statistics import write_current_session_statistics
from annotator.gui.state import ProjectState
from annotator.gui.window.state import WindowWidgets
from annotator.log.audit import CLOSE_AUDIT_ACTION
from annotator.preferences import Preferences


class ApplicationHost(Protocol):
    """Application values and callbacks consumed by lifecycle effects."""

    root: tk.Tk
    prefs: Preferences
    project: ProjectState
    widgets: WindowWidgets

    def close_sql_connection(self) -> None:
        """Close the current SQLite connection."""

        ...

    def log(self, message: str) -> None:
        """Record one application message."""

        ...


def load_saved_folder(host: ApplicationHost) -> None:
    """Offer to load the persisted folder on startup when it still exists."""

    saved_folder = host.prefs.get_path("image_folder")
    if saved_folder and saved_folder.is_dir():
        confirmed = messagebox.askokcancel(
            "Open last folder",
            "Open the last folder you were working on?\n\n"
            f"{saved_folder}",
            parent=host.root,
        )
        if not confirmed:
            return
        load_folder(host, saved_folder, automatic=True)


def close_sql_connection(host: ApplicationHost) -> None:
    """CODEX: Commit, close, and clear the active project connection.

    A failed commit leaves the connection open and attached so the caller can
    roll back or otherwise recover it.
    """

    connection = host.project.sql_connection
    if connection is None:
        return
    connection.commit()
    connection.close()
    host.project.sql_connection = None

# CMP: TODO - Clarify here whether this is triggered by closing the application
# through the X at the top of the application window, or what other conditions
# trigger it.
def close_application(host: ApplicationHost) -> None:
    """CODEX: Persist close state and destroy the root after a successful commit.

    A persistence failure rolls back staged close work, reports the original
    error, and leaves the project and window open for retry.
    """

    close_event: dict[str, Any] | None = None
    try:
        if host.project.coco is not None and host.project.image_paths:
            persist_current_image_position(host)
        close_event = record_application_close(host, commit=False)
        write_current_session_statistics(host)
        host.close_sql_connection()
    except (OSError, sqlite3.Error) as exc:
        if close_event is not None and host.project.sql_connection is not None:
            host.project.sql_connection.rollback()
        messagebox.showerror("Could not save before closing", str(exc))
        return
    if close_event is not None:
        finalize_committed_audit_events(host, [close_event])
    host.root.destroy()


def record_application_close(
    host: ApplicationHost,
    commit: bool = True,
) -> dict[str, Any] | None:
    """Record a final audit event for a normal application close."""

    if host.project.sql_connection is None:
        return None
    details = {"source": "application_close"}
    if host.project.folder is not None:
        details["folder"] = str(host.project.folder)
    if host.project.image_paths:
        details["image_name"] = current_image_name(host)
        details["image_index"] = host.project.current_index
    return write_audit_event(
        host,
        action=CLOSE_AUDIT_ACTION,
        before_state=None,
        after_state=None,
        details=details,
        source_table="application",
        commit=commit,
    )

# CMP: QUESTION: Why is SQLite listed as optional here?
# CMP: QUESTION: Does it make sense to set the timestamp here? The timestamp
#      for log messages should be owned by the logging module.
def append_log(host: ApplicationHost, message: str) -> None:
    """Append a timestamped GUI log line and its optional SQLite copy."""

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    display_message = f"{timestamp}  {message}"
    log_text = host.widgets.controls.log_text
    log_text.configure(state=tk.NORMAL)
    log_text.insert(tk.END, display_message + "\n")
    log_text.see(tk.END)
    log_text.configure(state=tk.DISABLED)
    if host.project.sql_connection is not None:
        try:
            sql_backend.append_log_entry(host.project.sql_connection, message)
        except sqlite3.Error:
            pass


def main() -> None:
    """Create the Tk root and run the Annotator application."""

    from annotator.gui.app import AnnotatorApp

    root = tk.Tk()
    AnnotatorApp(root)
    root.mainloop()
