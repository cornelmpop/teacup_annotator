"""Configuration-window chooser effects."""

from __future__ import annotations

from pathlib import Path
from tkinter import colorchooser
from tkinter import filedialog
from tkinter import messagebox
from typing import TYPE_CHECKING

from annotator.model.configuration import read_model_configuration

if TYPE_CHECKING:
    from annotator.config_window import ConfigurationWindow


def choose_model_weights(self: ConfigurationWindow) -> None:
    """Select a model weights file for model_weights."""

    initial = self.vars["model_weights"].get().strip()
    initial_dir = str(Path(initial).expanduser().parent) if initial else None
    filename = filedialog.askopenfilename(
        parent=self.window,
        title="Select model weights",
        initialdir=initial_dir,
    )
    if filename:
        self.vars["model_weights"].set(filename)


def choose_model_profile(self: ConfigurationWindow) -> None:
    """Stage model classes and inference settings from a sidecar .conf."""

    if self.app.project.folder is None:
        messagebox.showwarning(
            "Load a folder first",
            "Load the annotation folder before importing a model profile.",
            parent=self.window,
        )
        return
    filename = filedialog.askopenfilename(
        parent=self.window,
        title="Select model profile",
        initialdir=str(self.app.project.folder),
        filetypes=(("Model configuration", "*.conf"), ("All files", "*")),
    )
    if not filename:
        return
    threshold, class_names_by_id = read_model_configuration(Path(filename))
    class_names = tuple(class_names_by_id.values())
    self.model_profile_class_names = class_names
    self.vars["default_threshold"].set(str(threshold))
    self.vars["class_order"].set(", ".join(class_names))
    self.default_class_combo.configure(values=class_names)
    if class_names and self.vars["default_class"].get() not in class_names:
        self.vars["default_class"].set(class_names[0])


def choose_colour(self: ConfigurationWindow, key: str) -> None:
    """Choose one hex colour preference with the system colour picker."""

    current = self.vars[key].get().strip() or self.fallback_preferences.get(
        key, "#ffffff"
    )
    _rgb, colour = colorchooser.askcolor(color=current, parent=self.window)
    if colour:
        self.vars[key].set(colour)
