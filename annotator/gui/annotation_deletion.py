"""CODEX: Delete region annotations and arrow annotations selected in the GUI."""

from __future__ import annotations

from typing import Protocol
from typing import cast

from annotator.gui.audit.undo import push_undo
from annotator.gui.arrow_editing import delete_arrow_at
from annotator.gui.arrow_editing import save_arrows_after_edit
from annotator.gui.arrow_interaction import ArrowInteractionHost
from annotator.gui.arrow_interaction import arrow_index_at
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.hit_testing import annotation_index_at
from annotator.gui.persistence import autosave_current_image
from annotator.gui.project.navigation import current_image_name
from annotator.gui.render_state import mark_annotations_changed
from annotator.gui.selection import clear_annotation_selection
from annotator.gui.selection import current_annotations
from annotator.gui.selection import multiple_annotations_selected
from annotator.gui.selection import selected_arrow_indexes
from annotator.gui.selection import selected_annotation_indexes
from annotator.gui.state import InteractionState
from annotator.gui.view_geometry import image_point_from_canvas


class AnnotationDeletionHost(ArrowInteractionHost, Protocol):
    """CODEX: Application state and effects required by annotation deletion."""

    interaction: InteractionState

# CMP: TODO - document canvas_point parameter.
# CMP: TODO - clarify why 'unobscured arrow annotation' is important, and why topmost
#      annotation is deleted.
def delete_annotation_at(
    host: AnnotationDeletionHost,
    canvas_point: tuple[float, float],
) -> None:
    """CODEX: Delete the topmost region annotation or unobscured arrow annotation."""

    if host.project.coco is None:
        return
    image_point = image_point_from_canvas(canvas_point, host.view)
    if image_point is None:
        return
    annotations = current_annotations(host.project)
    annotation_index = annotation_index_at(annotations, image_point)
    arrow_index = arrow_index_at(host, image_point)
    if arrow_index is not None and annotation_index is None:
        delete_arrow_at(host, arrow_index)
        return
    if annotation_index is not None:
        delete_annotation_index(host, annotation_index)


def delete_annotation_index(
    host: AnnotationDeletionHost,
    index: int,
) -> None:
    """CODEX: Delete one region annotation by its exact current-image index."""

    annotations = current_annotations(host.project)
    if host.project.coco is None or not (0 <= index < len(annotations)):
        return
    push_undo(host, action="delete_annotation", annotation_index=index)
    host.project.coco.delete_annotation(current_image_name(host), index)
    clear_annotation_selection(host.interaction)
    host.interaction.selected_arrow_index = None
    host.interaction.selected_arrow_indices.clear()
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    host.interaction.mode = None
    host.interaction.merge_primary_index = None

    # CMP: TODO - Document inline why these lines are needed here
    mark_annotations_changed(host)
    host.project.dirty = True
    autosave_current_image(host)
    redraw_canvas(cast(CanvasRenderHost, host))


def delete_selected_annotation_or_arrow(
    host: AnnotationDeletionHost,
) -> None:
    """CODEX: Delete the active bulk selection or single selected annotation."""

    if multiple_annotations_selected(host.interaction):
        delete_selected_annotations(host)
        return
    if host.interaction.selected_arrow_indices:
        delete_selected_arrows(host)
        return
    if host.interaction.selected_arrow_index is not None:
        delete_arrow_at(host, host.interaction.selected_arrow_index)
        return
    if (
        host.project.coco is not None
        and host.interaction.selected_annotation_index is not None
    ):
        delete_annotation_index(
            host,
            host.interaction.selected_annotation_index,
        )

# CMP: TODO - Document naming - this function and the one above
#      have names that ar ea bit confusing, or maybe the docstring
#      in the above function, indicating bulk (i.e., plural) is what
#      I find confusing.
def delete_selected_annotations(host: AnnotationDeletionHost) -> None:
    """CODEX: Delete all region annotations selected for bulk operations."""

    if host.project.coco is None:
        return
    indexes = selected_annotation_indexes(host.project, host.interaction)
    if not indexes:
        return
    push_undo(
        host,
        action="delete_annotation",
        details={"annotation_indexes": indexes},
    )

    # CMP: TODO - document briefly why we are sorting in reverse order here.
    for index in sorted(indexes, reverse=True):
        host.project.coco.delete_annotation(current_image_name(host), index)
    clear_annotation_selection(host.interaction)
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None

    # CMP: TODO - As noted in a previous function as well, document this
    # CMP: QUESTION - several lines are reused verbatim across functions -
    #      why not refactor?
    mark_annotations_changed(host)
    host.project.dirty = True
    autosave_current_image(host)
    redraw_canvas(cast(CanvasRenderHost, host))


def delete_selected_arrows(host: AnnotationDeletionHost) -> None:
    """CODEX: Delete all arrow annotations selected for bulk operations."""

    if host.project.folder is None:
        return
    image_name = current_image_name(host)
    arrows = host.project.arrows_by_image.get(image_name, [])
    indexes = selected_arrow_indexes(host.project, host.interaction)
    if not indexes:
        return
    selected_arrows = [arrows[index] for index in indexes]
    push_undo(
        host,
        action="delete_arrow",
        details={
            "image_name": image_name,
            "arrow_indexes": indexes,
            "arrow_uuids": [arrow.arrow_uuid for arrow in selected_arrows],
            "arrows": [arrow.coords for arrow in selected_arrows],
        },
        source_table="annotations",
    )
    for index in sorted(indexes, reverse=True):
        del arrows[index]
    if arrows:
        host.project.arrows_by_image[image_name] = arrows
    else:
        host.project.arrows_by_image.pop(image_name, None)
    host.interaction.selected_arrow_index = None
    host.interaction.selected_arrow_indices.clear()
    save_arrows_after_edit(host)
    redraw_canvas(cast(CanvasRenderHost, host))
