"""Tests for frozen zoom fills and active shape-drag delta geometry."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from PIL import Image

from annotator.coco.models import Annotation
from annotator.gui import zoom_annotations
from annotator.gui import zoom_preview
from annotator.gui.canvas_annotations import draw_annotations
from annotator.gui.render_state import invalidate_annotation_overlay
from tests.support import StatefulHost


def zoom_drag_host() -> StatefulHost:
    """Return loaded image, annotation, and zoom-canvas state for a drag."""

    host = StatefulHost()
    host.widgets = SimpleNamespace(
        controls=SimpleNamespace(zoom_canvas=mock.Mock()),
        viewer=SimpleNamespace(canvas=mock.Mock()),
    )
    host.view.current_image = Image.new("RGB", (500, 500), "white")
    host.view.display_size = (500, 500)
    host.view.image_origin = (0.0, 0.0)
    host.view.zoom = 1.0
    host.project.image_paths = [Path("image.jpg")]
    host.project.coco = mock.Mock()
    host.project.coco.annotations_for.return_value = [
        Annotation(
            1,
            1,
            1,
            [[(10, 20), (35, 15), (30, 40), (10, 40)]],
            raw={"annotation_type": "polygon"},
        ),
        Annotation(
            2,
            1,
            2,
            [[(35, 15), (50, 20), (50, 40), (30, 40)]],
            raw={"annotation_type": "polygon"},
        ),
    ]
    host.interaction.selected_annotation_index = 0
    host.interaction.selected_annotation_indices = {0}
    host.interaction.drag_vertex_ref = (0, 1)
    host.interaction.drag_shared_vertex_refs = [(1, 0, 0)]
    host.zoom_photo = None
    host.annotation_overlay_key = None
    host.annotation_overlay_photo = None
    return host


class ZoomDragFillTests(unittest.TestCase):
    """Active shape drags reuse frozen fills and add only moving geometry."""

    def test_known_bug_regression_active_drag_uses_frozen_fill_and_delta(
        self,
    ) -> None:
        """CODEX: BUG-2026-09-28-ZOOM-DRAG-FILL-RERASTERIZATION.

        An active vertex drag must bypass the complete annotation-fill
        rasterizer, composite the retained pre-drag raster, and then add the
        current local delta before vector overlays are drawn.
        """

        host = zoom_drag_host()
        effects = mock.Mock()
        with (
            mock.patch(
                "annotator.gui.zoom_preview.ImageTk.PhotoImage",
                return_value=mock.sentinel.photo,
            ),
            mock.patch.object(
                zoom_preview,
                "draw_annotation_overlay_on_crop",
                side_effect=effects.full_fill,
            ) as full_fill,
            mock.patch.object(
                zoom_preview,
                "composite_cached_annotation_overlay",
                side_effect=effects.frozen_fill,
                create=True,
            ),
            mock.patch.object(
                zoom_preview,
                "draw_drag_delta_fill_on_crop",
                side_effect=effects.delta_fill,
                create=True,
            ),
            mock.patch.object(
                zoom_preview,
                "draw_zoom_annotation_outlines",
                side_effect=effects.outlines,
            ),
            mock.patch.object(
                zoom_preview,
                "draw_zoom_overlapping_edges",
                side_effect=effects.overlaps,
            ),
            mock.patch.object(
                zoom_preview,
                "draw_zoom_edit_overlays",
                side_effect=effects.edits,
            ),
            mock.patch.object(
                zoom_preview,
                "draw_zoom_crosshair",
                side_effect=effects.crosshair,
            ),
            mock.patch.object(
                zoom_preview,
                "draw_zoom_vertex_ids",
                side_effect=effects.vertex_ids,
            ),
        ):
            zoom_preview.update_zoom_preview(host, (250.0, 250.0))

        full_fill.assert_not_called()
        self.assertEqual(
            [call[0] for call in effects.mock_calls],
            [
                "frozen_fill",
                "delta_fill",
                "outlines",
                "overlaps",
                "edits",
                "crosshair",
                "vertex_ids",
            ],
        )

    def test_cached_overlay_maps_main_canvas_pixels_into_zoom_crop(self) -> None:
        """A cached display-space raster maps exactly into the crop at zoom one."""

        host = zoom_drag_host()
        host.view.annotation_overlay_image = Image.new(
            "RGBA",
            (4, 4),
            (255, 0, 0, 255),
        )
        crop = Image.new("RGBA", (2, 2), "white")

        zoom_preview.composite_cached_annotation_overlay(
            host,
            crop,
            1,
            1,
        )

        self.assertEqual(
            list(crop.getdata()),
            [(255, 0, 0, 255)] * 4,
        )

    def test_polygon_delta_uses_moved_and_shared_local_triangles(self) -> None:
        """Each moved free vertex contributes its current neighbour triangle."""

        host = zoom_drag_host()
        crop = Image.new("RGBA", (50, 50), "white")
        overlay = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
        with (
            mock.patch(
                "annotator.gui.zoom_annotations.class_colour_map",
                return_value={"one": "#010203", "two": "#040506"},
            ),
            mock.patch(
                "annotator.gui.zoom_annotations.annotation_fill",
                side_effect=[(1, 2, 3, 40), (4, 5, 6, 50)],
            ),
            mock.patch(
                "annotator.gui.zoom_annotations.mixed_annotation_overlay",
                return_value=overlay,
            ) as mixed_overlay,
            mock.patch.object(crop, "alpha_composite") as composite,
        ):
            zoom_annotations.draw_drag_delta_fill_on_crop(
                host,
                crop,
                5,
                10,
            )

        mixed_overlay.assert_called_once_with(
            (50, 50),
            [
                (
                    [(5, 10), (30, 5), (25, 30)],
                    (1, 2, 3, 40),
                ),
                (
                    [(25, 30), (30, 5), (45, 10)],
                    (4, 5, 6, 50),
                ),
            ],
        )
        composite.assert_called_once_with(overlay)

    def test_rectangle_delta_uses_current_rectangle(self) -> None:
        """A resized rectangle contributes its complete current constrained shape."""

        host = zoom_drag_host()
        rectangle = Annotation(
            1,
            1,
            1,
            [[(10, 10), (40, 10), (40, 30), (10, 30)]],
            raw={"annotation_type": "rectangle"},
        )
        host.project.coco.annotations_for.return_value = [rectangle]
        host.interaction.drag_vertex_ref = None
        host.interaction.drag_rectangle_side_ref = (0, 1)
        host.interaction.drag_shared_vertex_refs = []
        crop = Image.new("RGBA", (50, 50), "white")
        with (
            mock.patch(
                "annotator.gui.zoom_annotations.class_colour_map",
                return_value={"rectangle": "#010203"},
            ),
            mock.patch(
                "annotator.gui.zoom_annotations.annotation_fill",
                return_value=(1, 2, 3, 40),
            ),
            mock.patch(
                "annotator.gui.zoom_annotations.mixed_annotation_overlay",
                return_value=None,
            ) as mixed_overlay,
        ):
            zoom_annotations.draw_drag_delta_fill_on_crop(
                host,
                crop,
                5,
                5,
            )

        mixed_overlay.assert_called_once_with(
            (50, 50),
            [
                (
                    [(5, 5), (35, 5), (35, 25), (5, 25)],
                    (1, 2, 3, 40),
                )
            ],
        )

    def test_main_canvas_retains_fill_pixels_for_a_later_drag(self) -> None:
        """Main fill construction retains the Pillow image behind the Tk photo."""

        host = zoom_drag_host()
        overlay = Image.new("RGBA", (500, 500), (1, 2, 3, 40))
        with (
            mock.patch(
                "annotator.gui.canvas_annotations.class_colour_map",
                return_value={"one": "#010203", "two": "#040506"},
            ),
            mock.patch(
                "annotator.gui.canvas_annotations.annotation_fill",
                return_value=(1, 2, 3, 40),
            ),
            mock.patch(
                "annotator.gui.canvas_annotations.annotation_outline",
                return_value="#010203",
            ),
            mock.patch(
                "annotator.gui.canvas_annotations.mixed_annotation_overlay",
                return_value=overlay,
            ),
            mock.patch(
                "annotator.gui.canvas_annotations.ImageTk.PhotoImage",
                return_value=mock.sentinel.photo,
            ),
        ):
            draw_annotations(host)

        self.assertIs(host.view.annotation_overlay_image, overlay)

    def test_annotation_invalidation_releases_retained_fill_pixels(self) -> None:
        """Annotation invalidation releases both Pillow and Tk fill rasters."""

        host = zoom_drag_host()
        host.view.annotation_overlay_image = mock.sentinel.overlay_image
        host.annotation_overlay_key = mock.sentinel.overlay_key
        host.annotation_overlay_photo = mock.sentinel.overlay_photo

        invalidate_annotation_overlay(host)

        self.assertIsNone(host.view.annotation_overlay_image)
        self.assertIsNone(host.annotation_overlay_key)
        self.assertIsNone(host.annotation_overlay_photo)


if __name__ == "__main__":
    unittest.main()
