"""Own New annotation and Change class submenu construction."""

# CMP: TODO - The name and suggests this should also own the delete submenu construction.
# Clarify.

from __future__ import annotations

from functools import partial
import tkinter as tk
from typing import cast
from typing import Protocol

from annotator.gui.annotation_classes import AnnotationClassHost
from annotator.gui.annotation_classes import change_annotation_class_at
from annotator.gui.annotation_modes import AnnotationModeHost
from annotator.gui.annotation_modes import start_new_annotation
from annotator.gui.annotation_modes import start_new_rectangle_annotation
from annotator.gui.menu_support import add_menu_command
from annotator.gui.menu_support import bind_menu_key
from annotator.gui.menu_support import class_menu_shortcut_map
from annotator.gui.menu_support import menu_binding
from annotator.gui.model.settings import active_class_names
from annotator.gui.model.settings import ModelSettingsHost


class ContextMenuSectionHost(ModelSettingsHost, Protocol):
    """Preferences and class queries required by context-menu sections."""

# CMP: Arrows are kept conceptually separated because they have a specific
# semantic meaning in Teacup that does not translate 100% cleanly to generic
# keypoint annotations.
def build_new_annotation_menu(
    host: ContextMenuSectionHost,
    parent: tk.Menu,
    can_start_new: bool,
) -> tk.Menu:
    """Build polygon and rectangle creation commands and parent shortcuts."""

    menu = tk.Menu(parent, tearoff=0)
    polygon_command = partial(
        start_new_annotation,
        cast(AnnotationModeHost, host),
    )
    rectangle_command = partial(
        start_new_rectangle_annotation,
        cast(AnnotationModeHost, host),
    )
    add_menu_command(
        host.prefs,
        menu,
        "polygon",
        polygon_command,
        "key_binding_new_polygon",
    )
    add_menu_command(
        host.prefs,
        menu,
        "rectangle",
        rectangle_command,
        "key_binding_new_rectangle",
    )
    bind_menu_key(
        parent,
        menu_binding(host.prefs, "key_binding_new_polygon"),
        polygon_command,
        enabled=can_start_new,
    )
    bind_menu_key(
        parent,
        menu_binding(host.prefs, "key_binding_new_rectangle"),
        rectangle_command,
        enabled=can_start_new,
    )
    return menu


def build_change_class_menu(
    host: ContextMenuSectionHost,
    parent: tk.Menu,
    canvas_point: tuple[float, float],
    can_edit_annotation: bool,
) -> tk.Menu:
    """Build active-class commands and bind their numeric shortcuts."""

    menu = tk.Menu(parent, tearoff=0)
    class_names = active_class_names(host)
    shortcuts = class_menu_shortcut_map(class_names)
    for class_name in class_names:
        shortcut = shortcuts.get(class_name, "")
        command = partial(
            change_annotation_class_at,
            cast(AnnotationClassHost, host),
            canvas_point,
            class_name,
        )
        menu.add_command(
            label=class_name,
            command=command,
            state=tk.NORMAL if can_edit_annotation else tk.DISABLED,
            accelerator=shortcut,
        )
        bind_menu_key(
            menu,
            shortcut,
            command,
            enabled=can_edit_annotation,
        )
        bind_menu_key(
            parent,
            shortcut,
            command,
            enabled=can_edit_annotation,
        )
    return menu
