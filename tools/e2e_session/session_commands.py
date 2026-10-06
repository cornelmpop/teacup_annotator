"""CODEX: Resolve and dispatch semantic e2e session commands.

CODEX: The shared command registry owns recorder associations and legal names.
CODEX: This module translates resolved GUI input actions through that metadata
CODEX: and delegates replay to the corresponding production application
CODEX: operations.
"""

from __future__ import annotations

from typing import Any
from typing import cast

from tools.e2e_session.session_action_registry import SESSION_COMMAND_NAMES
from tools.e2e_session.session_action_registry import command_definition
from tools.e2e_session.session_command_registry import (
    SESSION_COMMAND_BY_INPUT_ACTION_NAME,
)


def command_name_for_input_action(action: Any) -> str | None:
    """CODEX: Return the session command name for a resolved input action."""

    # CODEX: Preserve the contract that unknown input actions have no command.
    input_action_name = getattr(action, "name", None)
    return SESSION_COMMAND_BY_INPUT_ACTION_NAME.get(input_action_name)


def _dispatch_autoclose(app: Any) -> None:
    """CODEX: Ask the production polygon operation to autoclose ``app``."""

    from annotator.gui.new_polygon_completion import NewPolygonHost
    from annotator.gui.new_polygon_completion import attempt_autoclose_new_polygon

    attempt_autoclose_new_polygon(cast(NewPolygonHost, app))


def _dispatch_cancel(app: Any) -> None:
    """CODEX: Ask the production cancellation operation to update ``app``."""

    from annotator.gui.annotation_cancellation import AnnotationCancellationHost
    from annotator.gui.annotation_cancellation import cancel_selection_or_mode

    cancel_selection_or_mode(cast(AnnotationCancellationHost, app))


def _dispatch_delete_selected(app: Any) -> None:
    """CODEX: Ask the production deletion operation to update ``app``."""

    from annotator.gui.annotation_deletion import AnnotationDeletionHost
    from annotator.gui.annotation_deletion import delete_selected_annotation_or_arrow

    delete_selected_annotation_or_arrow(cast(AnnotationDeletionHost, app))


def _dispatch_delete_vertices(app: Any) -> None:
    """CODEX: Ask the production vertex deletion operation to update ``app``."""

    from annotator.gui.vertex_deletion import VertexDeletionHost
    from annotator.gui.vertex_deletion import delete_selected_vertices

    delete_selected_vertices(cast(VertexDeletionHost, app))


def _dispatch_next_image(app: Any) -> None:
    """CODEX: Ask production navigation to advance ``app`` one image."""

    from annotator.gui.project.navigation import NavigationHost
    from annotator.gui.project.navigation import next_image

    next_image(cast(NavigationHost, app))


def _dispatch_previous_image(app: Any) -> None:
    """CODEX: Ask production navigation to move ``app`` back one image."""

    from annotator.gui.project.navigation import NavigationHost
    from annotator.gui.project.navigation import previous_image

    previous_image(cast(NavigationHost, app))


def _dispatch_resample_selected(app: Any) -> None:
    """CODEX: Ask the production resampling operation to update ``app``."""

    from annotator.gui.annotation_resampling import AnnotationResamplingHost
    from annotator.gui.annotation_resampling import simplify_selected_annotation

    simplify_selected_annotation(cast(AnnotationResamplingHost, app))


def _dispatch_start_arrow(app: Any) -> None:
    """CODEX: Ask the production arrow operation to enter drawing mode."""

    from annotator.gui.arrow_editing import ArrowEditingHost
    from annotator.gui.arrow_editing import start_draw_arrow

    start_draw_arrow(cast(ArrowEditingHost, app))


def _dispatch_start_polygon(app: Any) -> None:
    """CODEX: Ask the production mode operation to begin a polygon."""

    from annotator.gui.annotation_modes import AnnotationModeHost
    from annotator.gui.annotation_modes import start_new_annotation

    start_new_annotation(cast(AnnotationModeHost, app))


def _dispatch_start_rectangle(app: Any) -> None:
    """CODEX: Ask the production mode operation to begin a rectangle."""

    from annotator.gui.annotation_modes import AnnotationModeHost
    from annotator.gui.annotation_modes import start_new_rectangle_annotation

    start_new_rectangle_annotation(cast(AnnotationModeHost, app))


def _dispatch_toggle_review(app: Any) -> None:
    """CODEX: Ask the production review operation to toggle ``app``."""

    from annotator.gui.project.review import ReviewHost
    from annotator.gui.project.review import toggle_current_image_review

    toggle_current_image_review(cast(ReviewHost, app))


def _dispatch_zoom_in(app: Any) -> None:
    """CODEX: Ask the production viewport operation to zoom ``app`` inward."""

    from annotator.gui.input.viewport import zoom_at

    zoom_at(app, 1)


def _dispatch_zoom_out(app: Any) -> None:
    """CODEX: Ask the production viewport operation to zoom ``app`` outward."""

    from annotator.gui.input.viewport import zoom_at

    zoom_at(app, -1)


_REPLAY_FUNCTIONS_BY_NAME = {
    replay_function.__name__: replay_function
    for replay_function in (
        _dispatch_autoclose,
        _dispatch_cancel,
        _dispatch_delete_selected,
        _dispatch_delete_vertices,
        _dispatch_next_image,
        _dispatch_previous_image,
        _dispatch_resample_selected,
        _dispatch_start_arrow,
        _dispatch_start_polygon,
        _dispatch_start_rectangle,
        _dispatch_toggle_review,
        _dispatch_zoom_in,
        _dispatch_zoom_out,
    )
}


def dispatch_session_command(app: Any, command_name: str) -> None:
    """CODEX: Execute one registered semantic command against ``app``.

    CODEX: Registry metadata selects the local function that delegates to the
    CODEX: same production operation as the corresponding GUI shortcut.
    """

    definition = command_definition(command_name)
    if definition is None:
        raise ValueError(f"unsupported session command {command_name!r}")
    replay_function = _REPLAY_FUNCTIONS_BY_NAME[definition.replay_function]
    replay_function(app)
