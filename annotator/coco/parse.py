"""Parse imported COCO-like region geometry and optional detector scores.

Region annotations may provide standard polygon `segmentation`, compatibility
`polygons_xy` point lists, or detection-style `bbox` values. Supported
coordinates are converted to image-coordinate floats. Malformed or unsupported
geometry produces an empty result so one bad imported annotation does not abort
the remaining payload.

This module does not decode COCO RLE masks, clip coordinates to an image, or
validate polygon topology. Model-run output parsing lives in
`annotator.model.outputs`, and arrow geometry does not pass through this module.
"""

from __future__ import annotations

from typing import Any


def annotation_polygons(annotation: dict[str, Any]) -> list[list[tuple[float, float]]]:
    """Return the first usable geometry source in an imported annotation.

    Prefer standard COCO `segmentation`, then compatibility `polygons_xy`.
    When either field yields at least one polygon, lower-priority fields are
    ignored. If neither does, interpret the first four float-coercible values
    of a list-valued `bbox` as COCO `[x, y, width, height]` and return its four
    corners.

    Return an empty list when no supported source produces editable geometry.
    Bbox dimensions and coordinates are used as supplied; their sign, bounds,
    and finiteness are not validated. An unsupported RLE segmentation may
    therefore fall through to `polygons_xy` or `bbox`.
    """

    # Standard COCO polygon geometry takes precedence over compatibility fields.
    polygons = normalize_polygons(annotation.get("segmentation"))
    if polygons:
        return polygons
    # Older point-list imports apply only when segmentation yields no polygon.
    polygons = normalize_polygons(annotation.get("polygons_xy"))
    if polygons:
        return polygons
    # Detection boxes are the final fallback for editable rectangle geometry.
    bbox = annotation.get("bbox")
    if isinstance(bbox, list) and len(bbox) >= 4:
        try:
            x_coord, y_coord, width, height = (float(value) for value in bbox[:4])
        except (TypeError, ValueError):
            return []
        return [
            [
                (x_coord, y_coord),
                (x_coord + width, y_coord),
                (x_coord + width, y_coord + height),
                (x_coord, y_coord + height),
            ]
        ]
    return []


def normalize_polygons(value: Any) -> list[list[tuple[float, float]]]:
    """Return supported polygon candidates as float coordinate pairs.

    Accept a single flat coordinate list or an outer list whose candidates are
    either flat coordinate lists or point-list polygons. A point-list polygon
    therefore requires the outer polygon list. Each candidate must contain at
    least three coordinate pairs, and its coordinates must already be numeric.

    Skip malformed candidates independently and return an empty list for empty,
    non-list, or mapping values. This conversion does not close outlines,
    remove duplicate points, combine polygons, or validate their topology.
    """

    # Mappings include COCO RLE data, which this polygon-only importer cannot decode.
    if not value or isinstance(value, dict):
        return []
    if is_flat_polygon(value):
        value = [value]
    polygons: list[list[tuple[float, float]]] = []
    if not isinstance(value, list):
        return polygons
    for polygon in value:
        points: list[tuple[float, float]] = []
        if is_flat_polygon(polygon):
            iterator = zip(polygon[0::2], polygon[1::2])
        elif is_point_polygon(polygon):
            iterator = polygon
        else:
            continue
        for point in iterator:
            try:
                points.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError, IndexError):
                continue
        if len(points) >= 3:
            polygons.append(points)
    return polygons


def is_flat_polygon(value: Any) -> bool:
    """Return whether `value` is one supported flattened polygon.

    The value must be a list containing at least three numeric coordinate pairs:
    six or more items with an even length. This structural check deliberately
    does not coerce strings or validate coordinate finiteness, polygon bounds,
    or topology.
    """

    return (
        isinstance(value, list)
        and len(value) >= 6
        and len(value) % 2 == 0
        and all(isinstance(item, (int, float)) for item in value)
    )


def is_point_polygon(value: Any) -> bool:
    """Return whether `value` is one supported point-list polygon.

    The value must be a list of at least three points. Each point may be a list
    or tuple and must begin with two numeric coordinates; additional point
    elements are ignored during normalization.

    This is a structural check only. It does not validate coordinate finiteness,
    duplicate vertices, bounds, winding, or topology.
    """

    return (
        isinstance(value, list)
        and len(value) >= 3
        and all(
            isinstance(point, (list, tuple))
            and len(point) >= 2
            and isinstance(point[0], (int, float))
            and isinstance(point[1], (int, float))
            for point in value
        )
    )


def optional_float(value: Any) -> float | None:
    """Return an imported optional value as `float`, or `None` if unusable.

    Annotation loading uses this for detector scores so a missing value or a
    conversion that raises `TypeError` or `ValueError` does not discard
    otherwise usable region geometry. Any value accepted by `float()` is
    retained; this function does not enforce finiteness or a confidence range.
    """

    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
