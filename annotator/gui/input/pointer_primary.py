"""Translate primary-button presses into annotation editing effects."""

from __future__ import annotations

import tkinter as tk
from typing import cast

from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.annotation_deletion import AnnotationDeletionHost
from annotator.gui.annotation_deletion import delete_annotation_at
from annotator.gui.annotation_cancellation import AnnotationCancellationHost
from annotator.gui.annotation_cancellation import cancel_selection_or_mode
from annotator.gui.annotation_merging import AnnotationMergingHost
from annotator.gui.annotation_merging import finish_merge_annotation_at
from annotator.gui.arrow_editing import ArrowEditingHost
from annotator.gui.arrow_editing import handle_arrow_click
from annotator.gui.arrow_interaction import ArrowInteractionHost
from annotator.gui.arrow_interaction import arrow_endpoint_at
from annotator.gui.arrow_interaction import arrow_index_at
from annotator.gui.arrow_interaction import begin_arrow_endpoint_drag
from annotator.gui.hit_testing import annotation_border_at
from annotator.gui.hit_testing import annotation_index_at
from annotator.gui.hit_testing import rectangle_side_at
from annotator.gui.hit_testing import vertex_at
from annotator.gui.input.state import PointerHost
from annotator.gui.interactions import InputAction
from annotator.gui.interactions import PointerFacts
from annotator.gui.interactions import left_press_transition
from annotator.gui.new_polygon_completion import NewPolygonHost
from annotator.gui.new_polygon_points import add_new_polygon_point
from annotator.gui.polygon_start import PolygonStartHost
from annotator.gui.polygon_start import finish_select_start_at
from annotator.gui.selection import current_annotations
from annotator.gui.selection import selected_annotation
from annotator.gui.selection import selected_annotation_is_rectangle
from annotator.gui.snap_graph import snapping_tolerance_image
from annotator.gui.snapping import snapped_edit_point
from annotator.gui.view_geometry import canvas_event_point
from annotator.gui.view_geometry import image_point_from_canvas
from annotator.gui.vertex_editing import VertexEditingHost
from annotator.gui.vertex_editing import begin_rectangle_side_drag
from annotator.gui.vertex_editing import begin_vertex_drag
from annotator.gui.vertex_editing import insert_vertex_at

# CMP: TODO - Whoa! Improve documentation. This function is quite complex
#      and the docstrings don't lay out the logic.
def on_left_press(host: PointerHost, event: tk.Event) -> str | None:
    """Apply the transition selected by a left-button press."""

    if host.interaction.worker_running:
        return "break"
    host.widgets.viewer.canvas.focus_set()
    canvas_point = canvas_event_point(host.widgets.viewer.canvas, event)
    host.view.cursor_canvas_point = canvas_point
    image_point = image_point_from_canvas(canvas_point, host.view)
    annotation = selected_annotation(host.project, host.interaction)
    annotations = current_annotations(host.project)
    annotation_index = (
        annotation_index_at(annotations, image_point)
        if image_point is not None
        else None
    )
    arrow_endpoint_index = arrow_endpoint_at(
        cast(ArrowInteractionHost, host),
        canvas_point,
    )
    selected_vertex_ref = vertex_at(annotation, canvas_point, host.view)
    selected_is_rectangle = selected_annotation_is_rectangle(
        host.project,
        host.interaction,
    )
    rectangle_side_ref = None
    border_ref = None
    if (
        image_point is not None
        and annotation is not None
        and selected_is_rectangle
        and selected_vertex_ref is None
    ):
        rectangle_side_ref = rectangle_side_at(
            annotation,
            canvas_point,
            host.view,
        )
    if (
        image_point is not None
        and annotation is not None
        and not selected_is_rectangle
        and selected_vertex_ref is None
    ):
        border_ref = annotation_border_at(annotation, canvas_point, host.view)
    arrow_index = (
        arrow_index_at(cast(ArrowInteractionHost, host), image_point)
        if image_point is not None
        else None
    )
    transition = left_press_transition(
        host.interaction,
        PointerFacts(
            canvas_point=canvas_point,
            image_point=image_point,
            annotation_index=annotation_index,
            arrow_index=arrow_index,
            arrow_endpoint_index=arrow_endpoint_index,
            vertex_ref=selected_vertex_ref,
            rectangle_side_ref=rectangle_side_ref,
            border_ref=border_ref,
            selected_annotation_present=annotation is not None,
            selected_annotation_is_rectangle=selected_is_rectangle,
        ),
    )
    host.interaction = transition.interaction
    if transition.redraw:
        redraw_canvas(cast(CanvasRenderHost, host))

    if transition.action is InputAction.CANCEL_SELECTION_OR_MODE:
        cancel_selection_or_mode(cast(AnnotationCancellationHost, host))
    elif transition.action is InputAction.FINISH_SELECT_START:
        finish_select_start_at(
            cast(PolygonStartHost, host),
            image_point,  # type: ignore[arg-type]
            canvas_point,
        )
    elif transition.action is InputAction.ADD_NEW_POLYGON_POINT:
        add_new_polygon_point(
            cast(NewPolygonHost, host),
            image_point,  # type: ignore[arg-type]
            canvas_point,
        )
    elif transition.action is InputAction.HANDLE_ARROW_CLICK:
        handle_arrow_click(
            cast(ArrowEditingHost, host),
            image_point,  # type: ignore[arg-type]
        )
    elif transition.action is InputAction.FINISH_MERGE:
        finish_merge_annotation_at(
            cast(AnnotationMergingHost, host),
            image_point,  # type: ignore[arg-type]
        )
    elif transition.action is InputAction.DELETE_AT_POINT:
        delete_annotation_at(cast(AnnotationDeletionHost, host), canvas_point)
    elif transition.action is InputAction.BEGIN_ARROW_ENDPOINT_DRAG:
        begin_arrow_endpoint_drag(
            cast(ArrowInteractionHost, host),
            arrow_endpoint_index,  # type: ignore[arg-type]
        )
    elif transition.action is InputAction.BEGIN_VERTEX_DRAG:
        begin_vertex_drag(
            cast(VertexEditingHost, host),
            selected_vertex_ref,  # type: ignore[arg-type]
        )
    elif transition.action is InputAction.BEGIN_RECTANGLE_SIDE_DRAG:
        begin_rectangle_side_drag(
            cast(VertexEditingHost, host),
            rectangle_side_ref,  # type: ignore[arg-type]
        )
    elif transition.action is InputAction.INSERT_VERTEX:
        insert_vertex_at(
            cast(VertexEditingHost, host),
            border_ref,  # type: ignore[arg-type]
            snapped_edit_point(
                host.project,
                host.view,
                host.interaction,
                image_point,  # type: ignore[arg-type]
                host.snap_edits_var.get(),
                snapping_tolerance_image(host.prefs, host.view),
            ),
        )
    elif transition.action is InputAction.START_PAN:
        host.widgets.viewer.canvas.scan_mark(event.x, event.y)

    return "break" if transition.consumed else None
