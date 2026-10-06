"""Configure the Tk root and assemble the complete window record."""

from __future__ import annotations

from tkinter import ttk

from annotator.gui.constants import CONTROL_PANEL_WIDTH
from annotator.gui.window.controls import build_controls
from annotator.gui.window.state import WindowHost
from annotator.gui.window.state import WindowWidgets
from annotator.gui.window.toolbar import build_toolbar
from annotator.gui.window.viewer import build_viewer
from annotator.icons import create_toolbar_icons
from annotator.release_identity import APP_NAME
from annotator.release_identity import APP_VERSION

# CMP: TODO - consider moving these preferences to a theme file.
#      probably makes sense if we are consolidating all stylistic
#      preferences in one place.
def build_window(host: WindowHost) -> WindowWidgets:
    """Configure the root and return every application widget."""

    host.root.title(f"{APP_NAME} v{APP_VERSION}")
    host.root.geometry("1200x760")
    host.root.minsize(900, 600)
    host.root.protocol("WM_DELETE_WINDOW", host.on_close)
    style = ttk.Style(host.root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    host.root.columnconfigure(0, weight=1)
    host.root.rowconfigure(0, weight=0)
    host.root.rowconfigure(1, weight=1)

    host.toolbar_icons = create_toolbar_icons(host.root)
    toolbar = build_toolbar(host)
    main = ttk.Frame(host.root, padding=8)
    main.grid(row=1, column=0, sticky="nsew")
    main.columnconfigure(0, weight=1)
    main.columnconfigure(1, weight=0, minsize=CONTROL_PANEL_WIDTH)
    main.rowconfigure(0, weight=1)
    return WindowWidgets(
        toolbar=toolbar,
        viewer=build_viewer(host, main),
        controls=build_controls(host, main),
    )
