"""Tests for explicitly marking the current image for deletion."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests.support import StatefulHost
from annotator.gui.project.deletion import mark_current_image_for_deletion
from annotator.gui.project.deletion import restore_current_image_from_trash


def deletion_mark_host() -> StatefulHost:
    """Return a state owner with the effects required to mark one image."""

    host = StatefulHost()
    host.project.folder = Path("/images")
    host.project.image_paths = [Path("/images/a.jpg")]
    host.project.current_index = 0
    host.project.sql_connection = mock.Mock()
    host.log = mock.Mock()
    return host


class MarkImageForDeletionTests(unittest.TestCase):
    """Deletion marking keeps SQLite, backup, audit, and UI state aligned."""

    def test_mark_current_image_persists_state_and_audit(self) -> None:
        """A successful mark updates authoritative and in-memory state."""

        host = deletion_mark_host()
        with (
            mock.patch(
                "annotator.gui.project.deletion."
                "sql_backend.persist_image_deletion_state"
            ) as persist,
            mock.patch(
                "annotator.gui.project.deletion.save_deletion_marks"
            ) as save_backup,
            mock.patch(
                "annotator.gui.project.deletion.update_image_status"
            ) as update_status,
            mock.patch(
                "annotator.gui.project.deletion.update_buttons"
            ) as update_buttons,
            mock.patch(
                "annotator.gui.project.deletion.write_audit_event"
            ) as write_audit,
        ):
            mark_current_image_for_deletion(host)

        persist.assert_called_once_with(
            host.project.sql_connection,
            {"a.jpg"},
            marked_for_deletion=True,
            moved_to_trash=False,
        )
        self.assertEqual(host.project.deletion_marks, {"a.jpg"})
        self.assertEqual(host.project.session_deletion_marks, {"a.jpg"})
        save_backup.assert_called_once_with(
            host.project.folder,
            {"a.jpg"},
        )
        write_audit.assert_called_once_with(
            host,
            action="mark_image_for_deletion",
            before_state=None,
            after_state={
                "image_name": "a.jpg",
                "marked_for_deletion": True,
                "source_table": "project_images",
            },
            details={"image_name": "a.jpg", "image_index": 0},
            source_table="project_images",
        )
        update_status.assert_called_once_with(host)
        update_buttons.assert_called_once_with(host)

    def test_sqlite_failure_stops_before_in_memory_mark(self) -> None:
        """A failed authoritative write reports the error without divergence."""

        host = deletion_mark_host()
        with (
            mock.patch(
                "annotator.gui.project.deletion."
                "sql_backend.persist_image_deletion_state",
                side_effect=sqlite3.OperationalError("read only"),
            ),
            mock.patch(
                "annotator.gui.project.deletion.messagebox.showerror"
            ) as showerror,
            mock.patch(
                "annotator.gui.project.deletion.write_audit_event"
            ) as write_audit,
            mock.patch(
                "annotator.gui.project.deletion.update_buttons"
            ) as update_buttons,
        ):
            mark_current_image_for_deletion(host)

        self.assertEqual(host.project.deletion_marks, set())
        self.assertEqual(host.project.session_deletion_marks, set())
        showerror.assert_called_once_with(
            "Could not mark image",
            "read only",
        )
        write_audit.assert_not_called()
        update_buttons.assert_not_called()

    def test_backup_failure_warns_after_authoritative_mark(self) -> None:
        """A regenerable deletion backup failure does not undo SQLite state."""

        host = deletion_mark_host()
        with (
            mock.patch(
                "annotator.gui.project.deletion."
                "sql_backend.persist_image_deletion_state"
            ),
            mock.patch(
                "annotator.gui.project.deletion.save_deletion_marks",
                side_effect=OSError("backup read only"),
            ),
            mock.patch(
                "annotator.gui.project.deletion.messagebox.showwarning"
            ) as showwarning,
            mock.patch("annotator.gui.project.deletion.update_image_status"),
            mock.patch("annotator.gui.project.deletion.update_buttons"),
            mock.patch(
                "annotator.gui.project.deletion.write_audit_event"
            ) as write_audit,
        ):
            mark_current_image_for_deletion(host)

        self.assertEqual(host.project.deletion_marks, {"a.jpg"})
        self.assertIn("backup read only", showwarning.call_args.args[1])
        write_audit.assert_called_once()

    def test_restore_current_image_clears_pending_deletion_state(self) -> None:
        """Known-bug regression restore_marked_image_button_clears_stale_deletion_2026-08-26."""

        host = deletion_mark_host()
        host.project.deletion_marks = {"a.jpg"}
        host.project.session_deletion_marks = {"a.jpg"}
        with (
            mock.patch(
                "annotator.gui.project.deletion."
                "sql_backend.persist_image_deletion_state"
            ) as persist,
            mock.patch(
                "annotator.gui.project.deletion.save_deletion_marks"
            ) as save_backup,
            mock.patch(
                "annotator.gui.project.deletion.update_image_status"
            ) as update_status,
            mock.patch(
                "annotator.gui.project.deletion.update_buttons"
            ) as update_buttons,
            mock.patch(
                "annotator.gui.project.deletion.write_audit_event"
            ) as write_audit,
        ):
            restore_current_image_from_trash(host)

        persist.assert_called_once_with(
            host.project.sql_connection,
            {"a.jpg"},
            marked_for_deletion=False,
            moved_to_trash=False,
        )
        self.assertEqual(host.project.deletion_marks, set())
        self.assertEqual(host.project.session_deletion_marks, set())
        save_backup.assert_called_once_with(
            host.project.folder,
            set(),
        )
        write_audit.assert_called_once_with(
            host,
            action="restore_image_from_trash",
            before_state={
                "image_name": "a.jpg",
                "marked_for_deletion": True,
                "moved_to_trash": False,
                "source_table": "project_images",
            },
            after_state={
                "image_name": "a.jpg",
                "marked_for_deletion": False,
                "moved_to_trash": False,
                "source_table": "project_images",
            },
            details={"image_name": "a.jpg", "image_index": 0},
            source_table="project_images",
        )
        update_status.assert_called_once_with(host)
        update_buttons.assert_called_once_with(host)


if __name__ == "__main__":
    unittest.main()
