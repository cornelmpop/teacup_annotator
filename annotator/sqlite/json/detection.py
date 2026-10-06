"""CODEX: Detect legacy COCO JSON that may need first-time SQLite import.

This module decides whether existing JSON annotation files should be promoted
into an empty Teacup-native database. It does not certify complete schema
compatibility; schema preparation remains the responsibility of
``annotator.sqlite.schema.ensure_schema``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from annotator.coco.io import image_annotation_path
from annotator.project.paths import project_file_path
from annotator.sqlite.constants import DATABASE_FILENAME
from annotator.sqlite.constants import ProgressCallback
from annotator.sqlite.schema import SUPPORTED_SCHEMA_VERSION
from annotator.sqlite.schema import _schema_version_key


def json_sources_exist(folder: Path, image_paths: list[Path]) -> bool:
    """CODEX: Return True when legacy JSON annotation files are present."""

    if (folder / "annotations.json").is_file():
        return True
    return any(
        image_annotation_path(folder, image_path.name).is_file()
        for image_path in image_paths
    )


def json_migration_required(folder: Path, image_paths: list[Path]) -> bool:
    """CODEX: Return True when JSON exists and the native document is empty.

    A missing or empty database is an import candidate. A nonempty database must
    advertise ``SUPPORTED_SCHEMA_VERSION`` before this function inspects
    ``project_images``. Full schema validation stays with ``ensure_schema`` so
    malformed versioned databases fail through normal SQLite operations instead
    of being reinterpreted here.
    """

    if not json_sources_exist(folder, image_paths):
        return False
    return not native_project_established(folder)


def native_project_established(folder: Path) -> bool:
    """CODEX: Return whether SQLite already owns the project's class state.

    A missing database or a valid current database with no project-image rows
    is available for first-load initialization. A database containing project
    images is established and therefore owns class names, order, and colours.

    Known incompatible databases are also treated as established so a backup
    ``classes.json`` can never initialize over them before normal schema
    handling rejects the unsupported version. Unknown or malformed nonempty
    databases raise their natural SQLite or version error at this read-only
    boundary. The function never creates or modifies project files.
    """

    database_path = project_file_path(folder, DATABASE_FILENAME)
    if not database_path.is_file():
        return False
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    try:
        table_row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            LIMIT 1
            """
        ).fetchone()
        if table_row is None:
            return False
        schema_row = connection.execute(
            """
            SELECT schema_value
            FROM schema_metadata
            WHERE schema_key = 'schema_version'
            """
        ).fetchone()
        schema_version = _schema_version_key(schema_row[0])
        supported_version = _schema_version_key(SUPPORTED_SCHEMA_VERSION)
        if schema_version != supported_version:
            return True
        count_row = connection.execute("SELECT COUNT(*) FROM project_images").fetchone()
        image_row_count = count_row[0]
        return image_row_count > 0
    finally:
        connection.close()


def _report_progress(
    progress: ProgressCallback | None,
    value: int,
    message: str,
) -> None:
    """CODEX: Report migration progress when the GUI supplied a callback."""

    if progress is not None:
        progress(value, message)
