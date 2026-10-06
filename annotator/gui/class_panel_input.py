"""Own class-panel wheel input, bindings, highlighting, and action menus."""

from __future__ import annotations

from functools import partial
import sys
import tkinter as tk
from typing import cast
from typing import Protocol

from annotator.gui.class_panel import CLASS_PANEL_BACKGROUND
from annotator.gui.class_panel import CLASS_PANEL_HIGHLIGHT
from annotator.gui.interactions import bind_canvas_wheel
from annotator.gui.interactions import wheel_axis_and_direction
from annotator.gui.local_class_actions import LocalClassActionHost
from annotator.gui.local_class_actions import add_local_class
from annotator.gui.local_class_actions import change_local_class_colour
from annotator.gui.local_class_actions import delete_local_class
from annotator.gui.menu_support import MenuState
from annotator.gui.menu_support import post_menu
from annotator.gui.state import InteractionState
from annotator.gui.window.state import WindowWidgets
from annotator.preferences import Preferences


class ClassPanelInputHost(LocalClassActionHost, Protocol):
    """Application state required by Classes-panel input and menus."""

    prefs: Preferences
    interaction: InteractionState
    widgets: WindowWidgets
    class_panel_rows: dict[str, tuple[tk.Misc, tk.Misc]]


def bind_class_panel_events(
    host: ClassPanelInputHost,
    widget: tk.Misc,
    class_name: str | None = None,
) -> None:
    """Bind context-menu and shared wheel behavior to a panel widget."""

    # CMP: TODO - explain platform-specific code rationale.
    callback = partial(show_class_panel_menu, host, class_name=class_name)
    widget.bind(
        "<ButtonPress-2>" if sys.platform == "darwin" else "<ButtonPress-3>",
        callback,
    )
    widget.bind("<Control-ButtonPress-1>", callback)
    bind_canvas_wheel(widget, partial(on_class_panel_wheel, host))


def on_class_panel_wheel(
    host: ClassPanelInputHost,
    event: tk.Event,
) -> str:
    """Scroll Classes-panel overflow using normalized wheel input."""

    reverse = host.prefs.get_bool("reverse_horizontal_wheel", True)
    horizontal, direction = wheel_axis_and_direction(event, reverse)
    if direction == 0:
        return "break"
    canvas = host.widgets.controls.class_list_canvas
    if horizontal:
        canvas.xview_scroll(direction, tk.UNITS)
    else:
        canvas.yview_scroll(direction, tk.UNITS)
    return "break"


def show_class_panel_menu(
    host: ClassPanelInputHost,
    event: tk.Event,
    class_name: str | None = None,
) -> str:
    """Open class actions and highlight the targeted class row."""

    if host.interaction.worker_running:
        return "break"
    for row_name, widgets in getattr(host, "class_panel_rows", {}).items():
        background = (
            CLASS_PANEL_HIGHLIGHT
            if row_name == class_name
            else CLASS_PANEL_BACKGROUND
        )
        for widget in widgets:
            widget.configure(background=background)

    menu = tk.Menu(host.root, tearoff=0)
    enabled = cast(
        MenuState,
        tk.NORMAL if host.project.folder is not None else tk.DISABLED,
    )

    # CMP: If not over a current entry, only show the 'Add class' opt.
    if class_name is not None:
        menu.add_command(
            label="Delete class",
            command=partial(delete_local_class, host, class_name),
            state=enabled,
        )
        menu.add_command(
            label="Change colour",
            command=partial(change_local_class_colour, host, class_name),
            state=enabled,
        )
        menu.add_separator()
    menu.add_command(
        label="Add class",
        command=partial(add_local_class, host),
        state=enabled,
    )
    post_menu(menu, event.x_root, event.y_root)
    return "break"
