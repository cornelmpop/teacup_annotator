"""Query and mutate current GUI region- and arrow-annotation selections."""

from __future__ import annotations

from annotator.arrows import Arrow
from annotator.coco.models import Annotation
from annotator.coco.type_helpers import annotation_export_type
from annotator.geom.rectangle import annotation_fully_inside_canvas_rect
from annotator.gui.constants import VERTEX_HALF
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState
from annotator.gui.view_geometry import image_to_canvas_point


def current_annotations(project: ProjectState) -> list[Annotation]:
    """Return current-image region annotations, or an empty unloaded result."""

    if project.coco is None or not project.image_paths:
        return []
    return project.coco.annotations_for(project.image_paths[project.current_index].name)


def selected_annotation(
    project: ProjectState,
    interaction: InteractionState,
) -> Annotation | None:
    """Return the selected region annotation when its index is valid."""

    selected_index = interaction.selected_annotation_index
    if selected_index is None:
        return None
    annotations = current_annotations(project)
    if 0 <= selected_index < len(annotations):
        return annotations[selected_index]
    return None

# CMP: TODO - Why do we need this? Calling the function seems longer than the
# code it actually runs!
def multiple_annotations_selected(interaction: InteractionState) -> bool:
    """Return whether bulk region-annotation actions should be used."""

    return len(interaction.selected_annotation_indices) > 1

# CMP: TODO - see above comment.
def multiple_arrows_selected(interaction: InteractionState) -> bool:
    """Return whether bulk arrow-annotation actions should be used."""

    return len(interaction.selected_arrow_indices) > 1


def selected_annotation_indexes(
    project: ProjectState,
    interaction: InteractionState,
) -> list[int]:
    """Return valid selected region-annotation indexes in stable order."""

    annotations = current_annotations(project)
    return [
        index
        for index in sorted(interaction.selected_annotation_indices)
        if 0 <= index < len(annotations)
    ]

# CMP: TODO - Document why we need to handle arrows separately from other
#      annotations.
def selected_arrow_indexes(
    project: ProjectState,
    interaction: InteractionState,
) -> list[int]:
    """Return valid selected arrow-annotation indexes in stable order."""

    if not project.image_paths:
        return []
    arrows = project.arrows_by_image.get(current_image_name_for_project(project), [])
    return [
        index
        for index in sorted(interaction.selected_arrow_indices)
        if 0 <= index < len(arrows)
    ]


def selected_annotation_is_rectangle(
    project: ProjectState,
    interaction: InteractionState,
) -> bool:
    """Return whether the selected region annotation is a constrained rectangle."""

    annotation = selected_annotation(project, interaction)
    return annotation is not None and annotation_export_type(annotation) == "rectangle"


def set_single_annotation_selection(
    interaction: InteractionState,
    annotation_index: int,
) -> None:
    """Replace the region-annotation selection with one explicit index."""

    interaction.selected_annotation_index = annotation_index
    interaction.selected_annotation_indices = {annotation_index}


def clear_annotation_selection(interaction: InteractionState) -> None:
    """Clear the single-edit and bulk region-annotation indexes."""

    interaction.selected_annotation_index = None
    interaction.selected_annotation_indices.clear()


def clear_arrow_selection(interaction: InteractionState) -> None:
    """Clear the single-edit and bulk arrow-annotation indexes."""

    interaction.selected_arrow_index = None
    interaction.selected_arrow_indices.clear()


def vertices_in_selection(
    project: ProjectState,
    view: ViewState,
    interaction: InteractionState,
) -> set[tuple[int, int]]:
    """Return selected region vertices overlapping the selection rectangle."""

    annotation = selected_annotation(project, interaction)
    rect = interaction.selection_rect
    if annotation is None or rect is None:
        return set()
    left, top, right, bottom = rect
    selected: set[tuple[int, int]] = set()

    # CMP: TODO - clarify the logic of the if statement; even clarifying
    # what VERTEX_HALF refers to would help.
    for polygon_index, polygon in enumerate(annotation.polygons):
        for vertex_index, image_point in enumerate(polygon):
            canvas_x, canvas_y = image_to_canvas_point(image_point, view)
            if (
                left - VERTEX_HALF <= canvas_x <= right + VERTEX_HALF
                and top - VERTEX_HALF <= canvas_y <= bottom + VERTEX_HALF
            ):
                selected.add((polygon_index, vertex_index))
    return selected


# CMP: TODO - Evaluate refactoring - do we need two different functions here?
def active_selection_rect(
    interaction: InteractionState,
) -> tuple[float, float, float, float] | None:
    """Return the current or completed vertex-selection rectangle."""

    if interaction.selection_drag_start and interaction.selection_drag_current:
        start_x, start_y = interaction.selection_drag_start
        current_x, current_y = interaction.selection_drag_current
        return (
            min(start_x, current_x),
            min(start_y, current_y),
            max(start_x, current_x),
            max(start_y, current_y),
        )
    return interaction.selection_rect


def active_annotation_selection_rect(
    interaction: InteractionState,
) -> tuple[float, float, float, float] | None:
    """Return the current or completed region-selection rectangle."""

    if (
        interaction.annotation_selection_drag_start
        and interaction.annotation_selection_drag_current
    ):
        start_x, start_y = interaction.annotation_selection_drag_start
        current_x, current_y = interaction.annotation_selection_drag_current
        return (
            min(start_x, current_x),
            min(start_y, current_y),
            max(start_x, current_x),
            max(start_y, current_y),
        )
    return interaction.annotation_selection_rect

# CMP: TODO - Clarify docstring. select enclosed... when no region is enclosed is
#      unclear.
def select_objects_in_rect(
    project: ProjectState,
    view: ViewState,
    interaction: InteractionState,
    rect: tuple[float, float, float, float] | None,
) -> None:
    """Select enclosed regions, or arrow annotations when no region is enclosed."""

    clear_annotation_selection(interaction)
    clear_arrow_selection(interaction)
    if rect is None:
        return
    selected = {
        annotation_index
        for annotation_index, annotation in enumerate(current_annotations(project))
        if annotation_fully_inside_canvas_rect(
            annotation.polygons,
            rect,
            view.zoom,
            view.image_origin,
        )
    }
    if selected:
        interaction.selected_annotation_indices = selected
        interaction.selected_annotation_index = sorted(selected)[-1]
    else:
        arrow_indexes = arrows_in_canvas_rect(project, view, rect)
        interaction.selected_arrow_indices = arrow_indexes
        if arrow_indexes:
            interaction.selected_arrow_index = sorted(arrow_indexes)[-1]
    interaction.selected_vertices.clear()
    interaction.selection_rect = None

# CMP: TODO - refactor naming - the semantic difference between these two
#      function names is too easy to miss. Perhaps something like:
#      find_arrow_indices_in_canvas_rect and is_arrow_inside_canvas_rect.
def arrows_in_canvas_rect(
    project: ProjectState,
    view: ViewState,
    rect: tuple[float, float, float, float],
) -> set[int]:
    """Return current-image arrow annotations enclosed by a canvas rectangle."""

    if not project.image_paths:
        return set()
    arrows = project.arrows_by_image.get(current_image_name_for_project(project), [])
    return {
        arrow_index
        for arrow_index, arrow in enumerate(arrows)
        if arrow_inside_canvas_rect(arrow, rect, view)
    }


def arrow_inside_canvas_rect(
    arrow: Arrow,
    rect: tuple[float, float, float, float],
    view: ViewState,
) -> bool:
    """Return whether an arrow annotation is enclosed by a canvas rectangle."""

    left, top, right, bottom = rect
    start_x, start_y = image_to_canvas_point(arrow.start, view)
    end_x, end_y = image_to_canvas_point(arrow.end, view)
    return (
        left <= start_x <= right
        and top <= start_y <= bottom
        and left <= end_x <= right
        and top <= end_y <= bottom
    )

# CMP: TODO - Clarify why this abstraction is needed - the call is longer than the
# executed code, and the docstring doesn't explain why callers should use it.
def current_image_name_for_project(project: ProjectState) -> str:
    """Return the current image name for selection helpers."""

    return project.image_paths[project.current_index].name

# CMP: QUESTION - Can't we use a generic function instead? Separate functions are currently
# implemented to check this, whether a point is inside an annotation, whether an arrow is inside
# an annotation. Really, they all check whether a point is inside a polygonal boundary, and the
# logic of how that check happens shouldn't be repeated across functions.
def point_inside_selection(
    interaction: InteractionState,
    canvas_point: tuple[float, float],
) -> bool:
    """Return whether a canvas point lies inside the saved selection rectangle."""

    if interaction.selection_rect is None:
        return False
    left, top, right, bottom = interaction.selection_rect
    x_coord, y_coord = canvas_point
    return left <= x_coord <= right and top <= y_coord <= bottom
