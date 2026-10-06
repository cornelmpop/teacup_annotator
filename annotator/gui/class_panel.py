"""Own class counts, rows, sizing, and default-class synchronization."""

from __future__ import annotations

import tkinter as tk
from typing import cast
from typing import Protocol
from typing import TYPE_CHECKING

from annotator.gui.constants import ANNOTATION_OUTLINE
from annotator.gui.menu_support import class_menu_shortcut_map
from annotator.gui.model.settings import active_class_names
from annotator.gui.model.settings import class_colour_map
from annotator.gui.model.settings import configured_default_class
from annotator.gui.model.settings import ModelSettingsHost
from annotator.gui.selection import current_annotations
from annotator.gui.state import ProjectState

if TYPE_CHECKING:
    from annotator.gui.class_panel_input import ClassPanelInputHost
    from annotator.gui.window.state import WindowWidgets


CLASS_PANEL_ROW_HEIGHT = 24
CLASS_PANEL_MAX_ROWS = 5
# CMP: TODO: Move these class-panel chrome colours to annotator/gui/theme.py with
# the related dialog and window canvas palette values.
CLASS_PANEL_BACKGROUND = "#f0f0f0"
CLASS_PANEL_FOREGROUND = "#000000"
CLASS_PANEL_HIGHLIGHT = "#c9ddf2"


class ClassPanelHost(ModelSettingsHost, Protocol):
    """Application values required to render and size the Classes panel."""

    widgets: WindowWidgets
    class_panel_rows: dict[str, tuple[tk.Misc, tk.Misc]]


def current_class_counts(project: ProjectState) -> dict[str, int]:
    """Count annotation objects by class for the displayed image."""

    if project.coco is None or not project.image_paths:
        return {}
    counts: dict[str, int] = {}
    for annotation in current_annotations(project):
        class_name = project.coco.category_name_for_id(annotation.category_id)
        counts[class_name] = counts.get(class_name, 0) + 1
    return counts

# CMP: TODO - Stylistic elements (such as colour) should not be hard coded here.
#      So, highlightbackground should not be defined as a colour here. Padding
#      can stay here, of course.
def refresh_class_panel(host: ClassPanelHost) -> None:
    """Render active classes, current-image counts, and saved colours."""

    if not hasattr(host, "widgets"):
        return
    # Import after module initialization to avoid the panel/action import cycle.
    from annotator.gui.class_panel_input import bind_class_panel_events

    input_host = cast("ClassPanelInputHost", host)
    for child in host.widgets.controls.class_list_frame.winfo_children():
        child.destroy()

    class_names = active_class_names(host)
    colour_map = class_colour_map(host)
    class_counts = current_class_counts(host.project)
    class_shortcuts = class_menu_shortcut_map(class_names)
    host.class_panel_rows = {}
    for row, class_name in enumerate(class_names):
        shortcut = class_shortcuts.get(class_name)
        row_frame = tk.Frame(
            host.widgets.controls.class_list_frame,
            background=CLASS_PANEL_BACKGROUND,
        )
        row_frame.grid(row=row, column=0, sticky="ew")
        row_frame.columnconfigure(0, weight=1)
        name_label = tk.Label(
            row_frame,
            text=(
                f"{shortcut + '. ' if shortcut else ''}{class_name} "
                f"({class_counts.get(class_name, 0)})"
            ),
            anchor="w",
            background=CLASS_PANEL_BACKGROUND,
            foreground=CLASS_PANEL_FOREGROUND,
        )
        name_label.grid(row=0, column=0, sticky="ew", padx=(4, 8), pady=2)
        swatch = tk.Canvas(
            row_frame,
            width=16,
            height=16,
            background=colour_map.get(class_name, ANNOTATION_OUTLINE),
            highlightthickness=1,
            highlightbackground="#777777",
        )
        swatch.grid(row=0, column=1, padx=(0, 5), pady=3)
        host.class_panel_rows[class_name] = (row_frame, name_label)
        bind_class_panel_events(input_host, row_frame, class_name)
        bind_class_panel_events(input_host, name_label, class_name)
        bind_class_panel_events(input_host, swatch, class_name)

    visible_rows = min(max(1, len(class_names)), CLASS_PANEL_MAX_ROWS)
    class_list = host.widgets.controls.class_list_canvas
    class_list.configure(height=visible_rows * CLASS_PANEL_ROW_HEIGHT)
    class_list.itemconfigure(host.widgets.controls.class_list_window, width=1)
    host.widgets.controls.class_list_frame.update_idletasks()
    requested_width = host.widgets.controls.class_list_frame.winfo_reqwidth()
    canvas_width = max(1, class_list.winfo_width())
    class_list.itemconfigure(
        host.widgets.controls.class_list_window,
        width=max(canvas_width, requested_width),
    )
    class_list.configure(scrollregion=class_list.bbox("all") or (0, 0, 0, 0))
    host.widgets.controls.default_class_dropdown.configure(values=class_names)
    selected_class = host.session_default_class_var.get().strip()
    if selected_class not in class_names:
        configured_class = configured_default_class(host)
        fallback_class = (
            configured_class
            if configured_class in class_names
            else class_names[0] if class_names else ""
        )
        host.session_default_class_var.set(fallback_class)


def on_class_list_frame_configure(
    host: ClassPanelHost,
    _event: tk.Event,
) -> None:
    """Keep scroll bounds aligned with dynamically rebuilt class rows."""

    class_list = host.widgets.controls.class_list_canvas
    class_list.configure(scrollregion=class_list.bbox("all") or (0, 0, 0, 0))


def on_class_list_canvas_configure(
    host: ClassPanelHost,
    event: tk.Event,
) -> None:
    """Fill the viewport while preserving overflow for long class names."""

    requested_width = host.widgets.controls.class_list_frame.winfo_reqwidth()
    host.widgets.controls.class_list_canvas.itemconfigure(
        host.widgets.controls.class_list_window,
        width=max(event.width, requested_width),
    )
