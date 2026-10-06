"""Configuration-window load, reload, and save effects."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING
from typing import cast

from annotator.coco.category_helpers import is_unused_default_category
from annotator.gui.local_class_persistence import LocalClassPersistenceHost
from annotator.gui.local_class_persistence import (
    refresh_after_local_class_change,
)
from annotator.gui.local_class_persistence import save_local_class_values
from annotator.gui.model.preferences import apply_runtime_preferences
from annotator.gui.model.preferences import ModelPreferenceHost
from annotator.gui.model.settings import active_class_names
from annotator.gui.model.settings import active_class_colours
from annotator.gui.model.settings import class_colour_map
from annotator.gui.model.settings import ModelSettingsHost
from annotator.gui.turtle_shell_notice import show_turtle_shell_notice
from annotator.model.configuration import save_model_conf
from annotator.project_metadata import PROJECT_METADATA_KEYS
from annotator.project_metadata import read_project_metadata
from annotator.project_metadata import write_project_metadata

if TYPE_CHECKING:
    from annotator.config_window import ConfigurationWindow


def load_values(self: ConfigurationWindow, values: dict[str, str]) -> None:
    """Populate controls from preference values."""

    self.update_scope_label()
    metadata_values = self.app.project.project_metadata
    for key in self.PROJECT_LINE_KEYS:
        self.vars[key].set(metadata_values.get(key, ""))
    for key, text_widget in self.project_text_widgets.items():
        text_widget.delete("1.0", tk.END)
        text_widget.insert("1.0", metadata_values.get(key, ""))
    model_values = dict(values)
    if self.app.project.folder is not None:
        model_values = dict.fromkeys(self.MODEL_KEYS, "")
        model_values["default_class"] = values.get(
            "default_class",
            self.fallback_preferences.get("default_class", ""),
        )
        model_values.update(self.app.project.session_model_values)
    else:
        for key in self.FOLDER_MODEL_KEYS:
            model_values[key] = ""
    for key in self.MODEL_KEYS:
        value = model_values.get(key, self.fallback_preferences.get(key, ""))
        self.vars.setdefault(key, tk.StringVar(master=self.window)).set(value)
    self.loaded_model_values = {
        key: self.vars[key].get().strip() for key in self.MODEL_KEYS
    }
    self.model_profile_class_names = ()
    settings_host = cast(ModelSettingsHost, self.app)
    self.default_class_combo.configure(values=active_class_names(settings_host))
    for key in (*self.BEHAVIOR_KEYS, *self.COLOUR_KEYS, *self.key_binding_keys):
        value = values.get(key, self.fallback_preferences.get(key, ""))
        self.vars.setdefault(key, tk.StringVar(master=self.window)).set(value)
    for key in self.BOOLEAN_KEYS:
        value = values.get(key, self.fallback_preferences.get(key, "false")).lower()
        self.bool_vars[key].set(value in {"1", "yes", "true", "on"})


def reload(self: ConfigurationWindow) -> None:
    """Reload global preferences and active folder project metadata."""

    fresh = self.preferences_factory(self.prefs_path)
    self.app.project.project_metadata = read_project_metadata(
        self.app.project.folder,
        fresh.values,
    )
    self.load_values(dict(fresh.values))


def save(self: ConfigurationWindow) -> None:
    """CODEX: Validate and publish edited application and folder settings."""

    turtle_shell_was_enabled = self.app.prefs.get_bool(
        "autoclose_enabled",
        False,
    )
    default_class_error = self.validate_default_class(
        self.vars["default_class"].get()
    )
    if default_class_error is not None:
        messagebox.showerror(
            "Invalid default class",
            default_class_error,
            parent=self.window,
        )
        return
    metadata = {key: self.vars[key].get().strip() for key in self.PROJECT_LINE_KEYS}
    metadata.update(
        {
            key: text_widget.get("1.0", "end-1c").strip()
            for key, text_widget in self.project_text_widgets.items()
        }
    )
    if self.model_profile_class_names:
        if self.app.project.coco is None:
            return
        settings_host = cast(ModelSettingsHost, self.app)
        colour_map = class_colour_map(settings_host)
        palette = active_class_colours(settings_host)
        profile_colours = tuple(
            colour_map.get(name, palette[index % len(palette)])
            for index, name in enumerate(self.model_profile_class_names)
        )
        document = self.app.project.coco
        if is_unused_default_category(
            document.category_names(),
            any(document.annotations_by_image.values()),
        ):
            # CODEX: An unused placeholder is setup state, so the imported
            # CODEX: profile replaces it instead of retaining an extra class.
            document.categories = []
        for class_name in self.model_profile_class_names:
            document.category_id_for_name(class_name)
        if not save_local_class_values(
            cast(LocalClassPersistenceHost, self.app),
            self.model_profile_class_names,
            profile_colours,
        ):
            return
        refresh_after_local_class_change(
            cast(LocalClassPersistenceHost, self.app)
        )
    if self.app.project.folder is None:
        self.app.prefs.values.update(metadata)
    else:
        write_project_metadata(self.app.project.folder, metadata)
    self.app.project.project_metadata = metadata
    for key, variable in self.vars.items():
        if (
            key in PROJECT_METADATA_KEYS
            or (self.app.project.folder is not None and key in self.MODEL_KEYS)
            or (self.app.project.folder is None and key in self.FOLDER_MODEL_KEYS)
        ):
            continue
        self.app.prefs.values[key] = variable.get().strip()
    for key, bool_variable in self.bool_vars.items():
        self.app.prefs.values[key] = "true" if bool_variable.get() else "false"
    self.app.prefs.values["prefs_version"] = self.app_version
    self.app.prefs.save()
    if self.app.project.folder is not None:
        model_values = {
            key: self.vars[key].get().strip() for key in self.model_conf_keys
        }
        if (
            self.app.project.using_folder_model_conf
            or self.model_profile_class_names
            or model_values != self.loaded_model_values
        ):
            save_model_conf(self.app.project.folder, model_values)
            self.app.project.session_model_values = model_values
            self.app.project.using_folder_model_conf = True
            self.loaded_model_values = model_values
            self.model_profile_class_names = ()
            # CODEX: Publish the saved folder default to the main-window
            # CODEX: selector only after folder configuration persistence.
            self.app.session_default_class_var.set(
                model_values["default_class"]
            )
    else:
        self.app.project.session_model_values = {}
    apply_runtime_preferences(cast(ModelPreferenceHost, self.app))
    if (
        not turtle_shell_was_enabled
        and self.bool_vars["autoclose_enabled"].get()
    ):
        show_turtle_shell_notice(self.app.root)
    self.app.log("Configuration saved")
