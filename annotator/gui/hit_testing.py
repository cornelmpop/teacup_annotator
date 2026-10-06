"""Annotation hit-testing functions with explicit geometry inputs."""

from __future__ import annotations

from collections.abc import Sequence

from annotator.coco.models import Annotation
from annotator.coco.type_helpers import annotation_export_type
from annotator.geom.lines import segment_projection_fraction
from annotator.geom.lines import point_to_segment_distance
from annotator.geom.polygon import point_in_polygon
from annotator.geom.rectangle import rectangle_corners_from_polygon
from annotator.gui.constants import ANNOTATION_BORDER_INSERT_DISTANCE
from annotator.gui.constants import VERTEX_HALF
from annotator.gui.state import ViewState
from annotator.gui.view_geometry import Point
from annotator.gui.view_geometry import image_to_canvas_point

# CMP: TODO - Clarify why we are targetting the topmost annotation.
def annotation_index_at(
    annotations: Sequence[Annotation],
    image_point: Point,
) -> int | None:
    """Return the topmost annotation containing an image-space point."""

    # CMP: TODO - Explain the math here
    for index in range(len(annotations) - 1, -1, -1):
        annotation = annotations[index]
        if any(
            point_in_polygon(image_point, polygon) for polygon in annotation.polygons
        ):
            return index
    return None


def annotation_indexes_at(
    annotations: Sequence[Annotation],
    image_point: Point,
) -> list[int]:
    """Return every annotation containing an image point in storage order."""

    return [
        index
        for index, annotation in enumerate(annotations)
        if any(
            point_in_polygon(image_point, polygon) for polygon in annotation.polygons
        )
    ]

# CMP: TODO - Clarify why we need a separate function for polygons
def annotation_polygon_index_at(
    annotations: Sequence[Annotation],
    annotation_index: int,
    image_point: Point,
) -> int | None:
    """Return the polygon index under an image point for one annotation."""

    if annotation_index < 0 or annotation_index >= len(annotations):
        return None
    annotation = annotations[annotation_index]
    for polygon_index, polygon in enumerate(annotation.polygons):
        if point_in_polygon(image_point, polygon):
            return polygon_index
    return 0 if annotation.polygons else None


def vertex_at(
    annotation: Annotation | None,
    canvas_point: Point,
    view: ViewState,
) -> tuple[int, int] | None:
    """Return the annotation vertex under a canvas-space point."""

    if annotation is None:
        return None
    canvas_x, canvas_y = canvas_point
    for polygon_index, polygon in enumerate(annotation.polygons):
        for vertex_index, point in enumerate(polygon):
            vertex_x, vertex_y = image_to_canvas_point(point, view)
            if (
                abs(canvas_x - vertex_x) <= VERTEX_HALF
                and abs(canvas_y - vertex_y) <= VERTEX_HALF
            ):
                return polygon_index, vertex_index
    return None

# CMP: TODO - The function name seems misleading here, since it is about
# a specific annotation type (polygons).
def annotation_border_at(
    annotation: Annotation | None,
    canvas_point: Point,
    view: ViewState,
) -> tuple[int, int] | None:
    """Return the free-polygon segment near a canvas-space point."""

    if annotation is None or annotation_export_type(annotation) == "rectangle":
        return None

    best_distance = ANNOTATION_BORDER_INSERT_DISTANCE + 1.0
    best_ref: tuple[int, int] | None = None
    for polygon_index, polygon in enumerate(annotation.polygons):
        if len(polygon) < 3:
            continue
        for vertex_index, start in enumerate(polygon):
            end = polygon[(vertex_index + 1) % len(polygon)]
            distance = point_to_segment_distance(
                canvas_point,
                image_to_canvas_point(start, view),
                image_to_canvas_point(end, view),
            )
            if distance < best_distance:
                best_distance = distance
                best_ref = (polygon_index, vertex_index)

    if best_ref is None or best_distance > ANNOTATION_BORDER_INSERT_DISTANCE:
        return None
    return best_ref

# CMP: TODO - Possible refactor. This and the above function appear meargeable
# into a generic annotation_border_at(), with rectangle-specific corner exclusion.
def rectangle_side_at(
    annotation: Annotation | None,
    canvas_point: Point,
    view: ViewState,
) -> tuple[int, int] | None:
    """Return the rectangle side near a canvas point away from its corners."""

    if annotation is None or annotation_export_type(annotation) != "rectangle":
        return None

    best_distance = ANNOTATION_BORDER_INSERT_DISTANCE + 1.0
    best_ref: tuple[int, int] | None = None
    for polygon_index, polygon in enumerate(annotation.polygons):
        corners = rectangle_corners_from_polygon(polygon)
        if len(corners) < 4:
            continue
        canvas_corners = [
            image_to_canvas_point(corner, view) for corner in corners
        ]
        for side_index, start in enumerate(canvas_corners):
            end = canvas_corners[(side_index + 1) % len(canvas_corners)]
            fraction = segment_projection_fraction(canvas_point, start, end)
            if fraction < 0.05 or fraction > 0.95:
                continue
            distance = point_to_segment_distance(canvas_point, start, end)
            if distance < best_distance:
                best_distance = distance
                best_ref = (polygon_index, side_index)

    if best_ref is None or best_distance > ANNOTATION_BORDER_INSERT_DISTANCE:
        return None
    return best_ref


def annotation_contains(
    annotation: Annotation | None,
    image_point: Point | None,
) -> bool:
    """Return whether an image point lies inside an annotation."""

    if image_point is None or annotation is None:
        return False
    return any(
        point_in_polygon(image_point, polygon) for polygon in annotation.polygons
    )
