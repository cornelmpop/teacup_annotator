"""Contract tests for overlap rendering at shape-drag boundaries."""

import unittest
from unittest import mock

from annotator.gui.canvas_overlaps import draw_overlapping_edges
from annotator.gui.zoom_overlaps import draw_zoom_overlapping_edges
from tests.support import StatefulHost


def overlap_host() -> StatefulHost:
    """Return a host with overlap display enabled and no active drag."""

    host = StatefulHost()
    host.show_overlapping_edges_var = mock.Mock()
    host.show_overlapping_edges_var.get.return_value = True
    return host


class DragOverlapSuppressionTests(unittest.TestCase):
    """Overlap renderers hide stale geometry only while shapes move."""

    def test_main_overlap_is_suppressed_during_shape_drag(self) -> None:
        """Known-bug regression for
        vertex_drag_recomputes_quadratic_overlap_geometry_2026-09-02.
        """

        drag_states = (
            ("drag_vertex_ref", (0, 1)),
            ("drag_rectangle_side_ref", (0, 2)),
        )
        for field_name, field_value in drag_states:
            with self.subTest(field_name=field_name):
                host = overlap_host()
                setattr(host.interaction, field_name, field_value)

                with mock.patch(
                    "annotator.gui.canvas_overlaps.annotation_overlap_geometry",
                    return_value=([], []),
                ) as geometry:
                    draw_overlapping_edges(host)

                geometry.assert_not_called()

    def test_zoom_overlap_is_suppressed_during_shape_drag(self) -> None:
        """Known-bug regression for
        vertex_drag_recomputes_quadratic_overlap_geometry_2026-09-02.
        """

        drag_states = (
            ("drag_vertex_ref", (0, 1)),
            ("drag_rectangle_side_ref", (0, 2)),
        )
        for field_name, field_value in drag_states:
            with self.subTest(field_name=field_name):
                host = overlap_host()
                setattr(host.interaction, field_name, field_value)

                with mock.patch(
                    "annotator.gui.zoom_overlaps.annotation_overlap_geometry",
                    return_value=([], []),
                ) as geometry:
                    draw_zoom_overlapping_edges(host, 5, 6, 100)

                geometry.assert_not_called()

    def test_main_overlap_resumes_after_drag_state_clears(self) -> None:
        """Known-bug regression for
        vertex_drag_recomputes_quadratic_overlap_geometry_2026-09-02.
        """

        host = overlap_host()
        host.interaction.drag_vertex_ref = (0, 1)
        with mock.patch(
            "annotator.gui.canvas_overlaps.annotation_overlap_geometry",
            return_value=([], []),
        ) as geometry:
            draw_overlapping_edges(host)
            host.interaction.drag_vertex_ref = None
            draw_overlapping_edges(host)

        geometry.assert_called_once_with(host)

    def test_zoom_overlap_resumes_after_drag_state_clears(self) -> None:
        """Known-bug regression for
        vertex_drag_recomputes_quadratic_overlap_geometry_2026-09-02.
        """

        host = overlap_host()
        host.interaction.drag_rectangle_side_ref = (0, 2)
        with mock.patch(
            "annotator.gui.zoom_overlaps.annotation_overlap_geometry",
            return_value=([], []),
        ) as geometry:
            draw_zoom_overlapping_edges(host, 5, 6, 100)
            host.interaction.drag_rectangle_side_ref = None
            draw_zoom_overlapping_edges(host, 5, 6, 100)

        geometry.assert_called_once_with(host)


if __name__ == "__main__":
    unittest.main()
