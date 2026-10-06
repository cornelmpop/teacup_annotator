"""Functional vertex drag and insertion effects."""

from __future__ import annotations

import math
import tkinter as tk
from typing import Protocol
from typing import cast

from annotator.coco.type_helpers import annotation_export_type
from annotator.geom.lines import point_to_segment_distance
from annotator.geom.lines import segments_equivalent
from annotator.geom.snapping import EdgeInsertion
from annotator.geom.snapping import apply_edge_insertions
from annotator.gui.audit.undo import push_undo
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.persistence import AutosaveHost
from annotator.gui.persistence import autosave_current_image
from annotator.gui.render_state import RenderStateHost
from annotator.gui.render_state import mark_annotations_changed
from annotator.gui.selection import current_annotations
from annotator.gui.selection import selected_annotation
from annotator.gui.selection import selected_annotation_is_rectangle
from annotator.gui.snap_graph import snapping_tolerance_image
from annotator.gui.snapping import snapped_edit_point
from annotator.gui.vertex_drag_targets import VertexDragTargetHost
from annotator.gui.vertex_drag_targets import move_shared_drag_vertices
from annotator.gui.vertex_drag_targets import rectangle_drag_context
from annotator.gui.vertex_drag_targets import rectangle_side_drag_context
from annotator.gui.vertex_drag_targets import resize_selected_rectangle
from annotator.gui.vertex_drag_targets import shared_vertex_refs_for_drag

class VertexEditingHost(
    AutosaveHost,
    RenderStateHost,
    VertexDragTargetHost,
    Protocol,
):
    """CODEX/CMP: Application state and effects required to edit vertices."""

    snap_edits_var: tk.BooleanVar

    def set_canvas_cursor(self, cursor: str = "") -> None: ...


def begin_vertex_drag(
    host: VertexEditingHost,
    vertex_ref: tuple[int, int],
) -> None:
    """Begin dragging an annotation vertex."""

    annotation = selected_annotation(host.project, host.interaction)
    original_point: tuple[float, float] | None = None

    # CMP: TODO - Clarify what valid application state would result in an
    # out of range polygon/vertex index (i.e., why this check is justified here)
    if annotation is not None:
        polygon_index, vertex_index = vertex_ref
        if 0 <= polygon_index < len(
            annotation.polygons
        ) and 0 <= vertex_index < len(annotation.polygons[polygon_index]):
            original_point = annotation.polygons[polygon_index][vertex_index]
    push_undo(
        host,
        action=(
            "resize_rectangle"
            if selected_annotation_is_rectangle(host.project, host.interaction)
            else "move_vertex"
        ),
        annotation_index=host.interaction.selected_annotation_index,
        details={"vertex_ref": vertex_ref},
    )
    host.interaction.drag_vertex_ref = vertex_ref
    host.interaction.drag_vertex_original_point = original_point
    host.interaction.drag_shared_vertex_refs = shared_vertex_refs_for_drag(
        host,
        original_point,
    )
    host.interaction.drag_rectangle_context = rectangle_drag_context(
        host,
        vertex_ref,
    )
    host.set_canvas_cursor("cross")


def begin_rectangle_side_drag(
    host: VertexEditingHost,
    side_ref: tuple[int, int],
) -> None:
    """Begin dragging a selected rectangle side."""

    push_undo(
        host,
        action="resize_rectangle",
        annotation_index=host.interaction.selected_annotation_index,
        details={"side_ref": side_ref},
    )
    host.interaction.drag_vertex_ref = None
    host.interaction.drag_rectangle_side_ref = side_ref
    host.interaction.drag_vertex_original_point = None
    host.interaction.drag_shared_vertex_refs = []
    host.interaction.drag_rectangle_context = rectangle_side_drag_context(
        host,
        side_ref,
    )
    host.set_canvas_cursor("cross")


def drag_selected_vertex_to(
    host: VertexEditingHost,
    image_point: tuple[float, float],
) -> None:
    """Move the currently dragged annotation vertex."""

    if (
        host.interaction.drag_vertex_ref is None
        and host.interaction.drag_rectangle_side_ref is None
    ):
        return
    annotation = selected_annotation(host.project, host.interaction)
    if annotation is None:
        return
    if host.interaction.drag_vertex_ref is not None:
        polygon_index, vertex_index = host.interaction.drag_vertex_ref

        # CMP: TODO - Justify the need for these defensive checks,
        # particularly since there are no checks on negative index values
        if polygon_index >= len(annotation.polygons):
            return
        if vertex_index >= len(annotation.polygons[polygon_index]):
            return

    snapped_point = snapped_edit_point(
        host.project,
        host.view,
        host.interaction,
        image_point,
        host.snap_edits_var.get(),
        snapping_tolerance_image(host.prefs, host.view),
    )
    if annotation_export_type(annotation) == "rectangle":
        resize_selected_rectangle(host, snapped_point)
    elif host.interaction.drag_vertex_ref is not None:
        annotation.polygons[polygon_index][vertex_index] = snapped_point
        move_shared_drag_vertices(host, snapped_point)
    host.view.annotation_overlap_key = None
    host.project.dirty = True


def finish_vertex_drag(host: VertexEditingHost) -> None:
    """Finish dragging an annotation vertex and persist changed annotations."""

    changed_indices = []
    if host.interaction.selected_annotation_index is not None:
        changed_indices.append(host.interaction.selected_annotation_index)
    changed_indices.extend(
        annotation_index
        for annotation_index, _polygon_index, _vertex_index in (
            host.interaction.drag_shared_vertex_refs
        )
    )
    host.interaction.drag_vertex_ref = None
    host.interaction.drag_rectangle_side_ref = None
    host.interaction.drag_vertex_original_point = None
    host.interaction.drag_shared_vertex_refs = []
    host.interaction.drag_rectangle_context = None
    mark_annotations_changed(host)
    autosave_current_image(host, sorted(set(changed_indices)))
    redraw_canvas(cast(CanvasRenderHost, host))

# CMP: TODO - Clarify what is meant by 'after a selected ... segment'
def insert_vertex_at(
    host: VertexEditingHost,
    border_ref: tuple[int, int],
    image_point: tuple[float, float],
) -> None:
    """CODEX: Insert a vertex and preserve turtle-shell shared-edge edits.

    CODEX: Normal edit insertion mutates only the selected polygon. While
    CODEX: Turtle shell mode or the walk key is active, exact matching edges in
    CODEX: other free polygons receive the same vertex so later shared-vertex
    CODEX: drags keep the boundary synchronized.
    """

    annotations = current_annotations(host.project)
    selected_annotation_index = host.interaction.selected_annotation_index
    annotation = selected_annotation(host.project, host.interaction)
    if annotation is None or annotation_export_type(annotation) == "rectangle":
        return
    polygon_index, vertex_index = border_ref
    if polygon_index >= len(annotation.polygons):
        return
    polygon = annotation.polygons[polygon_index]
    if vertex_index >= len(polygon):
        return
    selected_segment = (
        polygon[vertex_index],
        polygon[(vertex_index + 1) % len(polygon)],
    )
    push_undo(
        host,
        action="insert_vertex",
        annotation_index=selected_annotation_index,
        details={"border_ref": border_ref},
    )
    polygon.insert(vertex_index + 1, image_point)
    shared_insertions: list[EdgeInsertion] = []
    if selected_annotation_index is not None and (
        host.autoclose_var.get() or host.interaction.w_down
    ):
        for annotation_index, other_annotation in enumerate(annotations):
            if annotation_index == selected_annotation_index:
                continue
            if annotation_export_type(other_annotation) == "rectangle":
                continue
            for other_polygon_index, other_polygon in enumerate(
                other_annotation.polygons
            ):
                if len(other_polygon) < 2:
                    continue
                for other_edge_index, other_start in enumerate(other_polygon):
                    other_end = other_polygon[
                        (other_edge_index + 1) % len(other_polygon)
                    ]
                    if not segments_equivalent(
                        selected_segment,
                        (other_start, other_end),
                        1e-6,
                    ):
                        continue
                    if point_to_segment_distance(
                        image_point,
                        other_start,
                        other_end,
                    ) > 1e-6:
                        continue
                    if (
                        math.dist(image_point, other_start) <= 1e-6
                        or math.dist(image_point, other_end) <= 1e-6
                    ):
                        continue
                    shared_insertions.append(
                        {
                            "annotation_index": annotation_index,
                            "polygon_index": other_polygon_index,
                            "edge_index": other_edge_index,
                            "point": image_point,
                        }
                    )
        apply_edge_insertions(annotations, shared_insertions)
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    mark_annotations_changed(host)
    host.project.dirty = True
    if shared_insertions and selected_annotation_index is not None:
        changed_indices = sorted(
            {
                selected_annotation_index,
                *(insertion["annotation_index"] for insertion in shared_insertions),
            }
        )
        autosave_current_image(host, changed_indices)
    else:
        autosave_current_image(host)
    redraw_canvas(cast(CanvasRenderHost, host))
