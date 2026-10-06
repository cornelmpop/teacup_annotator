"""CODEX: Test durable image ownership across navigation and Undo."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest import mock

from PIL import Image

import annotator.sqlite as sql_backend
from annotator.arrows import Arrow
from annotator.coco import CocoDocument
from annotator.gui.audit.undo import push_undo
from annotator.gui.audit.undo import undo
from annotator.gui.persistence import autosave_current_image
from annotator.gui.persistence import persist_arrows
from annotator.gui.persistence import persist_current_image_annotations
from annotator.gui.project.navigation import record_current_image_view
from tests.support import StatefulHost


ORIGINAL_A = [(1, 1), (5, 1), (5, 5), (1, 5)]
EDITED_A = [(1, 1), (8, 1), (5, 5), (1, 5)]
ORIGINAL_B = [(10, 10), (15, 10), (15, 15), (10, 15)]


def _sqlite_host(tmp_path: Path) -> tuple[StatefulHost, sqlite3.Connection]:
    """CODEX: Return a two-image host with fixed region identities."""

    image_paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
    for image_path in image_paths:
        Image.new("RGB", (20, 20), "white").save(image_path)
    document = CocoDocument(tmp_path, image_paths)
    annotation_a = document.add_annotation("a.jpg", ORIGINAL_A)
    annotation_a.raw["annotation_uuid"] = "ann:a"
    annotation_b = document.add_annotation("b.jpg", ORIGINAL_B)
    annotation_b.raw["annotation_uuid"] = "ann:b"
    connection = sql_backend.connect_database(tmp_path)
    for image_path in image_paths:
        sql_backend.persist_image(
            connection,
            document,
            image_path.name,
            write_json_backup=False,
        )

    host = StatefulHost()
    host.project.folder = tmp_path
    host.project.all_image_paths = image_paths
    host.project.image_paths = image_paths
    host.project.current_index = 0
    host.project.coco = document
    host.project.sql_connection = connection
    host.project.annotation_orders_by_uuid = sql_backend.load_annotation_orders(
        connection
    )
    host.prefs = mock.Mock()
    host.prefs.values = {}
    host.prefs.get_bool.return_value = False
    host.prefs.get_default_class.return_value = "object"
    host.prefs.get_class_colours.return_value = ("#123456",)
    host.session_default_class_var = mock.Mock()
    host.session_default_class_var.get.return_value = ""
    host.log = mock.Mock()
    return host, connection


def _audit_rows(connection: sqlite3.Connection) -> list[dict[str, object]]:
    """CODEX: Return ordered audit rows needed by the ownership assertions."""

    return sql_backend.read_audit_events(connection)


def test_cross_navigation_undo_persists_and_audits_its_owner(
    tmp_path: Path,
) -> None:
    """CODEX: Known-bug regression project_wide_undo_snapshot_stalls_image_local_edits_2026-09-01."""

    host, connection = _sqlite_host(tmp_path)
    try:
        push_undo(host, action="move_vertex", annotation_index=0)
        host.project.coco.annotations_for("a.jpg")[0].polygons[0] = EDITED_A
        with mock.patch("annotator.gui.project.status.update_edit_summary"):
            assert autosave_current_image(host)
            edit_event_id = _audit_rows(connection)[-1]["audit_event_id"]
            host.project.current_index = 1
            record_current_image_view(host)
            view_event_id = _audit_rows(connection)[-1]["audit_event_id"]
            with mock.patch("annotator.gui.audit.undo.redraw_canvas"):
                undo(host)

        assert view_event_id != edit_event_id
        assert host.project.current_index == 1
        assert host.project.coco.annotations_for("a.jpg")[0].polygons[0] == ORIGINAL_A
        assert host.project.coco.annotations_for("b.jpg")[0].polygons[0] == ORIGINAL_B
        reloaded = sql_backend.document_from_database(
            connection,
            tmp_path,
            host.project.all_image_paths,
        )
        assert reloaded.annotations_for("a.jpg")[0].polygons[0] == ORIGINAL_A
        assert reloaded.annotations_for("b.jpg")[0].polygons[0] == ORIGINAL_B

        undo_event = _audit_rows(connection)[-1]
        assert undo_event["action"] == "undo"
        assert undo_event["undo_of_audit_event_id"] == edit_event_id
        assert json.loads(undo_event["before_state_json"])["image_name"] == "a.jpg"
        assert json.loads(undo_event["after_state_json"])["image_name"] == "a.jpg"
        host.log.assert_any_call("Undid move_vertex on a.jpg")
    finally:
        connection.close()


def test_cross_navigation_undo_restores_local_arrows_and_sparse_orders(
    tmp_path: Path,
) -> None:
    """CODEX: Known-bug regression project_wide_undo_snapshot_stalls_image_local_edits_2026-09-01."""

    host, connection = _sqlite_host(tmp_path)
    arrow_a = Arrow("arr:a", 2.0, 2.0, 4.0, 4.0)
    arrow_b = Arrow("arr:b", 11.0, 11.0, 14.0, 14.0)
    host.project.arrows_by_image = {"a.jpg": [arrow_a], "b.jpg": [arrow_b]}
    sql_backend.persist_arrows(connection, host.project.arrows_by_image)
    host.project.annotation_orders_by_uuid = sql_backend.load_annotation_orders(
        connection
    )
    b_row_before = dict(
        connection.execute(
            "SELECT * FROM annotations WHERE annotation_uuid = 'arr:b'"
        ).fetchone()
    )
    try:
        push_undo(host, action="delete_annotation")
        host.project.coco.delete_annotation("a.jpg", 0)
        host.project.arrows_by_image.pop("a.jpg")
        persist_current_image_annotations(host, commit=False)
        persist_arrows(host, commit=False)
        with mock.patch("annotator.gui.project.status.update_edit_summary"):
            from annotator.gui.audit.events import flush_pending_audit_events

            flush_pending_audit_events(host)
            host.project.current_index = 1
            record_current_image_view(host)
            with mock.patch("annotator.gui.audit.undo.redraw_canvas"):
                undo(host)

        rows = connection.execute(
            """
            SELECT image_name, annotation_uuid, annotation_order
            FROM annotations
            JOIN project_images USING(image_id)
            ORDER BY image_name, annotation_order
            """
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("a.jpg", "ann:a", 0),
            ("a.jpg", "arr:a", 1),
            ("b.jpg", "ann:b", 0),
            ("b.jpg", "arr:b", 1),
        ]
        assert dict(
            connection.execute(
                "SELECT * FROM annotations WHERE annotation_uuid = 'arr:b'"
            ).fetchone()
        ) == b_row_before
    finally:
        connection.close()


def test_failed_offscreen_undo_requeues_snapshot_and_recovers_sqlite(
    tmp_path: Path,
) -> None:
    """CODEX: Known-bug regression project_wide_undo_snapshot_stalls_image_local_edits_2026-09-01."""

    host, connection = _sqlite_host(tmp_path)
    try:
        push_undo(host, action="move_vertex", annotation_index=0)
        host.project.coco.annotations_for("a.jpg")[0].polygons[0] = EDITED_A
        with mock.patch("annotator.gui.project.status.update_edit_summary"):
            assert autosave_current_image(host)
        host.project.current_index = 1

        with (
            mock.patch(
                "annotator.gui.persistence.sql_backend.persist_image",
                side_effect=sqlite3.OperationalError("write failed"),
            ) as persist_image,
            mock.patch("annotator.gui.audit.undo.redraw_canvas"),
            mock.patch("annotator.gui.persistence.messagebox.showerror"),
            mock.patch("annotator.gui.recovery.refresh_filter_options"),
            mock.patch("annotator.gui.recovery.load_current_image"),
        ):
            undo(host)

        assert persist_image.call_args.args[2] == "a.jpg"
        assert len(host.project.undo_stack) == 1
        assert host.project.coco.annotations_for("a.jpg")[0].polygons[0] == EDITED_A
        assert host.project.pending_audit_events == []
    finally:
        connection.close()
