"""Functional annotation-outline resampling workflows.

This GUI layer owns selection, preferences, Undo staging, persistence, redraws,
and audit metadata for user-triggered outline resampling. Geometry modules own
the UI-free polygon transformations.
"""

from __future__ import annotations

import tkinter as tk
from typing import Protocol
from typing import cast

from annotator.coco.type_helpers import annotation_export_type
from annotator.geom.polygon import simplify_polygon_outline
from annotator.gui.annotation_modes import resample_outline_enabled
from annotator.gui.audit.undo import push_undo
from annotator.gui.arrow_interaction import arrow_for_polygon_start
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.hit_testing import annotation_index_at
from annotator.gui.hit_testing import annotation_polygon_index_at
from annotator.gui.persistence import AutosaveHost
from annotator.gui.persistence import autosave_current_image
from annotator.gui.project.navigation import current_image_name
from annotator.gui.render_state import RenderStateHost
from annotator.gui.render_state import mark_annotations_changed
from annotator.gui.selection import current_annotations
from annotator.gui.selection import selected_annotation
from annotator.gui.selection import selected_annotation_indexes
from annotator.gui.selection import set_single_annotation_selection
from annotator.gui.state import InteractionState
from annotator.gui.view_geometry import image_point_from_canvas
from annotator.preferences import DEFAULT_PREFERENCE_VALUES


_EQUAL_DISTANCE_RESAMPLING_METHOD = "equal_distance"


class AnnotationResamplingHost(AutosaveHost, RenderStateHost, Protocol):
    """Application state and effects required to resample annotation outlines."""

    interaction: InteractionState
    autoclose_var: tk.BooleanVar

# CMP: Explain why rectangles are not resampled (i.e., that they degenerate
# to more compelex polygons if we enforce strict spacing rules, since original
# vertices are not guaranteed)
def resample_selected_annotations(host: AnnotationResamplingHost) -> None:
    """Resample every non-rectangle annotation in the bulk selection.

    The audit details record the stable resampling-method identifier here
    because this workflow chooses the algorithm and stages the edit event.
    """

    if host.project.coco is None or not resample_outline_enabled(host):
        return
    annotations = current_annotations(host.project)
    indexes = [
        index
        for index in selected_annotation_indexes(host.project, host.interaction)
        if annotation_export_type(annotations[index]) != "rectangle"
    ]
    if not indexes:
        return
    distance_px = host.prefs.get_float(
        "simplify_vertex_distance_px",
        float(DEFAULT_PREFERENCE_VALUES["simplify_vertex_distance_px"]),
        minimum=0.0,
    )
    vertex_count = host.prefs.get_int(
        "simplify_vertex_count",
        int(DEFAULT_PREFERENCE_VALUES["simplify_vertex_count"]),
        minimum=3,
    )
    changed = False
    push_undo(
        host,
        action="simplify_polygon",
        details={
            "annotation_indexes": indexes,
            "resampling_method": _EQUAL_DISTANCE_RESAMPLING_METHOD,
            "vertex_count": vertex_count,
        },
    )
    for annotation_index in indexes:
        annotation = annotations[annotation_index]
        for polygon_index, polygon in enumerate(annotation.polygons):
            arrow = arrow_for_polygon_start(
                host.project,
                current_image_name(host),
                polygon,
            )
            simplified = simplify_polygon_outline(
                polygon,
                redundant_distance=distance_px,
                vertex_count=vertex_count,
                arrow=arrow.coords if arrow is not None else None,
            )
            if len(simplified) >= 3:
                annotation.polygons[polygon_index] = simplified
                annotation.raw["simplified"] = True
                annotation.raw["simplify_vertex_count"] = vertex_count
                changed = True
    if not changed:
        host.project.undo_stack.pop()
        if host.project.pending_audit_events:
            host.project.pending_audit_events.pop()
        return
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    mark_annotations_changed(host)
    host.project.dirty = True
    autosave_current_image(host)
    redraw_canvas(cast(CanvasRenderHost, host))


def simplify_annotation_at(
    host: AnnotationResamplingHost,
    canvas_point: tuple[float, float],
) -> None:
    """Simplify the polygon under the context-menu cursor."""

    if host.project.coco is None or not resample_outline_enabled(host):
        return
    image_point = image_point_from_canvas(canvas_point, host.view)
    if image_point is None:
        return
    annotations = current_annotations(host.project)
    annotation_index = annotation_index_at(annotations, image_point)
    if annotation_index is None:
        return
    polygon_index = annotation_polygon_index_at(
        annotations,
        annotation_index,
        image_point,
    )
    if polygon_index is None:
        return
    simplify_annotation_index(host, annotation_index, polygon_index)


def simplify_selected_annotation(host: AnnotationResamplingHost) -> None:
    """Simplify the currently selected annotation."""

    if (
        host.interaction.selected_annotation_index is None
        or not resample_outline_enabled(host)
    ):
        return
    annotation = selected_annotation(host.project, host.interaction)
    if annotation is None or annotation_export_type(annotation) == "rectangle":
        return
    simplify_annotation_index(
        host,
        host.interaction.selected_annotation_index,
        0,
    )


# CMP: TODO - Again, explain why rectangles are left unchanged.
def simplify_annotation_index(
    host: AnnotationResamplingHost,
    annotation_index: int,
    polygon_index: int,
) -> None:
    """CODEX: Simplify one free-polygon component and leave rectangles unchanged.

    The audit details record the stable resampling-method identifier here
    because this workflow chooses the algorithm and stages the edit event.
    """

    if host.project.coco is None or not resample_outline_enabled(host):
        return
    annotations = current_annotations(host.project)
    if not (0 <= annotation_index < len(annotations)):
        return
    annotation = annotations[annotation_index]
    if annotation_export_type(annotation) == "rectangle":
        return
    if polygon_index < 0 or polygon_index >= len(annotation.polygons):
        return
    distance_px = host.prefs.get_float(
        "simplify_vertex_distance_px",
        float(DEFAULT_PREFERENCE_VALUES["simplify_vertex_distance_px"]),
        minimum=0.0,
    )
    vertex_count = host.prefs.get_int(
        "simplify_vertex_count",
        int(DEFAULT_PREFERENCE_VALUES["simplify_vertex_count"]),
        minimum=3,
    )
    polygon = annotation.polygons[polygon_index]
    arrow = arrow_for_polygon_start(
        host.project,
        current_image_name(host),
        polygon,
    )
    simplified = simplify_polygon_outline(
        polygon,
        redundant_distance=distance_px,
        vertex_count=vertex_count,
        arrow=arrow.coords if arrow is not None else None,
    )
    if len(simplified) < 3:
        return
    push_undo(
        host,
        action="simplify_polygon",
        annotation_index=annotation_index,
        details={
            "polygon_index": polygon_index,
            "resampling_method": _EQUAL_DISTANCE_RESAMPLING_METHOD,
            "vertex_count": vertex_count,
        },
    )
    annotation.polygons[polygon_index] = simplified
    annotation.raw["simplified"] = True
    annotation.raw["simplify_vertex_count"] = vertex_count
    set_single_annotation_selection(host.interaction, annotation_index)
    host.interaction.selected_arrow_index = None
    host.interaction.selected_arrow_indices.clear()
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    mark_annotations_changed(host)
    host.project.dirty = True
    autosave_current_image(host)
    redraw_canvas(cast(CanvasRenderHost, host))
