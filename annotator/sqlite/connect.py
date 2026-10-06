"""CODEX: Open writable project databases and identify application sessions.

This module owns configured connections to ``teacup/Teacup.sqlite3``, writable
open verification, and creation or reuse of process-scoped session rows. The
module-level UUID and start timestamp describe one Teacup application process
and are reused in every project database it opens.

Schema creation and verification belong to ``schema``. Higher-level loading
workflows own successful connection lifetimes and user-facing error handling.
SQLite and operating-system errors propagate unchanged, and this module never
changes filesystem permissions.
"""

from __future__ import annotations

import os
import platform
import socket
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path

from annotator.project.paths import project_data_folder
from annotator.project.paths import project_file_path
from annotator.release_identity import BACKEND_VERSION
from annotator.sqlite.constants import DATABASE_FILENAME

APPLICATION_SESSION_ID = str(uuid.uuid4())
APPLICATION_SESSION_STARTED_AT = int(time.time())


def connect_database(folder: Path) -> sqlite3.Connection:
    """CODEX: Return a verified writable connection to the project database.

    Ensure the folder's ``teacup`` directory exists and address
    ``Teacup.sqlite3`` through a resolved ``mode=rwc`` file URI, which requires
    read-write access and creates a missing database. For a new database, one
    preliminary SQLite open and close stabilizes file identity on Apple FSKit
    exFAT before the configured connection is established.

    The configured connection uses ``sqlite3.Row`` records, enforces foreign
    keys, waits up to five seconds for a database lock, and proves write-lock
    availability with an immediate transaction that is rolled back before
    return. The caller owns subsequent transactions and closing the connection.
    Schema preparation belongs to ``ensure_schema``.

    Preliminary-open, configured-open, and write-lock failures propagate
    unchanged. A connection that fails during configuration is closed. The
    function does not retry failed opens or inspect or change filesystem
    permissions.
    """

    project_data_folder(folder).mkdir(exist_ok=True)
    database_path = project_file_path(folder, DATABASE_FILENAME)
    database_uri = f"{database_path.resolve().as_uri()}?mode=rwc"
    if not database_path.exists():
        # CODEX: One SQLite-owned open stabilizes a new file's identity on Apple
        # CODEX: FSKit exFAT before the configured connection performs schema writes.
        sqlite3.connect(database_uri, uri=True, timeout=5.0).close()
    connection = sqlite3.connect(
        database_uri,
        uri=True,
        timeout=5.0,
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        # CODEX: Verify write-lock authority before schema or project-state work begins.
        connection.execute("BEGIN IMMEDIATE")
        connection.rollback()
    except sqlite3.OperationalError:
        connection.close()
        raise
    return connection


def _ensure_session(connection: sqlite3.Connection) -> str:
    """CODEX: Return the process session UUID, inserting its row when absent.

    ``APPLICATION_SESSION_ID`` and ``APPLICATION_SESSION_STARTED_AT`` are
    created once when this module is imported. Every project database opened by
    the same process therefore uses one session identity, while another process
    receives a different UUID.

    An existing row is returned without changing its metadata. A missing row is
    inserted with the Teacup version, process start time in Unix seconds, local
    timezone label, hostname, machine type, and operating-system description.

    The caller must provide the current ``sessions`` schema and owns the
    surrounding transaction. This function does not commit, and SQLite errors
    propagate unchanged.
    """

    row = connection.execute(
        "SELECT session_id FROM sessions WHERE session_id = ?",
        (APPLICATION_SESSION_ID,),
    ).fetchone()
    if row:
        return str(row["session_id"])

    connection.execute(
        """
        INSERT INTO sessions(
            session_id, app_version, started_time, session_timezone,
            hostname, host_type, os
        )
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (
            APPLICATION_SESSION_ID,
            BACKEND_VERSION,
            APPLICATION_SESSION_STARTED_AT,
            _local_timezone_name(),
            socket.gethostname(),
            platform.machine() or "unknown",
            platform.platform(),
        ),
    )
    return APPLICATION_SESSION_ID


def current_session_id(connection: sqlite3.Connection) -> str:
    """CODEX: Return the current process session UUID for one prepared database.

    Ensure the process session row exists through ``_ensure_session``, then
    return its UUID. The caller owns schema preparation, transaction completion,
    and the connection lifetime.
    """

    return _ensure_session(connection)


def _local_timezone_name() -> str:
    """CODEX: Return the best available label for the local timezone.

    Prefer a nonblank ``TZ`` environment value, then the active timezone
    object's database key, then its localized name or abbreviation. Return
    ``"local"`` when none is available. This value supports audit readability;
    the operating system and Python runtime own its content and availability.
    """

    environment_timezone = os.environ.get("TZ", "").strip()
    if environment_timezone:
        return environment_timezone
    timezone_info = datetime.now().astimezone().tzinfo
    timezone_key = getattr(timezone_info, "key", "")
    if timezone_key:
        return str(timezone_key)
    timezone_name = datetime.now().astimezone().tzname()
    return timezone_name or "local"
