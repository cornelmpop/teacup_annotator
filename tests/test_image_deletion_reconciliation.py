"""Tests for deterministic image deletion and manual restoration."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import annotator.sqlite as sql_backend
from annotator.log.audit import move_image_to_trash
from annotator.log.audit import remove_moved_image_sidecars


def deletion_state(
    connection: sqlite3.Connection,
    image_name: str,
) -> tuple[int, int]:
    """Return the authoritative marked and moved flags for one image."""

    row = connection.execute(
        """
        SELECT marked_for_deletion, moved_to_trash
        FROM project_images
        WHERE image_name = ?
        """,
        (image_name,),
    ).fetchone()
    return int(row["marked_for_deletion"]), int(row["moved_to_trash"])


class ImageDeletionReconciliationTests(unittest.TestCase):
    """Filesystem and SQLite state converge after deletion interruptions."""

    def test_move_deletes_sidecar_and_preserves_exact_image_name(self) -> None:
        """Only the authoritative image enters trash under its original name."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            sidecar_path = folder / "teacup" / "pi_json" / "image.jpg.json"
            Image.new("RGB", (10, 10), "white").save(image_path)
            sidecar_path.parent.mkdir(parents=True)
            sidecar_path.write_text("{}", encoding="utf-8")

            trash_path = move_image_to_trash(folder, image_path.name)

            trash_folder = folder / "teacup" / "trash"
            self.assertEqual(trash_path, trash_folder / image_path.name)
            self.assertTrue(trash_path.is_file())
            self.assertFalse(image_path.exists())
            self.assertFalse(sidecar_path.exists())
            self.assertFalse((trash_folder / sidecar_path.name).exists())

    def test_trash_collision_stops_before_sidecar_deletion(self) -> None:
        """An existing exact target is never overwritten or collision-renamed."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            trash_folder = folder / "teacup" / "trash"
            trash_folder.mkdir(parents=True)
            image_path = folder / "image.jpg"
            sidecar_path = folder / "teacup" / "pi_json" / "image.jpg.json"
            target_path = trash_folder / image_path.name
            Image.new("RGB", (10, 10), "white").save(image_path)
            sidecar_path.parent.mkdir()
            sidecar_path.write_text("{}", encoding="utf-8")
            target_path.write_bytes(b"existing")

            with self.assertRaisesRegex(
                FileExistsError,
                "restore, rename, or remove",
            ):
                move_image_to_trash(folder, image_path.name)

            self.assertTrue(image_path.is_file())
            self.assertTrue(sidecar_path.is_file())
            self.assertEqual(target_path.read_bytes(), b"existing")

    def test_image_move_error_leaves_authoritative_source_and_pending_sql(self) -> None:
        """A failed image move may discard only its regenerable JSON backup."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            sidecar_path = folder / "teacup" / "pi_json" / "image.jpg.json"
            Image.new("RGB", (10, 10), "white").save(image_path)
            sidecar_path.parent.mkdir(parents=True)
            sidecar_path.write_text("{}", encoding="utf-8")

            with mock.patch(
                "annotator.log.audit.shutil.move",
                side_effect=OSError("move failed"),
            ):
                with self.assertRaisesRegex(OSError, "move failed"):
                    move_image_to_trash(folder, image_path.name)

            self.assertTrue(image_path.is_file())
            self.assertFalse(sidecar_path.exists())

    def test_reconcile_finalizes_image_already_at_exact_trash_target(self) -> None:
        """Known-bug regression trash_source_reconciliation_missing_audit_events_2026-08-26."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (10, 10), "white").save(image_path)
            _document, connection = sql_backend.load_or_import_document(
                folder,
                [image_path],
            )
            sql_backend.persist_image_deletion_state(
                connection,
                {image_path.name},
                marked_for_deletion=True,
                moved_to_trash=False,
            )
            trash_folder = folder / "teacup" / "trash"
            trash_folder.mkdir()
            image_path.replace(trash_folder / image_path.name)

            completed, restored = sql_backend.reconcile_image_deletions(
                connection,
                folder,
            )

            self.assertEqual(completed, {image_path.name})
            self.assertEqual(restored, set())
            self.assertEqual(deletion_state(connection, image_path.name), (0, 1))
            events = sql_backend.read_audit_events(connection)
            event = events[-1]
            details = json.loads(event["details_json"])
            before_state = json.loads(event["before_state_json"])
            after_state = json.loads(event["after_state_json"])

            self.assertEqual(event["action"], "reconcile_image_deletion_state")
            self.assertEqual(details["completed_image_names"], [image_path.name])
            self.assertEqual(details["restored_image_names"], [])
            self.assertEqual(
                before_state,
                {
                    "images": [
                        {
                            "image_name": image_path.name,
                            "marked_for_deletion": True,
                            "moved_to_trash": False,
                        }
                    ]
                },
            )
            self.assertEqual(
                after_state,
                {
                    "images": [
                        {
                            "image_name": image_path.name,
                            "marked_for_deletion": False,
                            "moved_to_trash": True,
                        }
                    ]
                },
            )
            connection.close()

    def test_reconcile_recognizes_manual_restore_and_backup_save(self) -> None:
        """Known-bug regression trash_source_reconciliation_missing_audit_events_2026-08-26."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (10, 10), "white").save(image_path)
            _document, connection = sql_backend.load_or_import_document(
                folder,
                [image_path],
            )
            sql_backend.persist_image_deletion_state(
                connection,
                {image_path.name},
                marked_for_deletion=False,
                moved_to_trash=True,
            )
            trash_folder = folder / "teacup" / "trash"
            trash_folder.mkdir()
            trash_path = trash_folder / image_path.name
            image_path.replace(trash_path)
            trash_path.replace(image_path)

            completed, restored = sql_backend.reconcile_image_deletions(
                connection,
                folder,
            )
            sql_backend.save_json_backups_from_database(
                connection,
                folder,
                [image_path],
            )

            self.assertEqual(completed, set())
            self.assertEqual(restored, {image_path.name})
            self.assertEqual(deletion_state(connection, image_path.name), (0, 0))
            self.assertTrue(
                (folder / "teacup" / "pi_json" / "image.jpg.json").is_file()
            )
            events = sql_backend.read_audit_events(connection)
            event = events[-1]
            details = json.loads(event["details_json"])
            before_state = json.loads(event["before_state_json"])
            after_state = json.loads(event["after_state_json"])

            self.assertEqual(event["action"], "reconcile_image_deletion_state")
            self.assertEqual(details["completed_image_names"], [])
            self.assertEqual(details["restored_image_names"], [image_path.name])
            self.assertEqual(
                before_state,
                {
                    "images": [
                        {
                            "image_name": image_path.name,
                            "marked_for_deletion": False,
                            "moved_to_trash": True,
                        }
                    ]
                },
            )
            self.assertEqual(
                after_state,
                {
                    "images": [
                        {
                            "image_name": image_path.name,
                            "marked_for_deletion": False,
                            "moved_to_trash": False,
                        }
                    ]
                },
            )
            connection.close()

    def test_reconcile_rolls_back_flag_changes_when_audit_fails(self) -> None:
        """Known-bug regression trash_source_reconciliation_missing_audit_events_2026-08-26."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (10, 10), "white").save(image_path)
            _document, connection = sql_backend.load_or_import_document(
                folder,
                [image_path],
            )
            sql_backend.persist_image_deletion_state(
                connection,
                {image_path.name},
                marked_for_deletion=True,
                moved_to_trash=False,
            )
            trash_folder = folder / "teacup" / "trash"
            trash_folder.mkdir()
            image_path.replace(trash_folder / image_path.name)

            with mock.patch(
                "annotator.sqlite.deletion.append_audit_event",
                side_effect=sqlite3.IntegrityError("audit failed"),
            ):
                with self.assertRaisesRegex(sqlite3.IntegrityError, "audit failed"):
                    sql_backend.reconcile_image_deletions(connection, folder)

            self.assertEqual(deletion_state(connection, image_path.name), (1, 0))
            self.assertEqual(sql_backend.read_audit_events(connection), [])
            self.assertFalse(connection.in_transaction)
            connection.close()

    def test_reconcile_rejects_ambiguous_pending_paths(self) -> None:
        """Pending deletion never guesses when source and target both exist."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (10, 10), "white").save(image_path)
            _document, connection = sql_backend.load_or_import_document(
                folder,
                [image_path],
            )
            sql_backend.persist_image_deletion_state(
                connection,
                {image_path.name},
                marked_for_deletion=True,
                moved_to_trash=False,
            )
            trash_folder = folder / "teacup" / "trash"
            trash_folder.mkdir()
            Image.new("RGB", (10, 10), "black").save(trash_folder / image_path.name)

            with self.assertRaisesRegex(FileExistsError, "Both"):
                sql_backend.reconcile_image_deletions(connection, folder)

            self.assertEqual(deletion_state(connection, image_path.name), (1, 0))
            connection.close()

    def test_reconcile_rejects_missing_pending_source_and_target(self) -> None:
        """A pending image absent from both locations is reported, not completed."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (10, 10), "white").save(image_path)
            _document, connection = sql_backend.load_or_import_document(
                folder,
                [image_path],
            )
            sql_backend.persist_image_deletion_state(
                connection,
                {image_path.name},
                marked_for_deletion=True,
                moved_to_trash=False,
            )
            image_path.unlink()

            with self.assertRaisesRegex(FileNotFoundError, "Neither"):
                sql_backend.reconcile_image_deletions(connection, folder)

            self.assertEqual(deletion_state(connection, image_path.name), (1, 0))
            connection.close()

    def test_reconcile_validates_all_paths_before_updating_sqlite(self) -> None:
        """A later conflict leaves earlier reconcilable rows and SQL untouched."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            restored_path = folder / "a.jpg"
            conflicting_path = folder / "b.jpg"
            for image_path in (restored_path, conflicting_path):
                Image.new("RGB", (10, 10), "white").save(image_path)
            _document, connection = sql_backend.load_or_import_document(
                folder,
                [restored_path, conflicting_path],
            )
            sql_backend.persist_image_deletion_state(
                connection,
                {restored_path.name},
                marked_for_deletion=False,
                moved_to_trash=True,
            )
            sql_backend.persist_image_deletion_state(
                connection,
                {conflicting_path.name},
                marked_for_deletion=True,
                moved_to_trash=False,
            )
            trash_folder = folder / "teacup" / "trash"
            trash_folder.mkdir()
            Image.new("RGB", (10, 10), "black").save(
                trash_folder / conflicting_path.name
            )

            with self.assertRaisesRegex(FileExistsError, "Both"):
                sql_backend.reconcile_image_deletions(connection, folder)

            self.assertEqual(deletion_state(connection, restored_path.name), (0, 1))
            self.assertEqual(deletion_state(connection, conflicting_path.name), (1, 0))
            self.assertFalse(connection.in_transaction)
            connection.close()

    def test_preload_reconcile_handles_last_image_already_in_trash(self) -> None:
        """Recovery can finish before an empty source folder is rejected."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (10, 10), "white").save(image_path)
            _document, connection = sql_backend.load_or_import_document(
                folder,
                [image_path],
            )
            sql_backend.persist_image_deletion_state(
                connection,
                {image_path.name},
                marked_for_deletion=True,
                moved_to_trash=False,
            )
            trash_folder = folder / "teacup" / "trash"
            trash_folder.mkdir()
            image_path.replace(trash_folder / image_path.name)
            connection.close()

            completed, restored = sql_backend.reconcile_folder_image_deletions(folder)
            reopened = sql_backend.connect_database(folder)

            self.assertEqual(completed, {image_path.name})
            self.assertEqual(restored, set())
            self.assertEqual(deletion_state(reopened, image_path.name), (0, 1))
            reopened.close()

    def test_cleanup_removes_only_sqlite_known_moved_sidecars(self) -> None:
        """Unrelated apparent orphans remain available as recovery material."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            sidecar_folder = folder / "teacup" / "pi_json"
            sidecar_folder.mkdir(parents=True)
            known_sidecar = sidecar_folder / "known.jpg.json"
            unknown_sidecar = sidecar_folder / "unknown.jpg.json"
            known_sidecar.write_text("known", encoding="utf-8")
            unknown_sidecar.write_text("unknown", encoding="utf-8")

            removed = remove_moved_image_sidecars(folder, {"known.jpg"})

            self.assertEqual(removed, {known_sidecar})
            self.assertFalse(known_sidecar.exists())
            self.assertTrue(unknown_sidecar.is_file())


if __name__ == "__main__":
    unittest.main()
