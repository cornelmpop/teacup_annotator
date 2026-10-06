"""CODEX: Declare semantic e2e session command metadata.

CODEX: This registry owns each command's session name, worker-idle policy, and
CODEX: recorder associations with resolved input actions, configurable shortcut
CODEX: preferences, audit actions, and live interaction modes. It does not
CODEX: execute application commands or infer those associations from runtime
CODEX: state.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessionCommandDefinition:
    """CODEX: Describe one semantic command and its recorder/replay boundaries."""

    name: str
    replay_function: str
    input_action_name: str | None = None
    key_binding_preference: str | None = None
    audit_action: str | None = None
    live_mode: str | None = None
    waits_for_worker: bool = False


COMMAND_ACTIONS = (
    SessionCommandDefinition(
        "autoclose",
        "_dispatch_autoclose",
        input_action_name="ATTEMPT_AUTOCLOSE",
        key_binding_preference="key_binding_autoclose",
        waits_for_worker=True,
    ),
    SessionCommandDefinition(
        "cancel",
        "_dispatch_cancel",
        input_action_name="CANCEL_SELECTION_OR_MODE",
        key_binding_preference="key_binding_cancel",
    ),
    SessionCommandDefinition(
        "delete_selected",
        "_dispatch_delete_selected",
        input_action_name="DELETE_SELECTED_ANNOTATION_OR_ARROW",
        key_binding_preference="key_binding_delete_annotation",
        audit_action="delete_annotation",
        waits_for_worker=True,
    ),
    SessionCommandDefinition(
        "delete_vertices",
        "_dispatch_delete_vertices",
        input_action_name="DELETE_SELECTED_VERTICES",
        key_binding_preference="key_binding_delete_vertices",
        audit_action="delete_vertices",
        waits_for_worker=True,
    ),
    SessionCommandDefinition(
        "next_image",
        "_dispatch_next_image",
        input_action_name="NEXT_IMAGE",
    ),
    SessionCommandDefinition(
        "previous_image",
        "_dispatch_previous_image",
        input_action_name="PREVIOUS_IMAGE",
    ),
    SessionCommandDefinition(
        "resample_selected",
        "_dispatch_resample_selected",
        input_action_name="SIMPLIFY_SELECTED_ANNOTATION",
        key_binding_preference="key_binding_simplify_polygon",
        audit_action="simplify_polygon",
        waits_for_worker=True,
    ),
    SessionCommandDefinition(
        "start_arrow",
        "_dispatch_start_arrow",
        input_action_name="START_DRAW_ARROW",
        key_binding_preference="key_binding_draw_arrow",
        live_mode="arrow",
        waits_for_worker=True,
    ),
    SessionCommandDefinition(
        "start_polygon",
        "_dispatch_start_polygon",
        input_action_name="START_NEW_ANNOTATION",
        key_binding_preference="key_binding_new_polygon",
        live_mode="new",
        waits_for_worker=True,
    ),
    SessionCommandDefinition(
        "start_rectangle",
        "_dispatch_start_rectangle",
        input_action_name="START_NEW_RECTANGLE",
        key_binding_preference="key_binding_new_rectangle",
        live_mode="new_rectangle",
        waits_for_worker=True,
    ),
    SessionCommandDefinition(
        "toggle_review",
        "_dispatch_toggle_review",
        input_action_name="TOGGLE_REVIEW_FLAG",
        key_binding_preference="key_binding_flag_review",
        waits_for_worker=True,
    ),
    SessionCommandDefinition(
        "zoom_in",
        "_dispatch_zoom_in",
        input_action_name="ZOOM_IN",
    ),
    SessionCommandDefinition(
        "zoom_out",
        "_dispatch_zoom_out",
        input_action_name="ZOOM_OUT",
    ),
)

COMMAND_DEFINITIONS_BY_NAME = {
    definition.name: definition for definition in COMMAND_ACTIONS
}
SESSION_COMMAND_BY_INPUT_ACTION_NAME = {
    definition.input_action_name: definition.name
    for definition in COMMAND_ACTIONS
    if definition.input_action_name is not None
}
SESSION_COMMAND_BY_KEY_BINDING_PREFERENCE = {
    definition.key_binding_preference: definition.name
    for definition in COMMAND_ACTIONS
    if definition.key_binding_preference is not None
}
SESSION_COMMAND_BY_AUDIT_ACTION = {
    definition.audit_action: definition.name
    for definition in COMMAND_ACTIONS
    if definition.audit_action is not None
}
SESSION_COMMAND_BY_MODE = {
    definition.live_mode: definition.name
    for definition in COMMAND_ACTIONS
    if definition.live_mode is not None
}


def command_definition(command_name: str) -> SessionCommandDefinition | None:
    """CODEX: Return metadata for one semantic command name if it exists."""

    return COMMAND_DEFINITIONS_BY_NAME.get(command_name)
