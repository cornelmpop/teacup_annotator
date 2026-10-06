"""Own folder model-profile choice and live runtime preference effects."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from typing import cast
from typing import Protocol

from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.class_panel import ClassPanelHost
from annotator.gui.class_panel import refresh_class_panel
from annotator.gui.project.filtering import FilteringHost
from annotator.gui.project.filtering import refresh_filter_options
from annotator.gui.project.status import update_buttons
from annotator.gui.render_state import RenderStateHost
from annotator.gui.render_state import invalidate_annotation_overlay
from annotator.gui.snap_graph import invalidate_snap_graph
from annotator.gui.turtle_shell_notice import show_turtle_shell_notice
from annotator.gui.view_geometry import image_point_from_canvas
from annotator.gui.zoom_preview import ZoomPreviewHost
from annotator.gui.zoom_preview import update_zoom_preview
from annotator.model.configuration import FOLDER_MODEL_CONF_KEYS
from annotator.model.configuration import MODEL_CONF_FILENAME
from annotator.model.configuration import read_model_conf
from annotator.project.paths import project_file_path


MISSING_MODEL_CONF_WARNING = (
    "No model.conf was found in this folder. You can continue with manual "
    "annotation.\n\n"
    "If these annotations should comply with the classes defined for a "
    "particular model, open Configuration > Model to load that model's .conf "
    "profile and save the folder configuration. Model weights are not "
    "required.\n\n"
    "See the user manual for details."
)


class ModelPreferenceHost(FilteringHost, Protocol):
    """Tk state and effects used by model-profile and preference actions."""

    snap_new_var: tk.BooleanVar
    snap_edits_var: tk.BooleanVar
    show_vertex_ids_var: tk.BooleanVar
    show_labels_var: tk.BooleanVar
    live_lines_var: tk.BooleanVar
    autoclose_var: tk.BooleanVar
    show_overlapping_edges_var: tk.BooleanVar

# CMP: TODO - change this function's name to remove the 'maybe'
def maybe_use_folder_model_conf(
    host: ModelPreferenceHost,
    folder: Path,
) -> None:
    """Warn when model.conf is absent or offer its settings when present."""

    if not project_file_path(folder, MODEL_CONF_FILENAME).is_file():
        messagebox.showwarning(
            "No folder model configuration",
            MISSING_MODEL_CONF_WARNING,
            parent=host.root,
        )
        return
    values = read_model_conf(folder)
    if not values:
        return
    summary = "\n".join(
        f"{key}: {values[key]}"
        for key in FOLDER_MODEL_CONF_KEYS
        if values.get(key)
    )
    confirmed = messagebox.askyesno(
        "Use model.conf?",
        (
            f"{MODEL_CONF_FILENAME} was found in this folder.\n\n"
            f"{summary}\n\n"
            "Use these model settings for this session?"
        ),
    )
    if confirmed:
        host.project.session_model_values = values
        host.project.using_folder_model_conf = True
        host.log(f"Using {MODEL_CONF_FILENAME} settings for this session.")
    else:
        host.log(f"Ignored {MODEL_CONF_FILENAME}; using annotator_prefs.conf.")


def on_snap_checkbox_changed(host: ModelPreferenceHost) -> None:
    """Persist snapping checkbox changes."""

    host.prefs.set_bool("snap_new_enabled", bool(host.snap_new_var.get()))
    host.prefs.set_bool("snap_edits_enabled", bool(host.snap_edits_var.get()))


def on_show_vertex_ids_changed(host: ModelPreferenceHost) -> None:
    """Persist and redraw vertex-ID labels."""

    host.prefs.set_bool("show_vertex_ids", bool(host.show_vertex_ids_var.get()))
    redraw_canvas(cast(CanvasRenderHost, host))
    if host.view.cursor_canvas_point is None:
        return
    image_point = image_point_from_canvas(host.view.cursor_canvas_point, host.view)
    if image_point is not None:
        update_zoom_preview(cast(ZoomPreviewHost, host), image_point)


def on_show_labels_changed(host: ModelPreferenceHost) -> None:
    """Persist and redraw centered annotation class labels."""

    host.prefs.set_bool("show_labels", bool(host.show_labels_var.get()))
    redraw_canvas(cast(CanvasRenderHost, host))


def on_live_lines_changed(host: ModelPreferenceHost) -> None:
    """Persist and redraw live new-polygon guide lines."""

    host.prefs.set_bool("live_lines", bool(host.live_lines_var.get()))
    redraw_canvas(cast(CanvasRenderHost, host))

# CMP: I'm not sure why this function (and others here) are found
# in this file. With the current models model annotations and
# 'turtle shell mode' are completelly separate things.
def on_autoclose_changed(host: ModelPreferenceHost) -> None:
    """Persist Turtle shell mode preference changes."""

    enabled = bool(host.autoclose_var.get())
    host.prefs.set_bool("autoclose_enabled", enabled)
    if enabled:
        show_turtle_shell_notice(host.root)


def on_show_overlapping_edges_changed(host: ModelPreferenceHost) -> None:
    """Persist and redraw overlapping-edge highlights."""

    host.prefs.set_bool(
        "show_overlapping_edges",
        bool(host.show_overlapping_edges_var.get()),
    )
    redraw_canvas(cast(CanvasRenderHost, host))


def apply_runtime_preferences(host: ModelPreferenceHost) -> None:
    """Refresh live UI state from the current preferences."""

    host.snap_new_var.set(host.prefs.get_bool("snap_new_enabled", True))
    host.snap_edits_var.set(host.prefs.get_bool("snap_edits_enabled", True))
    host.show_vertex_ids_var.set(host.prefs.get_bool("show_vertex_ids", True))
    host.show_labels_var.set(host.prefs.get_bool("show_labels", False))
    host.live_lines_var.set(host.prefs.get_bool("live_lines", True))
    host.autoclose_var.set(host.prefs.get_bool("autoclose_enabled", True))
    host.show_overlapping_edges_var.set(
        host.prefs.get_bool("show_overlapping_edges", False)
    )
    invalidate_annotation_overlay(cast(RenderStateHost, host))
    invalidate_snap_graph(host.view)
    refresh_class_panel(cast(ClassPanelHost, host))
    refresh_filter_options(host)
    redraw_canvas(cast(CanvasRenderHost, host))
    update_buttons(host)
