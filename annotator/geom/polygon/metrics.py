"""Polygon measurement helpers for annotation geometry.

These functions operate on image-space `(x, y)` coordinate lists and keep GUI
hit testing, label placement, COCO serialization, SQLite export, and zoom
culling independent of Tk state. They intentionally use lightweight scalar math;
topological polygon repair or union behavior belongs in the Shapely-backed
polygon modules.
"""

from __future__ import annotations

import math

from annotator.geom.lines import point_to_segment_distance


def polygon_centroid(polygon: list[tuple[float, float]]) -> tuple[float, float]:
    """Return a stable center point for labels and vertex-normal directions.

    Use the shoelace centroid for area-bearing polygons. If the polygon has no
    usable signed area, return the arithmetic mean of its vertices instead so
    label placement still has a deterministic reference point. Empty polygons
    use the origin because there are no coordinates to average.
    """

    if not polygon:
        return 0.0, 0.0
    area_twice = 0.0
    center_x = 0.0
    center_y = 0.0
    for index, point in enumerate(polygon):
        next_point = polygon[(index + 1) % len(polygon)]
        cross = point[0] * next_point[1] - next_point[0] * point[1]
        area_twice += cross
        center_x += (point[0] + next_point[0]) * cross
        center_y += (point[1] + next_point[1]) * cross
    if abs(area_twice) < 1e-9:
        # Degenerate polygons still need a deterministic label reference point.
        return (
            sum(point[0] for point in polygon) / len(polygon),
            sum(point[1] for point in polygon) / len(polygon),
        )
    return center_x / (3 * area_twice), center_y / (3 * area_twice)


def signed_polygon_area(polygon: list[tuple[float, float]]) -> float:
    """Return the signed shoelace area in image coordinates.

    The sign reflects vertex order under the application's image-space
    coordinate system, where y increases downward. Callers that need magnitude,
    such as label polygon selection, take `abs(...)`.
    """

    area_value = 0.0
    for index, point in enumerate(polygon):
        next_point = polygon[(index + 1) % len(polygon)]
        area_value += point[0] * next_point[1] - next_point[0] * point[1]
    return area_value / 2.0


def polygon_distance_to_point(
    polygon: list[tuple[float, float]],
    point: tuple[float, float],
) -> float:
    """Return the shortest distance from `point` to any closed polygon edge.

    Treat the polygon as closed by measuring each vertex-to-next-vertex segment,
    including the final vertex back to the first. Polygons with fewer than two
    vertices have no measurable edge and return infinity.
    """

    if len(polygon) < 2:
        return float("inf")
    best_distance = float("inf")
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        best_distance = min(best_distance, point_to_segment_distance(point, start, end))
    return best_distance


def outward_vertex_normal(
    polygon: list[tuple[float, float]],
    vertex_index: int,
    center: tuple[float, float],
) -> tuple[float, float]:
    """Return a unit-length outward-ish normal for a polygon vertex label.

    Build the normal from the local tangent through the previous and next
    vertices, then flip it if needed so it points away from `center`. Degenerate
    local geometry falls back to the direction from `center` to the vertex, and
    fully collapsed geometry returns a deterministic rightward vector.
    """

    point = polygon[vertex_index]
    previous_point = polygon[vertex_index - 1]
    next_point = polygon[(vertex_index + 1) % len(polygon)]
    tangent = (next_point[0] - previous_point[0], next_point[1] - previous_point[1])
    normal = (tangent[1], -tangent[0])
    away = (point[0] - center[0], point[1] - center[1])
    # Choose the normal direction that points away from the supplied center.
    if normal[0] * away[0] + normal[1] * away[1] < 0:
        normal = (-normal[0], -normal[1])
    length = math.hypot(normal[0], normal[1])
    # Collapsed local geometry cannot define a tangent-based normal.
    if length <= 1e-9:
        length = math.hypot(away[0], away[1])
        if length <= 1e-9:
            return 1.0, 0.0
        return away[0] / length, away[1] / length
    return normal[0] / length, normal[1] / length


def polygon_intersects_box(
    polygon: list[tuple[float, float]],
    box: tuple[float, float, float, float],
) -> bool:
    """Return whether `polygon`'s bounding box intersects an `xyxy` box.

    This is a coarse visibility predicate for zoom and overlay culling, not an
    exact polygon intersection test. Empty polygons have no bounds and return
    `False`.
    """

    if not polygon:
        return False
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    poly_left, poly_right = min(xs), max(xs)
    poly_top, poly_bottom = min(ys), max(ys)
    box_left, box_top, box_right, box_bottom = box
    return not (
        poly_right < box_left
        or poly_left > box_right
        or poly_bottom < box_top
        or poly_top > box_bottom
    )


def bbox_for_polygon(polygon: list[tuple[float, float]]) -> list[float]:
    """Return the COCO-style `xywh` bounding box for one polygon.

    The result is `[left, top, width, height]` in image coordinates. Empty
    polygons return a zero-sized box at the origin.
    """

    if not polygon:
        return [0.0, 0.0, 0.0, 0.0]
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    return [left, top, right - left, bottom - top]


def bbox(polygons: list[list[tuple[float, float]]]) -> list[float]:
    """Return one COCO-style `xywh` bounding box around all polygons."""

    return bbox_for_polygon([point for polygon in polygons for point in polygon])


def point_in_polygon(
    point: tuple[float, float],
    polygon: list[tuple[float, float]],
) -> bool:
    """Return whether `point` is inside `polygon` for GUI hit testing.

    Use an even-odd ray-casting test over the polygon's closed outline. Polygons
    with fewer than three vertices cannot contain a point and return `False`.
    This is a lightweight hit-test helper, not a boundary-classification
    routine.
    """

    x_coord, y_coord = point
    inside = False
    vertex_count = len(polygon)
    if vertex_count < 3:
        return False
    # The final vertex implicitly connects back to the first vertex.
    previous_x, previous_y = polygon[-1]
    for current_x, current_y in polygon:
        crosses = (current_y > y_coord) != (previous_y > y_coord)
        if crosses:
            slope_x = (previous_x - current_x) * (y_coord - current_y)
            slope_y = previous_y - current_y
            if x_coord < slope_x / slope_y + current_x:
                inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside


def area(polygons: list[list[tuple[float, float]]]) -> float:
    """Return summed absolute area for COCO polygon lists."""

    return sum(abs(polygon_area(polygon)) for polygon in polygons)


def polygon_area(polygon: list[tuple[float, float]]) -> float:
    """Return signed shoelace area for one polygon.

    Polygons with fewer than three vertices have no area and return `0.0`. This
    is the same signed-area convention used by `signed_polygon_area`; it remains
    as the COCO/export-facing helper while `signed_polygon_area` is used by
    geometry code that wants the convention named explicitly.
    """

    if len(polygon) < 3:
        return 0.0
    total = 0.0
    for index, point in enumerate(polygon):
        next_point = polygon[(index + 1) % len(polygon)]
        total += point[0] * next_point[1] - next_point[0] * point[1]
    return total / 2.0
