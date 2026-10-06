"""Tests for functional new-polygon autoclose and completion."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from PIL import Image

from annotator.coco.models import Annotation
from tests.support import StatefulHost
from annotator.gui.new_polygon_completion import attempt_autoclose_new_polygon
from annotator.gui.new_polygon_completion import finish_new_polygon_annotation


def completion_host() -> StatefulHost:
    """Return loaded state and effects required by polygon completion."""

    host = StatefulHost()
    host.view.current_image = Image.new("RGB", (100, 100))
    host.view.display_size = (100, 100)
    host.project.image_paths = [Path("image.jpg")]
    host.project.current_index = 0
    host.project.coco = mock.Mock()
    host.project.coco.annotations_for.return_value = []
    host.prefs = mock.Mock()
    host.prefs.get_float.return_value = 5.0
    host.snap_new_var = mock.Mock()
    host.snap_new_var.get.return_value = True
    host.autoclose_var = mock.Mock()
    host.autoclose_var.get.return_value = True
    host.log = mock.Mock()
    host.update_canvas_cursor = mock.Mock()
    return host


class NewPolygonCompletionTests(unittest.TestCase):
    """Completion preserves autoclose geometry, audit data, and persistence."""

    def test_autoclose_requires_active_new_polygon_mode(self) -> None:
        """Autoclose is inactive outside a sufficiently populated new mode."""

        host = completion_host()
        host.interaction.temp_polygon = [(0, 0), (10, 0), (5, 5)]

        self.assertFalse(attempt_autoclose_new_polygon(host))

        host.interaction.mode = "new"
        host.snap_new_var.get.return_value = False
        self.assertFalse(attempt_autoclose_new_polygon(host))

    def test_autoclose_walks_path_and_reports_added_vertices(self) -> None:
        """A valid graph path extends the polygon before completing it."""

        host = completion_host()
        host.interaction.mode = "new"
        host.interaction.temp_polygon = [(10, 10), (20, 10), (30, 30)]
        path = [(30, 30), (20, 20), (10, 10)]

        with (
            mock.patch(
                "annotator.gui.new_polygon_completion.current_snap_graph",
                return_value=mock.sentinel.graph,
            ),
            mock.patch(
                "annotator.gui.new_polygon_completion."
                "polygon_has_unshared_vertex",
                return_value=True,
            ),
            mock.patch(
                "annotator.gui.new_polygon_completion."
                "existing_polygon_graph_paths",
                return_value=[path],
            ),
            mock.patch(
                "annotator.gui.new_polygon_completion."
                "polygon_is_non_degenerate",
                return_value=True,
            ),
            mock.patch(
                "annotator.gui.new_polygon_completion."
                "finish_new_polygon_annotation",
                return_value=True,
            ) as finish,
        ):
            result = attempt_autoclose_new_polygon(host)

        self.assertTrue(result)
        self.assertEqual(
            host.interaction.temp_polygon,
            [(10, 10), (20, 10), (30, 30), (20, 20)],
        )
        finish.assert_called_once_with(
            host,
            details={
                "annotation_type": "polygon",
                "autoclose": True,
                "autoclose_vertices_added": 1,
            },
        )

    def test_autoclose_rejects_path_overlapping_existing_annotation(self) -> None:
        """A turtle-shell path cannot close through occupied annotation area."""

        host = completion_host()
        host.interaction.mode = "new"
        host.interaction.temp_polygon = [(0, 0), (15, 0), (15, 15)]
        host.project.coco.annotations_for.return_value = [
            Annotation(
                1,
                1,
                1,
                [[(0, 0), (10, 0), (10, 10), (0, 10)]],
            )
        ]
        path = [(15, 15), (0, 15), (0, 0)]

        with (
            mock.patch(
                "annotator.gui.new_polygon_completion.current_snap_graph",
                return_value=mock.sentinel.graph,
            ),
            mock.patch(
                "annotator.gui.new_polygon_completion."
                "polygon_has_unshared_vertex",
                return_value=True,
            ),
            mock.patch(
                "annotator.gui.new_polygon_completion."
                "existing_polygon_graph_paths",
                return_value=[path],
            ),
            mock.patch(
                "annotator.gui.new_polygon_completion."
                "finish_new_polygon_annotation",
            ) as finish,
        ):
            result = attempt_autoclose_new_polygon(host)

        self.assertFalse(result)
        finish.assert_not_called()
        host.log.assert_called_once_with(
            "Turtle shell autoclose: path would overlap existing annotation."
        )

    def test_known_bug_regression_autoclose_tries_next_path_after_overlap(
        self,
    ) -> None:
        """Known-bug regression.

        turtle_shell_autoclose_stops_after_overlapping_shortest_path_2026-08-27
        """

        host = completion_host()
        host.interaction.mode = "new"
        host.interaction.temp_polygon = [(0, 0), (-10, 30), (20, 20)]
        host.project.coco.annotations_for.return_value = [
            Annotation(
                1,
                1,
                1,
                [[(0, 0), (20, 0), (20, 20), (0, 20)]],
            )
        ]

        with mock.patch(
            "annotator.gui.new_polygon_completion."
            "finish_new_polygon_annotation",
            return_value=True,
        ) as finish:
            result = attempt_autoclose_new_polygon(host)

        self.assertTrue(result)
        self.assertEqual(
            host.interaction.temp_polygon,
            [(0, 0), (-10, 30), (20, 20), (0, 20)],
        )
        finish.assert_called_once_with(
            host,
            details={
                "annotation_type": "polygon",
                "autoclose": True,
                "autoclose_vertices_added": 1,
            },
        )
        host.log.assert_not_called()

    def test_invalid_polygon_does_not_stage_completion(self) -> None:
        """Fewer than three vertices cannot create an annotation."""

        host = completion_host()
        host.interaction.temp_polygon = [(0, 0), (10, 0)]

        with mock.patch(
            "annotator.gui.new_polygon_completion.push_undo"
        ) as push_undo:
            result = finish_new_polygon_annotation(host)

        self.assertFalse(result)
        push_undo.assert_not_called()
        host.project.coco.add_annotation.assert_not_called()

    def test_completion_preserves_audit_uuid_and_autosave_targets(self) -> None:
        """Creation and shared-edge changes are persisted as one effect sequence."""

        host = completion_host()
        new_annotation = Annotation(
            annotation_id=2,
            image_id=1,
            category_id=3,
            polygons=[],
            raw={"annotation_uuid": "ann:new"},
        )
        source_annotation = Annotation(1, 1, 1, [[(0, 0), (5, 0), (0, 5)]])
        host.interaction.mode = "new"
        host.interaction.temp_polygon = [(10, 10), (30, 10), (20, 30)]
        host.interaction.temp_edge_insertions = [
            {"annotation_index": 0}
        ]
        host.project.pending_audit_events = [{"details": {}}]
        host.project.coco.annotations_for.return_value = [
            source_annotation,
            new_annotation,
        ]
        effects = mock.Mock()
        host.project.coco.add_annotation = effects.add_annotation
        effects.add_annotation.return_value = new_annotation
        host.log = effects.log
        host.update_canvas_cursor = effects.update_canvas_cursor

        with (
            mock.patch(
                "annotator.gui.new_polygon_completion.push_undo",
                side_effect=effects.push_undo,
            ),
            mock.patch(
                "annotator.gui.new_polygon_completion."
                "apply_temp_edge_insertions_to_annotations",
                side_effect=effects.apply_insertions,
            ),
            mock.patch(
                "annotator.gui.new_polygon_completion.mark_annotations_changed",
                side_effect=effects.mark_annotations_changed,
            ),
            mock.patch(
                "annotator.gui.new_polygon_completion.autosave_current_image",
                side_effect=effects.autosave_current_image,
            ),
            mock.patch(
                "annotator.gui.new_polygon_completion."
                "default_annotation_category_id",
                return_value=3,
            ),
            mock.patch(
                "annotator.gui.new_polygon_completion.redraw_canvas",
                side_effect=effects.redraw_canvas,
            ),
        ):
            effects.apply_insertions.return_value = 2
            result = finish_new_polygon_annotation(
                host,
                details={"autoclose": True},
            )

        self.assertTrue(result)
        self.assertEqual(
            effects.mock_calls,
            [
                mock.call.push_undo(
                    host,
                    action="create_annotation",
                    details={
                        "annotation_type": "polygon",
                        "shared_edge_vertices_inserted": 2,
                        "autoclose": True,
                    },
                    started_monotonic_ns=None,
                ),
                mock.call.apply_insertions(
                    host.project,
                    host.view,
                    host.interaction,
                ),
                mock.call.add_annotation(
                    "image.jpg",
                    [(10, 10), (30, 10), (20, 30)],
                    category_id=3,
                    annotation_type="polygon",
                ),
                mock.call.mark_annotations_changed(host),
                mock.call.autosave_current_image(host, [1, 0]),
                mock.call.log("New polygon annotation - ann:new"),
                mock.call.update_canvas_cursor(),
                mock.call.redraw_canvas(host),
            ],
        )
        self.assertEqual(
            host.project.pending_audit_events[-1]["source_uuid"],
            "ann:new",
        )
        self.assertEqual(
            host.project.pending_audit_events[-1]["details"][
                "shared_edge_vertices_inserted"
            ],
            2,
        )
        self.assertIsNone(host.interaction.mode)
        self.assertEqual(host.interaction.temp_polygon, [])
        self.assertEqual(host.interaction.temp_edge_insertions, [])
        self.assertTrue(host.project.dirty)


if __name__ == "__main__":
    unittest.main()
