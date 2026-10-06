"""Coordinate calculations shared by the Tk canvas controllers."""

from __future__ import annotations

import tkinter as tk

from annotator.geom.coordinates import map_point_between_spaces
from annotator.geom.coordinates import map_polygon_between_spaces
from annotator.gui.constants import MAX_ZOOM
from annotator.gui.interactions import MIN_ZOOM
from annotator.gui.state import ViewState

Point = tuple[float, float]
Size = tuple[int, int]


def canvas_polygon_points(
    polygon: list[Point],
    view: ViewState,
) -> list[float]:
    """Convert image-space polygon vertices to flat canvas coordinates."""

    mapped = map_polygon_between_spaces(
        polygon,
        target_origin=view.image_origin,
        scale=(view.zoom, view.zoom),
    )
    return [coordinate for point in mapped for coordinate in point]

# CMP: TODO - clarify meaning of 'scrollable' here.
def image_to_canvas_point(
    image_point: Point,
    view: ViewState,
) -> Point:
    """Convert one image-space point to scrollable canvas coordinates."""

    return map_point_between_spaces(
        image_point,
        target_origin=view.image_origin,
        scale=(view.zoom, view.zoom),
    )

# CMP: TODO - clarify meaning of 'scrollable' here.
def canvas_event_point(canvas: tk.Canvas, event: tk.Event) -> Point:
    """Return a Tk event location in scrollable canvas coordinates."""

    return canvas.canvasx(event.x), canvas.canvasy(event.y)


def image_point_from_canvas(
    canvas_point: Point,
    view: ViewState,
) -> Point | None:
    """Convert a canvas point to image pixels when it lies inside the image."""

    if view.current_image is None:
        return None
    canvas_x, canvas_y = canvas_point
    origin_x, origin_y = view.image_origin
    width, height = view.display_size
    image_canvas_x = canvas_x - origin_x
    image_canvas_y = canvas_y - origin_y
    if (
        image_canvas_x < 0
        or image_canvas_y < 0
        or image_canvas_x > width
        or image_canvas_y > height
    ):
        return None
    return map_point_between_spaces(
        canvas_point,
        source_origin=view.image_origin,
        scale=(1 / view.zoom, 1 / view.zoom),
    )


def clamp_canvas_point_to_image(
    canvas_point: Point,
    view: ViewState,
) -> Point:
    """Convert a canvas point to image pixels clamped to displayed bounds."""

    if view.current_image is None:
        return 0.0, 0.0
    canvas_x, canvas_y = canvas_point
    origin_x, origin_y = view.image_origin
    width, height = view.display_size
    clamped_x = max(0.0, min(float(width), canvas_x - origin_x))
    clamped_y = max(0.0, min(float(height), canvas_y - origin_y))
    return map_point_between_spaces(
        (clamped_x, clamped_y),
        scale=(1 / view.zoom, 1 / view.zoom),
    )


def clamp_point_to_image(
    image_point: Point,
    view: ViewState,
) -> Point:
    """Clamp image coordinates to source-image bounds when an image is loaded."""

    if view.current_image is None:
        return image_point
    width, height = view.current_image.size
    return (
        max(0.0, min(float(width), image_point[0])),
        max(0.0, min(float(height), image_point[1])),
    )


def fit_zoom(image_size: Size, canvas_size: Size) -> float:
    """Calculate a comfortable initial zoom for an image and canvas size."""

    image_width, image_height = image_size
    canvas_width = max(1, canvas_size[0] - 4)
    canvas_height = max(1, canvas_size[1] - 4)
    if canvas_width <= 2 or canvas_height <= 2:
        return 1.0
    fit = min(canvas_width / image_width, canvas_height / image_height)
    return max(MIN_ZOOM, min(MAX_ZOOM, fit * 0.96))


def scrollregion_size(scrollregion: str) -> Point:
    """Return width and height parsed from a Tk canvas scrollregion value."""

    try:
        left, top, right, bottom = (float(value) for value in scrollregion.split())
    except ValueError:
        return 1.0, 1.0
    return max(1.0, right - left), max(1.0, bottom - top)
