"""Resolve temporary vertices created by snapping new polygons to existing edges.

The GUI records non-vertex edge snaps while a new polygon is being drawn. This
module keeps those records independent of Tk state and applies them back to the
editable source polygons when the new polygon is completed.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TypedDict

from annotator.coco.models import Annotation
from annotator.coco.type_helpers import annotation_export_type
from annotator.geom.lines import closest_point_on_segment
from annotator.geom.polygon import polygon_with_inserted_edge_vertices

Point = tuple[float, float]


class EdgeInsertion(TypedDict):
    """Temporary vertex to insert into a current annotation polygon edge.

    The indexes refer to the current annotation list and polygon list at the
    time the insertion is applied.
    """

    annotation_index: int
    polygon_index: int
    edge_index: int
    point: Point


def edge_insertion_for_snap_point(
    annotations: Sequence[Annotation],
    point: Point,
    tolerance: float,
) -> EdgeInsertion | None:
    """Return the nearest editable source edge for a snapped non-vertex point.

    Rectangle annotations are excluded because their geometry is edited through
    rectangle-specific resize logic. Existing vertices are excluded because they
    are already graph nodes and do not need temporary edge insertion.
    """

    best_distance = tolerance
    best_insertion: EdgeInsertion | None = None
    for annotation_index, annotation in enumerate(annotations):
        # Rectangles own their geometry through rectangle editing, not edge splits.
        if annotation_export_type(annotation) == "rectangle":
            continue
        for polygon_index, polygon in enumerate(annotation.polygons):
            if len(polygon) < 2:
                continue
            for edge_index, start in enumerate(polygon):
                end = polygon[(edge_index + 1) % len(polygon)]
                candidate = closest_point_on_segment(point, start, end)
                distance = math.dist(point, candidate)
                if distance > best_distance:
                    continue
                # Vertex snaps are already represented in the snap graph.
                if (
                    math.dist(candidate, start) <= 1e-9
                    or math.dist(candidate, end) <= 1e-9
                ):
                    continue
                best_distance = distance
                best_insertion = {
                    "annotation_index": annotation_index,
                    "polygon_index": polygon_index,
                    "edge_index": edge_index,
                    "point": candidate,
                }
    return best_insertion


def edge_insertion_exists(
    existing_insertions: Sequence[EdgeInsertion],
    insertion: EdgeInsertion,
    tolerance: float,
) -> bool:
    """Return whether this source edge already has a nearby pending insertion."""

    return any(
        existing["annotation_index"] == insertion["annotation_index"]
        and existing["polygon_index"] == insertion["polygon_index"]
        and existing["edge_index"] == insertion["edge_index"]
        and math.dist(existing["point"], insertion["point"]) <= tolerance
        for existing in existing_insertions
    )


def apply_edge_insertions(
    annotations: Sequence[Annotation],
    insertions: Sequence[EdgeInsertion],
) -> int:
    """Insert pending snap vertices into editable annotation polygons in place.

    Stale annotation or polygon indexes are ignored because temporary insertions
    can outlive small GUI state changes. The return value is the number of
    vertices actually added after polygon insertion rules are applied.
    """

    insertions_by_polygon: dict[tuple[int, int], list[tuple[int, Point]]] = {}
    for insertion in insertions:
        key = (insertion["annotation_index"], insertion["polygon_index"])
        insertions_by_polygon.setdefault(key, []).append(
            (insertion["edge_index"], insertion["point"])
        )

    applied_count = 0
    for (annotation_index, polygon_index), polygon_insertions in (
        insertions_by_polygon.items()
    ):
        # Temporary records may be stale after annotation edits; stale targets
        # simply have nothing to apply.
        if not 0 <= annotation_index < len(annotations):
            continue
        annotation = annotations[annotation_index]
        # Rectangle geometry is not rewritten through polygon edge insertion.
        if (
            annotation_export_type(annotation) == "rectangle"
            or not 0 <= polygon_index < len(annotation.polygons)
        ):
            continue
        original_count = len(annotation.polygons[polygon_index])
        annotation.polygons[polygon_index] = polygon_with_inserted_edge_vertices(
            annotation.polygons[polygon_index],
            polygon_insertions,
        )
        applied_count += max(
            0,
            len(annotation.polygons[polygon_index]) - original_count,
        )
    return applied_count
