"""Structural application contracts consumed by Tk input adapters."""

from __future__ import annotations

import tkinter as tk
from typing import Protocol

from annotator.gui.render_state import RenderStateHost
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState
from annotator.gui.window.state import WindowWidgets
from annotator.preferences import Preferences

Point = tuple[float, float]


class InputStateHost(Protocol):
    """Shared state and widgets required by every input adapter."""

    root: tk.Tk
    prefs: Preferences
    project: ProjectState
    view: ViewState
    interaction: InteractionState
    widgets: WindowWidgets
    snap_edits_var: tk.BooleanVar
    autoclose_var: tk.BooleanVar


class PointerHost(InputStateHost, RenderStateHost, Protocol):
    """Application effects dispatched by pointer-button adapters."""



class MotionHost(InputStateHost, RenderStateHost, Protocol):
    """Application rendering effects used by motion and viewport adapters."""

    def set_canvas_cursor(self, cursor: str = "") -> None: ...


class KeyboardHost(InputStateHost, Protocol):
    """Application actions dispatched by keyboard adapters."""


class KeyboardInputHost(KeyboardHost, MotionHost, Protocol):
    """Combined keyboard and viewport contract needed by zoom shortcuts."""


class InputBindingHost(PointerHost, KeyboardInputHost, Protocol):
    """Complete structural host accepted by the window binding function."""
