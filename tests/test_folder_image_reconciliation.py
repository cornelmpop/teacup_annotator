"""Tests for load-time folder JPEG and SQLite image reconciliation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import annotator.sqlite as sql_backend
from annotator.arrows import Arrow
from annotator.coco import CocoDocument
from annotator.gui.project.folder_image_reconciliation import (
    RECONCILE_PROJECT_IMAGES_TITLE,
)
from annotator.gui.project.folder_image_reconciliation import (
    resolve_folder_image_reconciliation,
)
from annotator.coco.io import image_annotation_path
from annotator.project.discovery import ProjectDiscovery
from annotator.project.loading import ProjectLoadPlan
from tests.support import StatefulHost


def _save_image(path: Path, colour: str = "white") -> None:
    """Create one deterministic JPEG test image."""

    Image.new("RGB", (10, 12), colour).save(path)


def _create_sqlite_project(folder: Path, image_paths: list[Path]) -> None:
    """Create a SQLite-native project containing ``image_paths``."""

    document = CocoDocument(folder, image_paths)
    connection = sql_backend.connect_database(folder)
    try:
        sql_backend.persist_document(
            connection,
            document,
            write_json_backups=False,
        )
    finally:
        connection.close()


class FolderImageReconciliationTests(unittest.TestCase):
    """Folder-load reconciliation keeps root JPEGs and SQLite rows aligned."""

    def test_accepted_root_jpeg_addition_registers_image_row(self) -> None:
        """Known-bug regression folder_load_reconciles_jpeg_files_with_sqlite_2026-08-26."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            existing_path = folder / "a.jpg"
            added_path = folder / "b.jpg"
            _save_image(existing_path)
            _save_image(added_path, "blue")
            expected_added_md5sum = sql_backend.image_md5sum(added_path)
            _create_sqlite_project(folder, [existing_path])

            reconciliation = sql_backend.inspect_folder_image_reconciliation(
                folder,
                [existing_path, added_path],
            )
            sql_backend.apply_folder_image_reconciliation(reconciliation)

            connection = sql_backend.connect_database(folder)
            try:
                rows = connection.execute(
                    """
                    SELECT image_name, image_md5sum, width, height,
                           coco_image_id, moved_to_trash
                    FROM project_images
                    ORDER BY image_sequence_index, image_id
                    """
                ).fetchall()
                events = sql_backend.read_audit_events(connection)
                loaded_document = sql_backend.document_from_database(
                    connection,
                    folder,
                    [existing_path, added_path],
                )
            finally:
                connection.close()

        self.assertEqual(reconciliation.added_image_paths, (added_path,))
        self.assertEqual(reconciliation.missing_image_names, ())
        self.assertEqual([row["image_name"] for row in rows], ["a.jpg", "b.jpg"])
        self.assertEqual(rows[1]["image_md5sum"], expected_added_md5sum)
        self.assertEqual(rows[1]["width"], 10)
        self.assertEqual(rows[1]["height"], 12)
        self.assertEqual(rows[1]["coco_image_id"], 2)
        self.assertEqual(rows[1]["moved_to_trash"], 0)
        self.assertEqual([path.name for path in loaded_document.image_paths], ["a.jpg", "b.jpg"])
        self.assertEqual(events[-1]["action"], "reconcile_project_images")
        details = json.loads(events[-1]["details_json"])
        self.assertEqual(details["added_image_names"], ["b.jpg"])
        self.assertEqual(details["missing_image_names"], [])

    def test_accepted_missing_root_jpeg_records_trash_state(self) -> None:
        """Known-bug regression folder_load_reconciles_jpeg_files_with_sqlite_2026-08-26."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            active_path = folder / "a.jpg"
            missing_path = folder / "b.jpg"
            _save_image(active_path)
            _save_image(missing_path, "blue")
            document = CocoDocument(folder, [active_path, missing_path])
            document.add_annotation("b.jpg", [(1, 1), (8, 1), (8, 8), (1, 8)])
            connection = sql_backend.connect_database(folder)
            try:
                sql_backend.persist_document(
                    connection,
                    document,
                    write_json_backups=False,
                )
                sql_backend.persist_arrows(
                    connection,
                    {"b.jpg": [Arrow("arr:b", 1, 2, 3, 4)]},
                )
            finally:
                connection.close()
            missing_path.unlink()

            reconciliation = sql_backend.inspect_folder_image_reconciliation(
                folder,
                [active_path],
            )
            sql_backend.apply_folder_image_reconciliation(reconciliation)

            connection = sql_backend.connect_database(folder)
            try:
                row = connection.execute(
                    """
                    SELECT image_id, marked_for_deletion, moved_to_trash
                    FROM project_images
                    WHERE image_name = 'b.jpg'
                    """
                ).fetchone()
                annotation_count = connection.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM annotations
                    WHERE image_id = ?
                    """,
                    (row["image_id"],),
                ).fetchone()["count"]
                loaded_document, loaded_connection = sql_backend.load_or_import_document(
                    folder,
                    [active_path],
                )
                loaded_connection.close()
            finally:
                connection.close()

        self.assertEqual(reconciliation.added_image_paths, ())
        self.assertEqual(reconciliation.missing_image_names, ("b.jpg",))
        self.assertEqual(row["marked_for_deletion"], 0)
        self.assertEqual(row["moved_to_trash"], 1)
        self.assertEqual(annotation_count, 2)
        self.assertEqual([path.name for path in loaded_document.image_paths], ["a.jpg"])

    def test_same_name_md5_mismatch_remains_load_failure(self) -> None:
        """Known-bug regression folder_load_reconciles_jpeg_files_with_sqlite_2026-08-26."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "a.jpg"
            _save_image(image_path, "white")
            _create_sqlite_project(folder, [image_path])
            _save_image(image_path, "black")

            with self.assertRaisesRegex(ValueError, "Image content mismatch"):
                sql_backend.inspect_folder_image_reconciliation(folder, [image_path])

    def test_non_jpeg_files_do_not_trigger_reconciliation(self) -> None:
        """Known-bug regression folder_load_reconciles_jpeg_files_with_sqlite_2026-08-26."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "a.jpg"
            _save_image(image_path)
            _create_sqlite_project(folder, [image_path])
            (folder / "notes.json").write_text("{}", encoding="utf-8")

            reconciliation = sql_backend.inspect_folder_image_reconciliation(
                folder,
                [image_path],
            )

        self.assertFalse(reconciliation.has_changes())

    def test_projection_rejects_unregistered_discovered_jpeg(self) -> None:
        """Known-bug regression folder_load_reconciles_jpeg_files_with_sqlite_2026-08-26."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            registered_path = folder / "a.jpg"
            extra_path = folder / "b.jpg"
            _save_image(registered_path)
            _save_image(extra_path, "blue")
            _create_sqlite_project(folder, [registered_path])
            connection = sql_backend.connect_database(folder)
            try:
                with self.assertRaisesRegex(ValueError, "b.jpg"):
                    sql_backend.document_from_database(
                        connection,
                        folder,
                        [registered_path, extra_path],
                    )
            finally:
                connection.close()

    def test_rejecting_reconciliation_cancels_before_sql_apply(self) -> None:
        """Known-bug regression folder_load_reconciles_jpeg_files_with_sqlite_2026-08-26."""

        folder = Path("/project")
        image_path = folder / "a.jpg"
        reconciliation = sql_backend.FolderImageReconciliation(
            folder=folder,
            image_paths=(image_path,),
            added_image_paths=(image_path,),
            missing_image_names=("missing.jpg",),
        )
        load_plan = ProjectLoadPlan(
            discovery=ProjectDiscovery(folder, [image_path]),
            project_metadata={},
            migration_required=False,
            native_project_established=True,
        )
        host = StatefulHost()
        host.prefs = mock.Mock()
        host.root = mock.Mock()
        host.session_default_class_var = mock.Mock()
        host.log = mock.Mock()

        with (
            mock.patch(
                "annotator.gui.project.folder_image_reconciliation."
                "sql_backend.inspect_folder_image_reconciliation",
                return_value=reconciliation,
            ),
            mock.patch(
                "annotator.gui.project.folder_image_reconciliation."
                "sql_backend.apply_folder_image_reconciliation",
            ) as apply_reconciliation,
            mock.patch(
                "annotator.gui.project.folder_image_reconciliation."
                "messagebox.askyesno",
                return_value=False,
            ) as askyesno,
        ):
            result = resolve_folder_image_reconciliation(host, load_plan)

        self.assertIsNone(result)
        apply_reconciliation.assert_not_called()
        askyesno.assert_called_once()
        self.assertEqual(askyesno.call_args.args[0], RECONCILE_PROJECT_IMAGES_TITLE)
        self.assertIn("JSON and other non-JPEG files are ignored", askyesno.call_args.args[1])
        host.log.assert_called_once_with(
            "Folder load cancelled: project images were not reconciled"
        )

    def test_accepting_reconciliation_removes_missing_image_backup(self) -> None:
        """Known-bug regression folder_load_reconciles_jpeg_files_with_sqlite_2026-08-26."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "a.jpg"
            _save_image(image_path)
            sidecar_path = image_annotation_path(folder, "missing.jpg")
            sidecar_path.parent.mkdir(parents=True)
            sidecar_path.write_text("{}", encoding="utf-8")
            reconciliation = sql_backend.FolderImageReconciliation(
                folder=folder,
                image_paths=(image_path,),
                added_image_paths=(),
                missing_image_names=("missing.jpg",),
            )
            load_plan = ProjectLoadPlan(
                discovery=ProjectDiscovery(folder, [image_path]),
                project_metadata={},
                migration_required=False,
                native_project_established=True,
            )
            host = StatefulHost()
            host.prefs = mock.Mock()
            host.root = mock.Mock()
            host.session_default_class_var = mock.Mock()
            host.log = mock.Mock()

            with (
                mock.patch(
                    "annotator.gui.project.folder_image_reconciliation."
                    "sql_backend.inspect_folder_image_reconciliation",
                    return_value=reconciliation,
                ),
                mock.patch(
                    "annotator.gui.project.folder_image_reconciliation."
                    "sql_backend.apply_folder_image_reconciliation",
                ) as apply_reconciliation,
                mock.patch(
                    "annotator.gui.project.folder_image_reconciliation."
                    "messagebox.askyesno",
                    return_value=True,
                ),
            ):
                result = resolve_folder_image_reconciliation(host, load_plan)

            self.assertTrue(result)
            apply_reconciliation.assert_called_once_with(reconciliation)
            self.assertFalse(sidecar_path.exists())


if __name__ == "__main__":
    unittest.main()
