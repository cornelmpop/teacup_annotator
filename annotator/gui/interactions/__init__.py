"""Public input-transition API for keyboard, pointer, motion, and wheel code."""

from __future__ import annotations

from annotator.gui.interactions.keyboard import key_press_transition
from annotator.gui.interactions.keyboard import key_release_transition
from annotator.gui.interactions.motion import canvas_cursor
from annotator.gui.interactions.motion import mouse_leave_transition
from annotator.gui.interactions.motion import mouse_motion_transition
from annotator.gui.interactions.pointer_drag import left_drag_transition
from annotator.gui.interactions.pointer_drag import left_release_transition
from annotator.gui.interactions.pointer_drag import right_drag_transition
from annotator.gui.interactions.pointer_drag import right_release_transition
from annotator.gui.interactions.pointer_press import left_press_transition
from annotator.gui.interactions.pointer_press import middle_press_transition
from annotator.gui.interactions.pointer_press import right_press_transition
from annotator.gui.interactions.state import completed_drag_rect
from annotator.gui.interactions.state import InputAction
from annotator.gui.interactions.state import InputBindings
from annotator.gui.interactions.state import InputTransition
from annotator.gui.interactions.state import PointerFacts
from annotator.gui.interactions.wheel import bind_canvas_wheel
from annotator.gui.interactions.wheel import CANVAS_WHEEL_EVENTS
from annotator.gui.interactions.wheel import configured_horizontal_wheel_direction
from annotator.gui.interactions.wheel import is_horizontal_wheel_event
from annotator.gui.interactions.wheel import MIN_ZOOM
from annotator.gui.interactions.wheel import scroll_pixels_for_zoom
from annotator.gui.interactions.wheel import wheel_axis_and_direction
from annotator.gui.interactions.wheel import wheel_direction
from annotator.gui.interactions.wheel import zoom_preview_crop_size
from annotator.gui.interactions.wheel import ZOOM_CROP_SIZE

__all__ = [
    "CANVAS_WHEEL_EVENTS",
    "InputAction",
    "InputBindings",
    "InputTransition",
    "MIN_ZOOM",
    "PointerFacts",
    "ZOOM_CROP_SIZE",
    "bind_canvas_wheel",
    "canvas_cursor",
    "completed_drag_rect",
    "configured_horizontal_wheel_direction",
    "is_horizontal_wheel_event",
    "key_press_transition",
    "key_release_transition",
    "left_drag_transition",
    "left_press_transition",
    "left_release_transition",
    "middle_press_transition",
    "mouse_leave_transition",
    "mouse_motion_transition",
    "right_drag_transition",
    "right_press_transition",
    "right_release_transition",
    "scroll_pixels_for_zoom",
    "wheel_axis_and_direction",
    "wheel_direction",
    "wheel_transition",
    "zoom_preview_crop_size",
]

from annotator.gui.interactions.wheel import wheel_transition
