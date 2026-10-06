"""CODEX: Build editable polygon outlines from Shapely union geometry.

These helpers convert Shapely polygonal results back to Annotator's coordinate
list model. They are used when imported/model-generated components, vertex
deletion survivors, or annotation merges need one editable polygon set without
owning GUI state, persistence, or annotation metadata.

Annotator's editable region model has no hole ring representation. Normalization
therefore returns one gap-free exterior outline; callers that must not fill an
enclosed center can query the union topology before accepting the edit.
"""

from __future__ import annotations

import copy
from typing import Any

from shapely.geometry import Polygon
from shapely.ops import unary_union


def single_polygon_list(
    polygons: list[list[tuple[float, float]]],
) -> list[list[tuple[float, float]]]:
    """CODEX: Return one editable exterior polygon for the union of `polygons`.

    Ignore input outlines with fewer than three vertices or geometry Shapely
    cannot interpret. Invalid Shapely polygons are repaired with `buffer(0)`
    before unioning. When no usable shape remains, or Shapely cannot produce
    polygonal content, return a deep copy of the first original polygon so
    callers keep an editable geometry rather than losing the annotation.

    Disconnected polygonal results use their convex hull so one annotation stays
    one editable outline. Interior holes are also flattened here because this
    function owns normalization, not edit acceptance.
    """

    polygonal = _polygonal_union(polygons)
    if polygonal is None:
        # CODEX: Preserve one original editable outline rather than dropping the annotation.
        return [copy.deepcopy(polygons[0])] if polygons else []
    single = single_shapely_outline(polygonal)
    return [single] if single else ([copy.deepcopy(polygons[0])] if polygons else [])


def polygon_union_has_hole(polygons: list[list[tuple[float, float]]]) -> bool:
    """CODEX: Return whether `polygons` union into an interior-ring geometry."""

    polygonal = _polygonal_union(polygons)
    if polygonal is None:
        return False
    return any(part.interiors for part in polygonal_parts(polygonal))


def polygon_overlaps_any(
    polygon: list[tuple[float, float]],
    other_polygons: list[list[tuple[float, float]]],
) -> bool:
    """CODEX: Return whether `polygon` has positive-area overlap with another."""

    candidate = _shape_from_polygon(polygon)
    if candidate is None:
        return False
    for other_polygon in other_polygons:
        other = _shape_from_polygon(other_polygon)
        if other is None:
            continue
        if candidate.intersection(other).area > 1e-6:
            return True
    return False


def _polygonal_union(polygons: list[list[tuple[float, float]]]) -> Any | None:
    """CODEX: Return the Shapely polygonal union for usable input outlines."""

    shapes = []
    for polygon in polygons:
        shape = _shape_from_polygon(polygon)
        if shape is not None:
            shapes.append(shape)
    if not shapes:
        return None
    try:
        unioned = unary_union(shapes)
    except (TypeError, ValueError):
        return None
    return polygonal_geometry(unioned)


def _shape_from_polygon(polygon: list[tuple[float, float]]) -> Any | None:
    """CODEX: Return a repaired Shapely shape for an area-bearing outline."""

    if len(polygon) < 3:
        return None
    try:
        shape = Polygon(polygon)
    except (TypeError, ValueError):
        return None
    if not shape.is_valid:
        shape = shape.buffer(0)
    return None if shape.is_empty else shape


def polygonal_geometry(geometry: Any) -> Any | None:
    """CODEX: Return the polygonal area-bearing content of a Shapely geometry.

    Accept `Polygon` and `MultiPolygon` directly. For a `GeometryCollection`,
    discard non-polygon children such as lines or points, union the remaining
    polygonal children, and normalize the result recursively. Return `None`
    when no polygonal content remains.
    """

    if geometry is None or geometry.is_empty:
        return None
    geom_type = getattr(geometry, "geom_type", "")
    if geom_type in {"Polygon", "MultiPolygon"}:
        return geometry
    if geom_type == "GeometryCollection":
        # CODEX: Mixed collections may include line or point remnants from overlay work.
        polygonal_children = [
            child
            for child in geometry.geoms
            if getattr(child, "geom_type", "") in {"Polygon", "MultiPolygon"}
        ]
        if not polygonal_children:
            return None
        return polygonal_geometry(unary_union(polygonal_children))
    return None


def polygonal_parts(geometry: Any) -> list[Any]:
    """CODEX: Return polygon members from a polygonal Shapely geometry."""

    if getattr(geometry, "geom_type", "") == "Polygon":
        return [geometry]
    return list(geometry.geoms)


def single_shapely_outline(geometry: Any) -> list[tuple[float, float]]:
    """CODEX: Return one exterior ring for Shapely polygonal geometry."""

    polygonal = polygonal_geometry(geometry)
    if polygonal is None:
        return []
    target = (
        polygonal
        if getattr(polygonal, "geom_type", "") == "Polygon"
        else polygonal.convex_hull
    )
    if getattr(target, "geom_type", "") == "Polygon":
        return shapely_polygon_exterior(target)
    return []


def shapely_polygon_exterior(polygon: Any) -> list[tuple[float, float]]:
    """CODEX: Return one Shapely polygon exterior in Annotator coordinate-list form.

    Shapely exterior rings repeat the first coordinate at the end. Annotator
    stores polygon rings with implicit closure, so the repeated closing
    coordinate is removed before returning the point list.
    """

    points = [
        (float(x_coord), float(y_coord))
        for x_coord, y_coord in polygon.exterior.coords
    ]
    if len(points) > 1 and points[0] == points[-1]:
        # CODEX: Shapely closes exterior rings explicitly; Annotator stores implicit closure.
        points.pop()
    return points
