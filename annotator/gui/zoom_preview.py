"""Own zoom-crop lifecycle, layer orchestration, and preview clearing."""

from __future__ import annotations

import tkinter as tk
from typing import Protocol
from typing import TYPE_CHECKING

from PIL import Image
from PIL import ImageTk

from annotator.gui.constants import ZOOM_VIEW_SIZE
from annotator.gui.interactions import zoom_preview_crop_size
from annotator.gui.state import ViewState
from annotator.gui.zoom_annotations import ZoomAnnotationHost
from annotator.gui.zoom_annotations import draw_annotation_overlay_on_crop
from annotator.gui.zoom_annotations import draw_drag_delta_fill_on_crop
from annotator.gui.zoom_annotations import draw_zoom_annotation_outlines
from annotator.gui.zoom_edit_overlays import ZoomEditOverlayHost
from annotator.gui.zoom_edit_overlays import draw_zoom_edit_overlays
from annotator.gui.zoom_overlaps import ZoomOverlapHost
from annotator.gui.zoom_overlaps import draw_zoom_overlapping_edges
from annotator.gui.zoom_vertex_labels import ZoomVertexLabelHost
from annotator.gui.zoom_vertex_labels import draw_zoom_vertex_ids

if TYPE_CHECKING:
    from annotator.gui.window.state import WindowWidgets


class ZoomPreviewHost(
    ZoomAnnotationHost,
    ZoomOverlapHost,
    ZoomEditOverlayHost,
    ZoomVertexLabelHost,
    Protocol,
):
    """Combined layer capabilities and retained image needed by zoom preview."""

    view: ViewState
    widgets: WindowWidgets
    zoom_photo: ImageTk.PhotoImage | None


def update_zoom_preview(
    host: ZoomPreviewHost,
    image_point: tuple[float, float],
) -> None:
    """Render the zoom crop and its annotation and edit layers."""

    if host.view.current_image is None:
        clear_zoom_preview(host)
        return
    image_x, image_y = image_point
    crop_size = zoom_preview_crop_size(host.view.zoom)
    crop_left = int(round(image_x - crop_size / 2))
    crop_top = int(round(image_y - crop_size / 2))
    crop_right = crop_left + crop_size
    crop_bottom = crop_top + crop_size
    clipped_left = max(0, crop_left)
    clipped_top = max(0, crop_top)
    clipped_right = min(host.view.current_image.width, crop_right)
    clipped_bottom = min(host.view.current_image.height, crop_bottom)
    if clipped_right <= clipped_left or clipped_bottom <= clipped_top:
        clear_zoom_preview(host)
        return

    zoom_crop = Image.new("RGBA", (crop_size, crop_size), "white")
    crop = host.view.current_image.crop(
        (clipped_left, clipped_top, clipped_right, clipped_bottom)
    ).convert("RGBA")
    zoom_crop.paste(crop, (clipped_left - crop_left, clipped_top - crop_top))
    shape_drag_active = (
        host.interaction.drag_vertex_ref is not None
        or host.interaction.drag_rectangle_side_ref is not None
    )
    if shape_drag_active:
        # CODEX: Reuse the stable main fill and add only moving geometry;
        # CODEX: release invalidates this cache and restores exact fills.
        composite_cached_annotation_overlay(
            host,
            zoom_crop,
            crop_left,
            crop_top,
        )
        draw_drag_delta_fill_on_crop(
            host,
            zoom_crop,
            crop_left,
            crop_top,
        )
    else:
        draw_annotation_overlay_on_crop(
            host,
            zoom_crop,
            crop_left,
            crop_top,
            crop_size,
        )
    zoom_image = zoom_crop.convert("RGB").resize(
        (ZOOM_VIEW_SIZE, ZOOM_VIEW_SIZE),
        Image.Resampling.LANCZOS,
    )
    host.zoom_photo = ImageTk.PhotoImage(zoom_image)
    canvas = host.widgets.controls.zoom_canvas
    canvas.delete("all")
    canvas.create_image(0, 0, anchor=tk.NW, image=host.zoom_photo)
    draw_zoom_annotation_outlines(host, crop_left, crop_top, crop_size)
    draw_zoom_overlapping_edges(host, crop_left, crop_top, crop_size)
    draw_zoom_edit_overlays(host, crop_left, crop_top, crop_size)
    draw_zoom_crosshair(host)
    draw_zoom_vertex_ids(host, crop_left, crop_top, crop_size)


def composite_cached_annotation_overlay(
    host: ZoomPreviewHost,
    crop: Image.Image,
    crop_left: int,
    crop_top: int,
) -> None:
    """CODEX: Composite the retained main fill into a moving zoom crop.

    The display-space Pillow raster remains at its pre-drag annotation revision.
    An affine crop follows the pointer without rebuilding polygon masks, while
    Pillow owns interpolation and transparent pixels outside the source image.
    """

    overlay = host.view.annotation_overlay_image
    if overlay is None:
        return
    scale = host.view.zoom
    frozen_crop = overlay.transform(
        crop.size,
        Image.Transform.AFFINE,
        (
            scale,
            0.0,
            crop_left * scale,
            0.0,
            scale,
            crop_top * scale,
        ),
        resample=Image.Resampling.BILINEAR,
        fillcolor=(0, 0, 0, 0),
    )
    crop.alpha_composite(frozen_crop)

# CMP: TODO - Refactor. Stylistic elements should not be hard coded. Move
# to a theme file.
def draw_zoom_crosshair(host: ZoomPreviewHost) -> None:
    """Draw the mouse pointer mark in the centre of the zoom canvas."""

    center = ZOOM_VIEW_SIZE // 2
    radius = 12
    canvas = host.widgets.controls.zoom_canvas
    canvas.create_line(
        center - radius,
        center,
        center + radius,
        center,
        fill="#333333",
        width=1,
    )
    canvas.create_line(
        center,
        center - radius,
        center,
        center + radius,
        fill="#333333",
        width=1,
    )


def clear_zoom_preview(host: ZoomPreviewHost) -> None:
    """Clear the zoom canvas and release its retained Tk image."""

    host.widgets.controls.zoom_canvas.delete("all")
    host.zoom_photo = None
