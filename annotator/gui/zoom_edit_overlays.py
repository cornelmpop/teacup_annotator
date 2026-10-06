"""Own temporary edit geometry, handles, and snap markers in the zoom preview."""

from __future__ import annotations

from functools import partial
import tkinter as tk
from typing import Callable, Protocol, TYPE_CHECKING

from annotator.geom.coordinates import map_point_between_spaces
from annotator.gui.constants import VERTEX_HALF, ZOOM_VIEW_SIZE
from annotator.gui.interactions import MIN_ZOOM
from annotator.gui.selection import active_annotation_selection_rect
from annotator.gui.selection import active_selection_rect
from annotator.gui.selection import selected_annotation
from annotator.gui.snap_graph import live_line_image_point
from annotator.gui.snap_graph import snap_context_polygons
from annotator.gui.snap_graph import snapping_tolerance_image
from annotator.gui.snapping import new_polygon_live_line_colour
from annotator.gui.snapping import snap_preview_image_point
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState
from annotator.gui.view_geometry import image_point_from_canvas
from annotator.preferences import DEFAULT_PREFERENCE_VALUES
from annotator.preferences import Preferences

if TYPE_CHECKING:
    from annotator.gui.window.state import WindowWidgets

Point = tuple[float, float]


class ZoomEditOverlayHost(Protocol):
    """State, preferences, flags, and widgets required by zoom edit overlays."""

    prefs: Preferences
    project: ProjectState
    view: ViewState
    interaction: InteractionState
    widgets: WindowWidgets
    live_lines_var: tk.BooleanVar
    snap_new_var: tk.BooleanVar

# CMP: TODO - stylistic aspects should not be hard coded. Move to a
# theme file.
def draw_zoom_edit_overlays(
    host: ZoomEditOverlayHost,
    crop_left: int,
    crop_top: int,
    crop_size: int,
) -> None:
    """Draw in-progress creation, selection, and edit geometry."""

    # CMP: TODO - Document under what valid application state the crop
    # size could be zero or less
    if crop_size <= 0:
        return
    scale = ZOOM_VIEW_SIZE / crop_size
    to_zoom = partial(
        map_point_between_spaces,
        source_origin=(crop_left, crop_top),
        scale=(scale, scale),
    )
    canvas = host.widgets.controls.zoom_canvas

    if host.interaction.temp_polygon:
        zoom_points = [
            coordinate
            for point in host.interaction.temp_polygon
            for coordinate in to_zoom(point)
        ]
        if len(zoom_points) >= 4:
            canvas.create_line(
                zoom_points,
                fill="#f59e0b",
                width=2,
                tags=("temp_polygon",),
            )
        for point in host.interaction.temp_polygon:
            draw_zoom_vertex_square(host, to_zoom(point), fill="white")
        tolerance = snapping_tolerance_image(host.prefs, host.view)
        live_point = live_line_image_point(
            host.view,
            host.interaction,
            host.live_lines_var.get(),
        )
        if live_point is not None:
            canvas.create_line(
                *to_zoom(host.interaction.temp_polygon[-1]),
                *to_zoom(live_point),
                fill=new_polygon_live_line_colour(
                    host.project,
                    host.view,
                    host.interaction,
                    live_point,
                    host.snap_new_var.get(),
                    tolerance,
                    host.prefs.values.get(
                        "snap_live_line_colour",
                        DEFAULT_PREFERENCE_VALUES["snap_live_line_colour"],
                    ),
                ),
                width=2,
                dash=(5, 3),
                tags=("temp_polygon",),
            )

    for polygon in snap_context_polygons(
        host.project,
        host.view,
        host.interaction,
        host.snap_new_var.get(),
        snapping_tolerance_image(host.prefs, host.view),
    ):
        for point in polygon:
            draw_zoom_vertex_square(host, to_zoom(point), fill="white")
    draw_zoom_snap_preview_dot(host, to_zoom)

    annotation = selected_annotation(host.project, host.interaction)
    if annotation is not None:
        for polygon_index, polygon in enumerate(annotation.polygons):
            for vertex_index, point in enumerate(polygon):
                fill = (
                    "#d92323"
                    if (polygon_index, vertex_index)
                    in host.interaction.selected_vertices
                    else "white"
                )
                draw_zoom_vertex_square(host, to_zoom(point), fill=fill)

    rect = active_selection_rect(host.interaction)
    rect = rect or active_annotation_selection_rect(host.interaction)
    if rect is None:
        return
    image_scale = max(MIN_ZOOM, host.view.zoom)
    left_top = map_point_between_spaces(
        (rect[0], rect[1]),
        source_origin=host.view.image_origin,
        scale=(1 / image_scale, 1 / image_scale),
    )
    right_bottom = map_point_between_spaces(
        (rect[2], rect[3]),
        source_origin=host.view.image_origin,
        scale=(1 / image_scale, 1 / image_scale),
    )
    zoom_left_top = to_zoom(left_top)
    zoom_right_bottom = to_zoom(right_bottom)
    canvas.create_rectangle(
        *zoom_left_top,
        *zoom_right_bottom,
        fill="",
        outline="#6b7280",
        width=2,
        dash=(3, 3),
        tags=("selection_overlay",),
    )

# CMP: TODO - stylistic aspects should not be hard coded. Move to a
# theme file.
# CMP: QUESTION - Since this is a mirror of an operation which is implemented
#      in the main canvas, shouldn't we use a common function for both canvas,
#      with input points mapped either to image or to canvas (these functions
#      already exist)?
def draw_zoom_vertex_square(
    host: ZoomEditOverlayHost,
    point: Point,
    fill: str,
) -> None:
    """Draw one fixed-size vertex handle in the zoom preview."""

    x_coord, y_coord = point
    host.widgets.controls.zoom_canvas.create_rectangle(
        x_coord - VERTEX_HALF,
        y_coord - VERTEX_HALF,
        x_coord + VERTEX_HALF,
        y_coord + VERTEX_HALF,
        fill=fill,
        outline="#0057ff",
        width=1,
        tags=("vertex",),
    )

# CMP: TODO - Again, this is something we already do in the main canvas... Refactor
def draw_zoom_snap_preview_dot(
    host: ZoomEditOverlayHost,
    to_zoom: Callable[[Point], Point],
) -> None:
    """Draw the new-annotation snap target in the zoom preview."""

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
    zoom_x, zoom_y = to_zoom(snap_point)
    radius = 2.0
    host.widgets.controls.zoom_canvas.create_oval(
        zoom_x - radius,
        zoom_y - radius,
        zoom_x + radius,
        zoom_y + radius,
        fill="#dc2626",
        outline="#dc2626",
        width=0,
        tags=("snap_preview",),
    )
