"""Tooltip helpers for Annotator Tk widgets."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

class ToolTip:
    """Small hover tooltip for toolbar controls."""

    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 450) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.after_id: str | None = None
        self.window: tk.Toplevel | None = None
        widget.bind("<Enter>", self.schedule)
        widget.bind("<Leave>", self.hide)
        widget.bind("<ButtonPress>", self.hide)

    # CMP: TODO - This function should probably be called something like
    # show_tooltip_after_delay (extremely low priority todo).
    def schedule(self, _event: tk.Event | None = None) -> None:
        """Schedule showing the tooltip."""

        self.cancel()
        self.after_id = self.widget.after(self.delay_ms, self.show)

    def cancel(self) -> None:
        """Cancel a pending tooltip show."""

        if self.after_id is not None:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

    def set_text(self, text: str) -> None:
        """CODEX: Replace the tooltip text used for the next hover."""

        if self.text == text:
            return
        self.text = text
        if self.window is not None:
            self.hide()

    # CMP: TODO - Improve the documentation. The logic should be more obvious
    def show(self) -> None:
        """Display the tooltip near the widget."""

        if self.window is not None:
            return
        x_coord = self.widget.winfo_rootx() + 8
        y_coord = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x_coord}+{y_coord}")
        label = ttk.Label(
            self.window,
            text=self.text,
            relief=tk.SOLID,
            borderwidth=1,
            padding=(6, 3),
        )
        label.pack()

    def hide(self, _event: tk.Event | None = None) -> None:
        """Hide the tooltip."""

        self.cancel()
        if self.window is not None:
            self.window.destroy()
            self.window = None
