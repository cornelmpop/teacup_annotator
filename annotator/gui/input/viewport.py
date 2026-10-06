"""Viewport cursor, zoom, reset, and scrolling effects."""

from __future__ import annotations

import math
from typing import cast

from annotator.geom.coordinates import map_point_between_spaces
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.arrow_interaction import ArrowInteractionHost
from annotator.gui.arrow_interaction import arrow_endpoint_at
from annotator.gui.arrow_interaction import arrow_index_at
from annotator.gui.canvas_guides import CanvasGuideHost
from annotator.gui.canvas_guides import draw_guides
from annotator.gui.constants import MAX_ZOOM
from annotator.gui.constants import ZOOM_STEP
from annotator.gui.hit_testing import annotation_contains
from annotator.gui.hit_testing import vertex_at
from annotator.gui.input.state import MotionHost
from annotator.gui.interactions import MIN_ZOOM
from annotator.gui.interactions import canvas_cursor
from annotator.gui.interactions import scroll_pixels_for_zoom
from annotator.gui.render_state import invalidate_annotation_overlay
from annotator.gui.render_state import invalidate_display_cache
from annotator.gui.selection import selected_annotation
from annotator.gui.view_geometry import fit_zoom
from annotator.gui.view_geometry import image_point_from_canvas
from annotator.gui.view_geometry import scrollregion_size
from annotator.gui.zoom_preview import ZoomPreviewHost
from annotator.gui.zoom_preview import clear_zoom_preview
from annotator.gui.zoom_preview import update_zoom_preview


def update_canvas_cursor(host: MotionHost) -> None:
    """Show the cursor appropriate to the current mode and editable target."""

    fixed_cursor = canvas_cursor(
        host.interaction,
        cursor_point_present=host.view.cursor_canvas_point is not None,
        over_selected_annotation=False,
        over_selected_arrow=False,
    )
    if host.interaction.worker_running or host.interaction.mode in {
        "new",
        "new_rectangle",
        "arrow",
        "select_start",
    }:
        host.set_canvas_cursor(fixed_cursor)
        return
    if host.view.cursor_canvas_point is None:
        host.set_canvas_cursor(fixed_cursor)
        return
    canvas_point = host.view.cursor_canvas_point
    image_point = image_point_from_canvas(canvas_point, host.view)
    annotation = selected_annotation(host.project, host.interaction)
    over_selected_annotation = annotation is not None and (
        vertex_at(annotation, canvas_point, host.view) is not None
        or annotation_contains(annotation, image_point)
    )
    over_selected_arrow = host.interaction.selected_arrow_index is not None and (
        arrow_endpoint_at(
            cast(ArrowInteractionHost, host),
            canvas_point,
        )
        is not None
        or (
            image_point is not None
            and arrow_index_at(
                cast(ArrowInteractionHost, host),
                image_point,
            )
            == host.interaction.selected_arrow_index
        )
    )
    host.set_canvas_cursor(
        canvas_cursor(
            host.interaction,
            cursor_point_present=True,
            over_selected_annotation=over_selected_annotation,
            over_selected_arrow=over_selected_arrow,
        )
    )


# CMP: TODO - Refactor potential - I think the math is implemented at other call sites
# as well, independently.
def zoom_at(
    host: MotionHost,
    direction: int,
    event_x: int | None = None,
    event_y: int | None = None,
) -> None:
    """Zoom around the pointer or viewport center."""

    if host.view.current_image is None:
        return
    old_zoom = host.view.zoom
    next_zoom = old_zoom * (ZOOM_STEP if direction > 0 else 1 / ZOOM_STEP)
    host.view.zoom = max(MIN_ZOOM, min(MAX_ZOOM, next_zoom))
    if math.isclose(host.view.zoom, old_zoom):
        return

    canvas = host.widgets.viewer.canvas
    canvas_width = max(1, canvas.winfo_width())
    canvas_height = max(1, canvas.winfo_height())
    if event_x is None:
        event_x = canvas_width // 2
    if event_y is None:
        event_y = canvas_height // 2
    old_canvas_x = canvas.canvasx(event_x)
    old_canvas_y = canvas.canvasy(event_y)
    image_x, image_y = map_point_between_spaces(
        (old_canvas_x, old_canvas_y),
        source_origin=host.view.image_origin,
        scale=(1 / old_zoom, 1 / old_zoom),
    )

    redraw_canvas(cast(CanvasRenderHost, host))

    scroll_width, scroll_height = scrollregion_size(
        str(canvas.cget("scrollregion"))
    )
    anchor_x, anchor_y = map_point_between_spaces(
        (image_x, image_y),
        target_origin=host.view.image_origin,
        scale=(host.view.zoom, host.view.zoom),
    )
    target_left = anchor_x - event_x
    target_top = anchor_y - event_y
    canvas.xview_moveto(max(0.0, min(1.0, target_left / scroll_width)))
    canvas.yview_moveto(max(0.0, min(1.0, target_top / scroll_height)))
    host.view.cursor_canvas_point = (
        canvas.canvasx(event_x),
        canvas.canvasy(event_y),
    )
    draw_guides(cast(CanvasGuideHost, host))
    if (
        0 <= image_x <= host.view.current_image.width
        and 0 <= image_y <= host.view.current_image.height
    ):
        update_zoom_preview(
            cast(ZoomPreviewHost, host),
            (image_x, image_y),
        )
    else:
        clear_zoom_preview(cast(ZoomPreviewHost, host))


def reset_zoom(host: MotionHost) -> None:
    """Reset the current image to its fitted default zoom."""

    if host.view.current_image is None:
        return
    canvas = host.widgets.viewer.canvas
    canvas.update_idletasks()
    host.view.zoom = fit_zoom(
        (host.view.current_image.width, host.view.current_image.height),
        (canvas.winfo_width(), canvas.winfo_height()),
    )
    invalidate_display_cache(host)
    invalidate_annotation_overlay(host)
    redraw_canvas(cast(CanvasRenderHost, host))
    draw_guides(cast(CanvasGuideHost, host))


def scroll_by_wheel(
    host: MotionHost,
    horizontal: bool,
    direction: int,
) -> None:
    """Scroll by a stable image-pixel distance at the current zoom."""

    if direction == 0:
        return
    canvas = host.widgets.viewer.canvas
    scroll_width, scroll_height = scrollregion_size(
        str(canvas.cget("scrollregion"))
    )
    amount = scroll_pixels_for_zoom(direction, host.view.zoom)
    if horizontal:
        target_left = canvas.canvasx(0) + amount
        canvas.xview_moveto(
            max(0.0, min(1.0, target_left / scroll_width))
        )
        return
    target_top = canvas.canvasy(0) + amount
    canvas.yview_moveto(max(0.0, min(1.0, target_top / scroll_height)))
