"""Detect shared polygon vertices and edge spans for overlap highlighting.

These helpers operate on image-space polygon coordinate lists and return
geometry that the main canvas and zoom preview can render directly. They do not
mutate polygons, inspect annotation objects, or decide visibility/style; GUI
layers own annotation selection, caching, transforms, and drawing.

Edges are treated as closed polygon boundaries. Segment overlap semantics,
including collinearity tolerance and endpoint-only rejection, are delegated to
`annotator.geom.lines`.
"""

from __future__ import annotations

import math

from annotator.geom.lines import dedupe_segments
from annotator.geom.lines import overlapping_collinear_segment

Segment = tuple[tuple[float, float], tuple[float, float]]


def overlapping_polygon_edge_segments(
    polygons: list[list[tuple[float, float]]],
    tolerance: float = 1e-6,
) -> list[Segment]:
    """Return edge spans shared by two or more different polygons.

    Build closed-boundary segments for every polygon, ignore collapsed edges,
    and compare only edges from different polygon indexes. Returned spans use
    the first edge in each successful comparison as their coordinate direction,
    then tolerance-equivalent spans are deduplicated while preserving first
    occurrence.
    """

    edges: list[tuple[int, tuple[float, float], tuple[float, float]]] = []
    for polygon_index, polygon in enumerate(polygons):
        if len(polygon) < 2:
            continue
        for vertex_index, start in enumerate(polygon):
            end = polygon[(vertex_index + 1) % len(polygon)]
            # Collapsed polygon edges cannot contribute a visible shared span.
            if math.dist(start, end) > tolerance:
                edges.append((polygon_index, start, end))

    overlaps: list[Segment] = []
    for index, (polygon_a, start_a, end_a) in enumerate(edges):
        for polygon_b, start_b, end_b in edges[index + 1 :]:
            # Overlap highlights represent shared annotation boundaries, not
            # duplicate or adjacent edges within the same polygon.
            if polygon_a == polygon_b:
                continue
            overlap = overlapping_collinear_segment(
                start_a,
                end_a,
                start_b,
                end_b,
                tolerance,
            )
            if overlap is not None:
                overlaps.append(overlap)
    # Preserve the first reported span so rendering order stays stable.
    return dedupe_segments(overlaps, tolerance)


def overlapping_polygon_edge_segments_between(
    first_polygons: list[list[tuple[float, float]]],
    second_polygons: list[list[tuple[float, float]]],
    tolerance: float = 1e-6,
) -> list[Segment]:
    """Return edge spans shared between two polygon collections.

    Every closed edge from `first_polygons` is compared with every closed edge
    from `second_polygons`. This helper does not know annotation identity, so
    callers should pass disjoint collections when self-matches are not desired.
    Returned spans are deduplicated with the same tolerance-aware segment
    equivalence used by global overlap detection.
    """

    overlaps: list[Segment] = []
    for first in first_polygons:
        if len(first) < 2:
            continue
        for first_index, first_start in enumerate(first):
            first_end = first[(first_index + 1) % len(first)]
            for second in second_polygons:
                if len(second) < 2:
                    continue
                for second_index, second_start in enumerate(second):
                    second_end = second[(second_index + 1) % len(second)]
                    overlap = overlapping_collinear_segment(
                        first_start,
                        first_end,
                        second_start,
                        second_end,
                        tolerance,
                    )
                    if overlap is not None:
                        overlaps.append(overlap)
    # Preserve the first reported span so rendering order stays stable.
    return dedupe_segments(overlaps, tolerance)


def overlapping_polygon_vertices(
    polygons: list[list[tuple[float, float]]],
    tolerance: float = 1e-6,
) -> list[tuple[float, float]]:
    """Return vertices shared by two or more different polygons.

    Compare vertices from different polygon indexes and treat coordinates within
    `tolerance` as the same visual overlap. Each matched pair contributes the
    midpoint between the two source coordinates so near-coincident vertices
    render between their sources; repeated midpoint results are deduplicated in
    encounter order.
    """

    shared: list[tuple[float, float]] = []
    vertices: list[tuple[int, tuple[float, float]]] = []
    for polygon_index, polygon in enumerate(polygons):
        for vertex in polygon:
            vertices.append((polygon_index, vertex))
    for index, (polygon_a, vertex_a) in enumerate(vertices):
        for polygon_b, vertex_b in vertices[index + 1 :]:
            if polygon_a == polygon_b:
                continue
            if math.dist(vertex_a, vertex_b) <= tolerance:
                # Render near-coincident vertices at the midpoint of their sources.
                shared.append(
                    (
                        (vertex_a[0] + vertex_b[0]) / 2.0,
                        (vertex_a[1] + vertex_b[1]) / 2.0,
                    )
                )
    deduped: list[tuple[float, float]] = []
    for vertex in shared:
        # Preserve the first midpoint representative for each visual vertex.
        if any(math.dist(vertex, existing) <= tolerance for existing in deduped):
            continue
        deduped.append(vertex)
    return deduped
