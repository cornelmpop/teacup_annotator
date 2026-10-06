"""Functional annotation class-change workflows."""

from __future__ import annotations

from typing import Protocol
from typing import cast

from annotator.gui.audit.undo import push_undo
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.hit_testing import annotation_index_at
from annotator.gui.persistence import AutosaveHost
from annotator.gui.persistence import autosave_current_image
from annotator.gui.render_state import RenderStateHost
from annotator.gui.render_state import mark_annotations_changed
from annotator.gui.selection import current_annotations
from annotator.gui.selection import multiple_annotations_selected
from annotator.gui.selection import selected_annotation_indexes
from annotator.gui.selection import set_single_annotation_selection
from annotator.gui.state import InteractionState
from annotator.gui.view_geometry import image_point_from_canvas


class AnnotationClassHost(AutosaveHost, RenderStateHost, Protocol):
    """Application state and effects required to change annotation classes."""

    interaction: InteractionState


# CMP: TODO - Document parameters, specifically canvas_point
def change_annotation_class_at(
    host: AnnotationClassHost,
    canvas_point: tuple[float, float],
    class_name: str,
) -> None:
    """Change the class/category of the annotation under the cursor."""

    # CMP: TODO - Document host.project.coco here
    if host.project.coco is None:
        return
    if multiple_annotations_selected(host.interaction):
        change_selected_annotation_classes(host, class_name)
        return
    
    image_point = image_point_from_canvas(canvas_point, host.view)
    if image_point is None:
        return
    annotations = current_annotations(host.project)
    annotation_index = annotation_index_at(annotations, image_point)
    if annotation_index is None:
        return
    annotation = annotations[annotation_index]
    old_category_id = annotation.category_id
    old_class_name = host.project.coco.category_name_for_id(old_category_id)
    new_category_id = host.project.coco.category_id_for_name(class_name)
    if annotation.category_id == new_category_id:
        return

    # CMP: TODO - Document what push_undo does.
    push_undo(
        host,
        action="change_class",
        annotation_index=annotation_index,
        details={
            "old_category_id": old_category_id,
            "old_class_name": old_class_name,
            "new_category_id": new_category_id,
            "new_class_name": class_name,
        },
    )

    # CMP: QUESTION: Why do we need both obj_class and class_name if they
    #      resolve to the same var?
    annotation.category_id = new_category_id
    annotation.raw["obj_class"] = class_name
    annotation.raw["class_name"] = class_name
    set_single_annotation_selection(host.interaction, annotation_index)
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    mark_annotations_changed(host)

    # CMP: TODO - document here why the next line is needed
    host.project.dirty = True
    autosave_current_image(host)
    redraw_canvas(cast(CanvasRenderHost, host))

# CMP: QUESTION - would it not make sense to have this as a general purpose
# entry point where a single selection with coordinates passed is a special case?
def change_selected_annotation_classes(
    host: AnnotationClassHost,
    class_name: str,
) -> None:
    """Change the class/category of all bulk-selected annotations."""

    if host.project.coco is None:
        return
    annotations = current_annotations(host.project)
    indexes = selected_annotation_indexes(host.project, host.interaction)
    if not indexes:
        return
    new_category_id = host.project.coco.category_id_for_name(class_name)
    changed = [
        index
        for index in indexes
        if annotations[index].category_id != new_category_id
    ]
    if not changed:
        return
    push_undo(
        host,
        action="change_class",
        details={
            "annotation_indexes": changed,
            "new_category_id": new_category_id,
            "new_class_name": class_name,
        },
    )
    for annotation_index in changed:
        annotation = annotations[annotation_index]
        annotation.category_id = new_category_id
        annotation.raw["obj_class"] = class_name
        annotation.raw["class_name"] = class_name
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    mark_annotations_changed(host)
    host.project.dirty = True
    autosave_current_image(host)
    redraw_canvas(cast(CanvasRenderHost, host))
