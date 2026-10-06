"""Polygon snapping helpers for graph walks and edge projections.

This module keeps GUI snapping code independent of polygon graph construction
and finite-segment projection details. Turtle-shell/autoclose callers use graph
paths between existing vertices; point-entry and edit callers use edge
projection to find a nearby snap coordinate. GUI code owns image bounds,
annotation filtering, graph caching, and temporary insertion of snapped edge
vertices.
"""

from __future__ import annotations

import math

from annotator.geom.graph import build_existing_polygon_graph
from annotator.geom.graph import existing_polygon_graph_path
from annotator.geom.lines import closest_point_on_segment


def existing_polygon_vertex_path(
    polygons: list[list[tuple[float, float]]],
    start_point: tuple[float, float],
    target_point: tuple[float, float],
    tolerance: float,
) -> list[tuple[float, float]] | None:
    """Return a shortest exposed-boundary vertex path between two points.

    Build a fresh existing-polygon graph with `tolerance`, then resolve
    `start_point` and `target_point` to nearby graph vertices before routing.
    Shared polygon edges are omitted by graph construction, so returned paths
    follow exposed boundaries rather than interior seams. Return `None` when
    either point does not resolve to a graph node or no exposed-boundary route
    connects them.
    """

    # Build here for one-shot callers; GUI cache management lives in snap_graph.py.
    graph = build_existing_polygon_graph(polygons, tolerance)
    return existing_polygon_graph_path(graph, start_point, target_point, tolerance)


def nearest_snap_point_on_polygon_edges(
    point: tuple[float, float],
    polygons: list[list[tuple[float, float]]],
    tolerance: float,
) -> tuple[float, float] | None:
    """Return the nearest edge-projection snap point within `tolerance`.

    Treat every polygon with at least two vertices as an implicitly closed ring
    and project `point` onto each finite edge. Return the closest projected
    coordinate whose distance is within `tolerance`; return `None` when
    tolerance is not positive or no edge is close enough. Ties at the same
    distance are resolved by later polygon/edge scan order, matching the
    existing `<=` comparison.
    """

    # Nonpositive tolerances disable edge snapping.
    if tolerance <= 0:
        return None
    best_point: tuple[float, float] | None = None
    best_distance = tolerance
    for polygon in polygons:
        # A single point cannot expose a finite polygon edge.
        if len(polygon) < 2:
            continue
        for vertex_index, start in enumerate(polygon):
            end = polygon[(vertex_index + 1) % len(polygon)]
            # Projection allows snapping to edge interiors as well as vertices.
            candidate = closest_point_on_segment(point, start, end)
            distance = math.dist(point, candidate)
            # Later equal-distance candidates are acceptable and deterministic.
            if distance <= best_distance:
                best_distance = distance
                best_point = candidate
    return best_point
