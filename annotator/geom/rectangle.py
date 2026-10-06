"""Normalize, test, and resize axis-aligned annotation rectangles.

Boxes use `(left, top, right, bottom)`. Canonical rectangle corners run
clockwise in image coordinates: top-left (0), top-right (1), bottom-right (2),
and bottom-left (3). Side indices are top (0), right (1), bottom (2), and
left (3).

Selection helpers operate in their caller's coordinate space. Resize helpers
preserve canonical corner order, axis alignment, and a minimum width and height.
"""

from __future__ import annotations

import math

from annotator.geom.coordinates import map_point_between_spaces

def annotation_fully_inside_canvas_rect(
    polygons: list[list[tuple[float, float]]],
    rect: tuple[float, float, float, float],
    zoom: float,
    origin: tuple[float, float],
) -> bool:
    """Return whether every annotation vertex lies inside a canvas rectangle.

    Convert each image-space vertex using `origin + point * zoom` before testing
    it against the normalized `(left, top, right, bottom)` rectangle. Rectangle
    boundaries count as inside. Return `False` when the annotation has no
    vertices.

    This implements full-enclosure drag selection, not polygon-overlap testing.
    """

    points = [point for polygon in polygons for point in polygon]
    # An annotation without vertices has no geometry for enclosure selection.
    if not points:
        return False
    left, top, right, bottom = rect
    for point in points:
        canvas_x, canvas_y = map_point_between_spaces(
            point,
            target_origin=origin,
            scale=(zoom, zoom),
        )
        if not (left <= canvas_x <= right and top <= canvas_y <= bottom):
            return False
    return True


def boxes_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    """Return whether two positive-size normalized xyxy boxes overlap.

    Containment counts as overlap. Boxes that meet only along an edge or at one
    corner do not overlap. Both inputs are expected to satisfy `left <= right`
    and `top <= bottom`.
    """

    return not (
        first[2] <= second[0]
        or first[0] >= second[2]
        or first[3] <= second[1]
        or first[1] >= second[3]
    )


def point_in_box(
    point: tuple[float, float],
    box: tuple[float, float, float, float],
) -> bool:
    """Return whether `point` lies inside a normalized xyxy box.

    Points on the box boundary count as inside.
    """

    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def point_in_arrow_bbox(
    point: tuple[float, float],
    arrow: tuple[float, float, float, float],
    tolerance: float = 0.0,
) -> bool:
    """Return whether `point` lies inside an arrow's expanded endpoint bounds.

    Derive the bounds independently of arrow direction, then expand every side
    by `tolerance`. Boundary points count as inside. This is a coarse arrow hit
    area, not a distance test against the arrow shaft.
    """

    left = min(arrow[0], arrow[2]) - tolerance
    right = max(arrow[0], arrow[2]) + tolerance
    top = min(arrow[1], arrow[3]) - tolerance
    bottom = max(arrow[1], arrow[3]) + tolerance
    return left <= point[0] <= right and top <= point[1] <= bottom


def rectangle_corners_from_polygon(
    polygon: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Return canonical corners for the axis-aligned bounds of `polygon`.

    Return top-left, top-right, bottom-right, and bottom-left. Any nonempty
    polygon is converted to its bounding rectangle; this function does not test
    whether the input was already rectangular. Return an empty list for empty
    input.

    This normalization gives loading, merging, hit testing, and resizing the
    same corner order.
    """

    if not polygon:
        return []
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    # Rebuild from extrema so stored rectangles recover the canonical corner order.
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def rectangle_corner_index_for_vertex(
    polygon: list[tuple[float, float]],
    vertex_index: int,
) -> int:
    """Return the canonical corner nearest to one stored polygon vertex.

    First derive the polygon's canonical bounding corners. Constrain
    `vertex_index` to the available stored vertices, then return the nearest
    canonical corner. Return 0 for an empty polygon. If two corners are equally
    near, the lower index wins.

    This maps rectangles with noncanonical stored vertex order into the editing
    corner convention.
    """

    corners = rectangle_corners_from_polygon(polygon)
    if not corners:
        return 0
    # Stored rectangles may use another vertex order, so classify geometrically.
    vertex = polygon[min(max(0, vertex_index), len(polygon) - 1)]
    return min(range(len(corners)), key=lambda index: math.dist(vertex, corners[index]))


def resized_rectangle_from_corner(
    corner_index: int,
    opposite_point: tuple[float, float],
    dragged_point: tuple[float, float],
    min_size: float = 1.0,
) -> list[tuple[float, float]]:
    """Return a canonical rectangle after moving one corner.

    Keep `opposite_point` fixed and interpret `corner_index` modulo four. Keep
    the dragged corner on its original left or right and top or bottom side of
    the fixed corner. If necessary, adjust the dragged position to preserve at
    least `min_size` width and height.

    Return corners in canonical order regardless of the supplied drag
    coordinates.
    """

    fixed_x, fixed_y = opposite_point
    drag_x, drag_y = dragged_point
    corner_index = corner_index % 4
    # Keep the dragged corner on its original left or right of the fixed corner.
    if corner_index in {0, 3}:
        drag_x = min(drag_x, fixed_x - min_size)
    else:
        drag_x = max(drag_x, fixed_x + min_size)
    # Apply the same rule vertically so neither dimension falls below min_size.
    if corner_index in {0, 1}:
        drag_y = min(drag_y, fixed_y - min_size)
    else:
        drag_y = max(drag_y, fixed_y + min_size)
    left, right = min(fixed_x, drag_x), max(fixed_x, drag_x)
    top, bottom = min(fixed_y, drag_y), max(fixed_y, drag_y)
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def resized_rectangle_from_side(
    side_index: int,
    corners: list[tuple[float, float]],
    dragged_point: tuple[float, float],
    min_size: float = 1.0,
) -> list[tuple[float, float]]:
    """Return a canonical rectangle after moving one side.

    Expect `corners` in canonical order and interpret `side_index` modulo four.
    Use only the dragged coordinate perpendicular to the selected side, leaving
    the opposite side and the other dimension unchanged. Adjust the moved side
    when necessary to preserve `min_size`.

    Return the resized rectangle in canonical corner order.
    """

    left, top = corners[0]
    right, bottom = corners[2]
    drag_x, drag_y = dragged_point
    side_index = side_index % 4
    # Move only the selected side, stopping before it crosses the fixed side.
    if side_index == 0:
        top = min(drag_y, bottom - min_size)
    elif side_index == 1:
        right = max(drag_x, left + min_size)
    elif side_index == 2:
        bottom = max(drag_y, top + min_size)
    else:
        left = min(drag_x, right - min_size)
    return [(left, top), (right, top), (right, bottom), (left, bottom)]
