"""CODEX: Declare legal e2e actions and their recorder/replay metadata.

CODEX: This module owns each setup, session, and expectation definition,
CODEX: including recorder boundaries and replay policy. Registry lookups and
CODEX: semantic command composition remain in ``session_action_registry``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessionActionDefinition:
    """CODEX: Describe one legal verb, its recorder owners, and replay contract."""

    section: str
    verb: str
    kind: str
    replay_method: str | None = None
    validator: str | None = None
    waits_for_worker: bool = False
    pumps_after_dispatch: bool = True
    asserts_observations: bool = True
    recorder_boundaries: tuple[str, ...] = ()


SETUP_ACTIONS = (
    SessionActionDefinition(
        "setup", "fixture", "setup",
        recorder_boundaries=("recording_writer.RecordingSessionWriter.text",),
    ),
    SessionActionDefinition(
        "setup", "prefs", "setup",
        recorder_boundaries=(
            "recording_writer.RecordingSessionWriter.set_preferences",
        ),
    ),
    SessionActionDefinition(
        "setup", "window", "setup",
        recorder_boundaries=("recording_writer.RecordingSessionWriter.set_window",),
    ),
)

SESSION_ACTIONS = (
    SessionActionDefinition(
        "session", "arrow_point", "semantic_pointer", "_dispatch_arrow_point",
        "semantic_point", waits_for_worker=True,
        recorder_boundaries=("recording_semantic_actions.recording_arrow_point",),
    ),
    SessionActionDefinition(
        "session", "choose", "menu", "_dispatch_choose", waits_for_worker=True,
        recorder_boundaries=(
            "recording_menu_commands.RecordingMenuCommandHooks._recorded_menu_command",
        ),
    ),
    SessionActionDefinition(
        "session", "click", "raw_pointer", "_dispatch_click",
        waits_for_worker=True,
        recorder_boundaries=(
            "recording_pointer.RecordingPointerHooks._record_pointer_action",
        ),
    ),
    SessionActionDefinition(
        "session", "close", "lifecycle", "_dispatch_close",
        pumps_after_dispatch=False,
        recorder_boundaries=(
            "recording_runtime.RecordingRuntime._record_close_once",
        ),
    ),
    SessionActionDefinition(
        "session", "command", "semantic_command", "_dispatch_command", "command",
        recorder_boundaries=(
            "recording_input.RecordingInputHooks._recordable_command_action",
        ),
    ),
    SessionActionDefinition(
        "session", "config_choose", "configuration", "_dispatch_config_choose",
        waits_for_worker=True,
        recorder_boundaries=(
            "recording_configuration.recording_configuration_choose",
            "recording_configuration.recording_configuration_colour",
        ),
    ),
    SessionActionDefinition(
        "session", "config_save", "configuration", "_dispatch_config_save",
        waits_for_worker=True,
        recorder_boundaries=(
            "recording_configuration.recording_configuration_save",
        ),
    ),
    SessionActionDefinition(
        "session", "dialog", "dialog", "_dispatch_dialog",
        asserts_observations=False,
        recorder_boundaries=(
            "recording_dialogs.RecordingDialogHooks._record_dialog",
        ),
    ),
    SessionActionDefinition(
        "session", "drag", "raw_pointer", "_dispatch_drag", "drag",
        waits_for_worker=True,
        recorder_boundaries=(
            "recording_pointer.RecordingPointerHooks._record_pointer_action",
        ),
    ),
    SessionActionDefinition(
        "session", "hover", "hover", "_dispatch_hover",
        recorder_boundaries=(
            "recording_widget_input.RecordingWidgetInputHooks._record_hover",
        ),
    ),
    SessionActionDefinition(
        "session", "invoke", "widget", "_dispatch_invoke", waits_for_worker=True,
        recorder_boundaries=(
            "recording_widget_commands.RecordingWidgetCommandHooks._record_widget_invoke",
        ),
    ),
    SessionActionDefinition(
        "session", "key", "raw_key", "_dispatch_key",
        recorder_boundaries=(
            "recording_input.RecordingInputHooks._recordable_key_action",
        ),
    ),
    SessionActionDefinition(
        "session", "loaded", "lifecycle", "_dispatch_loaded",
        asserts_observations=False,
        recorder_boundaries=(
            "recording_action_log.RecordingActionLog.record_loaded_session_line",
        ),
    ),
    SessionActionDefinition(
        "session", "menu", "menu", "_dispatch_menu", waits_for_worker=True,
        recorder_boundaries=(
            "recording_menu_commands.RecordingMenuCommandHooks.post_menu",
        ),
    ),
    SessionActionDefinition(
        "session", "new_polygon_point", "semantic_pointer",
        "_dispatch_new_polygon_point", "semantic_point", waits_for_worker=True,
        recorder_boundaries=(
            "recording_semantic_actions.recording_new_polygon_point",
        ),
    ),
    SessionActionDefinition(
        "session", "resize", "lifecycle", "_dispatch_resize", "resize",
        recorder_boundaries=(
            "recording_widget_input.RecordingWidgetInputHooks._flush_resize",
        ),
    ),
    SessionActionDefinition(
        "session", "scroll", "viewport", "_dispatch_scroll", "scroll",
        recorder_boundaries=(
            "recording_wheel.RecordingWheelHooks._flush_wheel_actions",
        ),
    ),
    SessionActionDefinition(
        "session", "select", "widget", "_dispatch_select", waits_for_worker=True,
        recorder_boundaries=(
            "recording_widget_commands.RecordingWidgetCommandHooks._record_widget_selection",
        ),
    ),
    SessionActionDefinition(
        "session", "submit", "widget", "_dispatch_submit", "submit",
        waits_for_worker=True,
        recorder_boundaries=(
            "recording_widget_input.RecordingWidgetInputHooks._record_image_index_submit",
        ),
    ),
    SessionActionDefinition(
        "session", "type", "text", "_dispatch_type", waits_for_worker=True
    ),
    SessionActionDefinition("session", "wait", "timing", "_dispatch_wait"),
    SessionActionDefinition(
        "session", "zoom", "viewport", "_dispatch_zoom", "zoom",
        recorder_boundaries=(
            "recording_wheel.RecordingWheelHooks._flush_wheel_actions",
        ),
    ),
)

EXPECTATION_ACTIONS = (
    SessionActionDefinition(
        "expect", "outputs", "expectation",
        recorder_boundaries=("recording_writer.RecordingSessionWriter.text",),
    ),
)
