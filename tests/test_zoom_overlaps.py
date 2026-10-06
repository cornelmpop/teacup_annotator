"""Tests for zoom-preview overlap highlights."""

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from annotator.coco.models import Annotation
from tests.support import StatefulHost
from annotator.gui.zoom_overlaps import draw_overlap_segments_on_zoom
from annotator.gui.zoom_overlaps import draw_zoom_overlapping_edges


def overlap_host() -> StatefulHost:
    """Return annotation state, overlap preferences, and a zoom canvas."""

    host = StatefulHost()
    host.widgets = SimpleNamespace(
        controls=SimpleNamespace(zoom_canvas=mock.Mock())
    )
    host.project.image_paths = [Path("image.jpg")]
    host.project.coco = mock.Mock()
    host.project.coco.annotations_for.return_value = [
        Annotation(1, 1, 1, [[(0, 0), (10, 0), (10, 10)]])
    ]
    host.show_overlapping_edges_var = mock.Mock()
    host.show_overlapping_edges_var.get.return_value = True
    host.prefs = mock.Mock()
    host.prefs.get_int.return_value = 3
    return host


class ZoomOverlapTests(unittest.TestCase):
    """Zoom overlap rendering distinguishes global and selected edges."""

    def test_overlap_query_routes_global_and_selected_styles(self) -> None:
        """Configured overlap results produce both highlight passes."""

        host = overlap_host()
        segments = [((0.0, 0.0), (10.0, 0.0))]
        vertices = [(10.0, 0.0)]
        with (
            mock.patch(
                "annotator.gui.zoom_overlaps.annotation_overlap_geometry",
                return_value=(segments, vertices),
            ),
            mock.patch(
                "annotator.gui.zoom_overlaps.draw_overlap_segments_on_zoom"
            ) as draw_segments,
            mock.patch(
                "annotator.gui.zoom_overlaps.configured_colour",
                side_effect=("#112233", "#445566"),
            ),
            mock.patch(
                "annotator.gui.zoom_overlaps.selected_annotation_shared_edge_segments",
                return_value=[((1.0, 1.0), (2.0, 2.0))],
            ),
        ):
            draw_zoom_overlapping_edges(host, 5, 6, 100)

        self.assertEqual(len(draw_segments.call_args_list), 2)
        self.assertEqual(
            draw_segments.call_args_list[0].args[1:5],
            (segments, vertices, "#112233", 3),
        )
        self.assertEqual(
            draw_segments.call_args_list[1].args[1:5],
            (
                [((1.0, 1.0), (2.0, 2.0))],
                [],
                "#445566",
                3,
            ),
        )

    def test_segment_renderer_scales_lines_endpoints_and_vertices(self) -> None:
        """Image-space overlap geometry is mapped through crop origin and scale."""

        host = overlap_host()
        draw_overlap_segments_on_zoom(
            host,
            [((10.0, 20.0), (20.0, 20.0))],
            [(15.0, 25.0)],
            "#123456",
            4,
            5,
            10,
            2.0,
        )

        canvas = host.widgets.controls.zoom_canvas
        canvas.create_line.assert_called_once_with(
            10.0,
            20.0,
            30.0,
            20.0,
            fill="#123456",
            width=4,
            tags=("overlap_edge",),
        )
        self.assertEqual(len(canvas.create_oval.call_args_list), 3)
        self.assertEqual(
            canvas.create_oval.call_args_list[-1].args,
            (18.0, 28.0, 22.0, 32.0),
        )

    def test_known_bug_regression_renderer_skips_geometry_outside_crop(self) -> None:
        """Known-bug regression: Adler2002_403_0_7 draws only visible overlaps."""

        host = overlap_host()
        draw_overlap_segments_on_zoom(
            host,
            [
                ((10.0, 20.0), (20.0, 20.0)),
                ((500.0, 500.0), (510.0, 500.0)),
            ],
            [(15.0, 25.0), (500.0, 500.0)],
            "#123456",
            4,
            5,
            10,
            2.0,
        )

        canvas = host.widgets.controls.zoom_canvas
        self.assertEqual(canvas.create_line.call_count, 1)
        self.assertEqual(canvas.create_oval.call_count, 3)

    def test_disabled_overlap_display_is_a_noop(self) -> None:
        """The preference gate prevents geometry queries and drawing."""

        host = overlap_host()
        host.show_overlapping_edges_var.get.return_value = False
        with mock.patch(
            "annotator.gui.zoom_overlaps.annotation_overlap_geometry"
        ) as geometry:
            draw_zoom_overlapping_edges(host, 0, 0, 100)

        geometry.assert_not_called()


if __name__ == "__main__":
    unittest.main()
