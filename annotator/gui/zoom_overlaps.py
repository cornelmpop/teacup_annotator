"""Own overlapping-edge and shared-edge highlights in the zoom preview."""

from __future__ import annotations

from typing import Protocol

from annotator.geom.coordinates import map_point_between_spaces
from annotator.gui.canvas_overlaps import CanvasOverlapHost
from annotator.gui.canvas_overlaps import annotation_overlap_geometry
from annotator.gui.canvas_overlaps import selected_annotation_shared_edge_segments
from annotator.gui.constants import ZOOM_VIEW_SIZE
from annotator.gui.model.settings import configured_colour
from annotator.preferences import DEFAULT_PREFERENCE_VALUES

Point = tuple[float, float]
Segment = tuple[Point, Point]


class ZoomOverlapHost(CanvasOverlapHost, Protocol):
    """Preferences, queries, and widgets required by zoom overlap highlights."""


def draw_zoom_overlapping_edges(
    host: ZoomOverlapHost,
    crop_left: int,
    crop_top: int,
    crop_size: int,
) -> None:
    """CODEX: Draw configured overlaps except during an active shape drag."""

    # CODEX: Hide marks while geometry moves; release clears drag state
    # CODEX: before the authoritative recomputation.
    shape_drag_active = (
        host.interaction.drag_vertex_ref is not None
        or host.interaction.drag_rectangle_side_ref is not None
    )
    if (
        not host.show_overlapping_edges_var.get()
        or shape_drag_active
        or crop_size <= 0
    ):
        return
    segments, vertices = annotation_overlap_geometry(host)
    if not segments and not vertices:
        return
    colour = configured_colour(
        host,
        "overlapping_edge_colour",
        DEFAULT_PREFERENCE_VALUES["overlapping_edge_colour"],
    )
    width = host.prefs.get_int(
        "overlapping_edge_width",
        int(DEFAULT_PREFERENCE_VALUES["overlapping_edge_width"]),
        minimum=1,
    )
    scale = ZOOM_VIEW_SIZE / crop_size
    draw_overlap_segments_on_zoom(
        host,
        segments,
        vertices,
        colour,
        width,
        crop_left,
        crop_top,
        scale,
    )
    selected_segments = selected_annotation_shared_edge_segments(host)
    if selected_segments:
        draw_overlap_segments_on_zoom(
            host,
            selected_segments,
            [],
            configured_colour(
                host,
                "selected_shared_edge_colour",
                DEFAULT_PREFERENCE_VALUES["selected_shared_edge_colour"],
            ),
            width,
            crop_left,
            crop_top,
            scale,
        )


def draw_overlap_segments_on_zoom(
    host: ZoomOverlapHost,
    segments: list[Segment],
    vertices: list[Point],
    colour: str,
    width: int,
    crop_left: int,
    crop_top: int,
    scale: float,
) -> None:
    """Draw overlap segment and vertex marks on the zoom canvas."""

    canvas = host.widgets.controls.zoom_canvas
    radius = max(1.0, width / 2)
    crop_size = ZOOM_VIEW_SIZE / scale
    crop_right = crop_left + crop_size
    crop_bottom = crop_top + crop_size
    for start, end in segments:
        if (
            max(start[0], end[0]) < crop_left
            or min(start[0], end[0]) > crop_right
            or max(start[1], end[1]) < crop_top
            or min(start[1], end[1]) > crop_bottom
        ):
            continue
        start_x, start_y = map_point_between_spaces(
            start,
            source_origin=(crop_left, crop_top),
            scale=(scale, scale),
        )
        end_x, end_y = map_point_between_spaces(
            end,
            source_origin=(crop_left, crop_top),
            scale=(scale, scale),
        )
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
        if not (
            crop_left <= x_coord <= crop_right
            and crop_top <= y_coord <= crop_bottom
        ):
            continue
        zoom_x, zoom_y = map_point_between_spaces(
            (x_coord, y_coord),
            source_origin=(crop_left, crop_top),
            scale=(scale, scale),
        )
        canvas.create_oval(
            zoom_x - radius,
            zoom_y - radius,
            zoom_x + radius,
            zoom_y + radius,
            fill=colour,
            outline=colour,
            tags=("overlap_edge",),
        )
