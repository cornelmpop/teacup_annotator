"""Tests for SQLite schema-version enforcement."""

from __future__ import annotations

import sqlite3
import unittest

import annotator.sqlite as sql_backend
from annotator.sqlite.schema import _schema_version_key


class EnsureSchemaVersionTests(unittest.TestCase):
    """Schema preparation rejects unsupported nonempty databases."""

    def test_new_database_records_independent_schema_and_app_versions(self) -> None:
        """CODEX: Keep schema 1.9.4 independent from app release 0.9.8."""

        connection = sqlite3.connect(":memory:")
        try:
            sql_backend.ensure_schema(connection)
            schema_version = connection.execute(
                "SELECT schema_value FROM schema_metadata "
                "WHERE schema_key = 'schema_version'"
            ).fetchone()[0]
            implementation_versions = connection.execute(
                "SELECT to_schema_version, app_version "
                "FROM schema_implementations "
                "ORDER BY schema_implementation_id LIMIT 1"
            ).fetchone()
        finally:
            connection.close()

        self.assertEqual(schema_version, "1.9.4")
        self.assertEqual(implementation_versions, ("1.9.4", "0.9.8"))

    def test_nonempty_database_without_schema_metadata_raises(self) -> None:
        """Unknown nonempty databases fail before Teacup creates new tables."""

        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("CREATE TABLE legacy_table(value INTEGER)")

            with self.assertRaisesRegex(sqlite3.OperationalError, "schema_metadata"):
                sql_backend.ensure_schema(connection)
        finally:
            connection.close()

    def test_below_supported_schema_version_raises_database_error(self) -> None:
        """Known older schema versions are not silently accepted."""

        connection = sqlite3.connect(":memory:")
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

            with self.assertRaisesRegex(
                sqlite3.DatabaseError,
                "Unsupported Teacup SQLite schema version 1.9.3",
            ):
                sql_backend.ensure_schema(connection)
        finally:
            connection.close()

    def test_above_supported_schema_version_raises_before_writes(self) -> None:
        """CODEX: BUG-2026-10-05-FUTURE-SCHEMA-ACCEPTANCE.

        CODEX: A project created by a newer schema must be rejected before
        CODEX: schema preparation writes app-owned rows or readiness state.
        """

        connection = sqlite3.connect(":memory:")
        try:
            sql_backend.ensure_schema(connection)
            connection.execute("DROP TABLE annotator_schema_ready")
            connection.execute(
                "UPDATE schema_metadata SET schema_value = '1.9.5' "
                "WHERE schema_key = 'schema_version'"
            )
            connection.commit()
            changes_before_check = connection.total_changes

            with self.assertRaisesRegex(
                sqlite3.DatabaseError,
                "Unsupported Teacup SQLite schema version 1.9.5; "
                "supported version is 1.9.4",
            ):
                sql_backend.ensure_schema(connection)

            self.assertEqual(connection.total_changes, changes_before_check)
        finally:
            connection.close()

    def test_malformed_schema_version_raises(self) -> None:
        """Bad version metadata raises at the explicit comparison boundary."""

        connection = sqlite3.connect(":memory:")
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

            with self.assertRaises(ValueError):
                sql_backend.ensure_schema(connection)
        finally:
            connection.close()

    def test_schema_version_key_compares_numeric_parts(self) -> None:
        """Version comparison treats 1.10 as newer than 1.9."""

        current_key = _schema_version_key("1.10.0")
        older_key = _schema_version_key("1.9.4")

        self.assertGreater(current_key, older_key)


if __name__ == "__main__":
    unittest.main()
