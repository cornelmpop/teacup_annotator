"""Own edit-mode highlights and temporary main-canvas geometry."""

from __future__ import annotations

import tkinter as tk
from typing import Protocol
from typing import TYPE_CHECKING

from annotator.gui.constants import VERTEX_HALF
from annotator.gui.selection import current_annotations
from annotator.gui.snap_graph import live_line_image_point
from annotator.gui.snap_graph import snap_context_polygons
from annotator.gui.snap_graph import snapping_tolerance_image
from annotator.gui.snapping import new_polygon_live_line_colour
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState
from annotator.gui.view_geometry import canvas_polygon_points
from annotator.gui.view_geometry import image_to_canvas_point
from annotator.preferences import DEFAULT_PREFERENCE_VALUES
from annotator.preferences import Preferences

if TYPE_CHECKING:
    from annotator.gui.window.state import WindowWidgets


class CanvasEditOverlayHost(Protocol):
    """State, preferences, and widgets required for edit overlays."""

    prefs: Preferences
    project: ProjectState
    view: ViewState
    interaction: InteractionState
    widgets: WindowWidgets
    live_lines_var: tk.BooleanVar
    snap_new_var: tk.BooleanVar

# CMP: TODO - move the hard coded colour out of here - constants, or default
# preferences, or something like that should be the home. Same for other
# stylistic elements such as width
def draw_merge_primary_highlight(host: CanvasEditOverlayHost) -> None:
    """Highlight the primary annotation while waiting for merge target."""

    if (
        host.interaction.mode != "merge"
        or host.interaction.merge_primary_index is None
    ):
        return
    annotations = current_annotations(host.project)
    if not (0 <= host.interaction.merge_primary_index < len(annotations)):
        return
    for polygon in annotations[host.interaction.merge_primary_index].polygons:
        points = canvas_polygon_points(polygon, host.view)
        if len(points) < 6:
            continue
        host.widgets.viewer.canvas.create_polygon(
            points,
            fill="",
            outline="#f59e0b",
            width=3,
            dash=(6, 4),
            tags=("merge_primary",),
        )

# CMP: TODO - previous comment applies here as well.
def draw_multi_selected_annotations(host: CanvasEditOverlayHost) -> None:
    """Highlight annotations selected for bulk operations."""

    if not host.interaction.selected_annotation_indices:
        return
    annotations = current_annotations(host.project)
    for annotation_index in sorted(host.interaction.selected_annotation_indices):
        if not (0 <= annotation_index < len(annotations)):
            continue
        if (
            annotation_index == host.interaction.selected_annotation_index
            and len(host.interaction.selected_annotation_indices) == 1
        ):
            continue
        for polygon in annotations[annotation_index].polygons:
            points = canvas_polygon_points(polygon, host.view)
            if len(points) < 6:
                continue
            host.widgets.viewer.canvas.create_polygon(
                points,
                fill="",
                outline="#0057ff",
                width=2,
                dash=(5, 3),
                tags=("multi_selection",),
            )

# CMP: TODO - previous comment applies here as well.
def draw_temp_polygon(host: CanvasEditOverlayHost) -> None:
    """Draw vertices being added for a new annotation."""

    if not host.interaction.temp_polygon:
        return
    points = canvas_polygon_points(host.interaction.temp_polygon, host.view)
    canvas = host.widgets.viewer.canvas
    if len(points) >= 4:
        canvas.create_line(
            points,
            fill="#f59e0b",
            width=2,
            tags=("temp_polygon",),
        )
    for x_coord, y_coord in host.interaction.temp_polygon:
        canvas_x, canvas_y = image_to_canvas_point((x_coord, y_coord), host.view)
        canvas.create_rectangle(
            canvas_x - VERTEX_HALF,
            canvas_y - VERTEX_HALF,
            canvas_x + VERTEX_HALF,
            canvas_y + VERTEX_HALF,
            fill="white",
            outline="#0057ff",
            width=1,
            tags=("temp_vertex",),
        )
    draw_temp_live_line(host)


def draw_temp_live_line(host: CanvasEditOverlayHost) -> None:
    """Draw the dashed live segment from the newest polygon vertex."""

    tolerance = snapping_tolerance_image(host.prefs, host.view)
    live_point = live_line_image_point(
        host.view,
        host.interaction,
        host.live_lines_var.get(),
    )
    if live_point is None:
        return
    start_x, start_y = image_to_canvas_point(
        host.interaction.temp_polygon[-1], host.view
    )
    end_x, end_y = image_to_canvas_point(live_point, host.view)
    host.widgets.viewer.canvas.create_line(
        start_x,
        start_y,
        end_x,
        end_y,
        fill=new_polygon_live_line_colour(
            host.project,
            host.view,
            host.interaction,
            live_point,
            host.snap_new_var.get(),
            tolerance,
            host.prefs.values.get(
                "snap_live_line_colour",
                DEFAULT_PREFERENCE_VALUES["snap_live_line_colour"],
            ),
        ),
        width=2,
        dash=(5, 3),
        tags=("temp_polygon",),
    )

# CMP: TODO - previous comment applies here as well.
def draw_new_snap_context_vertices(host: CanvasEditOverlayHost) -> None:
    """CODEX: Show existing vertices available to new region annotations."""

    for polygon in snap_context_polygons(
        host.project,
        host.view,
        host.interaction,
        host.snap_new_var.get(),
        snapping_tolerance_image(host.prefs, host.view),
    ):
        for x_coord, y_coord in polygon:
            canvas_x, canvas_y = image_to_canvas_point(
                (x_coord, y_coord), host.view
            )
            host.widgets.viewer.canvas.create_rectangle(
                canvas_x - VERTEX_HALF,
                canvas_y - VERTEX_HALF,
                canvas_x + VERTEX_HALF,
                canvas_y + VERTEX_HALF,
                fill="white",
                outline="#0057ff",
                width=1,
                tags=("snap_context_vertex",),
            )
