"""Pointer motion, canvas-leave, and cursor transition decisions."""

from __future__ import annotations

from dataclasses import replace

from annotator.gui.interactions.state import InputAction
from annotator.gui.interactions.state import InputTransition
from annotator.gui.interactions.state import PointerFacts
from annotator.gui.state import InteractionState


def mouse_motion_transition(
    interaction: InteractionState,
    facts: PointerFacts,
) -> InputTransition:
    """Return state and composite display action for pointer motion."""

    if facts.image_point is None:
        action = (
            InputAction.MOTION_NEW_POLYGON
            if interaction.mode == "new"
            else InputAction.MOTION_OUTSIDE_IMAGE
        )
        return InputTransition(interaction, action)
    if interaction.mode == "arrow" and interaction.temp_arrow_start is not None:
        return InputTransition(
            replace(interaction, temp_arrow_current=facts.image_point),
            InputAction.MOTION_ARROW,
        )
    if interaction.mode == "new":
        return InputTransition(interaction, InputAction.MOTION_NEW_POLYGON)
    return InputTransition(interaction, InputAction.MOTION_IMAGE)


def mouse_leave_transition(interaction: InteractionState) -> InputTransition:
    """Return composite display cleanup for leaving the image canvas."""

    return InputTransition(
        interaction,
        InputAction.LEAVE_CANVAS,
        redraw=interaction.mode == "new",
    )


def canvas_cursor(
    interaction: InteractionState,
    *,
    cursor_point_present: bool,
    over_selected_annotation: bool,
    over_selected_arrow: bool,
) -> str:
    """Return the canvas cursor selected by current interaction facts."""

    if interaction.worker_running:
        return "watch"
    if interaction.mode in {"new", "new_rectangle", "arrow"}:
        return "cross"
    if interaction.mode == "select_start" or not cursor_point_present:
        return ""
    return "cross" if over_selected_annotation or over_selected_arrow else ""
