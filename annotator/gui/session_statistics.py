"""Refresh per-session statistics CSVs from GUI lifecycle boundaries."""

# CMP: QUESTION - Are there multiple per-session CSVs?

from __future__ import annotations

import sqlite3
import tkinter as tk
from typing import Protocol

import annotator.sqlite as sql_backend
from annotator.gui.state import ProjectState
from annotator.log.session_statistics import write_session_statistics_csv

SESSION_STATISTICS_REFRESH_MS = 60_000


class SessionStatisticsHost(Protocol):
    """Application state required to write and schedule session summaries."""

    project: ProjectState
    root: tk.Tk

    def log(self, message: str) -> None:
        """Record one user-visible application message."""

        ...


def write_current_session_statistics(host: SessionStatisticsHost) -> None:
    """Write the loaded folder's current session statistics CSV, if possible."""

    if host.project.folder is None or host.project.sql_connection is None:
        return
    session_id = sql_backend.current_session_id(host.project.sql_connection)
    write_session_statistics_csv(
        host.project.folder,
        host.project.sql_connection,
        session_id,
    )

# CMP: TODO - Document the logic of refreshing every 60 seconds (or whatever
# time).
def refresh_session_statistics(host: SessionStatisticsHost) -> None:
    """Refresh session statistics and schedule the next one-minute refresh."""

    try:
        write_current_session_statistics(host)
    except (OSError, sqlite3.Error) as exc:
        host.log(f"Session statistics update failed: {exc}")
    host.root.after(
        SESSION_STATISTICS_REFRESH_MS,
        refresh_session_statistics,
        host,
    )
