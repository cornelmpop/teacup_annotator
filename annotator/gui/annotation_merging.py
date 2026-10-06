"""Functional annotation merge workflows."""

from __future__ import annotations

from typing import Protocol
from typing import cast

from annotator.coco.type_helpers import annotation_export_type
from annotator.geom.polygon.union import polygon_union_has_hole
from annotator.gui.annotation_cancellation import AnnotationCancellationHost
from annotator.gui.annotation_cancellation import cancel_selection_or_mode
from annotator.gui.audit.undo import push_undo
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.hit_testing import annotation_index_at
from annotator.gui.persistence import AutosaveHost
from annotator.gui.persistence import autosave_current_image
from annotator.gui.project.navigation import current_image_name
from annotator.gui.render_state import RenderStateHost
from annotator.gui.render_state import mark_annotations_changed
from annotator.gui.selection import clear_annotation_selection
from annotator.gui.selection import current_annotations
from annotator.gui.selection import selected_annotation_indexes
from annotator.gui.selection import set_single_annotation_selection
from annotator.gui.view_geometry import image_point_from_canvas


_RING_MERGE_REFUSED_MESSAGE = (
    "Merge annotation: ring-forming merge not completed; keep shell sections "
    "as separate annotations."
)


class AnnotationMergingHost(
    AutosaveHost,
    RenderStateHost,
    AnnotationCancellationHost,
    Protocol,
):
    """Application state and effects required by annotation merging."""

    def log(self, message: str) -> None:
        """CODEX: Record one annotation-merge message."""

        ...


def merge_selected_annotations(host: AnnotationMergingHost) -> None:
    """Merge all bulk-selected annotations into the lowest-index annotation."""

    if host.project.coco is None:
        return
    indexes = selected_annotation_indexes(host.project, host.interaction)
    if len(indexes) < 2:
        return

    # CMP: TODO - Explain the rationale for using the smallest index
    #      rather than, for example, the first selected annotation, as the
    #      reference. This, as user-facing behaviour, makes little sense
    #      to me, since the user is has no insight into annotation indices.
    primary_index = min(indexes)
    merge_started = False
    successful_merge = False
    merged_indexes = [primary_index]
    blocked_ring_merge = False
    for secondary_index in sorted(
        (index for index in indexes if index != primary_index),
        reverse=True,
    ):
        if _merge_would_form_hole(host, primary_index, secondary_index):
            blocked_ring_merge = True
            continue
        if not merge_started:
            push_undo(
                host,
                action="merge_annotations",
                annotation_index=primary_index,
                details={"annotation_indexes": indexes},
            )
            merge_started = True
        merged_index = host.project.coco.merge_annotations(
            current_image_name(host),
            primary_index,
            secondary_index,
        )
        if merged_index is not None:
            successful_merge = True
            primary_index = merged_index
            merged_indexes.append(secondary_index)
            if host.project.pending_audit_events:
                host.project.pending_audit_events[-1]["details"][
                    "annotation_indexes"
                ] = sorted(merged_indexes)
    if merge_started and not successful_merge:
        _discard_staged_merge(host)
    if not successful_merge:
        if blocked_ring_merge:
            host.log(_RING_MERGE_REFUSED_MESSAGE)
        return
    if blocked_ring_merge:
        host.log(_RING_MERGE_REFUSED_MESSAGE)

    # CMP: TODO - Document the next line.
    set_single_annotation_selection(host.interaction, primary_index)
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    mark_annotations_changed(host)
    host.project.dirty = True
    autosave_current_image(host)
    redraw_canvas(cast(CanvasRenderHost, host))


def start_merge_annotation_at(
    host: AnnotationMergingHost,
    canvas_point: tuple[float, float],
) -> None:
    """Use the annotation under a canvas point as the merge primary."""

    image_point = image_point_from_canvas(canvas_point, host.view)
    if image_point is None:
        return
    index = annotation_index_at(
        current_annotations(host.project),
        image_point,
    )
    if index is None:
        return
    host.interaction.mode = "merge"
    host.interaction.merge_primary_index = index
    host.interaction.select_start_annotation_index = None
    host.interaction.select_start_polygon_index = None
    clear_annotation_selection(host.interaction)
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    host.interaction.temp_polygon = []
    host.interaction.temp_arrow_start = None
    host.interaction.temp_arrow_current = None
    host.log("Merge annotation: click the annotation to merge into the first one.")
    redraw_canvas(cast(CanvasRenderHost, host))


def finish_merge_annotation_at(
    host: AnnotationMergingHost,
    image_point: tuple[float, float],
) -> None:
    """Merge the clicked secondary annotation into the selected primary."""

    if (
        host.project.coco is None
        or host.interaction.merge_primary_index is None
    ):
        return
    primary_index = host.interaction.merge_primary_index

    # CMP: TODO - Document what happens is multiple annotations are under
    # the cursor.
    secondary_index = annotation_index_at(
        current_annotations(host.project),
        image_point,
    )
    if secondary_index is None:
        host.log("Merge annotation: no second annotation under the click.")
        return
    if secondary_index == primary_index:
        host.log("Merge annotation: choose a different second annotation.")
        return
    if _merge_would_form_hole(host, primary_index, secondary_index):
        host.log(_RING_MERGE_REFUSED_MESSAGE)
        cancel_selection_or_mode(host)
        return

    push_undo(
        host,
        action="merge_annotations",
        annotation_index=primary_index,
        details={
            "primary_index": primary_index,
            "secondary_index": secondary_index,
        },
    )
    merged_index = host.project.coco.merge_annotations(
        current_image_name(host),
        primary_index,
        secondary_index,
    )
    if merged_index is None:
        cancel_selection_or_mode(host)
        return
    clear_annotation_selection(host.interaction)
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    host.interaction.mode = None
    host.interaction.merge_primary_index = None
    mark_annotations_changed(host)
    host.project.dirty = True
    autosave_current_image(host)
    redraw_canvas(cast(CanvasRenderHost, host))


def _merge_would_form_hole(
    host: AnnotationMergingHost,
    primary_index: int,
    secondary_index: int,
) -> bool:
    """CODEX: Return whether a merge would require an unsupported hole ring."""

    annotations = current_annotations(host.project)
    if (
        primary_index < 0
        or secondary_index < 0
        or primary_index >= len(annotations)
        or secondary_index >= len(annotations)
    ):
        return False
    primary = annotations[primary_index]
    secondary = annotations[secondary_index]
    if all(
        annotation_export_type(annotation) == "rectangle"
        for annotation in (primary, secondary)
    ):
        return False
    return polygon_union_has_hole(primary.polygons + secondary.polygons)


def _discard_staged_merge(host: AnnotationMergingHost) -> None:
    """CODEX: Remove the Undo and audit entries for a refused merge."""

    if host.project.undo_stack:
        host.project.undo_stack.pop()
    if host.project.pending_audit_events:
        host.project.pending_audit_events.pop()
