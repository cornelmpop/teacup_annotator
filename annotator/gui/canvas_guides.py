"""Own cursor guide lines and the canvas snap-preview marker."""

from __future__ import annotations

import tkinter as tk
from typing import Any
from typing import Protocol
from typing import TYPE_CHECKING

from annotator.gui.snap_graph import snapping_tolerance_image
from annotator.gui.snapping import snap_preview_image_point
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState
from annotator.gui.view_geometry import image_point_from_canvas
from annotator.gui.view_geometry import image_to_canvas_point
from annotator.preferences import Preferences

if TYPE_CHECKING:
    from annotator.gui.window.state import WindowWidgets


class CanvasGuideHost(Protocol):
    """State, preferences, and widgets required by transient canvas guides."""

    prefs: Preferences
    project: ProjectState
    view: ViewState
    interaction: InteractionState
    widgets: WindowWidgets
    snap_new_var: tk.BooleanVar

# CMP: TODO - stylistic elements like colours should not be hard coded. Move
# to constants, a style file, or something along those lines.
def draw_guides(host: CanvasGuideHost) -> None:
    """Draw dotted cursor guide lines clipped to the displayed image."""

    canvas = host.widgets.viewer.canvas
    canvas.delete("guide")
    if host.view.cursor_canvas_point is None or host.view.current_image is None:
        return

    # CMP - TODO - Briefly explain here the coord system(s)
    x_coord, y_coord = host.view.cursor_canvas_point
    origin_x, origin_y = host.view.image_origin
    width, height = host.view.display_size
    left = origin_x
    top = origin_y
    right = origin_x + width
    bottom = origin_y + height
    if not (left <= x_coord <= right and top <= y_coord <= bottom):
        return
    line_options: dict[str, Any] = {
        "fill": "#4b5563",
        "dash": (2, 3),
        "width": 1,
        "tags": ("guide",),
    }
    canvas.create_line(left, y_coord, right, y_coord, **line_options)
    canvas.create_line(x_coord, top, x_coord, bottom, **line_options)

    # CMP: TODO - Clarify what this is all about. Not obvious what
    # tag_raise does.
    for tag in (
        "guide",
        "snap_preview",
        "vertex_id",
        "annotation_label",
        "class_tooltip",
    ):
        canvas.tag_raise(tag)

# CMP: TODO - stylistic elements like colours should not be hard coded. Move
# to constants, a style file, or something along those lines.
def draw_snap_preview_dot(host: CanvasGuideHost) -> None:
    """Draw the snap target that the next vertex action would use."""

    canvas = host.widgets.viewer.canvas
    canvas.delete("snap_preview")
    if host.view.cursor_canvas_point is None:
        return
    image_point = image_point_from_canvas(
        host.view.cursor_canvas_point,
        host.view,
    )
    snap_point = snap_preview_image_point(
        host.project,
        host.view,
        host.interaction,
        image_point,
        host.snap_new_var.get(),
        snapping_tolerance_image(host.prefs, host.view),
    )
    if snap_point is None:
        return
    canvas_x, canvas_y = image_to_canvas_point(snap_point, host.view)
    radius = 2.0
    canvas.create_oval(
        canvas_x - radius,
        canvas_y - radius,
        canvas_x + radius,
        canvas_y + radius,
        fill="#dc2626",
        outline="#dc2626",
        width=0,
        tags=("snap_preview",),
    )
    canvas.tag_raise("snap_preview")
