"""User notice for Turtle shell mode behavior."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

TURTLE_SHELL_NOTICE = (
    "Turtle shell mode is now active.\n\n"
    "- Arrows record connected shell orientation without reorienting polygons.\n"
    "- Resample outline is disabled while Turtle shell mode is active.\n"
    "- Enable snapping for new annotations and edits for best results."
)


def show_turtle_shell_notice(root: tk.Tk) -> None:
    """Show the reusable Turtle shell mode behavior notice."""

    messagebox.showinfo(
        "Turtle shell mode",
        TURTLE_SHELL_NOTICE,
        parent=root,
    )
