"""Pointer press transition decisions for selection, editing, panning, and menus."""

from __future__ import annotations

from dataclasses import replace

from annotator.gui.interactions.state import InputAction
from annotator.gui.interactions.state import InputTransition
from annotator.gui.interactions.state import PointerFacts
from annotator.gui.state import InteractionState


def left_press_transition(
    interaction: InteractionState,
    facts: PointerFacts,
) -> InputTransition:
    """Return state and action selected by a left-button press."""

    if facts.image_point is None:
        action = (
            InputAction.CANCEL_SELECTION_OR_MODE
            if interaction.mode == "select_start"
            else InputAction.NONE
        )
        return InputTransition(interaction, action, action is not InputAction.NONE)
    mode_actions = {
        "select_start": InputAction.FINISH_SELECT_START,
        "new": InputAction.ADD_NEW_POLYGON_POINT,
        "arrow": InputAction.HANDLE_ARROW_CLICK,
        "merge": InputAction.FINISH_MERGE,
    }
    if interaction.mode in mode_actions:
        return InputTransition(interaction, mode_actions[interaction.mode], True)
    if interaction.mode == "new_rectangle":
        next_interaction = replace(
            interaction,
            selection_drag_start=facts.canvas_point,
            selection_drag_current=facts.canvas_point,
            selection_rect=None,
            selected_vertices=set(),
        )
        return InputTransition(next_interaction, consumed=True, redraw=True)
    if interaction.mode == "delete":
        if facts.annotation_index is None and facts.arrow_index is None:
            return InputTransition(interaction, consumed=True)
        next_interaction = replace(
            interaction,
            selected_annotation_index=None,
            selected_annotation_indices=set(),
            selected_arrow_index=None,
            selected_arrow_indices=set(),
            mode=None,
        )
        return InputTransition(
            next_interaction,
            InputAction.DELETE_AT_POINT,
            True,
        )
    if interaction.x_down and interaction.mode is None:
        if facts.annotation_index is None:
            next_interaction = replace(
                interaction,
                annotation_selection_drag_start=facts.canvas_point,
                annotation_selection_drag_current=facts.canvas_point,
                annotation_selection_rect=None,
            )
        else:
            selected = set(interaction.selected_annotation_indices)
            selected.add(facts.annotation_index)
            next_interaction = replace(
                interaction,
                selected_annotation_index=facts.annotation_index,
                selected_annotation_indices=selected,
                selected_arrow_index=None,
                selected_arrow_indices=set(),
                selected_vertices=set(),
                selection_rect=None,
            )
        return InputTransition(next_interaction, consumed=True, redraw=True)
    if facts.arrow_endpoint_index is not None:
        return InputTransition(
            interaction,
            InputAction.BEGIN_ARROW_ENDPOINT_DRAG,
            True,
        )
    if facts.vertex_ref is not None:
        return InputTransition(interaction, InputAction.BEGIN_VERTEX_DRAG, True)
    if facts.rectangle_side_ref is not None:
        return InputTransition(
            interaction,
            InputAction.BEGIN_RECTANGLE_SIDE_DRAG,
            True,
        )
    if interaction.a_down and facts.selected_annotation_present:
        next_interaction = replace(
            interaction,
            selection_drag_start=facts.canvas_point,
            selection_drag_current=facts.canvas_point,
            selection_rect=None,
            selected_vertices=set(),
        )
        return InputTransition(next_interaction, consumed=True, redraw=True)
    if (
        facts.selected_annotation_present
        and not facts.selected_annotation_is_rectangle
        and facts.border_ref is not None
    ):
        return InputTransition(interaction, InputAction.INSERT_VERTEX, True)
    if facts.arrow_index is not None:
        next_interaction = replace(
            interaction,
            selected_annotation_index=None,
            selected_annotation_indices=set(),
            selected_arrow_index=facts.arrow_index,
            selected_arrow_indices=set(),
            selected_vertices=set(),
            selection_rect=None,
        )
        return InputTransition(next_interaction, consumed=True, redraw=True)
    if facts.annotation_index is not None:
        next_interaction = replace(
            interaction,
            selected_annotation_index=facts.annotation_index,
            selected_annotation_indices={facts.annotation_index},
            selected_arrow_index=None,
            selected_arrow_indices=set(),
            selected_vertices=set(),
            selection_rect=None,
        )
        return InputTransition(next_interaction, consumed=True, redraw=True)

    had_selection = (
        interaction.selected_annotation_index is not None
        or interaction.selected_arrow_index is not None
        or bool(interaction.selected_arrow_indices)
    )
    next_interaction = replace(interaction, panning=True)
    if had_selection:
        next_interaction = replace(
            next_interaction,
            selected_annotation_index=None,
            selected_annotation_indices=set(),
            selected_arrow_index=None,
            selected_arrow_indices=set(),
            selected_vertices=set(),
            selection_rect=None,
        )
    return InputTransition(
        next_interaction,
        InputAction.START_PAN,
        True,
        had_selection,
    )


def right_press_transition(
    interaction: InteractionState,
    facts: PointerFacts,
) -> InputTransition:
    """Return the drag or menu action selected by a right-button press."""

    if not facts.multiple_annotations_selected:
        if facts.arrow_endpoint_index is not None:
            return InputTransition(
                interaction,
                InputAction.BEGIN_ARROW_ENDPOINT_DRAG,
                True,
            )
        if facts.vertex_ref is not None:
            return InputTransition(interaction, InputAction.BEGIN_VERTEX_DRAG, True)
    action = (
        InputAction.SHOW_VERTEX_SELECTION_MENU
        if (
            not facts.multiple_annotations_selected
            and facts.inside_vertex_selection
            and interaction.selected_vertices
        )
        else InputAction.SHOW_CANVAS_MENU
    )
    return InputTransition(interaction, action, True)


def middle_press_transition(
    interaction: InteractionState,
    facts: PointerFacts,
) -> InputTransition:
    """Return vertex deletion for a valid free-polygon hit."""

    if facts.vertex_ref is None or facts.selected_annotation_is_rectangle:
        return InputTransition(interaction)
    return InputTransition(interaction, InputAction.DELETE_VERTEX, True)
