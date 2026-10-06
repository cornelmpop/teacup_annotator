"""CODEX: Index replayable e2e action and command metadata.

CODEX: This module composes declarative action definitions with semantic
CODEX: command definitions and exposes lookup maps used by parsers, recorders,
CODEX: and replay.
"""

from __future__ import annotations

from tools.e2e_session.session_action_definitions import EXPECTATION_ACTIONS
from tools.e2e_session.session_action_definitions import SESSION_ACTIONS
from tools.e2e_session.session_action_definitions import SETUP_ACTIONS
from tools.e2e_session.session_action_definitions import SessionActionDefinition
from tools.e2e_session.session_command_registry import COMMAND_ACTIONS
from tools.e2e_session.session_command_registry import COMMAND_DEFINITIONS_BY_NAME
from tools.e2e_session.session_command_registry import SessionCommandDefinition
from tools.e2e_session.session_command_registry import command_definition


ACTION_DEFINITIONS = (*SETUP_ACTIONS, *SESSION_ACTIONS, *EXPECTATION_ACTIONS)
ACTION_BY_SECTION_AND_VERB = {
    (definition.section, definition.verb): definition
    for definition in ACTION_DEFINITIONS
}
VERBS_BY_SECTION = {
    section: frozenset(
        definition.verb
        for definition in ACTION_DEFINITIONS
        if definition.section == section
    )
    for section in ("setup", "session", "expect")
}
SESSION_COMMAND_NAMES = frozenset(COMMAND_DEFINITIONS_BY_NAME)


def action_definition(section: str, verb: str) -> SessionActionDefinition | None:
    """CODEX: Return registry metadata for one section verb if it exists."""

    return ACTION_BY_SECTION_AND_VERB.get((section, verb))
