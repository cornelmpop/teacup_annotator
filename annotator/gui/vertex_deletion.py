"""Delete selected free-polygon vertices as an edit effect."""

from __future__ import annotations

from typing import Protocol
from typing import cast

from annotator.gui.audit.undo import push_undo
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.persistence import AutosaveHost
from annotator.gui.persistence import autosave_current_image
from annotator.gui.project.navigation import current_image_name
from annotator.gui.render_state import RenderStateHost
from annotator.gui.render_state import mark_annotations_changed
from annotator.gui.selection import clear_annotation_selection
from annotator.gui.selection import current_annotations
from annotator.gui.selection import selected_annotation_is_rectangle
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState


class VertexDeletionHost(AutosaveHost, RenderStateHost, Protocol):
    """Application state and effects required to delete selected vertices."""

    project: ProjectState
    interaction: InteractionState

# CMP: TODO - Clarify docstring: what rectangle?! It would also be helpful
# if the steps and their reason were outlined so the logic is easy to check.
def delete_selected_vertices(host: VertexDeletionHost) -> None:
    """Delete vertices selected by the rectangle."""

    # CMP: TODO - clarify under what circumstances the function would be
    # called if these conditions are met. Rationale: to determine whether
    # this is something that should be logged rather than returning silently
    if (
        host.project.coco is None
        or host.interaction.selected_annotation_index is None
        or not host.interaction.selected_vertices
        or selected_annotation_is_rectangle(host.project, host.interaction)
    ):
        return
    
    push_undo(
        host,
        action="delete_vertices",
        annotation_index=host.interaction.selected_annotation_index,
        details={"vertex_refs": sorted(host.interaction.selected_vertices)},
    )
    host.project.coco.delete_vertices(
        current_image_name(host),
        host.interaction.selected_annotation_index,
        host.interaction.selected_vertices,
    )
    if host.interaction.selected_annotation_index >= len(
        current_annotations(host.project)
    ):
        clear_annotation_selection(host.interaction)
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    mark_annotations_changed(cast(RenderStateHost, host))
    host.project.dirty = True
    autosave_current_image(cast(AutosaveHost, host))
    redraw_canvas(cast(CanvasRenderHost, host))
