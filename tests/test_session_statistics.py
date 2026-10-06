"""Tests for per-session edit timing summary CSVs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import annotator.sqlite as sql_backend
from annotator.gui.session_statistics import SESSION_STATISTICS_REFRESH_MS
from annotator.gui.session_statistics import refresh_session_statistics
from annotator.gui.session_statistics import write_current_session_statistics
from annotator.log.session_statistics import write_session_statistics_csv
from tests.support import StatefulHost


def append_timed_event(
    connection: sqlite3.Connection,
    session_id: str,
    action: str,
    duration_ms: int | None,
    annotation_type: str | None = None,
) -> None:
    """Append one audit event row with an explicit session and duration."""

    sql_backend.append_audit_event(
        connection,
        {
            "session_id": session_id,
            "action": action,
            "duration_ms": duration_ms,
            "event_time": 1,
            "details_json": json.dumps(
                {"annotation_type": annotation_type}
                if annotation_type is not None
                else {}
            ),
        },
    )


def append_shell_component(
    connection: sqlite3.Connection,
    session_id: str,
    event_time: int,
    duration_ms: int,
    annotation_uuid: str,
    polygon: list[tuple[float, float]],
) -> None:
    """Append one turtle-shell component audit row."""

    sql_backend.append_audit_event(
        connection,
        {
            "session_id": session_id,
            "action": "create_annotation",
            "source_uuid": annotation_uuid,
            "duration_ms": duration_ms,
            "event_time": event_time,
            "details_json": json.dumps(
                {
                    "image_name": "image.jpg",
                    "annotation_type": "polygon",
                    "autoclose": True,
                }
            ),
            "after_state_json": json.dumps(
                {
                    "image_name": "image.jpg",
                    "annotations": [
                        {
                            "annotation_uuid": annotation_uuid,
                            "polygon_coords": polygon,
                        }
                    ],
                }
            ),
        },
    )


class SessionStatisticsTests(unittest.TestCase):
    """Session timing summaries are derived from authoritative audit rows."""

    def test_known_bug_regression_statistics_use_uuid_and_typed_creates(
        self,
    ) -> None:
        """Known-bug regression: UUID CSV rows split creates and count shells."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            connection = sql_backend.connect_database(folder)
            try:
                sql_backend.ensure_schema(connection)
                session_id = sql_backend.current_session_id(connection)
                other_session_id = "00000000-0000-4000-8000-000000000002"
                connection.execute(
                    """
                    INSERT INTO sessions(
                        session_id, app_version, started_time,
                        session_timezone, hostname, host_type, os
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        other_session_id,
                        "Teacup Annotator 1.9.4",
                        1,
                        "UTC",
                        "host",
                        "type",
                        "os",
                    ),
                )
                for duration in (10, 20, 30):
                    append_timed_event(
                        connection,
                        session_id,
                        "move_vertex",
                        duration,
                    )
                append_timed_event(connection, session_id, "draw_arrow", 5)
                append_timed_event(
                    connection,
                    session_id,
                    "create_annotation",
                    250,
                    annotation_type="rectangle",
                )
                append_timed_event(connection, session_id, "view_image", 999)
                append_timed_event(connection, session_id, "move_vertex", None)
                append_timed_event(connection, other_session_id, "move_vertex", 1000)
                append_shell_component(
                    connection,
                    session_id,
                    1_500,
                    500,
                    "ann:shell-1",
                    [(0, 0), (10, 0), (10, 10), (0, 10)],
                )
                sql_backend.append_audit_event(
                    connection,
                    {
                        "session_id": session_id,
                        "action": "close_application",
                        "event_time": 4_000,
                        "details_json": "{}",
                    },
                )

                path = write_session_statistics_csv(
                    folder,
                    connection,
                    session_id,
                )
            finally:
                connection.close()

            with path.open("r", newline="", encoding="utf-8") as csv_file:
                rows = list(csv.reader(csv_file))

        self.assertEqual(
            path.stem,
            session_id,
        )
        self.assertEqual(
            rows,
            [
                [
                    "session_id",
                    "operation",
                    "operation_count",
                    "average_duration_ms",
                    "stdev_duration_ms",
                    "average_final_polygon_count",
                ],
                [
                    session_id,
                    "complete_turtle_shell",
                    "1",
                    "3000.000",
                    "0.000",
                    "1.000",
                ],
                [session_id, "create_polygon", "1", "500.000", "0.000", ""],
                [session_id, "create_rectangle", "1", "250.000", "0.000", ""],
                [session_id, "draw_arrow", "1", "5.000", "0.000", ""],
                [session_id, "move_vertex", "3", "20.000", "8.165", ""],
            ],
        )

    def test_write_current_session_statistics_uses_loaded_folder(self) -> None:
        """The GUI boundary writes the open folder's current session summary."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            connection = sql_backend.connect_database(folder)
            try:
                sql_backend.ensure_schema(connection)
                session_id = sql_backend.current_session_id(connection)
                append_timed_event(connection, session_id, "delete_arrow", 7)
                host = StatefulHost()
                host.project.folder = folder
                host.project.sql_connection = connection
                host.root = mock.Mock()
                host.log = mock.Mock()

                write_current_session_statistics(host)

                summary_path = folder / "teacup" / "statistics" / f"{session_id}.csv"
                self.assertTrue(summary_path.is_file())
            finally:
                connection.close()

    def test_refresh_session_statistics_writes_and_reschedules(self) -> None:
        """One timer tick writes the summary and schedules the next tick."""

        host = SimpleNamespace(root=mock.Mock(), log=mock.Mock())

        with mock.patch(
            "annotator.gui.session_statistics.write_current_session_statistics"
        ) as write_statistics:
            refresh_session_statistics(host)

        write_statistics.assert_called_once_with(host)
        host.root.after.assert_called_once_with(
            SESSION_STATISTICS_REFRESH_MS,
            refresh_session_statistics,
            host,
        )
        host.log.assert_not_called()

    def test_refresh_session_statistics_logs_timer_boundary_errors(self) -> None:
        """Periodic filesystem or SQLite failures are logged without stopping."""

        host = SimpleNamespace(root=mock.Mock(), log=mock.Mock())

        with mock.patch(
            "annotator.gui.session_statistics.write_current_session_statistics",
            side_effect=sqlite3.OperationalError("database is busy"),
        ):
            refresh_session_statistics(host)

        host.log.assert_called_once_with(
            "Session statistics update failed: database is busy"
        )
        host.root.after.assert_called_once_with(
            SESSION_STATISTICS_REFRESH_MS,
            refresh_session_statistics,
            host,
        )


if __name__ == "__main__":
    unittest.main()
