"""Own main-canvas redraw orchestration and base-image placement."""

from __future__ import annotations

import tkinter as tk
from typing import Any
from typing import Protocol
from typing import TYPE_CHECKING
from typing import cast

from PIL import ImageTk
from PIL import Image

from annotator.gui.canvas_annotations import CanvasAnnotationHost
from annotator.gui.canvas_annotations import draw_annotation_labels
from annotator.gui.canvas_annotations import draw_annotations
from annotator.gui.canvas_annotations import draw_selected_vertices
from annotator.gui.canvas_arrows import CanvasArrowHost
from annotator.gui.canvas_arrows import draw_arrows
from annotator.gui.canvas_arrows import draw_temp_arrow
from annotator.gui.canvas_edit_overlays import CanvasEditOverlayHost
from annotator.gui.canvas_edit_overlays import draw_merge_primary_highlight
from annotator.gui.canvas_edit_overlays import draw_multi_selected_annotations
from annotator.gui.canvas_edit_overlays import draw_new_snap_context_vertices
from annotator.gui.canvas_edit_overlays import draw_temp_polygon
from annotator.gui.canvas_guides import CanvasGuideHost
from annotator.gui.canvas_guides import draw_guides
from annotator.gui.canvas_guides import draw_snap_preview_dot
from annotator.gui.canvas_overlaps import CanvasOverlapHost
from annotator.gui.canvas_overlaps import draw_overlapping_edges
from annotator.gui.canvas_selection_overlays import CanvasSelectionOverlayHost
from annotator.gui.canvas_selection_overlays import draw_annotation_selection_rect
from annotator.gui.canvas_selection_overlays import draw_selection_overlay
from annotator.gui.canvas_tooltips import CanvasTooltipHost
from annotator.gui.canvas_tooltips import update_hover_class_tooltip
from annotator.gui.project.status import StatusHost
from annotator.gui.project.status import update_edit_summary
from annotator.gui.project.status import update_image_status
from annotator.gui.state import ViewState
from annotator.gui.vertex_labels import draw_selected_vertex_ids
from annotator.gui.vertex_labels import VertexLabelHost
from annotator.gui.view_geometry import image_point_from_canvas
from annotator.gui.zoom_preview import clear_zoom_preview
from annotator.gui.zoom_preview import update_zoom_preview
from annotator.gui.zoom_preview import ZoomPreviewHost

if TYPE_CHECKING:
    from annotator.gui.window.state import WindowWidgets


class CanvasRenderHost(Protocol):
    """Complete state, widgets, and retained images needed to redraw."""

    view: ViewState
    widgets: WindowWidgets
    photo_image: ImageTk.PhotoImage | None
    photo_image_key: tuple[Any, ...] | None
    annotation_overlay_photo: ImageTk.PhotoImage | None
    annotation_overlay_key: tuple[Any, ...] | None
    selection_overlay_photo: ImageTk.PhotoImage | None


def on_canvas_configure(host: CanvasRenderHost, _event: tk.Event) -> None:
    """Redraw a loaded image when the viewer pane changes size."""

    if host.view.current_image is not None:
        redraw_canvas(host)

# CMP: TODO - Clarify if rendering order matters, why, and if not,
# why not. In other words, justify the order below.
def redraw_canvas(host: CanvasRenderHost) -> None:
    """Redraw the image, annotations, vertices, selection, and guides."""

    host.widgets.viewer.canvas.delete("all")
    if host.view.current_image is None:
        clear_unloaded_canvas(host)
        return

    place_base_image(host)
    draw_selection_overlay(cast(CanvasSelectionOverlayHost, host))
    draw_annotations(cast(CanvasAnnotationHost, host))
    draw_annotation_labels(cast(CanvasAnnotationHost, host))
    draw_overlapping_edges(cast(CanvasOverlapHost, host))
    draw_merge_primary_highlight(cast(CanvasEditOverlayHost, host))
    draw_multi_selected_annotations(cast(CanvasEditOverlayHost, host))
    draw_selected_vertices(cast(CanvasAnnotationHost, host))
    draw_temp_polygon(cast(CanvasEditOverlayHost, host))
    draw_new_snap_context_vertices(cast(CanvasEditOverlayHost, host))
    draw_annotation_selection_rect(cast(CanvasSelectionOverlayHost, host))
    draw_arrows(cast(CanvasArrowHost, host))
    draw_temp_arrow(cast(CanvasArrowHost, host))
    draw_guides(cast(CanvasGuideHost, host))
    draw_snap_preview_dot(cast(CanvasGuideHost, host))
    draw_selected_vertex_ids(cast(VertexLabelHost, host))
    host.widgets.viewer.canvas.tag_raise("annotation_label")
    update_pointer_dependent_layers(host)
    update_image_status(cast(StatusHost, host))


def clear_unloaded_canvas(host: CanvasRenderHost) -> None:
    """Clear retained render state and status for an unloaded view."""

    host.widgets.viewer.canvas.configure(scrollregion=(0, 0, 0, 0))
    host.photo_image = None
    host.photo_image_key = None
    host.view.annotation_overlay_image = None
    host.annotation_overlay_photo = None
    host.annotation_overlay_key = None
    host.selection_overlay_photo = None
    update_image_status(cast(StatusHost, host))
    update_edit_summary(cast(StatusHost, host))


def place_base_image(host: CanvasRenderHost) -> None:
    """Resize, cache, place, and scroll-bound the current base image."""

    current_image = cast(Image.Image, host.view.current_image)
    viewport_width = max(1, host.widgets.viewer.canvas.winfo_width())
    viewport_height = max(1, host.widgets.viewer.canvas.winfo_height())
    width = max(1, int(round(current_image.width * host.view.zoom)))
    height = max(1, int(round(current_image.height * host.view.zoom)))
    host.view.display_size = (width, height)
    origin_x = max(0.0, (viewport_width - width) / 2)
    origin_y = max(0.0, (viewport_height - height) / 2)
    host.view.image_origin = (origin_x, origin_y)
    photo_key = (id(current_image), width, height)
    if host.photo_image is None or host.photo_image_key != photo_key:
        resized = current_image.resize((width, height), Image.Resampling.LANCZOS)
        host.photo_image = ImageTk.PhotoImage(resized)
        host.photo_image_key = photo_key
    host.widgets.viewer.canvas.create_image(
        origin_x,
        origin_y,
        image=host.photo_image,
        anchor=tk.NW,
        tags=("image",),
    )
    host.widgets.viewer.canvas.configure(
        scrollregion=(
            0,
            0,
            max(viewport_width, width + origin_x),
            max(viewport_height, height + origin_y),
        )
    )


def update_pointer_dependent_layers(host: CanvasRenderHost) -> None:
    """Refresh tooltip and zoom layers for the current cursor position."""

    if host.view.cursor_canvas_point is None:
        return
    image_point = image_point_from_canvas(
        host.view.cursor_canvas_point, host.view
    )
    update_hover_class_tooltip(
        cast(CanvasTooltipHost, host),
        host.view.cursor_canvas_point,
        image_point,
    )
    if image_point is not None:
        update_zoom_preview(cast(ZoomPreviewHost, host), image_point)
    else:
        clear_zoom_preview(cast(ZoomPreviewHost, host))
