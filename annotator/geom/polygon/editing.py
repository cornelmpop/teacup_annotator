"""CODEX: Polygon-editing operations shared by GUI workflows.

CODEX: This module owns small, UI-free transformations used when users select a
CODEX: new start vertex, finish or autoclose a polygon, and temporarily split
CODEX: existing edges for snapping.
CODEX: It works only with coordinate lists and snap graphs; callers own
CODEX: annotation lookup, GUI state, persistence, and Undo snapshots.
"""

from __future__ import annotations

import math
from typing import Any

from annotator.geom.graph import nearest_graph_node
from annotator.geom.lines import segment_projection_fraction
from annotator.geom.polygon.metrics import signed_polygon_area


def reorder_polygon_start_clockwise(
    polygon: list[tuple[float, float]],
    vertex_index: int,
) -> list[tuple[float, float]]:
    """Return `polygon` rotated to start at `vertex_index` and ordered clockwise.

    The selected vertex remains the first returned point. If the rotated point
    sequence has the opposite image-coordinate orientation, reverse only the
    remaining vertices so the same selected start point is preserved. Clamp
    out-of-range indexes to the nearest valid vertex because callers may pass
    interactive selection state that has drifted since hit testing.
    """

    if not polygon:
        return []
    vertex_index = max(0, min(len(polygon) - 1, vertex_index))
    rotated = polygon[vertex_index:] + polygon[:vertex_index]
    if signed_polygon_area(rotated) < 0:
        # Reverse after the selected start so the chosen vertex remains first.
        rotated = [rotated[0], *reversed(rotated[1:])]
    return list(rotated)


def polygon_is_non_degenerate(
    polygon: list[tuple[float, float]],
    minimum_area: float = 1e-6,
) -> bool:
    """Return whether `polygon` can represent an area-bearing annotation.

    Require at least three tolerance-distinct vertices and absolute signed area
    greater than `minimum_area`. The distinct-vertex check rejects repeated-point
    line shapes before area is considered, while the area threshold rejects
    collinear or collapsed shapes that still have three unique coordinates.
    """

    unique_points: list[tuple[float, float]] = []
    for point in polygon:
        if any(math.dist(point, existing) <= 1e-9 for existing in unique_points):
            continue
        unique_points.append(point)
    return len(unique_points) >= 3 and abs(signed_polygon_area(polygon)) > minimum_area


def polygon_has_unshared_vertex(
    polygon: list[tuple[float, float]],
    graph: dict[str, Any],
    tolerance: float,
) -> bool:
    """Return whether a candidate polygon contains a vertex absent from `graph`.

    Autoclose uses this to avoid completing a new polygon that only retraces
    existing graph nodes. `graph` is the exposed-boundary snap graph and
    `tolerance` is the same image-space tolerance used to build and query it.
    """

    return any(nearest_graph_node(graph, point, tolerance) is None for point in polygon)


def polygon_with_inserted_edge_vertices(
    polygon: list[tuple[float, float]],
    insertions: list[tuple[int, tuple[float, float]]],
) -> list[tuple[float, float]]:
    """Return a copy of `polygon` with pending edge split vertices inserted.

    Each insertion is `(edge_index, point)`, where `edge_index` identifies the
    source edge from `polygon[edge_index]` to the following vertex, wrapping at
    the end. Edge indexes are interpreted modulo the current polygon length,
    matching the closed-edge iteration convention used elsewhere in polygon
    geometry.

    Points equivalent to an existing endpoint are ignored because they would not
    split an edge or add a graph node. Multiple insertions on the same edge are
    ordered by projection along that edge, then emitted after the edge's start
    vertex. Consecutive duplicate vertices are suppressed in the returned list;
    the input polygon is never mutated.
    """

    if len(polygon) < 2 or not insertions:
        return list(polygon)
    by_edge: dict[int, list[tuple[float, tuple[float, float]]]] = {}
    for edge_index, point in insertions:
        normalized_edge = edge_index % len(polygon)
        start = polygon[normalized_edge]
        end = polygon[(normalized_edge + 1) % len(polygon)]
        # Endpoint-equivalent points are already represented by existing vertices.
        if math.dist(point, start) <= 1e-9 or math.dist(point, end) <= 1e-9:
            continue
        # Projection gives a stable order for multiple splits on the same edge.
        projection = segment_projection_fraction(point, start, end)
        by_edge.setdefault(normalized_edge, []).append((projection, point))

    next_polygon: list[tuple[float, float]] = []
    for vertex_index, vertex in enumerate(polygon):
        # Preserve walk order while suppressing consecutive duplicate vertices.
        if not next_polygon or math.dist(vertex, next_polygon[-1]) > 1e-9:
            next_polygon.append(vertex)
        edge_insertions = sorted(by_edge.get(vertex_index, []), key=lambda item: item[0])
        for _projection, point in edge_insertions:
            if math.dist(point, next_polygon[-1]) > 1e-9:
                next_polygon.append(point)
    return next_polygon
