"""Pointer drag and release transition decisions for active edit gestures."""

from __future__ import annotations

from dataclasses import replace

from annotator.gui.interactions.state import InputAction
from annotator.gui.interactions.state import InputTransition
from annotator.gui.interactions.state import PointerFacts
from annotator.gui.state import InteractionState

# CMP: TODO - The docstring is very generic. 
def left_drag_transition(
    interaction: InteractionState,
    facts: PointerFacts,
) -> InputTransition:
    """Return state and action for continued left-button movement."""

    if (
        interaction.drag_arrow_endpoint_index is not None
        and facts.image_point is not None
    ):
        return InputTransition(
            interaction,
            InputAction.DRAG_ARROW_ENDPOINT,
            True,
            True,
        )
    
    if (
        interaction.drag_vertex_ref is not None
        or interaction.drag_rectangle_side_ref is not None
    ):
        return InputTransition(interaction, InputAction.DRAG_VERTEX, True, True)

    if (
        interaction.mode == "arrow"
        and interaction.temp_arrow_start is not None
        and facts.image_point is not None
    ):
        return InputTransition(
            replace(interaction, temp_arrow_current=facts.image_point),
            consumed=True,
            redraw=True,
        )

    if interaction.selection_drag_start is not None:
        return InputTransition(
            replace(interaction, selection_drag_current=facts.canvas_point),
            consumed=True,
            redraw=True,
        )

    if interaction.annotation_selection_drag_start is not None:
        return InputTransition(
            replace(
                interaction,
                annotation_selection_drag_current=facts.canvas_point,
            ),
            consumed=True,
            redraw=True,
        )

    if interaction.panning:
        return InputTransition(interaction, InputAction.PAN, True)

    return InputTransition(interaction)


def left_release_transition(
    interaction: InteractionState,
    facts: PointerFacts,
) -> InputTransition:
    """Return state and action for a completed left-button interaction."""

    if interaction.drag_arrow_endpoint_index is not None:
        return InputTransition(
            interaction,
            InputAction.FINISH_ARROW_ENDPOINT_DRAG,
            True,
        )
    if (
        interaction.drag_vertex_ref is not None
        or interaction.drag_rectangle_side_ref is not None
    ):
        return InputTransition(
            interaction,
            InputAction.FINISH_VERTEX_DRAG,
            True,
        )
    if (
        interaction.mode == "new_rectangle"
        and interaction.selection_drag_start is not None
    ):
        return InputTransition(
            replace(interaction, selection_drag_current=facts.canvas_point),
            InputAction.FINISH_NEW_RECTANGLE,
            True,
        )
    if interaction.selection_drag_start is not None:
        next_interaction = replace(
            interaction,
            selection_drag_start=None,
            selection_drag_current=None,
            selection_rect=facts.selection_rect,
            selected_vertices=set(facts.selected_vertices),
        )
        return InputTransition(next_interaction, consumed=True, redraw=True)
    if interaction.annotation_selection_drag_start is not None:
        next_interaction = replace(
            interaction,
            annotation_selection_drag_start=None,
            annotation_selection_drag_current=None,
            annotation_selection_rect=None,
        )
        return InputTransition(
            next_interaction,
            InputAction.SELECT_OBJECTS_IN_RECT,
            True,
            True,
        )
    return InputTransition(replace(interaction, panning=False))


def right_drag_transition(interaction: InteractionState) -> InputTransition:
    """Return the selected endpoint or vertex drag action."""

    if interaction.drag_arrow_endpoint_index is not None:
        return InputTransition(
            interaction,
            InputAction.DRAG_ARROW_ENDPOINT,
            True,
            True,
        )
    if (
        interaction.drag_vertex_ref is not None
        or interaction.drag_rectangle_side_ref is not None
    ):
        return InputTransition(interaction, InputAction.DRAG_VERTEX, True, True)
    return InputTransition(interaction)


def right_release_transition(interaction: InteractionState) -> InputTransition:
    """Return the completion action for a right-button drag."""

    if interaction.drag_arrow_endpoint_index is not None:
        return InputTransition(
            interaction,
            InputAction.FINISH_ARROW_ENDPOINT_DRAG,
            True,
        )
    if (
        interaction.drag_vertex_ref is not None
        or interaction.drag_rectangle_side_ref is not None
    ):
        return InputTransition(
            interaction,
            InputAction.FINISH_VERTEX_DRAG,
            True,
        )
    return InputTransition(interaction)
