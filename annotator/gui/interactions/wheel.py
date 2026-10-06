"""Wheel binding, scroll, and zoom-size helpers for input adapters."""

from __future__ import annotations

from collections.abc import Callable
import tkinter as tk

from annotator.gui.interactions.state import InputAction
from annotator.gui.interactions.state import InputTransition
from annotator.gui.state import InteractionState

# CMP: QUESTION - are we defining the zoom crop size in two places?
SCROLL_WHEEL_IMAGE_PIXELS = 60
MIN_ZOOM = 0.05
ZOOM_CROP_SIZE = 220
CANVAS_WHEEL_EVENTS = (
    "<MouseWheel>",
    "<Shift-MouseWheel>",
    "<Button-4>",
    "<Button-5>",
    "<Button-6>",
    "<Button-7>",
)


def wheel_transition(
    interaction: InteractionState,
    *,
    horizontal: bool,
    direction: int,
) -> InputTransition:
    """Return zoom or scroll action for one normalized wheel event."""

    if direction == 0:
        return InputTransition(interaction, consumed=True)
    if interaction.z_down:
        return InputTransition(
            interaction,
            InputAction.ZOOM_AT_POINTER,
            True,
        )
    action = (
        InputAction.SCROLL_HORIZONTAL if horizontal else InputAction.SCROLL_VERTICAL
    )
    return InputTransition(interaction, action, True)


def bind_canvas_wheel(
    widget: tk.Misc, callback: Callable[[tk.Event], str | None]
) -> None:
    """Bind every supported Tk wheel event to one canvas callback."""

    for sequence in CANVAS_WHEEL_EVENTS:
        try:
            widget.bind(sequence, callback)
        except tk.TclError:
            continue


def wheel_direction(event: tk.Event) -> int:
    """Return scrollbar units for a wheel event."""

    event_num = getattr(event, "num", None)
    if event_num in {4, 6}:
        return -1
    if event_num in {5, 7}:
        return 1
    delta = int(getattr(event, "delta", 0))
    if delta == 0:
        return 0
    units = max(1, min(10, abs(delta) // 120 if abs(delta) >= 120 else abs(delta)))
    return -units if delta > 0 else units


def scroll_pixels_for_zoom(direction: int, zoom: float) -> float:
    """Return canvas pixels needed for a zoom-independent image scroll step."""

    return direction * SCROLL_WHEEL_IMAGE_PIXELS * max(MIN_ZOOM, zoom)


def configured_horizontal_wheel_direction(direction: int, reverse: bool) -> int:
    """Return horizontal wheel direction after applying user preference."""

    return -direction if reverse else direction


def zoom_preview_crop_size(zoom: float) -> int:
    """Return the image-space crop size that keeps the preview/main zoom ratio."""

    return max(1, int(round(ZOOM_CROP_SIZE / max(MIN_ZOOM, zoom))))


def is_horizontal_wheel_event(event: tk.Event) -> bool:
    """Return True for horizontal wheel events."""

    if getattr(event, "num", None) in {6, 7}:
        return True
    shift_mask = 0x0001
    return bool(int(getattr(event, "state", 0)) & shift_mask)


def wheel_axis_and_direction(
    event: tk.Event, reverse_horizontal: bool
) -> tuple[bool, int]:
    """Return normalized wheel axis and direction for any supported Tk event."""

    horizontal = is_horizontal_wheel_event(event)
    direction = wheel_direction(event)
    if horizontal:
        direction = configured_horizontal_wheel_direction(direction, reverse_horizontal)
    return horizontal, direction
