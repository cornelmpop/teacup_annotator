"""Own atomic class writes, JSON backup, and post-save refresh effects."""

from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox
from typing import cast
from typing import Protocol

import annotator.sqlite as sql_backend
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.class_panel import ClassPanelHost
from annotator.gui.class_panel import refresh_class_panel
from annotator.gui.constants import ANNOTATION_OUTLINE
from annotator.gui.display import FILTER_ALL
from annotator.gui.project.filtering import apply_image_filter
from annotator.gui.project.filtering import refresh_filter_options
from annotator.gui.project.navigation import current_image_name
from annotator.gui.project.status import update_buttons
from annotator.gui.recovery import RecoveryHost
from annotator.gui.recovery import restore_document_from_sql
from annotator.gui.render_state import invalidate_annotation_overlay
from annotator.local_class_settings import write_local_class_settings


class LocalClassPersistenceHost(RecoveryHost, Protocol):
    """Application state and effects required to save and publish classes."""

    root: tk.Tk


def save_local_class_values(
    host: LocalClassPersistenceHost,
    class_names: tuple[str, ...],
    class_colours: tuple[str, ...],
) -> bool:
    """Commit classes to SQLite, then refresh the classes.json backup."""

    if (
        host.project.folder is None
        or host.project.coco is None
        or host.project.sql_connection is None
    ):
        return False

    colour_by_name = dict(zip(class_names, class_colours))
    document_colours = tuple(
        colour_by_name.get(
            str(category.get("name", "")),
            ANNOTATION_OUTLINE,
        )
        for category in host.project.coco.categories
    )
    try:
        sql_backend.persist_classes(
            host.project.sql_connection,
            host.project.coco.categories,
            document_colours,
        )
    except sqlite3.Error as exc:
        restore_document_from_sql(host)
        messagebox.showerror(
            "Could not save custom classes",
            str(exc),
            parent=host.root,
        )
        return False
    host.project.session_class_names = class_names
    host.project.session_class_colours = class_colours
    host.project.using_local_class_settings = True
    host.project.dirty = True
    try:
        write_local_class_settings(
            host.project.folder,
            class_names,
            class_colours,
        )

    # CMP: TODO - Document what state this leaves the application in for
    # next reload. Should the user manually remove the now out-of-date
    # classes.json? Better yet, should we warn the user when loading classes
    # if the SQLite class definitions are NEWER than what's in the classes.json?
    # That would seem sensible.
    except (OSError, ValueError) as exc:
        messagebox.showwarning(
            "Class backup failed",
            f"Classes were saved to SQLite, but classes.json failed:\n\n{exc}",
            parent=host.root,
        )
    return True

# CMP: TODO - check that this actually updates/refreshes the menu. I think it does,
# but the names of the functions being called don't make this clear, so that should
# be better documented.
def refresh_after_local_class_change(
    host: LocalClassPersistenceHost,
) -> None:
    """Refresh menus, filters, colours, and buttons after a class action."""

    preferred_name = current_image_name(host) if host.project.image_paths else None
    refresh_class_panel(cast(ClassPanelHost, host))
    refresh_filter_options(host)
    if host.project.active_filter not in host.project.filter_options:
        apply_image_filter(
            host,
            FILTER_ALL,
            preferred_image_name=preferred_name,
            load_image=False,
        )
    invalidate_annotation_overlay(host)
    redraw_canvas(cast(CanvasRenderHost, host))
    update_buttons(host)
