"""CODEX: Clean, resample, and simplify polygon outlines.

This module owns UI-free polygon outline transformations used by annotation
simplification and arrow-guided explicit resampling start selection. GUI code
owns annotation selection, preferences, Undo, persistence, and any special
handling for a meaningful first vertex.

Two families of operations live here. Equal-distance resampling creates new
points along an implicitly closed ring. Shape-preserving simplification keeps
only original vertices and removes the least useful detail according to a
chosen algorithm.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString
from shapely.geometry import Point
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.ops import nearest_points

from annotator.geom.lines import closest_point_on_segment
from annotator.geom.lines import point_to_segment_distance


def simplify_polygon_outline(
    polygon: list[tuple[float, float]],
    redundant_distance: float,
    vertex_count: int,
    arrow: tuple[float, float, float, float] | None = None,
) -> list[tuple[float, float]]:
    """Return a cleaned polygon outline resampled to `vertex_count` vertices.

    First recover the exterior outline, then remove sequentially redundant
    vertices, then resample the closed ring at equal arc-length intervals. When
    `arrow` is provided and intersects the cleaned boundary, the first emitted
    vertex is the boundary point nearest the arrow start. Inputs that cannot
    produce a valid simplified polygon are preserved by the lower-level helpers.
    """

    outline = polygon_outer_outline(polygon)
    cleaned = remove_close_polygon_vertices(outline, redundant_distance)
    start = arrow_polygon_boundary_start(cleaned, arrow) if arrow is not None else None
    return resample_closed_polygon(cleaned, vertex_count, start)


def simplify_closed_polygon_visvalingam(
    polygon: list[tuple[float, float]],
    vertex_count: int,
) -> list[tuple[float, float]]:
    """Return `polygon` simplified by Visvalingam-Whyatt triangle area.

    Repeatedly remove the remaining vertex whose neighboring triangle has the
    smallest area until `vertex_count` vertices remain. Ties are resolved by the
    original vertex order so tests and user-visible results remain
    deterministic. The returned polygon contains only original input vertices.

    This count-target variant is useful when the user wants a fixed number of
    editable vertices while preserving major bends better than equal-distance
    resampling. It treats the polygon as an implicitly closed ring and returns a
    new list without mutating the input.
    """

    if len(polygon) < 3 or vertex_count < 3 or vertex_count >= len(polygon):
        return list(polygon)

    remaining = list(range(len(polygon)))
    while len(remaining) > vertex_count:
        removal_position = 0
        removal_score = (float("inf"), len(polygon))
        for position, vertex_index in enumerate(remaining):
            previous_point = polygon[remaining[position - 1]]
            point = polygon[vertex_index]
            next_point = polygon[remaining[(position + 1) % len(remaining)]]
            area = abs(
                (previous_point[0] * (point[1] - next_point[1]))
                + (point[0] * (next_point[1] - previous_point[1]))
                + (next_point[0] * (previous_point[1] - point[1]))
            ) / 2.0
            score = (area, vertex_index)
            if score < removal_score:
                removal_score = score
                removal_position = position
        # Removing by position preserves the original walk order of survivors.
        del remaining[removal_position]
    return [polygon[index] for index in remaining]


def simplify_closed_polygon_rdp(
    polygon: list[tuple[float, float]],
    vertex_count: int,
) -> list[tuple[float, float]]:
    """Return `polygon` simplified by count-target RDP deviation.

    Treat the ring as an open path cut across its longest original edge, then
    repeatedly split the retained shortcut segment whose omitted vertices have
    the greatest perpendicular distance from that shortcut. Ties prefer earlier
    original vertex indexes for deterministic results.

    This preserves original vertices only. It is a closed-ring adaptation of
    Ramer-Douglas-Peucker for callers that need an exact vertex count rather
    than an error threshold. The returned list follows the original polygon
    order and never mutates the input.
    """

    if len(polygon) < 3 or vertex_count < 3 or vertex_count >= len(polygon):
        return list(polygon)

    longest_edge_index = 0
    longest_edge_length = -1.0
    for index, start in enumerate(polygon):
        edge_length = math.dist(start, polygon[(index + 1) % len(polygon)])
        if edge_length > longest_edge_length:
            longest_edge_length = edge_length
            longest_edge_index = index

    start_index = (longest_edge_index + 1) % len(polygon)
    source_indices = [
        (start_index + offset) % len(polygon) for offset in range(len(polygon))
    ]
    points = [polygon[index] for index in source_indices]
    kept_positions = [0, len(points) - 1]

    while len(kept_positions) < vertex_count:
        kept_positions.sort()
        next_position: int | None = None
        next_score = (-1.0, -len(polygon))
        for left, right in zip(kept_positions, kept_positions[1:]):
            if right - left <= 1:
                continue
            for position in range(left + 1, right):
                distance = point_to_segment_distance(
                    points[position],
                    points[left],
                    points[right],
                )
                score = (distance, -source_indices[position])
                if score > next_score:
                    next_score = score
                    next_position = position
        if next_position is None:
            break
        # Each split commits one original vertex that best explains a shortcut.
        kept_positions.append(next_position)

    kept_indices = sorted(source_indices[position] for position in kept_positions)
    return [polygon[index] for index in kept_indices]


def simplify_closed_polygon_imai_iri(
    polygon: list[tuple[float, float]],
    vertex_count: int,
) -> list[tuple[float, float]]:
    """Return `polygon` simplified by Imai-Iri-style global error search.

    Evaluate every original vertex as a possible ring start, then use dynamic
    programming to choose `vertex_count` retained vertices that minimize the
    worst shortcut deviation around the closed boundary. Equal-error solutions
    prefer the lexicographically earliest set of original vertex indexes so the
    result is deterministic.

    This is more expensive than the greedy algorithms above, but it best matches
    the goal of preserving the existing curve while keeping only original
    vertices. The function does not repair geometry or manage a meaningful
    first vertex; callers can do that before or after simplification.
    """

    if len(polygon) < 3 or vertex_count < 3 or vertex_count >= len(polygon):
        return list(polygon)

    polygon_length = len(polygon)
    best_score: tuple[float, tuple[int, ...]] | None = None
    best_indices: tuple[int, ...] | None = None

    for start_index in range(polygon_length):
        source_indices = [
            (start_index + offset) % polygon_length
            for offset in range(polygon_length)
        ]
        source_indices.append(start_index)
        points = [polygon[index] for index in source_indices]

        shortcut_errors = [
            [0.0 for _column in range(polygon_length + 1)]
            for _row in range(polygon_length + 1)
        ]
        for left in range(polygon_length):
            for right in range(left + 1, polygon_length + 1):
                max_distance = 0.0
                for middle in range(left + 1, right):
                    max_distance = max(
                        max_distance,
                        point_to_segment_distance(
                            points[middle],
                            points[left],
                            points[right],
                        ),
                    )
                shortcut_errors[left][right] = max_distance

        states: list[dict[int, tuple[float, tuple[int, ...]]]] = [
            {} for _segment_count in range(vertex_count + 1)
        ]
        states[0][0] = (0.0, (0,))
        for segment_count in range(1, vertex_count + 1):
            for right in range(segment_count, polygon_length + 1):
                state: tuple[float, tuple[int, ...]] | None = None
                for left in range(segment_count - 1, right):
                    if left not in states[segment_count - 1]:
                        continue
                    previous_error, previous_path = states[segment_count - 1][left]
                    error = max(previous_error, shortcut_errors[left][right])
                    path = previous_path + (right,)
                    candidate = (error, path)
                    if state is None or candidate < state:
                        state = candidate
                if state is not None:
                    states[segment_count][right] = state

        if polygon_length not in states[vertex_count]:
            continue
        error, path = states[vertex_count][polygon_length]
        indices = tuple(sorted(source_indices[position] for position in path[:-1]))
        score = (error, indices)
        if best_score is None or score < best_score:
            best_score = score
            best_indices = indices

    if best_indices is None:
        return list(polygon)
    return [polygon[index] for index in best_indices]


def polygon_outer_outline(
    polygon: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Return the exterior outline after limited Shapely validity cleanup.

    Polygons with fewer than three points are returned unchanged as a new list.
    For larger inputs, build a Shapely polygon, run `buffer(0)` only when Shapely
    marks it invalid, and return the exterior ring without Shapely's repeated
    closing coordinate.

    If cleanup produces an empty geometry, a non-polygonal geometry, or too few
    exterior points, return the original coordinate list. If cleanup produces a
    `MultiPolygon`, use its convex hull exterior because the simplification
    workflow needs one continuous outline to resample.
    """

    if len(polygon) < 3:
        return list(polygon)
    try:
        shape = ShapelyPolygon(polygon)
    except (TypeError, ValueError):
        return list(polygon)
    if not shape.is_valid:
        # `buffer(0)` is the narrow Shapely repair used to recover an exterior ring.
        shape = shape.buffer(0)
    if shape.is_empty:
        return list(polygon)
    geom_type = getattr(shape, "geom_type", "")
    if geom_type == "Polygon":
        points = [
            (float(x_coord), float(y_coord))
            for x_coord, y_coord in shape.exterior.coords
        ]
    elif geom_type == "MultiPolygon":
        # Multiple cleaned pieces are reduced to one outline for resampling.
        hull = shape.convex_hull
        if getattr(hull, "geom_type", "") != "Polygon":
            return list(polygon)
        points = [
            (float(x_coord), float(y_coord))
            for x_coord, y_coord in hull.exterior.coords
        ]
    else:
        return list(polygon)
    if len(points) > 1 and points[0] == points[-1]:
        # Shapely repeats the first coordinate; this module uses implicit closure.
        points.pop()
    return points if len(points) >= 3 else list(polygon)


def remove_close_polygon_vertices(
    polygon: list[tuple[float, float]],
    threshold: float,
) -> list[tuple[float, float]]:
    """Return `polygon` with sequential vertices closer than `threshold` removed.

    Only adjacent vertices in walk order are considered; this is not a global
    near-duplicate merge. After the forward pass, also remove a final vertex
    that is too close to the first vertex so the implicitly closed ring does not
    retain a tiny closing edge. If cleanup would leave fewer than three
    vertices, return the original polygon as a new list.
    """

    if len(polygon) < 3 or threshold <= 0:
        return list(polygon)
    cleaned: list[tuple[float, float]] = []
    for point in polygon:
        if cleaned and math.dist(cleaned[-1], point) < threshold:
            continue
        cleaned.append(point)
    # The closing edge is implicit, so remove a redundant final point near the first.
    while len(cleaned) > 3 and math.dist(cleaned[0], cleaned[-1]) < threshold:
        cleaned.pop()
    return cleaned if len(cleaned) >= 3 else list(polygon)


def resample_closed_polygon(
    polygon: list[tuple[float, float]],
    vertex_count: int,
    start_point: tuple[float, float] | None = None,
) -> list[tuple[float, float]]:
    """Return `vertex_count` equal-distance samples around a closed polygon ring.

    The input ring is implicit: the last point connects back to the first. If
    `start_point` is provided, reorder the ring so sampling begins there before
    equal arc-length spacing is calculated. Polygons with fewer than three
    points, requested counts below three, or zero perimeter are returned
    unchanged as a new list.
    """

    if len(polygon) < 3 or vertex_count < 3:
        return list(polygon)
    # Start alignment happens before spacing so index zero remains the crossing.
    ring = rotate_closed_ring_to_start(polygon, start_point)
    perimeter = closed_ring_perimeter(ring)
    if perimeter <= 0:
        return list(polygon)
    step = perimeter / vertex_count
    return [
        point_on_closed_ring_at_distance(ring, index * step)
        for index in range(vertex_count)
    ]


def rotate_closed_ring_to_start(
    polygon: list[tuple[float, float]],
    start_point: tuple[float, float] | None,
) -> list[tuple[float, float]]:
    """Return ring vertices ordered so `start_point` is the first point.

    When `start_point` is provided, find the polygon edge whose nearest point is
    closest to it, insert `start_point` as the first returned coordinate, then
    continue with the original vertices after that edge and wrap around. This
    keeps arrow-aligned resampling anchored at the arrow/boundary crossing while
    retaining the original boundary walk order.
    """

    ring = list(polygon)
    if not ring or start_point is None:
        return ring
    best_index = 0
    best_distance = float("inf")
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        candidate = closest_point_on_segment(start_point, start, end)
        distance = math.dist(start_point, candidate)
        if distance < best_distance:
            best_distance = distance
            best_index = index
    # Insert the requested boundary point between the edge's start and end vertices.
    return [start_point] + ring[best_index + 1 :] + ring[: best_index + 1]


def closed_ring_perimeter(polygon: list[tuple[float, float]]) -> float:
    """Return the perimeter length of an implicitly closed polygon ring.

    Rings with fewer than two points have no measurable perimeter and return
    `0.0`.
    """

    if len(polygon) < 2:
        return 0.0
    return sum(
        math.dist(point, polygon[(index + 1) % len(polygon)])
        for index, point in enumerate(polygon)
    )


def point_on_closed_ring_at_distance(
    polygon: list[tuple[float, float]],
    distance: float,
) -> tuple[float, float]:
    """Return the interpolated ring point at `distance` along the closed boundary.

    Distances wrap around the perimeter, so values larger than the perimeter or
    negative values still resolve to a point on the ring. Zero-length segments
    are skipped. Callers are expected to pass at least one point; if that ring
    has no measurable perimeter, return its first point.
    """

    perimeter = closed_ring_perimeter(polygon)
    if perimeter <= 0:
        return polygon[0]
    # Distance wraps around the ring to keep every sample on the closed boundary.
    remaining = distance % perimeter
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        segment_length = math.dist(start, end)
        if segment_length == 0:
            continue
        if remaining <= segment_length:
            ratio = remaining / segment_length
            return (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            )
        remaining -= segment_length
    return polygon[0]


def arrow_polygon_boundary_start(
    polygon: list[tuple[float, float]],
    arrow: tuple[float, float, float, float],
) -> tuple[float, float] | None:
    """Return the arrow/boundary intersection nearest the arrow start.

    The arrow is treated as a finite line segment from `(x1, y1)` to `(x2, y2)`.
    The polygon boundary is treated as an implicitly closed ring. Shapely may
    return a point, multiple points, or a line overlap; `nearest_points` selects
    the intersection geometry point closest to the arrow start, which makes an
    arrow crossing a polygon twice choose its first boundary crossing.
    """

    if len(polygon) < 3:
        return None
    arrow_start = (arrow[0], arrow[1])
    arrow_end = (arrow[2], arrow[3])
    arrow_line = LineString([arrow_start, arrow_end])
    boundary = LineString([*polygon, polygon[0]])
    # Shapely represents both point crossings and collinear edge overlaps here.
    intersection = arrow_line.intersection(boundary)
    if intersection.is_empty:
        return None
    nearest = nearest_points(Point(arrow_start), intersection)[1]
    return float(nearest.x), float(nearest.y)
