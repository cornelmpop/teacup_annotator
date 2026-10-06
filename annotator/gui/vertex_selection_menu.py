"""Own selected-vertex context-menu orchestration."""

from __future__ import annotations

from functools import partial
import tkinter as tk
from typing import cast
from typing import Protocol

from annotator.gui.annotation_cancellation import AnnotationCancellationHost
from annotator.gui.annotation_cancellation import cancel_selection_or_mode
from annotator.gui.menu_support import add_menu_command
from annotator.gui.menu_support import post_menu
from annotator.gui.vertex_deletion import VertexDeletionHost
from annotator.gui.vertex_deletion import delete_selected_vertices
from annotator.preferences import Preferences


class VertexSelectionMenuHost(Protocol):
    """Application effects required by the selected-vertex context menu."""

    root: tk.Tk
    prefs: Preferences


def show_vertex_selection_menu(
    host: VertexSelectionMenuHost,
    event: tk.Event,
) -> None:
    """Open the Delete vertices and Cancel context menu."""

    menu = tk.Menu(host.root, tearoff=0)
    add_menu_command(
        host.prefs,
        menu,
        "Delete vertices",
        partial(delete_selected_vertices, cast(VertexDeletionHost, host)),
        "key_binding_delete_vertices",
    )
    add_menu_command(
        host.prefs,
        menu,
        "Cancel",
        partial(
            cancel_selection_or_mode,
            cast(AnnotationCancellationHost, host),
        ),
        "key_binding_cancel",
    )
    post_menu(menu, event.x_root, event.y_root)
