"""CODEX: Map points and polygons between affine coordinate spaces.

CODEX: These helpers own only ``target_origin + (point - source_origin) *
scale``. Callers retain clipping, bounds validation, rounding,
raster-transform direction, and output formatting.
"""

from __future__ import annotations

Point = tuple[float, float]


def map_point_between_spaces(
    point: Point,
    *,
    source_origin: Point = (0.0, 0.0),
    target_origin: Point = (0.0, 0.0),
    scale: Point = (1.0, 1.0),
) -> Point:
    """CODEX: Map one point from a source origin into a target space.

    CODEX: Scale may differ by axis. The function performs no clipping,
    rounding, validation, or type coercion; callers own those policies.
    """

    source_x, source_y = source_origin
    target_x, target_y = target_origin
    scale_x, scale_y = scale
    point_x, point_y = point
    return (
        target_x + (point_x - source_x) * scale_x,
        target_y + (point_y - source_y) * scale_y,
    )


def map_polygon_between_spaces(
    polygon: list[Point],
    *,
    source_origin: Point = (0.0, 0.0),
    target_origin: Point = (0.0, 0.0),
    scale: Point = (1.0, 1.0),
) -> list[Point]:
    """CODEX: Return a polygon mapped into a target coordinate space.

    CODEX: Vertex order is preserved and an empty input returns an empty new
    list. Callers retain clipping, rounding, validation, and output formatting.
    """

    source_x, source_y = source_origin
    target_x, target_y = target_origin
    scale_x, scale_y = scale
    return [
        (
            target_x + (point_x - source_x) * scale_x,
            target_y + (point_y - source_y) * scale_y,
        )
        for point_x, point_y in polygon
    ]
