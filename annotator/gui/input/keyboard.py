"""Translate Tk key events into explicit transitions and application effects."""

from __future__ import annotations

import tkinter as tk
from typing import cast

from annotator.gui.annotation_cancellation import AnnotationCancellationHost
from annotator.gui.annotation_cancellation import cancel_selection_or_mode
from annotator.gui.annotation_deletion import AnnotationDeletionHost
from annotator.gui.annotation_deletion import delete_selected_annotation_or_arrow
from annotator.gui.annotation_modes import AnnotationModeHost
from annotator.gui.annotation_modes import resample_outline_enabled
from annotator.gui.annotation_modes import start_new_annotation
from annotator.gui.annotation_modes import start_new_rectangle_annotation
from annotator.gui.annotation_resampling import AnnotationResamplingHost
from annotator.gui.annotation_resampling import simplify_selected_annotation
from annotator.gui.arrow_editing import ArrowEditingHost
from annotator.gui.arrow_editing import start_draw_arrow
from annotator.gui.input.state import KeyboardHost
from annotator.gui.input.state import KeyboardInputHost
from annotator.gui.input.viewport import zoom_at
from annotator.gui.interactions import InputAction
from annotator.gui.interactions import InputBindings
from annotator.gui.interactions import key_press_transition
from annotator.gui.interactions import key_release_transition
from annotator.gui.menu_support import menu_binding
from annotator.gui.new_polygon_completion import NewPolygonHost
from annotator.gui.new_polygon_completion import attempt_autoclose_new_polygon
from annotator.gui.project.navigation import NavigationHost
from annotator.gui.project.navigation import next_image
from annotator.gui.project.navigation import previous_image
from annotator.gui.project.review import ReviewHost
from annotator.gui.project.review import toggle_current_image_review
from annotator.gui.vertex_deletion import VertexDeletionHost
from annotator.gui.vertex_deletion import delete_selected_vertices


def input_bindings(host: KeyboardHost) -> InputBindings:
    """Resolve the current configurable key bindings from the application host."""

    return InputBindings(
        multi_select=menu_binding(host.prefs, "key_binding_multi_select"),
        autoclose=menu_binding(host.prefs, "key_binding_autoclose"),
        delete_annotation=menu_binding(
            host.prefs,
            "key_binding_delete_annotation",
        ),
        simplify_polygon=menu_binding(
            host.prefs,
            "key_binding_simplify_polygon",
        ),
        new_polygon=menu_binding(host.prefs, "key_binding_new_polygon"),
        new_rectangle=menu_binding(host.prefs, "key_binding_new_rectangle"),
        draw_arrow=menu_binding(host.prefs, "key_binding_draw_arrow"),
        flag_review=menu_binding(host.prefs, "key_binding_flag_review"),
    )


def focus_is_text_entry(host: KeyboardHost) -> bool:
    """Return whether keyboard input belongs to a text-entry widget."""

    focused_widget = host.root.focus_get()
    if focused_widget is not None and focused_widget.winfo_class() in {
        "Entry",
        "TEntry",
        "Text",
        "Spinbox",
        "TSpinbox",
    }:
        return True
    return focused_widget == host.widgets.viewer.image_index_entry


def on_key_press(host: KeyboardInputHost, event: tk.Event) -> None:
    """Apply the transition and application effect selected for a key press."""

    if focus_is_text_entry(host):
        return
    bindings = input_bindings(host)
    normalized = event.keysym[:1].lower()
    resample_enabled = bool(
        host.interaction.selected_annotation_index is not None
        and normalized == bindings.simplify_polygon
        and not host.interaction.worker_running
        and resample_outline_enabled(host)
    )
    transition = key_press_transition(
        host.interaction,
        event.keysym,
        bindings,
        text_entry_focused=False,
        resample_enabled=resample_enabled,
    )
    host.interaction = transition.interaction
    if transition.action is InputAction.ZOOM_IN:
        zoom_at(host, 1)
    elif transition.action is InputAction.ZOOM_OUT:
        zoom_at(host, -1)
    elif transition.action is InputAction.PREVIOUS_IMAGE:
        previous_image(cast(NavigationHost, host))
    elif transition.action is InputAction.NEXT_IMAGE:
        next_image(cast(NavigationHost, host))
    elif transition.action is InputAction.CANCEL_SELECTION_OR_MODE:
        cancel_selection_or_mode(cast(AnnotationCancellationHost, host))
    elif transition.action is InputAction.DELETE_SELECTED_VERTICES:
        delete_selected_vertices(cast(VertexDeletionHost, host))
    elif transition.action is InputAction.ATTEMPT_AUTOCLOSE:
        attempt_autoclose_new_polygon(cast(NewPolygonHost, host))
    elif transition.action is InputAction.DELETE_SELECTED_ANNOTATION_OR_ARROW:
        delete_selected_annotation_or_arrow(
            cast(AnnotationDeletionHost, host)
        )
    elif transition.action is InputAction.SIMPLIFY_SELECTED_ANNOTATION:
        simplify_selected_annotation(cast(AnnotationResamplingHost, host))
    elif transition.action is InputAction.START_NEW_ANNOTATION:
        start_new_annotation(cast(AnnotationModeHost, host))
    elif transition.action is InputAction.START_NEW_RECTANGLE:
        start_new_rectangle_annotation(cast(AnnotationModeHost, host))
    elif transition.action is InputAction.START_DRAW_ARROW:
        start_draw_arrow(cast(ArrowEditingHost, host))
    elif transition.action is InputAction.TOGGLE_REVIEW_FLAG:
        toggle_current_image_review(cast(ReviewHost, host))


def on_key_release(host: KeyboardHost, event: tk.Event) -> None:
    """Apply the modifier-state transition selected for a key release."""

    if focus_is_text_entry(host):
        return
    transition = key_release_transition(
        host.interaction,
        event.keysym,
        input_bindings(host),
        text_entry_focused=False,
    )
    host.interaction = transition.interaction
