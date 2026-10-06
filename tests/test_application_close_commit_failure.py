"""Regression tests for recoverable application-close commit failures."""

from types import SimpleNamespace
import sqlite3
import unittest
from unittest import mock

from annotator.gui.application import close_application
from annotator.gui.application import close_sql_connection
from annotator.log.audit import CLOSE_AUDIT_ACTION


class ApplicationCloseCommitFailureTests(unittest.TestCase):
    """The close boundary preserves a usable project after commit failure."""

    def test_commit_failure_rolls_back_and_allows_close_retry(self) -> None:
        """BUG-2026-10-04-APPLICATION-CLOSE-COMMIT-FAILURE: retry close."""

        connection = sqlite3.connect(":memory:")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE child ("
            "parent_id INTEGER REFERENCES parent(id) "
            "DEFERRABLE INITIALLY DEFERRED)"
        )
        connection.execute("BEGIN")
        connection.execute("INSERT INTO child VALUES (99)")
        host = SimpleNamespace(
            project=SimpleNamespace(
                sql_connection=connection,
                coco=None,
                image_paths=[],
                folder=None,
            ),
            root=mock.Mock(),
        )
        host.close_sql_connection = lambda: close_sql_connection(host)
        close_event = {
            "audit_event_id": 17,
            "action": CLOSE_AUDIT_ACTION,
        }

        with (
            mock.patch(
                "annotator.gui.application.record_application_close",
                return_value=close_event,
            ),
            mock.patch(
                "annotator.gui.application.write_current_session_statistics"
            ),
            mock.patch(
                "annotator.gui.application.finalize_committed_audit_events"
            ) as finalize_events,
            mock.patch(
                "annotator.gui.application.messagebox.showerror"
            ) as showerror,
        ):
            close_application(host)

            showerror.assert_called_once_with(
                "Could not save before closing",
                "FOREIGN KEY constraint failed",
            )
            self.assertIs(host.project.sql_connection, connection)
            self.assertFalse(connection.in_transaction)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM child").fetchone(),
                (0,),
            )
            finalize_events.assert_not_called()
            host.root.destroy.assert_not_called()

            close_application(host)

        self.assertIsNone(host.project.sql_connection)
        finalize_events.assert_called_once_with(host, [close_event])
        host.root.destroy.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
