"""Tests for undo snapshot staging."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import annotator.sqlite as sql_backend
from annotator.arrows import Arrow
from annotator.coco import CocoDocument
from annotator.gui.audit.undo import push_undo
from annotator.gui.audit.undo import undo
from annotator.gui.annotation_deletion import delete_selected_annotation_or_arrow
from tests.support import StatefulHost


def sqlite_gui_host(folder: Path, image_path: Path) -> StatefulHost:
    """Return a minimal GUI host for SQLite-backed undo tests."""

    host = StatefulHost()
    host.project.folder = folder
    host.project.all_image_paths = [image_path]
    host.project.image_paths = [image_path]
    host.project.current_index = 0
    host.prefs = mock.Mock()
    host.prefs.values = {}
    host.prefs.get_bool.return_value = False
    host.prefs.get_default_class.return_value = "object"
    host.prefs.get_class_colours.return_value = ("#123456",)
    host.session_default_class_var = mock.Mock()
    host.session_default_class_var.get.return_value = ""
    host.log = mock.Mock()
    return host


class UndoTests(unittest.TestCase):
    """Undo helpers capture state before destructive edits."""

    def test_push_undo_stages_snapshot_and_audit_before_state(self) -> None:
        """An undo snapshot records durable source and context details."""

        host = StatefulHost()
        folder = Path("/images")
        image_path = folder / "a.jpg"
        document = CocoDocument(folder, [image_path])
        annotation = document.add_annotation(
            "a.jpg",
            [(1.0, 1.0), (4.0, 1.0), (4.0, 4.0)],
        )
        annotation.raw["annotation_uuid"] = "ann:one"
        host.project.coco = document
        host.project.image_paths = [image_path]

        push_undo(
            host,
            action="move_vertex",
            annotation_index=0,
            details={"vertex_ref": (0, 1)},
        )

        event = host.project.pending_audit_events[0]
        self.assertEqual(len(host.project.undo_stack), 1)
        self.assertEqual(event["source_uuid"], "ann:one")
        self.assertEqual(event["details"]["image_name"], "a.jpg")
        self.assertEqual(event["details"]["annotation_index"], 0)
        self.assertIsInstance(event["started_monotonic_ns"], int)
        self.assertEqual(
            event["before_state"]["annotations"][0]["annotation_uuid"],
            "ann:one",
        )

    def test_push_undo_keeps_recent_stack_entries(self) -> None:
        """Undo history is capped to the most recent fifty snapshots."""

        host = StatefulHost()
        document = CocoDocument(Path("/images"), [Path("/images/a.jpg")])
        host.project.coco = document
        host.project.image_paths = [Path("/images/a.jpg")]

        for _index in range(51):
            push_undo(host)

        self.assertEqual(len(host.project.undo_stack), 50)

    def test_region_delete_undo_restores_original_order_beside_selected_arrow(
        self,
    ) -> None:
        """Known-bug regression mixed_selection_region_delete_reorders_arrows_2026-08-26."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (20, 20), "white").save(image_path)
            document = CocoDocument(folder, [image_path])
            polygon = document.add_annotation(
                image_path.name,
                [(1, 1), (5, 1), (5, 5), (1, 5)],
            )
            polygon.raw["annotation_uuid"] = "ann:polygon"
            rectangle = document.add_annotation(
                image_path.name,
                [(10, 10), (15, 10), (15, 15), (10, 15)],
            )
            rectangle.raw["annotation_uuid"] = "ann:rectangle"
            rectangle.raw["annotation_type"] = "rectangle"
            arrow = Arrow("arr:one", 2.0, 3.0, 16.0, 17.0)
            connection = sql_backend.connect_database(folder)
            try:
                sql_backend.persist_image(
                    connection,
                    document,
                    image_path.name,
                    write_json_backup=False,
                )
                sql_backend.persist_arrows(
                    connection,
                    {image_path.name: [arrow]},
                )
                host = sqlite_gui_host(folder, image_path)
                host.project.coco = document
                host.project.sql_connection = connection
                host.project.arrows_by_image = {image_path.name: [arrow]}
                host.project.annotation_orders_by_uuid = (
                    sql_backend.load_annotation_orders(connection)
                )
                host.interaction.selected_annotation_indices = {0, 1}
                host.interaction.selected_arrow_index = 0
                host.interaction.selected_arrow_indices = {0}

                with (
                    mock.patch(
                        "annotator.gui.annotation_deletion.redraw_canvas"
                    ),
                    mock.patch("annotator.gui.audit.undo.redraw_canvas"),
                    mock.patch(
                        "annotator.gui.audit.undo.messagebox.showerror"
                    ) as showerror,
                ):
                    delete_selected_annotation_or_arrow(host)
                    rows_after_delete = connection.execute(
                        """
                        SELECT annotation_uuid, annotation_role, annotation_order
                        FROM annotations
                        ORDER BY annotation_order
                        """
                    ).fetchall()
                    self.assertEqual(
                        [tuple(row) for row in rows_after_delete],
                        [("arr:one", "arrow", 2)],
                    )
                    self.assertEqual(
                        host.project.annotation_orders_by_uuid,
                        {"arr:one": 2},
                    )
                    self.assertEqual(
                        host.project.arrows_by_image,
                        {image_path.name: [arrow]},
                    )
                    undo(host)

                rows = connection.execute(
                    """
                    SELECT annotation_uuid, annotation_role, annotation_order
                    FROM annotations
                    ORDER BY annotation_order
                    """
                ).fetchall()
                self.assertEqual(
                    [tuple(row) for row in rows],
                    [
                        ("ann:polygon", "", 0),
                        ("ann:rectangle", "", 1),
                        ("arr:one", "arrow", 2),
                    ],
                )
                self.assertEqual(
                    host.project.annotation_orders_by_uuid,
                    {
                        "ann:polygon": 0,
                        "ann:rectangle": 1,
                        "arr:one": 2,
                    },
                )
                self.assertEqual(len(document.annotations_for(image_path.name)), 2)
                self.assertEqual(
                    host.project.arrows_by_image,
                    {image_path.name: [arrow]},
                )
                showerror.assert_not_called()
            finally:
                connection.close()
