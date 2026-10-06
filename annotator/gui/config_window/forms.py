"""Shared form helpers for the configuration editor."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from annotator.gui.interactions import wheel_axis_and_direction
from annotator.project.paths import project_file_path

if TYPE_CHECKING:
    from annotator.config_window import ConfigurationWindow


def update_scope_label(
    self: ConfigurationWindow,
    _event: tk.Event | None = None,
) -> None:
    """Show the file modified by the currently selected tab."""

    tab_name = self.notebook.tab(self.notebook.select(), "text")
    folder_filename = {
        "Project": "README.txt",
        "Model": "model.conf",
    }.get(tab_name)
    if self.app.project.folder is not None and folder_filename is not None:
        scope = (
            "Loaded folder - "
            f"{project_file_path(self.app.project.folder, folder_filename)}"
        )
    else:
        scope = f"Application defaults - {self.prefs_path}"
    self.scope_label.configure(text=f"Scope: {scope}")


def add_labeled_entry(
    self: ConfigurationWindow,
    parent: ttk.Frame,
    row: int,
    key: str,
    label: str | None = None,
    width: int = 32,
) -> None:
    """Add one labeled string preference entry."""

    ttk.Label(parent, text=label or self.LABELS.get(key, key)).grid(
        row=row,
        column=0,
        sticky="w",
        padx=(0, 8),
        pady=2,
    )
    variable = self.vars.setdefault(key, tk.StringVar(master=self.window))
    ttk.Entry(parent, textvariable=variable, width=width).grid(
        row=row,
        column=1,
        sticky="ew",
        pady=2,
    )


def on_project_wheel(self: ConfigurationWindow, event: tk.Event) -> str:
    """Scroll the Project form with the shared cross-platform wheel rules."""

    _horizontal, direction = wheel_axis_and_direction(
        event,
        self.app.prefs.get_bool("reverse_horizontal_wheel", True),
    )
    self.project_canvas.yview_scroll(direction, "units")
    return "break"


def build_footer(self: ConfigurationWindow) -> None:
    """Add Save/Reload/Close buttons."""

    footer = ttk.Frame(self.window, padding=(8, 4, 8, 8))
    footer.pack(fill=tk.X)
    ttk.Button(footer, text="Save", command=self.save).pack(side=tk.RIGHT)
    ttk.Button(footer, text="Reload", command=self.reload).pack(
        side=tk.RIGHT, padx=(0, 6)
    )
    ttk.Button(footer, text="Close", command=self.window.destroy).pack(
        side=tk.RIGHT, padx=(0, 6)
    )
