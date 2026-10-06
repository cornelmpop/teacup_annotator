"""CODEX: Decode active images and clear transient state only after successful loads."""

from __future__ import annotations

from typing import Any
from typing import Protocol
from typing import cast

from PIL import Image
from tkinter import messagebox

from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.class_panel import ClassPanelHost
from annotator.gui.class_panel import refresh_class_panel
from annotator.gui.project.navigation import persist_current_image_position
from annotator.gui.project.navigation import record_current_image_view
from annotator.gui.project.navigation import ViewAuditHost
from annotator.gui.project.status import StatusHost
from annotator.gui.project.status import update_buttons
from annotator.gui.project.status import update_edit_summary
from annotator.gui.project.status import update_image_index_entry
from annotator.gui.render_state import RenderStateHost
from annotator.gui.render_state import invalidate_annotation_overlay
from annotator.gui.render_state import invalidate_display_cache
from annotator.gui.selection import clear_annotation_selection
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState
from annotator.gui.view_geometry import fit_zoom


class ImageLoadingHost(RenderStateHost, StatusHost, ViewAuditHost, Protocol):
    """Application state and effects required by image loading."""

    project: ProjectState
    view: ViewState
    interaction: InteractionState
    widgets: Any
    photo_image: Any | None

    def set_canvas_cursor(self, cursor: str = "") -> None:
        """Set the main canvas cursor."""

        ...


def load_current_image(host: ImageLoadingHost) -> bool:
    """CODEX: Load the current target and report whether its pixels were published."""

    if not host.project.image_paths:
        host.view.current_image = None
        host.photo_image = None
        clear_view_interaction_state(host)
        refresh_class_panel(cast(ClassPanelHost, host))
        update_image_index_entry(host, force=True)
        update_edit_summary(host)
        redraw_canvas(cast(CanvasRenderHost, host))
        return True

    image_path = host.project.image_paths[host.project.current_index]
    try:
        with Image.open(image_path) as image:
            current_image = image.convert("RGB")
            host.view.current_image = current_image
    except OSError as exc:
        messagebox.showerror("Could not open image", str(exc))
        return False

    host.widgets.viewer.canvas.update_idletasks()
    host.view.zoom = fit_zoom(
        (current_image.width, current_image.height),
        (
            host.widgets.viewer.canvas.winfo_width(),
            host.widgets.viewer.canvas.winfo_height(),
        ),
    )
    invalidate_display_cache(cast(RenderStateHost, host))
    invalidate_annotation_overlay(cast(RenderStateHost, host))

    # CMP: TODO - This is a lot to keep track of. We should
    # probably be calling an authoritative reset function here,
    # rather than remembering everything that must be set. Doing
    # so here, in any case, seems outside the function's scope,
    # certainly beyond what's declared in the docstring.
    host.interaction.selected_annotation_index = None
    host.interaction.selected_annotation_indices.clear()
    host.interaction.selected_arrow_index = None
    host.interaction.selected_arrow_indices.clear()
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    host.interaction.mode = None
    host.interaction.temp_polygon = []
    host.interaction.temp_edge_insertions = []
    host.interaction.drag_vertex_ref = None
    host.interaction.drag_rectangle_side_ref = None
    host.interaction.drag_rectangle_context = None
    host.interaction.edit_started_at_monotonic_ns = None
    host.interaction.merge_primary_index = None
    host.interaction.select_start_annotation_index = None
    host.interaction.select_start_polygon_index = None
    host.interaction.temp_arrow_start = None
    host.interaction.temp_arrow_current = None
    host.set_canvas_cursor("")
    persist_current_image_position(host)
    record_current_image_view(host)
    refresh_class_panel(cast(ClassPanelHost, host))
    redraw_canvas(cast(CanvasRenderHost, host))
    update_image_index_entry(host, force=True)
    update_edit_summary(host)
    update_buttons(host)
    return True


def clear_view_interaction_state(host: ImageLoadingHost) -> None:
    """Clear selection and in-progress interactions for an empty view."""

    clear_annotation_selection(host.interaction)
    host.interaction.selected_arrow_index = None
    host.interaction.selected_arrow_indices.clear()
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    host.interaction.selection_drag_start = None
    host.interaction.selection_drag_current = None
    host.interaction.annotation_selection_drag_start = None
    host.interaction.annotation_selection_drag_current = None
    host.interaction.annotation_selection_rect = None
    host.interaction.mode = None
    host.interaction.temp_polygon = []
    host.interaction.temp_edge_insertions = []
    host.interaction.drag_vertex_ref = None
    host.interaction.drag_rectangle_side_ref = None
    host.interaction.drag_rectangle_context = None
    host.interaction.edit_started_at_monotonic_ns = None
    host.interaction.merge_primary_index = None
    host.interaction.temp_arrow_start = None
    host.interaction.temp_arrow_current = None
    host.set_canvas_cursor("")
