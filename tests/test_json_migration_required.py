"""Tests for JSON-to-SQLite migration detection boundaries."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import annotator.sqlite as sql_backend
from annotator.project.paths import project_file_path


class JsonMigrationRequiredTests(unittest.TestCase):
    """JSON migration detection distinguishes empty files from unknown schemas."""

    def test_empty_sqlite_file_remains_migration_candidate(self) -> None:
        """A zero-table SQLite file is equivalent to no initialized database."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "annotations.json").write_text("{}", encoding="utf-8")
            database_path = project_file_path(folder, sql_backend.DATABASE_FILENAME)
            database_path.parent.mkdir(parents=True)
            sqlite3.connect(database_path).close()

            migration_required = sql_backend.json_migration_required(folder, [])

        self.assertTrue(migration_required)

    def test_nonempty_database_without_schema_metadata_raises(self) -> None:
        """A nonempty unknown database is not treated as a harmless empty file."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "annotations.json").write_text("{}", encoding="utf-8")
            database_path = project_file_path(folder, sql_backend.DATABASE_FILENAME)
            database_path.parent.mkdir(parents=True)
            connection = sqlite3.connect(database_path)
            try:
                connection.execute("CREATE TABLE legacy_table(value INTEGER)")
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(sqlite3.OperationalError, "schema_metadata"):
                sql_backend.json_migration_required(folder, [])

    def test_database_below_supported_schema_version_is_not_candidate(self) -> None:
        """Known older Teacup schemas are left for normal schema handling."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "annotations.json").write_text("{}", encoding="utf-8")
            database_path = project_file_path(folder, sql_backend.DATABASE_FILENAME)
            database_path.parent.mkdir(parents=True)
            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE schema_metadata(
                        schema_key TEXT PRIMARY KEY,
                        schema_value TEXT NOT NULL,
                        schema_updated_time INTEGER NOT NULL
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO schema_metadata VALUES('schema_version', '1.9.3', 1)"
                )
                connection.commit()
            finally:
                connection.close()

            migration_required = sql_backend.json_migration_required(folder, [])

        self.assertFalse(migration_required)

    def test_database_above_supported_schema_is_not_migration_candidate(self) -> None:
        """CODEX: BUG-2026-10-05-FUTURE-SCHEMA-ACCEPTANCE.

        CODEX: JSON backup discovery must not initialize a database created by
        CODEX: a newer Teacup schema, even when it has no project-image rows.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "annotations.json").write_text("{}", encoding="utf-8")
            database_path = project_file_path(folder, sql_backend.DATABASE_FILENAME)
            database_path.parent.mkdir(parents=True)
            connection = sqlite3.connect(database_path)
            try:
                sql_backend.ensure_schema(connection)
                connection.execute(
                    "UPDATE schema_metadata SET schema_value = '1.9.5' "
                    "WHERE schema_key = 'schema_version'"
                )
                connection.commit()
            finally:
                connection.close()

            migration_required = sql_backend.json_migration_required(folder, [])
            connection = sqlite3.connect(database_path)
            try:
                schema_version = connection.execute(
                    "SELECT schema_value FROM schema_metadata "
                    "WHERE schema_key = 'schema_version'"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertFalse(migration_required)
        self.assertEqual(schema_version, "1.9.5")

    def test_malformed_schema_version_raises(self) -> None:
        """Bad version metadata raises at the explicit comparison boundary."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "annotations.json").write_text("{}", encoding="utf-8")
            database_path = project_file_path(folder, sql_backend.DATABASE_FILENAME)
            database_path.parent.mkdir(parents=True)
            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE schema_metadata(
                        schema_key TEXT PRIMARY KEY,
                        schema_value TEXT NOT NULL,
                        schema_updated_time INTEGER NOT NULL
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO schema_metadata VALUES('schema_version', 'bad', 1)"
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaises(ValueError):
                sql_backend.json_migration_required(folder, [])


if __name__ == "__main__":
    unittest.main()
