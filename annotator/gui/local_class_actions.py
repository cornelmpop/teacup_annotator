"""CODEX: Own folder-class loading, addition, recolouring, and deletion workflows."""

from __future__ import annotations

from pathlib import Path
from tkinter import colorchooser
from tkinter import messagebox
from typing import Protocol

from annotator.arrows import ARROW_SPEC_CLASS_NAME
from annotator.dialogs import LocalClassSourceDialog
from annotator.dialogs import NewLocalClassDialog
from annotator.gui.constants import ANNOTATION_OUTLINE
from annotator.gui.local_class_persistence import LocalClassPersistenceHost
from annotator.gui.local_class_persistence import (
    refresh_after_local_class_change,
)
from annotator.gui.local_class_persistence import save_local_class_values
from annotator.gui.model.settings import active_class_colours
from annotator.gui.model.settings import active_class_names
from annotator.gui.model.settings import ModelSettingsHost
from annotator.local_class_settings import LOCAL_CLASS_SETTINGS_FILENAME
from annotator.local_class_settings import read_local_class_settings
from annotator.project.paths import project_file_path


class LocalClassActionHost(
    LocalClassPersistenceHost,
    ModelSettingsHost,
    Protocol,
):
    """Queries and effects required by folder-local class actions."""

    def log(self, message: str) -> None: ...

# CMP: TODO - function name is odd, since output is deterministic.
#      consider prompt_for ... or something along those lines.
def maybe_use_local_class_settings(
    host: LocalClassActionHost,
    folder: Path,
) -> None:
    """CODEX: Offer ``classes.json`` as a new project's initial vocabulary.

    The caller owns proving that SQLite has no established project document and
    invokes this function before opening the database for writing. Accepting
    the backup publishes its ordered names and colours into session state for
    the initializer; choosing defaults clears only those class-session values.
    Missing files are a no-op, while selected malformed files propagate their
    natural parsing error to the folder-load boundary.
    """

    path = project_file_path(folder, LOCAL_CLASS_SETTINGS_FILENAME)
    if not path.is_file():
        return
    if LocalClassSourceDialog(host.root).result == "custom":
        settings = read_local_class_settings(folder)
        if settings is not None:
            class_names, class_colours = settings
            host.project.session_class_names = class_names
            host.project.session_class_colours = class_colours
            host.project.using_local_class_settings = True
            host.log(
                f"Loaded custom classes from {LOCAL_CLASS_SETTINGS_FILENAME}."
            )
            return
    host.project.session_class_names = ()
    host.project.session_class_colours = ()
    host.project.using_local_class_settings = False
    host.log("Using default classes from annotator_prefs.conf.")


def add_local_class(host: LocalClassActionHost) -> None:
    """Add one class and save the folder-local settings immediately."""

    if host.project.folder is None or host.project.coco is None:
        return
    class_names = active_class_names(host)
    class_colours = active_class_colours(host)
    initial_colour = class_colours[0] if class_colours else ANNOTATION_OUTLINE
    result = NewLocalClassDialog(
        host.root,
        (*class_names, ARROW_SPEC_CLASS_NAME),
        initial_colour,
    ).result
    if result is None:
        return
    class_name, colour = result
    next_names = (*class_names, class_name)
    next_colours = (*class_colours, colour)
    host.project.coco.category_id_for_name(class_name)
    if not save_local_class_values(host, next_names, next_colours):
        return
    refresh_after_local_class_change(host)
    host.log(f"Added annotation class: {class_name}")


def change_local_class_colour(
    host: LocalClassActionHost,
    class_name: str,
) -> None:
    """Choose and immediately save a new colour for an active class."""

    if host.project.folder is None:
        return
    class_names = active_class_names(host)
    if class_name not in class_names:
        return
    class_colours = list(active_class_colours(host))
    class_index = class_names.index(class_name)
    _rgb, colour = colorchooser.askcolor(
        color=class_colours[class_index],
        parent=host.root,
    )
    if not colour:
        return
    class_colours[class_index] = colour
    if not save_local_class_values(host, class_names, tuple(class_colours)):
        return
    refresh_after_local_class_change(host)
    host.log(f"Changed annotation class colour: {class_name}")


def delete_local_class(
    host: LocalClassActionHost,
    class_name: str,
) -> None:
    """Delete one unused class after confirmation and save immediately."""

    if host.project.folder is None or host.project.coco is None:
        return
    class_names = active_class_names(host)
    if class_name not in class_names:
        return
    if len(class_names) == 1:
        messagebox.showwarning(
            "Cannot delete class",
            "At least one annotation class is required.",
            parent=host.root,
        )
        return
    category_id = next(
        (
            int(category.get("id", -1))
            for category in host.project.coco.categories
            if str(category.get("name", "")) == class_name
        ),
        None,
    )
    if category_id is not None and any(
        annotation.category_id == category_id
        for annotations in host.project.coco.annotations_by_image.values()
        for annotation in annotations
    ):
        messagebox.showwarning(
            "Class is in use",
            (
                f"'{class_name}' is used by existing annotations. "
                "Change or delete those annotations before deleting the class."
            ),
            parent=host.root,
        )
        return
    if not messagebox.askyesno(
        "Delete annotation class?",
        f"Delete the class '{class_name}'?",
        parent=host.root,
    ):
        return

    class_colours = active_class_colours(host)
    class_index = class_names.index(class_name)
    next_names = class_names[:class_index] + class_names[class_index + 1 :]
    next_colours = class_colours[:class_index] + class_colours[class_index + 1 :]
    host.project.coco.categories = [
        category
        for category in host.project.coco.categories
        if str(category.get("name", "")) != class_name
    ]
    if not save_local_class_values(host, next_names, next_colours):
        return
    refresh_after_local_class_change(host)
    host.log(f"Deleted annotation class: {class_name}")
