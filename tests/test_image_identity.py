"""Tests for Teacup project image content identity."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import annotator.sqlite as sql_backend
from annotator.archive import create_archive
from annotator.arrows import Arrow
from annotator.coco import CocoDocument
from annotator.project.saving import ProjectSaveRequest
from annotator.project.saving import save_project


class ImageIdentityTests(unittest.TestCase):
    """Image MD5s bind annotations and arrows to source image bytes."""

    def test_image_md5sum_streams_known_digest(self) -> None:
        """The helper returns the precomputed MD5 for a known byte sequence."""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "payload.bin"
            path.write_bytes(b"abc")

            digest = sql_backend.image_md5sum(path)

        self.assertEqual(digest, "900150983cd24fb0d6963f7d28e17f72")

    def test_project_image_rows_store_md5_in_database_and_coco_export(self) -> None:
        """SQLite rows and generated COCO exports expose the source-image digest."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "sample.jpg"
            Image.new("RGB", (10, 10), "white").save(image_path)
            document = CocoDocument(folder, [image_path])
            connection = sql_backend.connect_database(folder)
            try:
                sql_backend.persist_document(
                    connection,
                    document,
                    write_json_backups=False,
                )
                expected_md5sum = sql_backend.image_md5sum(image_path)
                row = connection.execute(
                    """
                    SELECT image_md5sum
                    FROM project_images
                    WHERE image_name = ?
                    """,
                    (image_path.name,),
                ).fetchone()
                exported = sql_backend.document_from_database(
                    connection,
                    folder,
                    [image_path],
                ).to_payload()
            finally:
                connection.close()

        self.assertEqual(row["image_md5sum"], expected_md5sum)
        self.assertEqual(exported["images"][0]["image_md5sum"], expected_md5sum)

    def test_load_rejects_copied_database_with_same_filename_different_bytes(
        self,
    ) -> None:
        """A stale folder database cannot attach annotations to new image bytes."""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_folder = root / "source"
            target_folder = root / "target"
            source_folder.mkdir()
            target_folder.mkdir()
            source_image = source_folder / "same.jpg"
            target_image = target_folder / "same.jpg"
            Image.new("RGB", (20, 20), "red").save(source_image)
            Image.new("RGB", (20, 20), "blue").save(target_image)

            document = CocoDocument(source_folder, [source_image])
            document.add_annotation("same.jpg", [(1, 1), (8, 1), (8, 8), (1, 8)])
            connection = sql_backend.connect_database(source_folder)
            try:
                sql_backend.persist_document(
                    connection,
                    document,
                    write_json_backups=False,
                )
                sql_backend.persist_arrows(
                    connection,
                    {"same.jpg": [Arrow("arr:source", 1, 2, 3, 4)]},
                )
            finally:
                connection.close()

            (target_folder / "teacup").mkdir()
            shutil.copy2(
                source_folder / "teacup" / sql_backend.DATABASE_FILENAME,
                target_folder / "teacup" / sql_backend.DATABASE_FILENAME,
            )

            with self.assertRaisesRegex(ValueError, "Image content mismatch"):
                sql_backend.load_or_import_document(target_folder, [target_image])

    def test_persist_arrows_requires_project_image_row(self) -> None:
        """Arrow persistence rejects names absent from Teacup's image registry."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            connection = sql_backend.connect_database(folder)
            try:
                sql_backend.ensure_schema(connection)
                with self.assertRaisesRegex(ValueError, "missing.jpg"):
                    sql_backend.persist_arrows(
                        connection,
                        {"missing.jpg": [Arrow("arr:missing", 1, 2, 3, 4)]},
                    )
            finally:
                connection.close()

    def test_verification_rejects_unregistered_source_image(self) -> None:
        """Known-bug regression folder_load_reconciles_jpeg_files_with_sqlite_2026-08-26."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            registered_path = folder / "registered.jpg"
            extra_path = folder / "extra.jpg"
            Image.new("RGB", (10, 10), "white").save(registered_path)
            Image.new("RGB", (10, 10), "blue").save(extra_path)
            document = CocoDocument(folder, [registered_path])
            connection = sql_backend.connect_database(folder)
            try:
                sql_backend.persist_document(
                    connection,
                    document,
                    write_json_backups=False,
                )

                with self.assertRaisesRegex(ValueError, "extra.jpg"):
                    sql_backend.verify_project_image_hashes(
                        connection,
                        [registered_path, extra_path],
                    )
            finally:
                connection.close()

    def test_save_rejects_changed_image_bytes(self) -> None:
        """Explicit Save stops before exporting state for a replaced image."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "sample.jpg"
            Image.new("RGB", (10, 10), "white").save(image_path)
            document = CocoDocument(folder, [image_path])
            connection = sql_backend.connect_database(folder)
            try:
                sql_backend.persist_document(
                    connection,
                    document,
                    write_json_backups=False,
                )
                Image.new("RGB", (10, 10), "black").save(image_path)
                request = ProjectSaveRequest(
                    folder=folder,
                    connection=connection,
                    image_paths=[image_path],
                    project_metadata={},
                    write_json_backups=False,
                    model_configuration=None,
                    crop_padding_px=20,
                )

                with self.assertRaisesRegex(ValueError, "Image content mismatch"):
                    save_project(request, lambda: None, lambda _value, _message: None)
            finally:
                connection.close()

    def test_archive_rejects_changed_image_bytes(self) -> None:
        """Archive creation rechecks image bytes before snapshot packaging."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "images"
            folder.mkdir()
            image_path = folder / "sample.jpg"
            Image.new("RGB", (10, 10), "white").save(image_path)
            document = CocoDocument(folder, [image_path])
            connection = sql_backend.connect_database(folder)
            try:
                sql_backend.persist_document(
                    connection,
                    document,
                    write_json_backups=False,
                )
                Image.new("RGB", (10, 10), "black").save(image_path)

                with self.assertRaisesRegex(ValueError, "Image content mismatch"):
                    create_archive(
                        folder,
                        [image_path],
                        connection,
                        Path(temp_dir) / "dataset.zip",
                    )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
