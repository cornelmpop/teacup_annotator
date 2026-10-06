"""Translate secondary and middle-button presses into editing effects."""

from __future__ import annotations

import tkinter as tk
from typing import cast

from annotator.gui.audit.undo import push_undo
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.hit_testing import vertex_at
from annotator.gui.arrow_interaction import ArrowInteractionHost
from annotator.gui.arrow_interaction import arrow_endpoint_at
from annotator.gui.arrow_interaction import begin_arrow_endpoint_drag
from annotator.gui.context_menus import ContextMenuHost
from annotator.gui.context_menus import show_canvas_menu
from annotator.gui.input.state import PointerHost
from annotator.gui.interactions import InputAction
from annotator.gui.interactions import PointerFacts
from annotator.gui.interactions import middle_press_transition
from annotator.gui.interactions import right_press_transition
from annotator.gui.persistence import AutosaveHost
from annotator.gui.persistence import autosave_current_image
from annotator.gui.project.navigation import current_image_name
from annotator.gui.render_state import mark_annotations_changed
from annotator.gui.selection import clear_annotation_selection
from annotator.gui.selection import current_annotations
from annotator.gui.selection import multiple_annotations_selected
from annotator.gui.selection import point_inside_selection
from annotator.gui.selection import selected_annotation
from annotator.gui.selection import selected_annotation_is_rectangle
from annotator.gui.view_geometry import canvas_event_point
from annotator.gui.vertex_editing import VertexEditingHost
from annotator.gui.vertex_editing import begin_vertex_drag
from annotator.gui.vertex_selection_menu import VertexSelectionMenuHost
from annotator.gui.vertex_selection_menu import show_vertex_selection_menu


def on_right_press(host: PointerHost, event: tk.Event) -> str:
    """Apply the drag or menu transition selected by a right press."""

    if host.interaction.worker_running:
        return "break"
    host.widgets.viewer.canvas.focus_set()
    canvas_point = canvas_event_point(host.widgets.viewer.canvas, event)
    host.view.cursor_canvas_point = canvas_point
    annotation = selected_annotation(host.project, host.interaction)
    arrow_endpoint_index = arrow_endpoint_at(
        cast(ArrowInteractionHost, host),
        canvas_point,
    )
    selected_vertex_ref = vertex_at(annotation, canvas_point, host.view)
    transition = right_press_transition(
        host.interaction,
        PointerFacts(
            canvas_point=canvas_point,
            arrow_endpoint_index=arrow_endpoint_index,
            vertex_ref=selected_vertex_ref,
            multiple_annotations_selected=multiple_annotations_selected(
                host.interaction
            ),
            inside_vertex_selection=point_inside_selection(
                host.interaction,
                canvas_point,
            ),
        ),
    )
    host.interaction = transition.interaction
    if transition.action is InputAction.BEGIN_ARROW_ENDPOINT_DRAG:
        begin_arrow_endpoint_drag(
            cast(ArrowInteractionHost, host),
            arrow_endpoint_index,  # type: ignore[arg-type]
        )
    elif transition.action is InputAction.BEGIN_VERTEX_DRAG:
        begin_vertex_drag(
            cast(VertexEditingHost, host),
            selected_vertex_ref,  # type: ignore[arg-type]
        )
    elif transition.action is InputAction.SHOW_VERTEX_SELECTION_MENU:
        show_vertex_selection_menu(
            cast(VertexSelectionMenuHost, host),
            event,
        )
    else:
        show_canvas_menu(cast(ContextMenuHost, host), event)
    return "break"

# CMP: TODO - Change function name so that it is explicit about what
#      action is performed. As is, when called from a different module, that
#      action is not immediately obvious on review.
def on_middle_press(host: PointerHost, event: tk.Event) -> str | None:
    """Apply free-polygon vertex deletion selected by a middle press."""

    if host.interaction.worker_running:
        return "break"
    canvas_point = canvas_event_point(host.widgets.viewer.canvas, event)
    annotation = selected_annotation(host.project, host.interaction)
    vertex_ref = vertex_at(annotation, canvas_point, host.view)
    transition = middle_press_transition(
        host.interaction,
        PointerFacts(
            canvas_point=canvas_point,
            vertex_ref=vertex_ref,
            selected_annotation_is_rectangle=(
                selected_annotation_is_rectangle(
                    host.project,
                    host.interaction,
                )
            ),
        ),
    )
    if transition.action is not InputAction.DELETE_VERTEX:
        return None
    host.interaction = transition.interaction
    push_undo(
        host,
        action="delete_vertex",
        annotation_index=host.interaction.selected_annotation_index,
        details={"vertex_ref": vertex_ref},
    )
    host.project.coco.delete_vertices(  # type: ignore[union-attr]
        current_image_name(host),
        host.interaction.selected_annotation_index or 0,
        {vertex_ref},  # type: ignore[arg-type]
    )
    if (
        host.interaction.selected_annotation_index is not None
        and host.interaction.selected_annotation_index
        >= len(current_annotations(host.project))
    ):
        clear_annotation_selection(host.interaction)
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    mark_annotations_changed(host)
    host.project.dirty = True
    autosave_current_image(cast(AutosaveHost, host))
    redraw_canvas(cast(CanvasRenderHost, host))
    return "break"
