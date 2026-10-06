"""Build image navigation and the main annotation canvas."""

from __future__ import annotations

from functools import partial
import tkinter as tk
from tkinter import ttk

from annotator.gui.project.navigation import jump_to_image_index_from_entry
from annotator.gui.project.navigation import next_image
from annotator.gui.project.navigation import previous_image
from annotator.gui.window.state import ViewerWidgets
from annotator.gui.window.state import WindowHost


def build_viewer(host: WindowHost, parent: ttk.Frame) -> ViewerWidgets:
    """CODEX: Create navigation and a replay-stable canvas viewport with scrollbars."""

    viewer = ttk.Frame(parent)
    viewer.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    viewer.columnconfigure(0, weight=1)
    viewer.rowconfigure(1, weight=1)

    nav = ttk.Frame(viewer)
    nav.grid(row=0, column=0, sticky="ew", pady=(0, 6))
    previous_button = ttk.Button(
        nav,
        text="Previous",
        command=partial(previous_image, host),
    )
    previous_button.pack(side=tk.LEFT)
    next_button = ttk.Button(nav, text="Next", command=partial(next_image, host))
    next_button.pack(side=tk.LEFT, padx=(6, 0))
    index_frame = ttk.Frame(nav)
    index_frame.pack(side=tk.LEFT, padx=(12, 0))
    image_index_entry = ttk.Entry(
        index_frame,
        textvariable=host.image_index_var,
        width=6,
        justify=tk.RIGHT,
    )
    image_index_entry.pack(side=tk.LEFT)
    image_index_entry.bind(
        "<Return>",
        partial(jump_to_image_index_from_entry, host),
    )
    image_index_entry.bind(
        "<KP_Enter>",
        partial(jump_to_image_index_from_entry, host),
    )
    image_count_label = ttk.Label(index_frame, text="/ 0")
    image_count_label.pack(side=tk.LEFT, padx=(4, 0))
    image_status = ttk.Label(nav, text="No folder loaded")
    image_status.pack(side=tk.LEFT, padx=(12, 0))

    canvas_frame = ttk.Frame(viewer)
    canvas_frame.grid(row=1, column=0, sticky="nsew")
    canvas_frame.columnconfigure(0, weight=1)
    canvas_frame.rowconfigure(0, weight=1)
    # TODO: Move this main viewer canvas chrome colour to annotator/gui/theme.py
    # with the related window canvas palette values.
    canvas = tk.Canvas(
        canvas_frame,
        background="#202124",
        highlightthickness=0,
        xscrollincrement=1,
        yscrollincrement=1,
    )
    canvas.grid(row=0, column=0, sticky="nsew")
    # CODEX: Own scrollbar thickness so Tk 8 and Tk 9 give the canvas the same pixels.
    x_scroll = tk.Scrollbar(
        canvas_frame,
        orient=tk.HORIZONTAL,
        command=canvas.xview,
        width=14,
    )
    y_scroll = tk.Scrollbar(
        canvas_frame,
        orient=tk.VERTICAL,
        command=canvas.yview,
        width=14,
    )
    x_scroll.grid(row=1, column=0, sticky="ew")
    y_scroll.grid(row=0, column=1, sticky="ns")
    canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
    return ViewerWidgets(
        previous_button=previous_button,
        next_button=next_button,
        image_index_entry=image_index_entry,
        image_count_label=image_count_label,
        image_status=image_status,
        canvas=canvas,
    )
