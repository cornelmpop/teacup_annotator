"""Functional entry and completion effects for annotation creation modes."""

from __future__ import annotations

import time
import tkinter as tk
from typing import cast
from typing import Protocol

from annotator.gui.annotation_cancellation import AnnotationCancellationHost
from annotator.gui.annotation_cancellation import cancel_selection_or_mode
from annotator.gui.audit.undo import push_undo
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.model.settings import default_annotation_category_id
from annotator.gui.model.settings import ModelSettingsHost
from annotator.gui.persistence import AutosaveHost
from annotator.gui.persistence import autosave_current_image
from annotator.gui.project.navigation import current_image_name
from annotator.gui.render_state import RenderStateHost
from annotator.gui.render_state import mark_annotations_changed
from annotator.gui.selection import active_selection_rect
from annotator.gui.selection import current_annotations
from annotator.gui.snap_graph import snapping_tolerance_image
from annotator.gui.snapping import snapped_new_point
from annotator.gui.state import InteractionState
from annotator.gui.view_geometry import clamp_canvas_point_to_image


class AnnotationModeHost(
    AutosaveHost,
    RenderStateHost,
    AnnotationCancellationHost,
    Protocol,
):
    """Application state and effects required by annotation creation modes."""

    interaction: InteractionState
    snap_new_var: tk.BooleanVar

    def set_canvas_cursor(self, cursor: str = "") -> None: ...
    def log(self, message: str) -> None: ...


class ResampleOutlineHost(Protocol):
    """Tk mode state required to decide whether resampling is available."""

    autoclose_var: tk.BooleanVar


def resample_outline_enabled(
    host: ResampleOutlineHost,
    can_edit_annotation: bool = True,
) -> bool:
    """Return whether outline resampling is compatible with the active mode.

    Turtle shell mode depends on shared vertices and edge walks while the user
    creates or edits polygons. Resampling changes vertex spacing, so it remains
    disabled while that mode is active.
    """

    return bool(can_edit_annotation and not host.autoclose_var.get())


# CMP: TODO - There are a lot of variables for a human to keep track of. Could
# this not be exposed as a function (e.g., something like interaction.reset()),
# so that only 'interaction' has to keep track of all these vals to ensure proper
# reset? Here the responsibility seems distributed across multiple callers? IF
# this is supposed to be authoritative, then that should be clearly documented here.
def clear_transient_annotation_state(
    interaction: InteractionState,
    keep_mode: bool = False,
) -> None:
    """Clear temporary edit state before entering a new annotation mode."""

    if not keep_mode:
        interaction.mode = None
    interaction.temp_polygon = []
    interaction.temp_edge_insertions = []
    interaction.edit_started_at_monotonic_ns = None
    interaction.drag_vertex_original_point = None
    interaction.drag_shared_vertex_refs = []
    interaction.merge_primary_index = None
    interaction.temp_arrow_start = None
    interaction.temp_arrow_current = None
    interaction.selected_annotation_index = None
    interaction.selected_annotation_indices.clear()
    interaction.selected_arrow_index = None
    interaction.selected_arrow_indices.clear()
    interaction.selected_vertices.clear()
    interaction.selection_rect = None
    interaction.selection_drag_start = None
    interaction.selection_drag_current = None
    interaction.annotation_selection_drag_start = None
    interaction.annotation_selection_drag_current = None
    interaction.annotation_selection_rect = None


def start_new_annotation(host: AnnotationModeHost) -> None:
    """Enter new polygon annotation mode when an image is loaded."""

    if host.view.current_image is None:
        return
    host.interaction.mode = "new"
    clear_transient_annotation_state(host.interaction, keep_mode=True)
    host.interaction.edit_started_at_monotonic_ns = time.monotonic_ns()
    host.set_canvas_cursor("cross")

    # CMP: TODO - Document here what happens if the annotation is not
    # finished. Does it get logged still? With what state? Shouldn't it
    # be assigned a UUID before this, so the UUID can be logged, and
    # therefore unfinished annotations can be traced in the audit? OR
    # is the implicit behaviour (e.g., log showing New Polygon
    # followed immediately by e.g., New Polygon) enough?
    host.log("New polygon annotation")
    redraw_canvas(cast(CanvasRenderHost, host))


def start_new_rectangle_annotation(host: AnnotationModeHost) -> None:
    """Enter new rectangle annotation mode when an image is loaded."""

    if host.view.current_image is None:
        return
    host.interaction.mode = "new_rectangle"
    clear_transient_annotation_state(host.interaction, keep_mode=True)
    host.interaction.edit_started_at_monotonic_ns = time.monotonic_ns()
    host.set_canvas_cursor("cross")

    # CMP: TODO - Same comment as for the polygon function.
    host.log("New rectangle annotation")
    redraw_canvas(cast(CanvasRenderHost, host))


# CMP: TODO - The docstrings must document the snapping behaviour too,
# unless 'snapping' below refers to something else, which would be
# confusing and needs clarification anyhow.
# CMP: TODO 2 - Why doesn't a polygon annotation not get the same
# treatment here? Is a comparable function for polygons defined in a
# separate function? If so, that should be documented here.
def finish_new_rectangle_annotation(host: AnnotationModeHost) -> None:
    """Create and persist a rectangle from the active drag selection."""

    if host.project.coco is None:
        return
    rect = active_selection_rect(host.interaction)
    if rect is None:
        return
    left, top, right, bottom = rect
    if abs(right - left) < 2 or abs(bottom - top) < 2:
        cancel_selection_or_mode(host)
        return
    tolerance = snapping_tolerance_image(host.prefs, host.view)
    top_left = snapped_new_point(
        host.project,
        host.view,
        host.interaction,
        clamp_canvas_point_to_image((left, top), host.view),
        host.snap_new_var.get(),
        tolerance,
    )
    bottom_right = snapped_new_point(
        host.project,
        host.view,
        host.interaction,
        clamp_canvas_point_to_image((right, bottom), host.view),
        host.snap_new_var.get(),
        tolerance,
    )
    x1, y1 = top_left
    x2, y2 = bottom_right
    if abs(x2 - x1) < 1 or abs(y2 - y1) < 1:
        cancel_selection_or_mode(host)
        return
    polygon = [
        (min(x1, x2), min(y1, y2)),
        (max(x1, x2), min(y1, y2)),
        (max(x1, x2), max(y1, y2)),
        (min(x1, x2), max(y1, y2)),
    ]

    # CMP: TODO - Clarify where does the completion time or duration get
    # recorded.
    push_undo(
        host,
        action="create_annotation",
        details={"annotation_type": "rectangle"},
        started_monotonic_ns=host.interaction.edit_started_at_monotonic_ns,
    )
    annotation = host.project.coco.add_annotation(
        current_image_name(host),
        polygon,
        category_id=default_annotation_category_id(
            cast(ModelSettingsHost, host)
        ),
        annotation_type="rectangle",
    )
    annotation_index = len(current_annotations(host.project)) - 1
    if host.project.pending_audit_events:
        host.project.pending_audit_events[-1]["source_uuid"] = annotation.raw.get(
            "annotation_uuid"
        )
    host.interaction.mode = None
    host.interaction.edit_started_at_monotonic_ns = None
    host.interaction.selection_drag_start = None
    host.interaction.selection_drag_current = None
    host.interaction.selection_rect = None
    mark_annotations_changed(host)
    host.project.dirty = True
    autosave_current_image(host, [annotation_index])
    host.log(f"New rectangle annotation - {annotation.raw.get('annotation_uuid')}")
    host.update_canvas_cursor()
    redraw_canvas(cast(CanvasRenderHost, host))
