"""Measure and compare finite 2D segments for interactive geometry.

Scalar tuple calculations keep snapping and hit testing lightweight. Shared-edge
helpers apply caller-provided tolerances to find and deduplicate nearly
collinear spans for overlap highlighting. General topological intersections
belong to Shapely-backed polygon workflows.
"""

from __future__ import annotations

import math

def segment_projection_fraction(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Return where `point` projects onto the segment from `start` to `end`.

    Return 0 at `start` and 1 at `end`. A projection before `start` becomes 0,
    and one beyond `end` becomes 1. Return 0 when `start` and `end` are the same
    point. This fraction orders inserted vertices and excludes rectangle corners.
    """

    segment_x = end[0] - start[0]
    segment_y = end[1] - start[1]
    length_squared = segment_x * segment_x + segment_y * segment_y
    # A segment whose endpoints are the same has no direction along which to project.
    if length_squared == 0:
        return 0.0
    projection = (
        ((point[0] - start[0]) * segment_x + (point[1] - start[1]) * segment_y)
        / length_squared
    )
    return max(0.0, min(1.0, projection))


def overlapping_collinear_segment(
    start_a: tuple[float, float],
    end_a: tuple[float, float],
    start_b: tuple[float, float],
    end_b: tuple[float, float],
    tolerance: float,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Return the span of segment A shared by nearly collinear segment B.

    Use A as the reference axis. Reject a collapsed A or B endpoints farther
    than `tolerance` from A's infinite line. Return the projected common span in
    A's direction; endpoint-only contact and negligible spans return `None`.

    Distance checks use coordinate units, while the final span check compares
    `tolerance` with a normalized fraction of A's length.
    """

    axis_x = end_a[0] - start_a[0]
    axis_y = end_a[1] - start_a[1]
    length_sq = axis_x * axis_x + axis_y * axis_y
    # A collapsed reference segment cannot expose a meaningful shared span.
    if length_sq <= tolerance * tolerance:
        return None
    # Both endpoints must follow A's line; a crossing is not a shared edge.
    if (
        point_to_line_distance(start_b, start_a, end_a) > tolerance
        or point_to_line_distance(end_b, start_a, end_a) > tolerance
    ):
        return None
    start_b_projection = (
        (start_b[0] - start_a[0]) * axis_x + (start_b[1] - start_a[1]) * axis_y
    ) / length_sq
    end_b_projection = (
        (end_b[0] - start_a[0]) * axis_x + (end_b[1] - start_a[1]) * axis_y
    ) / length_sq
    overlap_start = max(0.0, min(start_b_projection, end_b_projection))
    overlap_end = min(1.0, max(start_b_projection, end_b_projection))
    # Endpoint-only contact belongs to vertex highlighting, not edge highlighting.
    if overlap_end - overlap_start <= tolerance:
        return None
    return (
        (start_a[0] + axis_x * overlap_start, start_a[1] + axis_y * overlap_start),
        (start_a[0] + axis_x * overlap_end, start_a[1] + axis_y * overlap_end),
    )


def point_to_line_distance(
    point: tuple[float, float],
    line_start: tuple[float, float],
    line_end: tuple[float, float],
) -> float:
    """Return the distance from `point` to the infinite line through two points.

    `line_start` and `line_end` identify the line but do not bound it. If they
    are no more than `1e-12` apart, they do not define a direction; return the
    distance from `point` to `line_start` instead.
    """

    dx = line_end[0] - line_start[0]
    dy = line_end[1] - line_start[1]
    length = math.hypot(dx, dy)
    # Without a line direction, the only meaningful distance is to its defining point.
    if length <= 1e-12:
        return math.dist(point, line_start)
    return abs(dy * point[0] - dx * point[1] + line_end[0] * line_start[1] - line_end[1] * line_start[0]) / length


def dedupe_segments(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
    tolerance: float,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Return the first occurrence of each tolerantly equivalent segment.

    Endpoint direction is ignored. Preserving the first occurrence retains its
    coordinates and input order for overlap rendering.
    """

    deduped: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for segment in segments:
        if any(segments_equivalent(segment, existing, tolerance) for existing in deduped):
            continue
        deduped.append(segment)
    return deduped


def segments_equivalent(
    first: tuple[tuple[float, float], tuple[float, float]],
    second: tuple[tuple[float, float], tuple[float, float]],
    tolerance: float,
) -> bool:
    """Return whether both endpoints match within tolerance in either direction.

    Each endpoint comparison includes the `tolerance` boundary.
    """

    return (
        math.dist(first[0], second[0]) <= tolerance
        and math.dist(first[1], second[1]) <= tolerance
    ) or (
        math.dist(first[0], second[1]) <= tolerance
        and math.dist(first[1], second[0]) <= tolerance
    )


def point_to_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Return the shortest distance from `point` to the segment.

    Use the perpendicular projection when it falls between `start` and `end`;
    otherwise measure to the nearer endpoint. When both endpoints are the same,
    measure to that single point.
    """

    point_x, point_y = point
    start_x, start_y = start
    end_x, end_y = end
    segment_x = end_x - start_x
    segment_y = end_y - start_y
    length_squared = segment_x * segment_x + segment_y * segment_y
    if length_squared == 0:
        return math.hypot(point_x - start_x, point_y - start_y)

    projection = (
        ((point_x - start_x) * segment_x + (point_y - start_y) * segment_y)
        / length_squared
    )
    projection = max(0.0, min(1.0, projection))
    closest_x = start_x + projection * segment_x
    closest_y = start_y + projection * segment_y
    return math.hypot(point_x - closest_x, point_y - closest_y)


def closest_point_on_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[float, float]:
    """Return the point on the segment nearest to `point`.

    Return the perpendicular projection when it falls between `start` and `end`;
    otherwise return the nearer endpoint. When both endpoints are the same,
    return `start`.
    """

    point_x, point_y = point
    start_x, start_y = start
    end_x, end_y = end
    segment_x = end_x - start_x
    segment_y = end_y - start_y
    length_squared = segment_x * segment_x + segment_y * segment_y
    if length_squared == 0:
        return start
    projection = (
        ((point_x - start_x) * segment_x + (point_y - start_y) * segment_y)
        / length_squared
    )
    projection = max(0.0, min(1.0, projection))
    return start_x + projection * segment_x, start_y + projection * segment_y
