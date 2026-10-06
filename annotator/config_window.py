"""Own the Tk configuration window shell and shared editor state.

The tab builders, chooser callbacks, form helpers, and save/reload effects live
under `annotator.gui.config_window.*`; this module assembles them onto one
`ConfigurationWindow` object because Tk widgets need a persistent owner. The
window edits global preferences when no folder is loaded, and folder-local
project/model files when a project is active.
"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any

from annotator.gui.config_window.choices import choose_colour as _choose_colour
from annotator.gui.config_window.choices import (
    choose_model_profile as _choose_model_profile,
)
from annotator.gui.config_window.choices import (
    choose_model_weights as _choose_model_weights,
)
from annotator.gui.config_window.effects import load_values as _load_values
from annotator.gui.config_window.effects import reload as _reload
from annotator.gui.config_window.effects import save as _save
from annotator.gui.config_window.forms import add_labeled_entry as _add_labeled_entry
from annotator.gui.config_window.forms import build_footer as _build_footer
from annotator.gui.config_window.forms import on_project_wheel as _on_project_wheel
from annotator.gui.config_window.forms import (
    update_scope_label as _update_scope_label,
)
from annotator.gui.config_window.tabs import build_behavior_tab as _build_behavior_tab
from annotator.gui.config_window.tabs import build_colour_tab as _build_colour_tab
from annotator.gui.config_window.tabs import build_keys_tab as _build_keys_tab
from annotator.gui.config_window.tabs import build_model_tab as _build_model_tab
from annotator.gui.config_window.tabs import build_project_tab as _build_project_tab
from annotator.project_metadata import PROJECT_METADATA_KEYS
from annotator.project_metadata import PROJECT_METADATA_LABELS


_PROJECT_TEXT_KEYS = (
    "project_description",
    "collection_methodology",
    "annotation_methodology",
    "quality_control_methodology",
)


class ConfigurationWindow:
    """Stateful owner for the tabbed Configuration dialog.

    The class stores Tk variables, text widgets, tab frames, and injected
    persistence/validation collaborators. Behavior is composed from small
    helper modules by assigning their functions as methods, keeping the widget
    owner separate from tab-specific construction and save logic.
    """

    BOOLEAN_KEYS = (
        "snap_new_enabled",
        "snap_edits_enabled",
        "show_vertex_ids",
        "show_labels",
        "live_lines",
        "autoclose_enabled",
        "show_overlapping_edges",
        "write_json_backups",
        "reverse_horizontal_wheel",
    )
    BEHAVIOR_KEYS = (
        "snapping_tolerance_px",
        "simplify_vertex_distance_px",
        "simplify_vertex_count",
        "overlapping_edge_width",
        "crop_padding_px",
    )
    MODEL_KEYS = (
        "model_weights",
        "default_threshold",
        "class_order",
        "default_class",
    )
    FOLDER_MODEL_KEYS = ("default_threshold", "class_order")
    COLOUR_KEYS = (
        "snap_live_line_colour",
        "overlapping_edge_colour",
        "selected_shared_edge_colour",
    )
    PROJECT_TEXT_KEYS = _PROJECT_TEXT_KEYS
    PROJECT_LINE_KEYS = tuple(
        key for key in PROJECT_METADATA_KEYS if key not in _PROJECT_TEXT_KEYS
    )
    LABELS = {
        **PROJECT_METADATA_LABELS,
        "model_weights": "Model weights",
        "default_class": "Default class",
        "snap_new_enabled": "Enable snapping for new annotations",
        "snap_edits_enabled": "Enable snapping for edits",
        "show_vertex_ids": "Show vertex IDs",
        "show_labels": "Show labels",
        "live_lines": "Live lines",
        "autoclose_enabled": "Turtle shell mode",
        "show_overlapping_edges": "Show overlapping edges",
        "write_json_backups": "Write JSON backups",
        "reverse_horizontal_wheel": "Reverse horizontal wheel",
        "snapping_tolerance_px": "Snapping tolerance (px)",
        "simplify_vertex_distance_px": "Resample redundant distance (px)",
        "simplify_vertex_count": "Resampled vertex count",
        "overlapping_edge_width": "Overlapping edge width",
        "crop_padding_px": "Crop padding (px)",
        "snap_live_line_colour": "Snap/live-line colour",
        "overlapping_edge_colour": "Overlapping edge colour",
        "selected_shared_edge_colour": "Selected shared-edge colour",
    }

    # Bind split helper functions as methods so helper modules can stay focused
    # while Tk still has one persistent object owning all widget state.
    build_project_tab = _build_project_tab
    build_model_tab = _build_model_tab
    build_behavior_tab = _build_behavior_tab
    build_colour_tab = _build_colour_tab
    build_keys_tab = _build_keys_tab
    build_footer = _build_footer
    update_scope_label = _update_scope_label
    add_labeled_entry = _add_labeled_entry
    _on_project_wheel = _on_project_wheel
    choose_model_weights = _choose_model_weights
    choose_model_profile = _choose_model_profile
    choose_colour = _choose_colour
    load_values = _load_values
    reload = _reload
    save = _save

    def __init__(
        self,
        app: Any,
        *,
        app_version: str,
        fallback_preferences: dict[str, str],
        model_conf_keys: tuple[str, ...],
        prefs_path: Path,
        preferences_factory: Any,
        validate_default_class: Any,
    ) -> None:
        """Create the dialog, wire helper-owned tabs, and load current values.

        Constructor arguments are injected so tests and the main app can supply
        the active preference store, model-key policy, app version, and
        default-class validation without this Tk shell importing those
        responsibilities directly.
        """

        self.app = app
        self.app_version = app_version
        self.fallback_preferences = fallback_preferences
        self.model_conf_keys = model_conf_keys
        self.prefs_path = prefs_path
        self.preferences_factory = preferences_factory
        self.validate_default_class = validate_default_class
        # Generate key binding rows from defaults so new configurable shortcuts
        # appear without maintaining a second ordered list in this Tk shell.
        self.key_binding_keys = tuple(
            key for key in fallback_preferences if key.startswith("key_binding_")
        )

        self.window = tk.Toplevel(app.root)
        self.window.title("Configuration")
        self.window.geometry("760x620")
        self.window.configure(
            background=ttk.Style(app.root).lookup("TFrame", "background")
        )
        self.vars: dict[str, tk.StringVar] = {}
        self.bool_vars: dict[str, tk.BooleanVar] = {}
        self.project_text_widgets: dict[str, tk.Text] = {}
        self.project_canvas: tk.Canvas
        self.default_class_combo: ttk.Combobox
        self.model_profile_class_names: tuple[str, ...] = ()
        self.loaded_model_values: dict[str, str] = {}

        self.scope_label = ttk.Label(self.window, anchor="w")
        self.scope_label.pack(fill=tk.X, padx=16, pady=(8, 0))
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 4))
        self.project_tab = ttk.Frame(self.notebook, padding=8)
        self.model_tab = ttk.Frame(self.notebook, padding=8)
        self.behavior_tab = ttk.Frame(self.notebook, padding=8)
        self.colour_tab = ttk.Frame(self.notebook, padding=8)
        self.keys_tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.project_tab, text="Project")
        self.notebook.add(self.model_tab, text="Model")
        self.notebook.add(self.behavior_tab, text="Behavior")
        self.notebook.add(self.colour_tab, text="Colours")
        self.notebook.add(self.keys_tab, text="Key bindings")
        self.notebook.bind("<<NotebookTabChanged>>", self.update_scope_label)

        self.build_project_tab()
        self.build_model_tab()
        self.build_behavior_tab()
        self.build_colour_tab()
        self.build_keys_tab()
        self.build_footer()
        self.load_values(dict(self.app.prefs.values))
        self.restore()

    def restore(self) -> None:
        """Show an existing editor beside the main window and return focus to it.

        Reusing one configuration window avoids losing unsaved edits when the
        user presses Configuration again.
        """

        self.app.root.update_idletasks()
        x = self.app.root.winfo_rootx() + 40
        y = self.app.root.winfo_rooty() + 40
        self.window.deiconify()
        self.window.geometry(f"{x:+d}{y:+d}")
        self.window.lift()
        self.window.focus_force()
