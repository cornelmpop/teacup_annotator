"""Build the zoom, class, preference, log, and summary controls."""

from __future__ import annotations

from functools import partial
import tkinter as tk
from tkinter import ttk
from typing import cast

from annotator.gui.constants import CONTROL_PANEL_WIDTH
from annotator.gui.constants import ZOOM_VIEW_SIZE
from annotator.gui.model.preferences import ModelPreferenceHost
from annotator.gui.model.preferences import on_autoclose_changed
from annotator.gui.model.preferences import on_live_lines_changed
from annotator.gui.model.preferences import on_show_labels_changed
from annotator.gui.model.preferences import on_show_overlapping_edges_changed
from annotator.gui.model.preferences import on_show_vertex_ids_changed
from annotator.gui.model.preferences import on_snap_checkbox_changed
from annotator.gui.window.class_controls import build_class_controls
from annotator.gui.window.state import ControlWidgets
from annotator.gui.window.state import WindowHost


def build_controls(host: WindowHost, parent: ttk.Frame) -> ControlWidgets:
    """Create the complete right-side control panel."""

    preference_host = cast(ModelPreferenceHost, host)
    controls = ttk.Frame(parent, padding=(8, 0, 0, 0))
    controls.configure(width=CONTROL_PANEL_WIDTH)
    controls.grid(row=0, column=1, sticky="nsew")
    controls.grid_propagate(False)
    controls.columnconfigure(0, weight=1)
    controls.rowconfigure(3, weight=1)

    zoom_frame = ttk.LabelFrame(controls, text="Zoom")
    zoom_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    zoom_frame.columnconfigure(0, weight=1)
    # TODO: Move these zoom preview chrome colours to annotator/gui/theme.py
    # with the related dialog and canvas palette values.
    zoom_canvas = tk.Canvas(
        zoom_frame,
        width=ZOOM_VIEW_SIZE,
        height=ZOOM_VIEW_SIZE,
        background="#f7f7f7",
        highlightthickness=1,
        highlightbackground="#999999",
    )
    zoom_canvas.grid(row=0, column=0, padx=8, pady=8)

    (
        class_list_canvas,
        class_list_frame,
        class_list_window,
        default_class_dropdown,
    ) = build_class_controls(
        host,
        controls,
    )

    snap_frame = ttk.LabelFrame(controls, text="Controls")
    snap_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
    snap_frame.columnconfigure(0, weight=1)
    show_vertex_ids_check = ttk.Checkbutton(
        snap_frame,
        text="Show vertex IDs",
        variable=host.show_vertex_ids_var,
        command=partial(on_show_vertex_ids_changed, preference_host),
    )
    show_vertex_ids_check.grid(row=0, column=0, sticky="w")
    live_lines_check = ttk.Checkbutton(
        snap_frame,
        text="Live lines",
        variable=host.live_lines_var,
        command=partial(on_live_lines_changed, preference_host),
    )
    live_lines_check.grid(row=1, column=0, sticky="w", pady=(4, 0))
    show_labels_check = ttk.Checkbutton(
        snap_frame,
        text="Show labels",
        variable=host.show_labels_var,
        command=partial(on_show_labels_changed, preference_host),
    )
    show_labels_check.grid(row=2, column=0, sticky="w", pady=(4, 0))
    autoclose_check = ttk.Checkbutton(
        snap_frame,
        text="Turtle shell mode",
        variable=host.autoclose_var,
        command=partial(on_autoclose_changed, preference_host),
    )
    autoclose_check.grid(
        row=1,
        column=1,
        sticky="w",
        padx=(12, 0),
        pady=(4, 0),
    )
    show_overlapping_edges_check = ttk.Checkbutton(
        snap_frame,
        text="Show overlapping edges",
        variable=host.show_overlapping_edges_var,
        command=partial(on_show_overlapping_edges_changed, preference_host),
    )
    show_overlapping_edges_check.grid(
        row=0,
        column=1,
        sticky="w",
        padx=(12, 0),
    )
    ttk.Label(snap_frame, text="Enable snapping for:").grid(
        row=3,
        column=0,
        columnspan=2,
        sticky="w",
        pady=(4, 2),
    )
    snap_new_check = ttk.Checkbutton(
        snap_frame,
        text="new",
        variable=host.snap_new_var,
        command=partial(on_snap_checkbox_changed, preference_host),
    )
    snap_edits_check = ttk.Checkbutton(
        snap_frame,
        text="edits",
        variable=host.snap_edits_var,
        command=partial(on_snap_checkbox_changed, preference_host),
    )
    snap_new_check.grid(row=4, column=0, sticky="w")
    snap_edits_check.grid(row=4, column=1, sticky="w", padx=(12, 0))

    log_text = tk.Text(
        controls,
        width=44,
        height=12,
        wrap="word",
        state=tk.DISABLED,
        relief=tk.SOLID,
        borderwidth=1,
    )
    log_text.grid(row=3, column=0, sticky="nsew")
    summary_text = tk.Text(
        controls,
        width=44,
        height=2,
        wrap="none",
        state=tk.DISABLED,
        relief=tk.SOLID,
        borderwidth=1,
        font=("TkFixedFont", 10),
    )
    summary_text.grid(row=4, column=0, sticky="ew", pady=(8, 0))
    return ControlWidgets(
        zoom_canvas=zoom_canvas,
        class_list_canvas=class_list_canvas,
        class_list_frame=class_list_frame,
        class_list_window=class_list_window,
        default_class_dropdown=default_class_dropdown,
        show_vertex_ids_check=show_vertex_ids_check,
        live_lines_check=live_lines_check,
        show_labels_check=show_labels_check,
        autoclose_check=autoclose_check,
        show_overlapping_edges_check=show_overlapping_edges_check,
        snap_new_check=snap_new_check,
        snap_edits_check=snap_edits_check,
        log_text=log_text,
        summary_text=summary_text,
    )
