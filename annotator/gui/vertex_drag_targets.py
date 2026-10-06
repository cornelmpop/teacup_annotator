"""Shared-vertex and rectangle targets used during vertex dragging."""

from __future__ import annotations

import math
import tkinter as tk
from typing import Any
from typing import Protocol

from annotator.coco.type_helpers import annotation_export_type
from annotator.geom.rectangle import rectangle_corner_index_for_vertex
from annotator.geom.rectangle import rectangle_corners_from_polygon
from annotator.geom.rectangle import resized_rectangle_from_corner
from annotator.geom.rectangle import resized_rectangle_from_side
from annotator.gui.selection import current_annotations
from annotator.gui.selection import selected_annotation
from annotator.gui.selection import selected_annotation_is_rectangle
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState


class VertexDragTargetHost(Protocol):
    """State and Tk flag required to resolve related drag targets."""

    project: ProjectState
    interaction: InteractionState
    autoclose_var: tk.BooleanVar

# CMP: TODO - Clarify docstring. Not immediately obvious what is meant
# by polygon vertices sharing the dragged point.
def shared_vertex_refs_for_drag(
    host: VertexDragTargetHost,
    original_point: tuple[float, float] | None,
) -> list[tuple[int, int, int]]:
    """Return other free-polygon vertices sharing the dragged point."""

    # CMP: TODO - Document why rectangle annotations are treated differently,
    # and how this condition interacts with ..._type(annotation) == "rectangle"
    # below
    if (
        original_point is None
        or host.interaction.selected_annotation_index is None
        or selected_annotation_is_rectangle(host.project, host.interaction)
    ):
        return []
    
    shared_refs: list[tuple[int, int, int]] = []
    for annotation_index, annotation in enumerate(
        current_annotations(host.project)
    ):
        if annotation_index == host.interaction.selected_annotation_index:
            continue
        if annotation_export_type(annotation) == "rectangle":
            continue
        for polygon_index, polygon in enumerate(annotation.polygons):
            for vertex_index, point in enumerate(polygon):
                if math.dist(point, original_point) <= 1e-6:
                    shared_refs.append(
                        (annotation_index, polygon_index, vertex_index)
                    )
    return shared_refs

# CMP: TODO - The docstring here suggests that the above function also only
# applies to turtle-shell annotations. If that's the case, that should be
# documented. It would also be useful to clarify why turtle-shell editing
# requires separate functions.
def move_shared_drag_vertices(
    host: VertexDragTargetHost,
    point: tuple[float, float],
) -> None:
    """Move matching free-polygon vertices during turtle-shell editing."""

    if not (host.autoclose_var.get() or host.interaction.w_down):
        return
    annotations = current_annotations(host.project)
    for (
        annotation_index,
        polygon_index,
        vertex_index,
    ) in host.interaction.drag_shared_vertex_refs:
        if not (0 <= annotation_index < len(annotations)):
            continue
        annotation = annotations[annotation_index]
        if annotation_export_type(annotation) == "rectangle":
            continue
        if not (0 <= polygon_index < len(annotation.polygons)):
            continue
        if not (0 <= vertex_index < len(annotation.polygons[polygon_index])):
            continue
        annotation.polygons[polygon_index][vertex_index] = point

# CMP: TODO - The function name should probably include _vertex_ or _corner_, since we
# have a different function below for side dragging.
def rectangle_drag_context(
    host: VertexDragTargetHost,
    vertex_ref: tuple[int, int],
) -> dict[str, Any] | None:
    """Return fixed rectangle geometry for a corner drag."""

    annotation = selected_annotation(host.project, host.interaction)
    if annotation is None or annotation_export_type(annotation) != "rectangle":
        return None
    polygon_index, vertex_index = vertex_ref
    if polygon_index >= len(annotation.polygons):
        return None
    polygon = annotation.polygons[polygon_index]
    if len(polygon) < 4 or vertex_index >= len(polygon):
        return None
    corner_index = rectangle_corner_index_for_vertex(polygon, vertex_index)
    corners = rectangle_corners_from_polygon(polygon)
    return {
        "polygon_index": polygon_index,
        "corner_index": corner_index,
        "opposite_point": corners[(corner_index + 2) % 4],
    }


def rectangle_side_drag_context(
    host: VertexDragTargetHost,
    side_ref: tuple[int, int],
) -> dict[str, Any] | None:
    """Return fixed rectangle geometry for a side drag."""

    annotation = selected_annotation(host.project, host.interaction)
    if annotation is None or annotation_export_type(annotation) != "rectangle":
        return None
    polygon_index, side_index = side_ref
    if polygon_index >= len(annotation.polygons):
        return None
    polygon = annotation.polygons[polygon_index]

    # CMP: TODO - clarify reason for needing this check. States that would match
    # this condition here would imply that the annotation_export_type(annotation) is
    # not doing its job. We shouldn't be second-guessing other functions. Checking
    # this should probably not be this function's responsibility.
    if len(polygon) < 4:
        return None
    return {
        "polygon_index": polygon_index,
        "side_index": side_index % 4,
    }

# CMP: TODO - clarify why the docstrings don't allow for side resizing
def resize_selected_rectangle(
    host: VertexDragTargetHost,
    image_point: tuple[float, float],
) -> None:
    """Resize the selected rectangle from the dragged corner."""

    annotation = selected_annotation(host.project, host.interaction)
    if annotation is None or annotation_export_type(annotation) != "rectangle":
        return
    context = host.interaction.drag_rectangle_context
    if context is None and host.interaction.drag_vertex_ref is not None:
        context = rectangle_drag_context(
            host,
            host.interaction.drag_vertex_ref,
        )
    if context is None:
        return
    if "side_index" in context:
        polygon_index = int(context.get("polygon_index", 0))
        if polygon_index >= len(annotation.polygons):
            return
        polygon = resized_rectangle_from_side(
            int(context["side_index"]),
            rectangle_corners_from_polygon(annotation.polygons[polygon_index]),
            image_point,
        )
    else:
        polygon = resized_rectangle_from_corner(
            int(context["corner_index"]),
            context["opposite_point"],
            image_point,
        )
    annotation.polygons = [polygon]
