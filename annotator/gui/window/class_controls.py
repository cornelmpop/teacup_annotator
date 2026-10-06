"""Own construction and binding of the Classes control group."""

from __future__ import annotations

from functools import partial
import tkinter as tk
from tkinter import ttk
from typing import cast

from annotator.gui.class_panel import ClassPanelHost
from annotator.gui.class_panel import on_class_list_canvas_configure
from annotator.gui.class_panel import on_class_list_frame_configure
from annotator.gui.class_panel_input import ClassPanelInputHost
from annotator.gui.class_panel_input import bind_class_panel_events
from annotator.gui.window.state import WindowHost


def build_class_controls(
    host: WindowHost,
    parent: ttk.Frame,
) -> tuple[tk.Canvas, ttk.Frame, int, ttk.Combobox]:
    """Create class rows, scrollbars, bindings, and the default selector."""

    classes_frame = ttk.LabelFrame(parent, text="Classes")
    classes_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    classes_frame.columnconfigure(0, weight=1)
    classes_frame.rowconfigure(0, weight=1)
    # TODO: Move this class-list canvas chrome colour to annotator/gui/theme.py
    # with the related class-panel palette constants.
    class_list_canvas = tk.Canvas(
        classes_frame,
        height=24,
        highlightthickness=0,
        background="#f0f0f0",
    )
    class_list_canvas.grid(row=0, column=0, sticky="nsew")
    class_y_scroll = ttk.Scrollbar(
        classes_frame,
        orient=tk.VERTICAL,
        command=class_list_canvas.yview,
    )
    class_y_scroll.grid(row=0, column=1, sticky="ns")
    class_x_scroll = ttk.Scrollbar(
        classes_frame,
        orient=tk.HORIZONTAL,
        command=class_list_canvas.xview,
    )
    class_x_scroll.grid(row=1, column=0, sticky="ew")
    class_list_canvas.configure(
        xscrollcommand=class_x_scroll.set,
        yscrollcommand=class_y_scroll.set,
    )
    class_list_frame = ttk.Frame(class_list_canvas)
    class_list_frame.columnconfigure(0, weight=1)
    class_list_window = class_list_canvas.create_window(
        (0, 0),
        window=class_list_frame,
        anchor=tk.NW,
    )
    panel_host = cast(ClassPanelHost, host)
    input_host = cast(ClassPanelInputHost, host)
    class_list_frame.bind(
        "<Configure>",
        partial(on_class_list_frame_configure, panel_host),
    )
    class_list_canvas.bind(
        "<Configure>",
        partial(on_class_list_canvas_configure, panel_host),
    )
    bind_class_panel_events(input_host, class_list_canvas)
    bind_class_panel_events(input_host, class_list_frame)

    default_class_frame = ttk.Frame(classes_frame, padding=(4, 4, 4, 0))
    default_class_frame.grid(row=2, column=0, columnspan=2, sticky="ew")
    ttk.Label(default_class_frame, text="Default class").pack(
        side=tk.LEFT,
        padx=(0, 8),
    )
    default_class_dropdown = ttk.Combobox(
        default_class_frame,
        textvariable=host.session_default_class_var,
        state="readonly",
    )
    default_class_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True)
    return (
        class_list_canvas,
        class_list_frame,
        class_list_window,
        default_class_dropdown,
    )
