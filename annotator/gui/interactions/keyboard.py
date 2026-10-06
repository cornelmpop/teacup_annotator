"""Keyboard transition decisions for the Tk-free input core."""

from __future__ import annotations

from dataclasses import replace

from annotator.gui.interactions.state import InputAction
from annotator.gui.interactions.state import InputBindings
from annotator.gui.interactions.state import InputTransition
from annotator.gui.state import InteractionState


def key_press_transition(
    interaction: InteractionState,
    key: str,
    bindings: InputBindings,
    *,
    text_entry_focused: bool,
    resample_enabled: bool,
) -> InputTransition:
    """Return replacement state and action for one key press."""

    if text_entry_focused:
        return InputTransition(interaction)
    if key in {"plus", "equal", "KP_Add"}:
        return InputTransition(interaction, InputAction.ZOOM_IN, True)
    if key in {"minus", "underscore", "KP_Subtract"}:
        return InputTransition(interaction, InputAction.ZOOM_OUT, True)
    if key == "Left":
        return InputTransition(interaction, InputAction.PREVIOUS_IMAGE, True)
    if key == "Right":
        return InputTransition(interaction, InputAction.NEXT_IMAGE, True)

    normalized_key = key.lower()
    next_interaction = interaction
    resolve_action = False
    if normalized_key == "a":
        if (
            interaction.selected_annotation_index is None
            and interaction.selected_arrow_index is None
            and not interaction.selected_arrow_indices
            and interaction.mode is None
        ):
            resolve_action = True
        else:
            next_interaction = replace(interaction, a_down=True)
    elif normalized_key == bindings.multi_select:
        next_interaction = replace(interaction, x_down=True)
    elif normalized_key == bindings.autoclose:
        next_interaction = replace(interaction, w_down=True)
        resolve_action = True
    elif normalized_key == "z":
        next_interaction = replace(interaction, z_down=True)
    elif key == "Escape":
        return InputTransition(
            interaction,
            InputAction.CANCEL_SELECTION_OR_MODE,
            True,
        )
    elif key == "Return":
        action = (
            InputAction.NONE
            if interaction.worker_running
            else InputAction.DELETE_SELECTED_VERTICES
        )
        return InputTransition(interaction, action, True)
    else:
        resolve_action = True

    if not resolve_action:
        return InputTransition(next_interaction, consumed=True)
    normalized = key[:1].lower()
    if not normalized or interaction.worker_running:
        return InputTransition(next_interaction, consumed=True)
    if normalized == bindings.flag_review:
        return InputTransition(
            next_interaction,
            InputAction.TOGGLE_REVIEW_FLAG,
            True,
        )
    if interaction.mode == "new" and normalized == bindings.autoclose:
        return InputTransition(
            next_interaction,
            InputAction.ATTEMPT_AUTOCLOSE,
            True,
        )
    if (
        interaction.selected_annotation_index is not None
        or interaction.selected_arrow_index is not None
        or interaction.selected_arrow_indices
    ):
        if normalized == bindings.delete_annotation:
            return InputTransition(
                next_interaction,
                InputAction.DELETE_SELECTED_ANNOTATION_OR_ARROW,
                True,
            )
        if (
            interaction.selected_annotation_index is not None
            and normalized == bindings.simplify_polygon
            and resample_enabled
        ):
            return InputTransition(
                next_interaction,
                InputAction.SIMPLIFY_SELECTED_ANNOTATION,
                True,
            )
        return InputTransition(next_interaction, consumed=True)
    if interaction.mode is None:
        if normalized == bindings.new_polygon:
            action = InputAction.START_NEW_ANNOTATION
        elif normalized == bindings.new_rectangle:
            action = InputAction.START_NEW_RECTANGLE
        elif normalized == bindings.draw_arrow:
            action = InputAction.START_DRAW_ARROW
        else:
            action = InputAction.NONE
        return InputTransition(next_interaction, action, True)
    return InputTransition(next_interaction, consumed=True)


def key_release_transition(
    interaction: InteractionState,
    key: str,
    bindings: InputBindings,
    *,
    text_entry_focused: bool,
) -> InputTransition:
    """Return modifier state after one key release."""

    if text_entry_focused:
        return InputTransition(interaction)
    normalized = key.lower()
    if normalized == "a":
        next_interaction = replace(interaction, a_down=False)
    elif normalized == bindings.multi_select:
        next_interaction = replace(interaction, x_down=False)
    elif normalized == bindings.autoclose:
        next_interaction = replace(interaction, w_down=False)
    elif normalized == "z":
        next_interaction = replace(interaction, z_down=False)
    else:
        return InputTransition(interaction)
    return InputTransition(next_interaction, consumed=True)
