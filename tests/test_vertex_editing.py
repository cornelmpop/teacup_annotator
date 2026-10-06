"""Tests for functional vertex drag and insertion effects."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from PIL import Image

from annotator.coco.models import Annotation
from tests.support import StatefulHost
from annotator.gui.vertex_editing import begin_vertex_drag
from annotator.gui.vertex_editing import drag_selected_vertex_to
from annotator.gui.vertex_editing import finish_vertex_drag
from annotator.gui.vertex_editing import insert_vertex_at


def editable_annotation(annotation_type: str = "polygon") -> Annotation:
    """Return one free polygon or constrained rectangle fixture."""

    return Annotation(
        annotation_id=1,
        image_id=1,
        category_id=1,
        polygons=[[(10, 10), (40, 10), (40, 40), (10, 40)]],
        raw={"annotation_type": annotation_type},
    )


def vertex_editing_host(
    annotation_type: str = "polygon",
) -> StatefulHost:
    """Return loaded state and effects required by vertex editing."""

    host = StatefulHost()
    host.view.current_image = Image.new("RGB", (100, 100))
    host.view.display_size = (100, 100)
    host.project.image_paths = [Path("image.jpg")]
    host.project.current_index = 0
    host.project.coco = mock.Mock()
    host.project.coco.annotations_for.return_value = [
        editable_annotation(annotation_type)
    ]
    host.interaction.selected_annotation_index = 0
    host.interaction.selected_annotation_indices = {0}
    host.prefs = mock.Mock()
    host.prefs.get_float.return_value = 5.0
    host.snap_edits_var = mock.Mock()
    host.snap_edits_var.get.return_value = True
    host.autoclose_var = mock.Mock()
    host.autoclose_var.get.return_value = False
    host.set_canvas_cursor = mock.Mock()
    return host


class VertexEditingTests(unittest.TestCase):
    """Vertex editing preserves drag setup, mutation, and durable effects."""

    def test_begin_vertex_drag_records_targets_and_undo(self) -> None:
        """Drag setup snapshots Undo and resolves related geometry once."""

        host = vertex_editing_host()

        with (
            mock.patch(
                "annotator.gui.vertex_editing.shared_vertex_refs_for_drag",
                return_value=[(1, 0, 0)],
            ) as shared_refs,
            mock.patch(
                "annotator.gui.vertex_editing.rectangle_drag_context",
                return_value=mock.sentinel.context,
            ) as rectangle_context,
            mock.patch("annotator.gui.vertex_editing.push_undo") as push_undo,
        ):
            begin_vertex_drag(host, (0, 1))

        push_undo.assert_called_once_with(
            host,
            action="move_vertex",
            annotation_index=0,
            details={"vertex_ref": (0, 1)},
        )
        self.assertEqual(host.interaction.drag_vertex_ref, (0, 1))
        self.assertEqual(host.interaction.drag_vertex_original_point, (40, 10))
        self.assertEqual(
            host.interaction.drag_shared_vertex_refs,
            [(1, 0, 0)],
        )
        self.assertIs(
            host.interaction.drag_rectangle_context,
            mock.sentinel.context,
        )
        shared_refs.assert_called_once_with(host, (40, 10))
        rectangle_context.assert_called_once_with(host, (0, 1))
        host.set_canvas_cursor.assert_called_once_with("cross")

    def test_drag_free_vertex_uses_snapped_point_and_shared_targets(self) -> None:
        """A free-polygon drag mutates its point and shared edit targets."""

        host = vertex_editing_host()
        annotation = host.project.coco.annotations_for.return_value[0]
        host.interaction.drag_vertex_ref = (0, 1)

        with (
            mock.patch(
                "annotator.gui.vertex_editing.snapped_edit_point",
                return_value=(45, 12),
            ),
            mock.patch(
                "annotator.gui.vertex_editing.move_shared_drag_vertices"
            ) as move_shared,
        ):
            drag_selected_vertex_to(host, (44, 11))

        self.assertEqual(annotation.polygons[0][1], (45, 12))
        move_shared.assert_called_once_with(host, (45, 12))
        self.assertIsNone(host.view.annotation_overlap_key)
        self.assertTrue(host.project.dirty)

    def test_drag_rectangle_delegates_to_constrained_resize(self) -> None:
        """Rectangle vertices remain governed by the rectangle-resize helper."""

        host = vertex_editing_host("rectangle")
        host.interaction.drag_vertex_ref = (0, 1)

        with (
            mock.patch(
                "annotator.gui.vertex_editing.snapped_edit_point",
                return_value=(45, 12),
            ),
            mock.patch(
                "annotator.gui.vertex_editing.resize_selected_rectangle"
            ) as resize,
            mock.patch(
                "annotator.gui.vertex_editing.move_shared_drag_vertices"
            ) as move_shared,
        ):
            drag_selected_vertex_to(host, (44, 11))

        resize.assert_called_once_with(host, (45, 12))
        move_shared.assert_not_called()

    def test_finish_vertex_drag_autosaves_every_changed_annotation(self) -> None:
        """Drag completion clears transient state and saves unique targets."""

        host = vertex_editing_host()
        host.interaction.drag_vertex_ref = (0, 1)
        host.interaction.drag_vertex_original_point = (40, 10)
        host.interaction.drag_shared_vertex_refs = [
            (2, 0, 0),
            (1, 0, 1),
            (2, 1, 0),
        ]
        host.interaction.drag_rectangle_context = {"corner_index": 1}
        effects = mock.Mock()

        with (
            mock.patch(
                "annotator.gui.vertex_editing.mark_annotations_changed",
                side_effect=effects.mark_annotations_changed,
            ),
            mock.patch(
                "annotator.gui.vertex_editing.autosave_current_image",
                side_effect=effects.autosave_current_image,
            ),
            mock.patch(
                "annotator.gui.vertex_editing.redraw_canvas",
                side_effect=effects.redraw_canvas,
            ),
        ):
            finish_vertex_drag(host)

        self.assertEqual(
            effects.mock_calls,
            [
                mock.call.mark_annotations_changed(host),
                mock.call.autosave_current_image(host, [0, 1, 2]),
                mock.call.redraw_canvas(host),
            ],
        )
        self.assertIsNone(host.interaction.drag_vertex_ref)
        self.assertIsNone(host.interaction.drag_vertex_original_point)
        self.assertEqual(host.interaction.drag_shared_vertex_refs, [])
        self.assertIsNone(host.interaction.drag_rectangle_context)

    def test_insert_vertex_stages_undo_and_autosaves(self) -> None:
        """Insertion places the new point after its segment and persists it."""

        host = vertex_editing_host()
        annotation = host.project.coco.annotations_for.return_value[0]
        host.interaction.selected_vertices = {(0, 1)}
        host.interaction.selection_rect = (1, 2, 3, 4)
        effects = mock.Mock()

        with (
            mock.patch(
                "annotator.gui.vertex_editing.push_undo",
                side_effect=effects.push_undo,
            ),
            mock.patch(
                "annotator.gui.vertex_editing.mark_annotations_changed",
                side_effect=effects.mark_annotations_changed,
            ),
            mock.patch(
                "annotator.gui.vertex_editing.autosave_current_image",
                side_effect=effects.autosave_current_image,
            ),
            mock.patch(
                "annotator.gui.vertex_editing.redraw_canvas",
                side_effect=effects.redraw_canvas,
            ),
        ):
            insert_vertex_at(host, (0, 1), (25, 10))

        self.assertEqual(
            effects.mock_calls,
            [
                mock.call.push_undo(
                    host,
                    action="insert_vertex",
                    annotation_index=0,
                    details={"border_ref": (0, 1)},
                ),
                mock.call.mark_annotations_changed(host),
                mock.call.autosave_current_image(host),
                mock.call.redraw_canvas(host),
            ],
        )
        self.assertEqual(annotation.polygons[0][2], (25, 10))
        self.assertEqual(host.interaction.selected_vertices, set())
        self.assertIsNone(host.interaction.selection_rect)
        self.assertTrue(host.project.dirty)

    def test_known_bug_regression_shared_edge_insert_creates_drag_target(
        self,
    ) -> None:
        """Known-bug regression turtle_shell_insert_vertex_breaks_shared_edge_2026-08-26."""

        host = vertex_editing_host()
        left = Annotation(
            annotation_id=1,
            image_id=1,
            category_id=1,
            polygons=[[(0, 0), (10, 0), (10, 10), (0, 10)]],
            raw={"annotation_type": "polygon"},
        )
        right = Annotation(
            annotation_id=2,
            image_id=1,
            category_id=1,
            polygons=[[(10, 0), (20, 0), (20, 10), (10, 10)]],
            raw={"annotation_type": "polygon"},
        )
        host.project.coco.annotations_for.return_value = [left, right]
        host.autoclose_var.get.return_value = True
        host.snap_edits_var.get.return_value = False
        effects = mock.Mock()

        with (
            mock.patch("annotator.gui.vertex_editing.push_undo"),
            mock.patch("annotator.gui.vertex_editing.mark_annotations_changed"),
            mock.patch(
                "annotator.gui.vertex_editing.autosave_current_image",
                side_effect=effects.autosave_current_image,
            ),
            mock.patch("annotator.gui.vertex_editing.redraw_canvas"),
        ):
            insert_vertex_at(host, (0, 1), (10, 5))

        self.assertEqual(
            left.polygons[0],
            [(0, 0), (10, 0), (10, 5), (10, 10), (0, 10)],
        )
        self.assertEqual(
            right.polygons[0],
            [(10, 0), (20, 0), (20, 10), (10, 10), (10, 5)],
        )
        effects.autosave_current_image.assert_called_once_with(host, [0, 1])

        with mock.patch("annotator.gui.vertex_editing.push_undo"):
            begin_vertex_drag(host, (0, 2))
            drag_selected_vertex_to(host, (12, 5))

        self.assertEqual(host.interaction.drag_shared_vertex_refs, [(1, 0, 4)])
        self.assertEqual(left.polygons[0][2], (12, 5))
        self.assertEqual(right.polygons[0][4], (12, 5))

        finish_effects = mock.Mock()
        with (
            mock.patch("annotator.gui.vertex_editing.mark_annotations_changed"),
            mock.patch(
                "annotator.gui.vertex_editing.autosave_current_image",
                side_effect=finish_effects.autosave_current_image,
            ),
            mock.patch("annotator.gui.vertex_editing.redraw_canvas"),
        ):
            finish_vertex_drag(host)

        finish_effects.autosave_current_image.assert_called_once_with(host, [0, 1])


if __name__ == "__main__":
    unittest.main()
