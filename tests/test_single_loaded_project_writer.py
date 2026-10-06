"""Regression coverage for exclusive ownership of a loaded SQLite project."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import annotator.sqlite as sql_backend


class SingleLoadedProjectWriterTests(unittest.TestCase):
    """A loaded document prevents a second stale writable projection."""

    def test_loaded_project_rejects_second_writer_and_preserves_owner_saves(
        self,
    ) -> None:
        """Known-bug regression BUG-2026-09-29-STALE-WRITER-DATA-LOSS."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "a.jpg"
            Image.new("RGB", (20, 10), "white").save(image_path)
            real_connect = sqlite3.connect

            def connect_without_lock_wait(
                *args: object,
                **kwargs: object,
            ) -> sqlite3.Connection:
                """Use the production connection path with a short test timeout."""

                kwargs["timeout"] = 0.01
                return real_connect(*args, **kwargs)

            with mock.patch(
                "annotator.sqlite.connect.sqlite3.connect",
                side_effect=connect_without_lock_wait,
            ):
                document_a, connection_a = sql_backend.load_or_import_document(
                    folder,
                    [image_path],
                )
                connection_b: sqlite3.Connection | None = None
                try:
                    document_a.add_annotation(
                        "a.jpg",
                        [(1, 1), (5, 1), (5, 4), (1, 4)],
                    )
                    sql_backend.persist_image(
                        connection_a,
                        document_a,
                        "a.jpg",
                        write_json_backup=False,
                    )

                    with self.assertRaisesRegex(
                        sqlite3.OperationalError,
                        "database is locked",
                    ):
                        _document_b, connection_b = (
                            sql_backend.load_or_import_document(
                                folder,
                                [image_path],
                            )
                        )

                    document_a.add_annotation(
                        "a.jpg",
                        [(7, 1), (11, 1), (11, 4), (7, 4)],
                    )
                    sql_backend.persist_image(
                        connection_a,
                        document_a,
                        "a.jpg",
                        write_json_backup=False,
                    )
                finally:
                    if connection_b is not None:
                        connection_b.close()
                    connection_a.close()

                document_c, connection_c = sql_backend.load_or_import_document(
                    folder,
                    [image_path],
                )
                try:
                    polygons = [
                        annotation.polygons[0]
                        for annotation in document_c.annotations_for("a.jpg")
                    ]
                finally:
                    connection_c.close()

        self.assertEqual(
            polygons,
            [
                [(1.0, 1.0), (5.0, 1.0), (5.0, 4.0), (1.0, 4.0)],
                [(7.0, 1.0), (11.0, 1.0), (11.0, 4.0), (7.0, 4.0)],
            ],
        )


if __name__ == "__main__":
    unittest.main()
