"""Translate pointer drags and releases into annotation editing effects."""

from __future__ import annotations

import tkinter as tk
from typing import cast

from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.annotation_modes import AnnotationModeHost
from annotator.gui.annotation_modes import finish_new_rectangle_annotation
from annotator.gui.arrow_interaction import ArrowInteractionHost
from annotator.gui.arrow_interaction import drag_selected_arrow_endpoint_to
from annotator.gui.arrow_interaction import finish_arrow_endpoint_drag
from annotator.gui.canvas_guides import CanvasGuideHost
from annotator.gui.canvas_guides import draw_guides
from annotator.gui.input.state import PointerHost
from annotator.gui.interactions import InputAction
from annotator.gui.interactions import PointerFacts
from annotator.gui.interactions import completed_drag_rect
from annotator.gui.interactions import left_drag_transition
from annotator.gui.interactions import left_release_transition
from annotator.gui.interactions import right_drag_transition
from annotator.gui.interactions import right_release_transition
from annotator.gui.selection import select_objects_in_rect
from annotator.gui.selection import vertices_in_selection
from annotator.gui.view_geometry import canvas_event_point
from annotator.gui.view_geometry import clamp_canvas_point_to_image
from annotator.gui.view_geometry import image_point_from_canvas
from annotator.gui.vertex_editing import VertexEditingHost
from annotator.gui.vertex_editing import drag_selected_vertex_to
from annotator.gui.vertex_editing import finish_vertex_drag


def on_left_drag(host: PointerHost, event: tk.Event) -> str | None:
    """Apply the transition selected by a left-button drag."""

    if host.interaction.worker_running:
        return "break"
    canvas_point = canvas_event_point(host.widgets.viewer.canvas, event)
    host.view.cursor_canvas_point = canvas_point
    image_point = image_point_from_canvas(canvas_point, host.view)
    drag_point = image_point
    if drag_point is None and (
        host.interaction.drag_vertex_ref is not None
        or host.interaction.drag_rectangle_side_ref is not None
    ):
        drag_point = clamp_canvas_point_to_image(canvas_point, host.view)
    transition = left_drag_transition(
        host.interaction,
        PointerFacts(canvas_point=canvas_point, image_point=image_point),
    )
    host.interaction = transition.interaction
    if transition.action is InputAction.DRAG_ARROW_ENDPOINT:
        drag_selected_arrow_endpoint_to(
            cast(ArrowInteractionHost, host),
            image_point,  # type: ignore[arg-type]
        )
    elif transition.action is InputAction.DRAG_VERTEX:
        drag_selected_vertex_to(
            cast(VertexEditingHost, host),
            drag_point,  # type: ignore[arg-type]
        )
    elif transition.action is InputAction.PAN:
        host.widgets.viewer.canvas.scan_dragto(event.x, event.y, gain=1)
        draw_guides(cast(CanvasGuideHost, host))
    if transition.redraw:
        redraw_canvas(cast(CanvasRenderHost, host))
    return "break" if transition.consumed else None


def on_left_release(host: PointerHost, event: tk.Event) -> str | None:
    """Apply the transition selected by a left-button release."""

    if host.interaction.worker_running:
        return "break"
    canvas_point = canvas_event_point(host.widgets.viewer.canvas, event)
    host.view.cursor_canvas_point = canvas_point
    selection_rect = completed_drag_rect(
        host.interaction.selection_drag_start,
        canvas_point,
    )
    annotation_selection_rect = completed_drag_rect(
        host.interaction.annotation_selection_drag_start,
        canvas_point,
    )
    selecting_vertices = host.interaction.selection_drag_start is not None
    transition = left_release_transition(
        host.interaction,
        PointerFacts(
            canvas_point=canvas_point,
            selection_rect=(
                selection_rect
                if selecting_vertices
                else annotation_selection_rect
            ),
        ),
    )
    host.interaction = transition.interaction
    if selecting_vertices:
        host.interaction.selected_vertices = vertices_in_selection(
            host.project,
            host.view,
            host.interaction,
        )

    if transition.action is InputAction.FINISH_ARROW_ENDPOINT_DRAG:
        finish_arrow_endpoint_drag(cast(ArrowInteractionHost, host))
    elif transition.action is InputAction.FINISH_VERTEX_DRAG:
        finish_vertex_drag(cast(VertexEditingHost, host))
    elif transition.action is InputAction.FINISH_NEW_RECTANGLE:
        finish_new_rectangle_annotation(cast(AnnotationModeHost, host))
    elif transition.action is InputAction.SELECT_OBJECTS_IN_RECT:
        select_objects_in_rect(
            host.project,
            host.view,
            host.interaction,
            annotation_selection_rect,
        )
    if transition.redraw:
        redraw_canvas(cast(CanvasRenderHost, host))
    return "break" if transition.consumed else None


def on_right_drag(host: PointerHost, event: tk.Event) -> str | None:
    """Apply the active endpoint or vertex right-drag transition."""

    if host.interaction.worker_running:
        return "break"
    transition = right_drag_transition(host.interaction)
    if not transition.consumed:
        return None
    canvas_point = canvas_event_point(host.widgets.viewer.canvas, event)
    image_point = image_point_from_canvas(canvas_point, host.view)
    if image_point is None:
        image_point = clamp_canvas_point_to_image(canvas_point, host.view)
    host.interaction = transition.interaction
    if transition.action is InputAction.DRAG_ARROW_ENDPOINT:
        drag_selected_arrow_endpoint_to(
            cast(ArrowInteractionHost, host),
            image_point,
        )
    else:
        drag_selected_vertex_to(cast(VertexEditingHost, host), image_point)
        host.view.cursor_canvas_point = canvas_point
    if transition.redraw:
        redraw_canvas(cast(CanvasRenderHost, host))
    return "break"


def on_right_release(host: PointerHost, _event: tk.Event) -> str | None:
    """Apply the active endpoint or vertex completion transition."""

    if host.interaction.worker_running:
        return "break"
    transition = right_release_transition(host.interaction)
    host.interaction = transition.interaction
    if transition.action is InputAction.FINISH_ARROW_ENDPOINT_DRAG:
        finish_arrow_endpoint_drag(cast(ArrowInteractionHost, host))
    elif transition.action is InputAction.FINISH_VERTEX_DRAG:
        finish_vertex_drag(cast(VertexEditingHost, host))
    return "break" if transition.consumed else None
