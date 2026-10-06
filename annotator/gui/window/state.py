"""Typed widget records and callback contract for window construction."""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk
from typing import Any
from typing import Mapping
from typing import Protocol

from annotator.gui.tooltip import ToolTip
from annotator.gui.project.archive import ArchiveHost
from annotator.gui.project.review import ReviewHost


@dataclass(frozen=True, slots=True)
class ToolbarWidgets:
    """Widgets owned by the application toolbar."""

    load_button: ttk.Button
    run_button: ttk.Button
    save_button: ttk.Button
    archive_button: ttk.Button
    config_button: ttk.Button
    filter_dropdown: ttk.OptionMenu
    view_flagged_button: ttk.Button
    filter_button: ttk.Button
    delete_image_button: ttk.Button
    delete_image_tooltip: ToolTip
    reset_zoom_button: ttk.Button
    flag_review_button: ttk.Button


@dataclass(frozen=True, slots=True)
class ViewerWidgets:
    """Navigation and main-canvas widgets."""

    previous_button: ttk.Button
    next_button: ttk.Button
    image_index_entry: ttk.Entry
    image_count_label: ttk.Label
    image_status: ttk.Label
    canvas: tk.Canvas


@dataclass(frozen=True, slots=True)
class ControlWidgets:
    """Zoom, class, preference, log, and summary widgets."""

    zoom_canvas: tk.Canvas
    class_list_canvas: tk.Canvas
    class_list_frame: ttk.Frame
    class_list_window: int
    default_class_dropdown: ttk.Combobox
    show_vertex_ids_check: ttk.Checkbutton
    live_lines_check: ttk.Checkbutton
    show_labels_check: ttk.Checkbutton
    autoclose_check: ttk.Checkbutton
    show_overlapping_edges_check: ttk.Checkbutton
    snap_new_check: ttk.Checkbutton
    snap_edits_check: ttk.Checkbutton
    log_text: tk.Text
    summary_text: tk.Text


@dataclass(frozen=True, slots=True)
class WindowWidgets:
    """Complete widget tree published after successful construction."""

    toolbar: ToolbarWidgets
    viewer: ViewerWidgets
    controls: ControlWidgets


class WindowHost(ArchiveHost, ReviewHost, Protocol):
    """Application callbacks and variables consumed by window construction."""

    root: tk.Tk
    toolbar_icons: Mapping[str, Any]
    image_index_var: tk.StringVar
    filter_var: tk.StringVar
    session_default_class_var: tk.StringVar
    show_vertex_ids_var: tk.BooleanVar
    live_lines_var: tk.BooleanVar
    show_labels_var: tk.BooleanVar
    autoclose_var: tk.BooleanVar
    show_overlapping_edges_var: tk.BooleanVar
    snap_new_var: tk.BooleanVar
    snap_edits_var: tk.BooleanVar

    def on_close(self) -> None: ...
    def close_sql_connection(self) -> None: ...
    def open_config_window(self) -> None: ...
    def reset_zoom(self) -> None: ...
