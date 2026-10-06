"""Functional cancellation of active annotation interactions."""

from __future__ import annotations

from typing import Protocol
from typing import cast

from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.selection import clear_annotation_selection
from annotator.gui.state import InteractionState


class AnnotationCancellationHost(Protocol):
    """State and effects required to cancel an annotation interaction."""

    interaction: InteractionState

    def update_canvas_cursor(self) -> None: ...

# CMP: TODO - Update this functions docstrings, and module docstrings as well.
def cancel_selection_or_mode(host: AnnotationCancellationHost) -> None:
    """Clear the active selection or edit mode and refresh changed UI state."""

    interaction = host.interaction
    was_select_start = interaction.mode == "select_start"
    changed = bool(
        interaction.selected_vertices
        or interaction.selection_rect
        or interaction.selection_drag_start
        or interaction.mode
        or interaction.temp_polygon
        or interaction.merge_primary_index is not None
        or interaction.temp_arrow_start is not None
        or interaction.selected_arrow_index is not None
        or interaction.selected_arrow_indices
    )
    if was_select_start:
        clear_annotation_selection(interaction)
    interaction.selected_vertices.clear()
    interaction.selection_rect = None
    interaction.selection_drag_start = None
    interaction.selection_drag_current = None
    interaction.annotation_selection_drag_start = None
    interaction.annotation_selection_drag_current = None
    interaction.annotation_selection_rect = None
    interaction.mode = None
    interaction.temp_polygon = []
    interaction.temp_edge_insertions = []
    interaction.edit_started_at_monotonic_ns = None
    interaction.drag_vertex_ref = None
    interaction.drag_rectangle_side_ref = None
    interaction.drag_vertex_original_point = None
    interaction.drag_shared_vertex_refs = []
    interaction.drag_rectangle_context = None
    interaction.merge_primary_index = None
    interaction.temp_arrow_start = None
    interaction.temp_arrow_current = None
    interaction.selected_arrow_index = None
    interaction.selected_arrow_indices.clear()
    if changed:
        host.update_canvas_cursor()
        redraw_canvas(cast(CanvasRenderHost, host))
