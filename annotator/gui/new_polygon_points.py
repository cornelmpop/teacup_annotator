"""Functional point-entry effects for new polygons."""

from __future__ import annotations

import math
from typing import cast

from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.geom.graph import existing_polygon_graph_path
from annotator.gui.constants import NEW_POLYGON_CLOSE_DISTANCE
from annotator.gui.constants import VERTEX_HALF
from annotator.gui.new_polygon_completion import NewPolygonHost
from annotator.gui.new_polygon_completion import attempt_autoclose_new_polygon
from annotator.gui.new_polygon_completion import finish_new_polygon_annotation
from annotator.gui.snap_graph import current_snap_graph
from annotator.gui.snap_graph import snapping_tolerance_image
from annotator.gui.snapping import register_new_polygon_edge_snap
from annotator.gui.snapping import snapped_new_point
from annotator.gui.view_geometry import image_to_canvas_point


def add_new_polygon_point(
    host: NewPolygonHost,
    image_point: tuple[float, float],
    canvas_point: tuple[float, float],
) -> None:
    """Add, remove, or close one vertex in new annotation mode."""

    if host.project.coco is None:
        return
    if host.interaction.temp_polygon:
        last = host.interaction.temp_polygon[-1]
        last_canvas = image_to_canvas_point(last, host.view)
        if (
            abs(canvas_point[0] - last_canvas[0]) <= VERTEX_HALF
            and abs(canvas_point[1] - last_canvas[1]) <= VERTEX_HALF
        ):
            host.interaction.temp_polygon.pop()
            redraw_canvas(cast(CanvasRenderHost, host))
            return
    if len(host.interaction.temp_polygon) >= 3:
        first = host.interaction.temp_polygon[0]
        first_canvas = image_to_canvas_point(first, host.view)
        if math.dist(first_canvas, canvas_point) <= NEW_POLYGON_CLOSE_DISTANCE:
            finish_new_polygon_annotation(host)
            return
    tolerance = snapping_tolerance_image(host.prefs, host.view)
    snapped_point = snapped_new_point(
        host.project,
        host.view,
        host.interaction,
        image_point,
        host.snap_new_var.get(),
        tolerance,
    )
    snapped_point = register_new_polygon_edge_snap(
        host.project,
        host.view,
        host.interaction,
        snapped_point,
        host.snap_new_var.get(),
        tolerance,
    )
    append_new_polygon_point(host, snapped_point)
    if host.autoclose_var.get() and attempt_autoclose_new_polygon(host):
        return
    redraw_canvas(cast(CanvasRenderHost, host))


def append_new_polygon_point(
    host: NewPolygonHost,
    point: tuple[float, float],
) -> None:
    """Append a new point, walking existing edges when available."""

    if not host.interaction.temp_polygon:
        host.interaction.temp_polygon.append(point)
        return
    tolerance = snapping_tolerance_image(host.prefs, host.view)
    graph = current_snap_graph(
        host.project,
        host.view,
        host.interaction,
        tolerance,
    )
    if (
        host.autoclose_var.get()
        and host.snap_new_var.get()
        and tolerance is not None
        and graph is not None
    ):
        path = existing_polygon_graph_path(
            graph,
            host.interaction.temp_polygon[-1],
            point,
            tolerance,
        )
        if path is not None and len(path) > 1:
            host.interaction.temp_polygon[-1] = path[0]
            for path_point in path[1:]:
                if (
                    math.dist(path_point, host.interaction.temp_polygon[-1])
                    > 1e-9
                ):
                    host.interaction.temp_polygon.append(path_point)
            return
    host.interaction.temp_polygon.append(point)
