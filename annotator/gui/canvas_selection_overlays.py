"""Own canvas selection rectangles and translucent selection overlays."""

from __future__ import annotations

import tkinter as tk
from typing import Protocol
from typing import TYPE_CHECKING

from PIL import Image
from PIL import ImageTk

from annotator.gui.selection import active_annotation_selection_rect
from annotator.gui.selection import active_selection_rect
from annotator.gui.state import InteractionState

if TYPE_CHECKING:
    from annotator.gui.window.state import WindowWidgets


class CanvasSelectionOverlayHost(Protocol):
    """State and widgets required to render canvas selection overlays."""

    interaction: InteractionState
    widgets: WindowWidgets
    selection_overlay_photo: ImageTk.PhotoImage | None


# CMP: TODO - Stylistic elements (e.g., colour) should not be hard coded. Move
# to a more suitable place.
def draw_selection_overlay(host: CanvasSelectionOverlayHost) -> None:
    """Draw the grey vertex-selection rectangle and retain its Tk image."""

    rect = active_selection_rect(host.interaction)
    if rect is None:
        host.selection_overlay_photo = None
        return
    left, top, right, bottom = rect
    width = max(1, int(round(right - left)))
    height = max(1, int(round(bottom - top)))
    overlay = Image.new("RGBA", (width, height), (128, 128, 128, 128))
    host.selection_overlay_photo = ImageTk.PhotoImage(overlay)
    canvas = host.widgets.viewer.canvas
    canvas.create_image(
        left,
        top,
        image=host.selection_overlay_photo,
        anchor=tk.NW,
        tags=("selection_overlay",),
    )
    canvas.create_rectangle(
        left,
        top,
        left + width,
        top + height,
        fill="",
        outline="#555555",
        width=1,
        tags=("selection_overlay",),
    )

# CMP: TODO - Stylistic elements (e.g., colour) should not be hard coded. Move
# to a more suitable place.
def draw_annotation_selection_rect(
    host: CanvasSelectionOverlayHost,
) -> None:
    """Draw the transparent X-drag annotation-selection rectangle."""

    rect = active_annotation_selection_rect(host.interaction)
    if rect is None:
        return
    host.widgets.viewer.canvas.create_rectangle(
        *rect,
        fill="",
        outline="#6b7280",
        width=2,
        dash=(3, 3),
        tags=("annotation_selection_rect",),
    )
