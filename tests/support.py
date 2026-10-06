"""Shared lightweight test hosts for GUI function tests."""

from __future__ import annotations

from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState


class StatefulHost:
    """Provide independent typed GUI state records for tests."""

    def __init__(self) -> None:
        """Initialize empty records for an unloaded test host."""

        self.project = ProjectState()
        self.view = ViewState()
        self.interaction = InteractionState()
