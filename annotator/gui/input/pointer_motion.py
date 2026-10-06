"""Translate pointer motion, leave, and wheel events into view effects."""

from __future__ import annotations

import tkinter as tk
from typing import cast

from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.canvas_edit_overlays import CanvasEditOverlayHost
from annotator.gui.canvas_edit_overlays import draw_new_snap_context_vertices
from annotator.gui.canvas_edit_overlays import draw_temp_polygon
from annotator.gui.canvas_guides import CanvasGuideHost
from annotator.gui.canvas_guides import draw_guides
from annotator.gui.canvas_guides import draw_snap_preview_dot
from annotator.gui.canvas_tooltips import CanvasTooltipHost
from annotator.gui.canvas_tooltips import update_hover_class_tooltip
from annotator.gui.input.state import MotionHost
from annotator.gui.input.state import Point
from annotator.gui.input.viewport import scroll_by_wheel
from annotator.gui.input.viewport import update_canvas_cursor
from annotator.gui.input.viewport import zoom_at
from annotator.gui.interactions import InputAction
from annotator.gui.interactions import PointerFacts
from annotator.gui.interactions import mouse_leave_transition
from annotator.gui.interactions import mouse_motion_transition
from annotator.gui.interactions import wheel_axis_and_direction
from annotator.gui.interactions import wheel_transition
from annotator.gui.view_geometry import canvas_event_point
from annotator.gui.view_geometry import image_point_from_canvas
from annotator.gui.zoom_preview import ZoomPreviewHost
from annotator.gui.zoom_preview import clear_zoom_preview
from annotator.gui.zoom_preview import update_zoom_preview


def on_mouse_motion(host: MotionHost, event: tk.Event) -> None:
    """Apply the display transition selected by pointer motion."""

    host.view.cursor_canvas_point = canvas_event_point(
        host.widgets.viewer.canvas,
        event,
    )
    image_point = image_point_from_canvas(
        host.view.cursor_canvas_point,
        host.view,
    )
    transition = mouse_motion_transition(
        host.interaction,
        PointerFacts(
            canvas_point=host.view.cursor_canvas_point,
            image_point=image_point,
        ),
    )
    host.interaction = transition.interaction
    draw_guides(cast(CanvasGuideHost, host))
    draw_snap_preview_dot(cast(CanvasGuideHost, host))
    update_canvas_cursor(host)
    if transition.action is InputAction.MOTION_OUTSIDE_IMAGE:
        clear_zoom_preview(cast(ZoomPreviewHost, host))
        host.widgets.viewer.canvas.delete("class_tooltip")
    elif transition.action is InputAction.MOTION_ARROW:
        redraw_canvas(cast(CanvasRenderHost, host))
    elif transition.action is InputAction.MOTION_NEW_POLYGON:
        canvas = host.widgets.viewer.canvas
        canvas.delete("temp_polygon")
        canvas.delete("temp_vertex")
        canvas.delete("snap_context_vertex")
        draw_temp_polygon(cast(CanvasEditOverlayHost, host))
        draw_new_snap_context_vertices(cast(CanvasEditOverlayHost, host))
        update_image_dependent_motion_layers(host, image_point)
    else:
        update_image_dependent_motion_layers(host, image_point)


def update_image_dependent_motion_layers(
    host: MotionHost,
    image_point: Point | None,
) -> None:
    """CODEX: Refresh zoom and tooltip layers only for real image points."""

    if image_point is None:
        clear_zoom_preview(cast(ZoomPreviewHost, host))
        host.widgets.viewer.canvas.delete("class_tooltip")
        return
    update_zoom_preview(cast(ZoomPreviewHost, host), image_point)
    update_hover_class_tooltip(
        cast(CanvasTooltipHost, host),
        host.view.cursor_canvas_point,
        image_point,
    )


def on_mouse_leave(host: MotionHost, _event: tk.Event) -> None:
    """Apply the display cleanup selected when the pointer leaves."""

    host.view.cursor_canvas_point = None
    transition = mouse_leave_transition(host.interaction)
    host.interaction = transition.interaction
    draw_guides(cast(CanvasGuideHost, host))
    host.widgets.viewer.canvas.delete("snap_preview")
    clear_zoom_preview(cast(ZoomPreviewHost, host))
    host.widgets.viewer.canvas.delete("class_tooltip")
    update_canvas_cursor(host)
    if transition.redraw:
        redraw_canvas(cast(CanvasRenderHost, host))


def on_mouse_wheel(host: MotionHost, event: tk.Event) -> str:
    """Scroll the viewer, or zoom when the z key is held."""

    reverse_horizontal = host.prefs.get_bool("reverse_horizontal_wheel", True)
    horizontal, direction = wheel_axis_and_direction(
        event,
        reverse_horizontal,
    )
    transition = wheel_transition(
        host.interaction,
        horizontal=horizontal,
        direction=direction,
    )
    host.interaction = transition.interaction
    if transition.action is InputAction.ZOOM_AT_POINTER:
        zoom_at(host, 1 if direction < 0 else -1, event.x, event.y)
    elif transition.action is InputAction.SCROLL_HORIZONTAL:
        scroll_by_wheel(host, horizontal=True, direction=direction)
        draw_guides(cast(CanvasGuideHost, host))
    elif transition.action is InputAction.SCROLL_VERTICAL:
        scroll_by_wheel(host, horizontal=False, direction=direction)
        draw_guides(cast(CanvasGuideHost, host))
    return "break"
