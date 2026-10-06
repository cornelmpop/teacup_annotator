"""Functional polygon start-vertex selection."""

from __future__ import annotations

from typing import Protocol
from typing import cast

from annotator.geom.polygon import point_in_polygon
from annotator.geom.polygon import reorder_polygon_start_clockwise
from annotator.gui.annotation_cancellation import AnnotationCancellationHost
from annotator.gui.annotation_cancellation import cancel_selection_or_mode
from annotator.gui.audit.undo import push_undo
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.hit_testing import annotation_index_at
from annotator.gui.hit_testing import annotation_polygon_index_at
from annotator.gui.hit_testing import vertex_at
from annotator.gui.persistence import AutosaveHost
from annotator.gui.persistence import autosave_current_image
from annotator.gui.render_state import RenderStateHost
from annotator.gui.render_state import mark_annotations_changed
from annotator.gui.selection import current_annotations
from annotator.gui.selection import selected_annotation
from annotator.gui.selection import set_single_annotation_selection
from annotator.gui.view_geometry import image_point_from_canvas


class PolygonStartHost(
    AutosaveHost,
    RenderStateHost,
    AnnotationCancellationHost,
    Protocol,
):
    """Application state and effects required to select a polygon start."""

    def set_canvas_cursor(self, cursor: str = "") -> None: ...

# CMP: TODO - clarify the need for two functions to handle this task.
def start_select_start_at(
    host: PolygonStartHost,
    canvas_point: tuple[float, float],
) -> None:
    """Start choosing a new first vertex for the annotation under a point."""

    if host.project.coco is None:
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
    host.interaction.mode = "select_start"
    set_single_annotation_selection(host.interaction, annotation_index)
    host.interaction.selected_arrow_index = None
    host.interaction.selected_arrow_indices.clear()
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    host.interaction.select_start_annotation_index = annotation_index
    host.interaction.select_start_polygon_index = polygon_index
    host.interaction.temp_polygon = []
    host.interaction.merge_primary_index = None
    host.interaction.temp_arrow_start = None
    host.interaction.temp_arrow_current = None
    host.set_canvas_cursor("")
    host.log("Select start: click the vertex that should become vertex 1.")
    redraw_canvas(cast(CanvasRenderHost, host))


def finish_select_start_at(
    host: PolygonStartHost,
    image_point: tuple[float, float],
    canvas_point: tuple[float, float],
) -> None:
    """Finish or cancel vertex-start selection."""

    annotation = selected_annotation(host.project, host.interaction)
    if (
        host.project.coco is None
        or annotation is None
        or host.interaction.select_start_annotation_index is None
        or host.interaction.select_start_polygon_index is None
    ):
        cancel_selection_or_mode(host)
        return
    polygon_index = host.interaction.select_start_polygon_index
    if polygon_index >= len(annotation.polygons):
        cancel_selection_or_mode(host)
        return
    polygon = annotation.polygons[polygon_index]
    vertex_ref = vertex_at(annotation, canvas_point, host.view)
    if vertex_ref is None:
        if not point_in_polygon(image_point, polygon):
            cancel_selection_or_mode(host)
        return
    clicked_polygon_index, vertex_index = vertex_ref
    if clicked_polygon_index != polygon_index:
        return
    reordered = reorder_polygon_start_clockwise(polygon, vertex_index)
    if reordered == polygon:
        cancel_selection_or_mode(host)
        return
    push_undo(
        host,
        action="select_start_vertex",
        annotation_index=host.interaction.select_start_annotation_index,
        details={
            "polygon_index": polygon_index,
            "vertex_index": vertex_index,
        },
    )
    annotation.polygons[polygon_index] = reordered
    host.interaction.mode = None
    host.interaction.select_start_annotation_index = None
    host.interaction.select_start_polygon_index = None
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    mark_annotations_changed(host)
    host.project.dirty = True
    autosave_current_image(host)
    host.update_canvas_cursor()
    redraw_canvas(cast(CanvasRenderHost, host))
