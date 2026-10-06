"""CODEX: Define the shared database filename and progress callback type.

The database basename is the public name used by connection, archive, metadata,
and recovery workflows. The callback type is shared by SQLite loading and JSON
backup operations.

Canonical path construction belongs to ``annotator.project.paths``. Schema
table names and annotation vocabularies belong to the packaged ``Teacup.sql``
schema and the modules that read or write those rows.
"""

from __future__ import annotations

from typing import Callable

# CODEX: Project path helpers place this authoritative database basename under
# CODEX: the canonical ``teacup`` directory; archives reuse the same filename.
DATABASE_FILENAME = "Teacup.sqlite3"

# CODEX: SQLite loading and JSON-backup workflows report a whole-number
# CODEX: percentage plus a user-facing stage message; callbacks return no value.
ProgressCallback = Callable[[int, str], None]
