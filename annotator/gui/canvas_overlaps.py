"""Own cached main-canvas overlap geometry and rendering."""

from __future__ import annotations

import tkinter as tk
from typing import Protocol
from typing import TYPE_CHECKING

from annotator.geom.polygon import overlapping_polygon_edge_segments
from annotator.geom.polygon import overlapping_polygon_edge_segments_between
from annotator.geom.polygon import overlapping_polygon_vertices
from annotator.gui.model.settings import configured_colour
from annotator.gui.model.settings import ModelSettingsHost
from annotator.gui.project.navigation import current_image_name
from annotator.gui.selection import current_annotations
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState
from annotator.gui.view_geometry import image_to_canvas_point
from annotator.preferences import DEFAULT_PREFERENCE_VALUES

if TYPE_CHECKING:
    from annotator.gui.window.state import WindowWidgets

Point = tuple[float, float]
Segment = tuple[Point, Point]


class CanvasOverlapHost(ModelSettingsHost, Protocol):
    """Preferences, selection, view, and widgets required for overlaps."""

    project: ProjectState
    view: ViewState
    interaction: InteractionState
    widgets: WindowWidgets
    show_overlapping_edges_var: tk.BooleanVar


def draw_overlapping_edges(host: CanvasOverlapHost) -> None:
    """CODEX: Highlight shared polygon geometry except during a shape drag."""

    # CODEX: Hide marks while geometry moves; release clears drag state
    # CODEX: before the authoritative recomputation.
    shape_drag_active = (
        host.interaction.drag_vertex_ref is not None
        or host.interaction.drag_rectangle_side_ref is not None
    )
    if not host.show_overlapping_edges_var.get() or shape_drag_active:
        return

    segments, vertices = annotation_overlap_geometry(host)
    if not segments and not vertices:
        return
    width = host.prefs.get_int(
        "overlapping_edge_width",
        int(DEFAULT_PREFERENCE_VALUES["overlapping_edge_width"]),
        minimum=1,
    )
    draw_overlap_segments_on_canvas(
        host,
        segments,
        vertices,
        configured_colour(
            host,
            "overlapping_edge_colour",
            DEFAULT_PREFERENCE_VALUES["overlapping_edge_colour"],
        ),
        width,
    )
    selected_segments = selected_annotation_shared_edge_segments(host)
    if selected_segments:
        draw_overlap_segments_on_canvas(
            host,
            selected_segments,
            [],
            configured_colour(
                host,
                "selected_shared_edge_colour",
                DEFAULT_PREFERENCE_VALUES["selected_shared_edge_colour"],
            ),
            width,
        )

# CMP: TODO - Explain what this is needed for.
def annotation_overlap_geometry(
    host: CanvasOverlapHost,
) -> tuple[list[Segment], list[Point]]:
    """Return overlap geometry cached for the current image revision."""

    polygons = [
        polygon
        for annotation in current_annotations(host.project)
        for polygon in annotation.polygons
    ]
    overlap_key = (
        str(host.project.folder),
        current_image_name(host),
        host.view.annotation_revision,
    )
    if host.view.annotation_overlap_key != overlap_key:
        segments = overlapping_polygon_edge_segments(polygons)
        vertices = overlapping_polygon_vertices(polygons)
        host.view.annotation_overlap_geometry = (segments, vertices)
        host.view.annotation_overlap_key = overlap_key
    else:
        segments, vertices = host.view.annotation_overlap_geometry
    return segments, vertices


def draw_overlap_segments_on_canvas(
    host: CanvasOverlapHost,
    segments: list[Segment],
    vertices: list[Point],
    colour: str,
    width: int,
) -> None:
    """Draw overlap segment and vertex highlights on the main canvas."""

    radius = max(1.0, width / 2)
    canvas = host.widgets.viewer.canvas
    for start, end in segments:
        start_x, start_y = image_to_canvas_point(start, host.view)
        end_x, end_y = image_to_canvas_point(end, host.view)
        canvas.create_line(
            start_x,
            start_y,
            end_x,
            end_y,
            fill=colour,
            width=width,
            tags=("overlap_edge",),
        )
        for x_coord, y_coord in ((start_x, start_y), (end_x, end_y)):
            canvas.create_oval(
                x_coord - radius,
                y_coord - radius,
                x_coord + radius,
                y_coord + radius,
                fill=colour,
                outline=colour,
                tags=("overlap_edge",),
            )
    for x_coord, y_coord in vertices:
        canvas_x, canvas_y = image_to_canvas_point((x_coord, y_coord), host.view)
        canvas.create_oval(
            canvas_x - radius,
            canvas_y - radius,
            canvas_x + radius,
            canvas_y + radius,
            fill=colour,
            outline=colour,
            tags=("overlap_edge",),
        )


def selected_annotation_shared_edge_segments(
    host: CanvasOverlapHost,
) -> list[Segment]:
    """Return shared-edge spans for the single selected annotation."""

    if (
        host.interaction.selected_annotation_index is None
        or len(host.interaction.selected_annotation_indices) != 1
    ):
        return []
    annotations = current_annotations(host.project)
    if not (0 <= host.interaction.selected_annotation_index < len(annotations)):
        return []
    selected_polygons = annotations[
        host.interaction.selected_annotation_index
    ].polygons
    other_polygons = [
        polygon
        for annotation_index, annotation in enumerate(annotations)
        if annotation_index != host.interaction.selected_annotation_index
        for polygon in annotation.polygons
    ]
    return overlapping_polygon_edge_segments_between(
        selected_polygons, other_polygons
    )
