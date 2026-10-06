"""Functional autoclose and completion effects for new polygons."""

from __future__ import annotations

import math
import tkinter as tk
from typing import Any
from typing import cast
from typing import Protocol

from annotator.geom.graph import existing_polygon_graph_paths
from annotator.geom.polygon import polygon_has_unshared_vertex
from annotator.geom.polygon import polygon_is_non_degenerate
from annotator.geom.polygon.union import polygon_overlaps_any
from annotator.gui.audit.undo import push_undo
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.persistence import AutosaveHost
from annotator.gui.persistence import autosave_current_image
from annotator.gui.model.settings import default_annotation_category_id
from annotator.gui.model.settings import ModelSettingsHost
from annotator.gui.project.navigation import current_image_name
from annotator.gui.render_state import RenderStateHost
from annotator.gui.render_state import mark_annotations_changed
from annotator.gui.selection import clear_annotation_selection
from annotator.gui.selection import current_annotations
from annotator.gui.snap_graph import apply_temp_edge_insertions_to_annotations
from annotator.gui.snap_graph import current_snap_graph
from annotator.gui.snap_graph import existing_polygons_for_snap_graph
from annotator.gui.snap_graph import snapping_tolerance_image


_AUTOCLOSE_OVERLAP_MESSAGE = (
    "Turtle shell autoclose: path would overlap existing annotation."
)


class NewPolygonHost(AutosaveHost, RenderStateHost, Protocol):
    """Application state and effects required to create a polygon."""

    snap_new_var: tk.BooleanVar
    autoclose_var: tk.BooleanVar

    def log(self, message: str) -> None:
        """CODEX: Record one polygon-completion message."""

        ...

    def update_canvas_cursor(self) -> None: ...

# CMP: TODO - Add inline omment on the specifics of the algorithm implementation
#      so the logic and potential issues become more visible. Also document
#      the main issues being considered in the function docstring.
def attempt_autoclose_new_polygon(host: NewPolygonHost) -> bool:
    """CODEX: Close a new polygon by walking exposed existing edges when possible."""

    interaction = host.interaction
    if (
        interaction.mode != "new"
        or len(interaction.temp_polygon) < 3
        or not host.snap_new_var.get()
    ):
        return False
    tolerance = snapping_tolerance_image(host.prefs, host.view)
    if tolerance is None:
        return False
    graph = current_snap_graph(
        host.project,
        host.view,
        interaction,
        tolerance,
    )
    if graph is None or not polygon_has_unshared_vertex(
        interaction.temp_polygon,
        graph,
        tolerance,
    ):
        return False
    overlap_rejected = False
    for path in existing_polygon_graph_paths(
        graph,
        interaction.temp_polygon[-1],
        interaction.temp_polygon[0],
        tolerance,
    ):
        candidate = list(interaction.temp_polygon)
        if len(path) == 1:
            candidate.pop()
        else:
            candidate[-1] = path[0]
            candidate[0] = path[-1]
            for point in path[1:-1]:
                if math.dist(point, candidate[-1]) > 1e-9:
                    candidate.append(point)
        if not polygon_is_non_degenerate(candidate):
            continue
        # CODEX: The reported autoclose bug is candidate-specific: an
        # CODEX: overlapping shortest path must not prevent trying the next
        # CODEX: exposed route between the same snapped endpoints.
        if _candidate_overlaps_existing_annotations(host, candidate):
            overlap_rejected = True
            continue
        interaction.temp_polygon = candidate
        return finish_new_polygon_annotation(
            host,
            details={
                "annotation_type": "polygon",
                "autoclose": True,
                "autoclose_vertices_added": max(0, len(path) - 2),
            },
        )
    if overlap_rejected:
        host.log(_AUTOCLOSE_OVERLAP_MESSAGE)
    return False

# CMP: I clarified the docstring; TODO - clarify the 'details' parameter
# in the docstring. What sort of load are we expecting?
def finish_new_polygon_annotation(
    host: NewPolygonHost,
    details: dict[str, Any] | None = None,
) -> bool:
    """CODEX/CMP: Persist the new polygon as a manual annotation."""

    # CMP: TODO - document cases under which temp_polygon could have length
    # below 3 (i.e., why we are doing this check, specifically).
    interaction = host.interaction
    if (
        host.project.coco is None
        or len(interaction.temp_polygon) < 3
        or not polygon_is_non_degenerate(interaction.temp_polygon)
    ):
        return False
    audit_details: dict[str, Any] = {"annotation_type": "polygon"}
    if interaction.temp_edge_insertions:
        audit_details["shared_edge_vertices_inserted"] = len(
            interaction.temp_edge_insertions
        )
    audit_details.update(details or {})
    push_undo(
        host,
        action="create_annotation",
        details=audit_details,
        started_monotonic_ns=interaction.edit_started_at_monotonic_ns,
    )
    source_annotation_indices = sorted(
        {
            int(insertion["annotation_index"])
            for insertion in interaction.temp_edge_insertions
        }
    )
    inserted_vertices = apply_temp_edge_insertions_to_annotations(
        host.project,
        host.view,
        interaction,
    )
    if inserted_vertices:
        audit_details["shared_edge_vertices_inserted"] = inserted_vertices
        if host.project.pending_audit_events:
            host.project.pending_audit_events[-1]["details"][
                "shared_edge_vertices_inserted"
            ] = inserted_vertices
    annotation = host.project.coco.add_annotation(
        current_image_name(host),
        list(interaction.temp_polygon),
        category_id=default_annotation_category_id(
            cast(ModelSettingsHost, host)
        ),
        annotation_type="polygon",
    )
    annotation_index = len(current_annotations(host.project)) - 1
    if host.project.pending_audit_events:
        host.project.pending_audit_events[-1]["source_uuid"] = annotation.raw.get(
            "annotation_uuid"
        )
    clear_annotation_selection(interaction)
    interaction.mode = None
    interaction.temp_polygon = []
    interaction.temp_edge_insertions = []
    interaction.edit_started_at_monotonic_ns = None
    mark_annotations_changed(host)
    host.project.dirty = True
    autosave_current_image(
        host,
        [annotation_index, *source_annotation_indices],
    )

    # CMP: TODO - Check that this matches the format of other annotation additions in the logs.
    host.log(f"New polygon annotation - {annotation.raw.get('annotation_uuid')}")
    host.update_canvas_cursor()
    redraw_canvas(cast(CanvasRenderHost, host))
    return True


def _candidate_overlaps_existing_annotations(
    host: NewPolygonHost,
    candidate: list[tuple[float, float]],
) -> bool:
    """CODEX: Return whether an autoclose candidate covers existing region area."""

    existing_polygons = existing_polygons_for_snap_graph(
        host.project,
        host.interaction,
    )
    return polygon_overlaps_any(candidate, existing_polygons)
