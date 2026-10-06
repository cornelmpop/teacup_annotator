"""Tkinter image annotation GUI."""

from __future__ import annotations

import queue
import tkinter as tk
from typing import Any
from typing import cast
from typing import Mapping

from PIL import ImageTk

from annotator.config_window import ConfigurationWindow
from annotator.dialogs import ProgressDialog
from annotator.gui.application import append_log
from annotator.gui.application import close_application
from annotator.gui.application import close_sql_connection
from annotator.gui.application import load_saved_folder
from annotator.gui.class_panel import ClassPanelHost
from annotator.gui.class_panel import refresh_class_panel
from annotator.gui.display import FILTER_ALL
from annotator.gui.input.viewport import reset_zoom as reset_view_zoom
from annotator.gui.input.viewport import update_canvas_cursor as update_view_cursor
from annotator.gui.model.results import finish_model_run
from annotator.gui.model.worker import poll_worker_queue
from annotator.gui.project.status import update_buttons
from annotator.gui.project.status import update_edit_summary
from annotator.gui.session_statistics import SESSION_STATISTICS_REFRESH_MS
from annotator.gui.session_statistics import refresh_session_statistics
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState
from annotator.gui.window.bindings import bind_window_events
from annotator.gui.window.root import build_window
from annotator.model.configuration import FOLDER_MODEL_CONF_KEYS
from annotator.icons import create_logo_photo
from annotator.preferences import DEFAULT_PREFERENCE_VALUES
from annotator.preferences import PREFS_PATH
from annotator.preferences import Preferences
from annotator.preferences.validation import validate_default_class
from annotator.project_metadata import read_project_metadata
from annotator.release_identity import APP_VERSION


class AnnotatorApp:
    """Top-level controller for the annotation GUI."""

    def __init__(self, root: tk.Tk) -> None:

        # CMP: TODO - Add brief descriptions here for how
        # these custom states work
        self.project = ProjectState()
        self.view = ViewState()
        self.interaction = InteractionState()
        self.root = root
        self.prefs = Preferences(PREFS_PATH)
        self.project.project_metadata = read_project_metadata(None, self.prefs.values)
        self.configuration_window: Any | None = None
        self.session_default_class_var = tk.StringVar(master=self.root, value="")

        # CMP: TODO - add in-line comment clarifying the relationship
        # between these vars with similar names (e.g., photo_image, logo_photo,
        # iconphoto)
        self.photo_image: ImageTk.PhotoImage | None = None
        self.logo_photo = create_logo_photo(self.root)
        self.root.iconphoto(False, self.logo_photo)
        self.photo_image_key: tuple[Any, ...] | None = None
        self.annotation_overlay_photo: ImageTk.PhotoImage | None = None
        self.annotation_overlay_key: tuple[Any, ...] | None = None
        self.selection_overlay_photo: ImageTk.PhotoImage | None = None
        self.zoom_photo: ImageTk.PhotoImage | None = None
        self.worker_queue: "queue.Queue[tuple[str, Any]]" = queue.Queue()

        # CMP: TODO - comment here on what these do and why they are
        # defined here.
        self.snap_new_var = tk.BooleanVar(
            master=self.root,
            value=self.prefs.get_bool("snap_new_enabled", True),
        )
        self.snap_edits_var = tk.BooleanVar(
            master=self.root,
            value=self.prefs.get_bool("snap_edits_enabled", True),
        )
        self.show_vertex_ids_var = tk.BooleanVar(
            master=self.root,
            value=self.prefs.get_bool("show_vertex_ids", True),
        )
        self.show_labels_var = tk.BooleanVar(
            master=self.root,
            value=self.prefs.get_bool("show_labels", False),
        )
        self.live_lines_var = tk.BooleanVar(
            master=self.root,
            value=self.prefs.get_bool("live_lines", True),
        )
        self.autoclose_var = tk.BooleanVar(
            master=self.root,
            value=self.prefs.get_bool("autoclose_enabled", True),
        )
        self.show_overlapping_edges_var = tk.BooleanVar(
            master=self.root,
            value=self.prefs.get_bool("show_overlapping_edges", False),
        )
        self.image_index_var = tk.StringVar(master=self.root, value="")
        self.filter_var = tk.StringVar(master=self.root, value=FILTER_ALL)
        self.model_progress_dialog: ProgressDialog | None = None
        self.toolbar_icons: Mapping[str, Any] = {}

        self.widgets = build_window(self)
        refresh_class_panel(cast(ClassPanelHost, self))
        update_edit_summary(self)
        bind_window_events(self, self.widgets)
        update_buttons(self)
        self.root.after(150, load_saved_folder, self)
        self.root.after(100, poll_worker_queue, self, finish_model_run)
        self.root.after(
            SESSION_STATISTICS_REFRESH_MS,
            refresh_session_statistics,
            self,
        )

    def on_close(self) -> None:
        """Close the application through its single lifecycle boundary."""

        close_application(self)

    def close_sql_connection(self) -> None:
        """Close the active project database connection."""

        close_sql_connection(self)

    # CMP: TODO - Why are the SQLite logs called optional here?
    def log(self, message: str) -> None:
        """Append a message to the GUI and optional SQLite logs."""

        append_log(self, message)

    def open_config_window(self) -> None:
        """Open or restore the single preferences editor."""

        if (
            self.configuration_window is not None
            and self.configuration_window.window.winfo_exists()
        ):
            self.configuration_window.restore()
            return
        self.configuration_window = ConfigurationWindow(
            self,
            app_version=APP_VERSION,
            fallback_preferences=DEFAULT_PREFERENCE_VALUES,
            model_conf_keys=FOLDER_MODEL_CONF_KEYS,
            prefs_path=PREFS_PATH,
            preferences_factory=Preferences,
            validate_default_class=validate_default_class,
        )

    def set_canvas_cursor(self, cursor: str = "") -> None:
        """Set the canvas cursor without failing on unsupported names."""

        try:
            self.widgets.viewer.canvas.configure(cursor=cursor)
        except tk.TclError:
            self.widgets.viewer.canvas.configure(cursor="")

    def update_canvas_cursor(self) -> None:
        """Refresh the canvas cursor through the explicit viewport effect."""

        update_view_cursor(self)

    def reset_zoom(self) -> None:
        """Reset viewer zoom through the explicit viewport effect."""

        reset_view_zoom(self)
