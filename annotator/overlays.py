"""Rasterize annotation fill overlays shared by canvas and zoom preview.

This module owns image-space compositing only. GUI modules decide which
polygons are visible, compute style colours, and place the resulting image on a
Tk canvas or zoom crop; this module turns those polygons into an RGBA Pillow
image with overlap colours that read like mixed pigment.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from PIL import Image
from PIL import ImageDraw

from annotator.geom.coordinates import map_polygon_between_spaces


def mixed_annotation_overlay(
    size: tuple[int, int],
    polygon_fills: list[tuple[list[tuple[float, float]], tuple[int, int, int, int]]],
) -> Image.Image | None:
    """Return an RGBA annotation-fill overlay, or None when nothing is visible.

    `size` is the output image size in pixels. Polygon coordinates must already
    be expressed in that output coordinate system. Alpha is accumulated
    additively, while colour is averaged in RYB space weighted by each polygon
    mask so overlaps become more opaque and mix like annotation pigment instead
    of simple RGB stacking.
    """

    # Returning None lets callers skip Pillow/Tk image allocation when no fill
    # can affect the rendered view.
    if not polygon_fills:
        return None

    width, height = size
    alpha_sum = np.zeros((height, width), dtype=np.float32)
    ryb_sum = np.zeros((height, width, 3), dtype=np.float32)
    for points, fill in polygon_fills:
        if len(points) < 3 or fill[3] <= 0:
            continue
        # Build each polygon mask only over its clamped pixel box. Full-canvas
        # masks are noticeably more expensive on large images and zoomed views.
        polygon_box = polygon_pixel_bbox(points, width, height)
        if polygon_box is None:
            continue
        left, top, right, bottom = polygon_box
        mask_size = (right - left, bottom - top)
        shifted_points = map_polygon_between_spaces(
            points,
            source_origin=(left, top),
        )
        mask = Image.new("L", mask_size, 0)
        ImageDraw.Draw(mask).polygon(round_polygon_points(shifted_points), fill=int(fill[3]))
        mask_array = np.asarray(mask, dtype=np.float32)
        if not np.any(mask_array):
            continue
        ryb = np.array(rgb_to_ryb(fill[:3]), dtype=np.float32)
        alpha_slice = alpha_sum[top:bottom, left:right]
        ryb_slice = ryb_sum[top:bottom, left:right]
        # Keep opacity separate from colour accumulation: alpha controls final
        # visibility, while RYB weights preserve pigment-like overlap colour.
        alpha_slice += mask_array
        ryb_slice += mask_array[:, :, None] * ryb

    # If every polygon was degenerate, transparent, or outside the image,
    # callers should behave as though there is no overlay at all.
    visible = alpha_sum > 0
    if not np.any(visible):
        return None
    mixed_ryb = np.zeros_like(ryb_sum)
    mixed_ryb[visible] = ryb_sum[visible] / alpha_sum[visible, None]
    mixed_rgb = ryb_array_to_rgb(mixed_ryb)
    overlay_array = np.zeros((height, width, 4), dtype=np.uint8)
    overlay_array[:, :, :3] = np.clip(np.rint(mixed_rgb * 255), 0, 255).astype(np.uint8)
    # Pillow expects 8-bit RGBA channels, so accumulated alpha is clipped after
    # mixing rather than during per-polygon accumulation.
    overlay_array[:, :, 3] = np.clip(np.rint(alpha_sum), 0, 255).astype(np.uint8)
    return Image.fromarray(overlay_array, "RGBA")


def polygon_pixel_bbox(
    points: list[tuple[float, float]],
    width: int,
    height: int,
) -> tuple[int, int, int, int] | None:
    """Return a clamped half-open pixel box covering a polygon.

    The one-pixel low-side and two-pixel high-side padding keeps rounded Pillow
    polygon vertices from being clipped at the local mask edge.
    """

    if not points or width <= 0 or height <= 0:
        return None
    left = max(0, int(math.floor(min(x_coord for x_coord, _y in points))) - 1)
    top = max(0, int(math.floor(min(y_coord for _x, y_coord in points))) - 1)
    right = min(width, int(math.ceil(max(x_coord for x_coord, _y in points))) + 2)
    bottom = min(height, int(math.ceil(max(y_coord for _x, y_coord in points))) + 2)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def round_polygon_points(
    points: list[tuple[float, float]],
) -> list[tuple[int, int]]:
    """Round float geometry at the Pillow mask boundary.

    Callers keep annotation geometry in float/image coordinates; only Pillow's
    rasterizer needs integer points.
    """

    return [(int(round(x_coord)), int(round(y_coord))) for x_coord, y_coord in points]


def rgb_to_ryb(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """Convert an RGB colour to RYB coordinates for pigment-style mixing.

    Annotation overlaps should read like translucent marked regions blending
    together, so yellow and blue produce a greenish overlap rather than the
    dull result produced by naive RGB averaging.
    """

    red, green, blue = (channel / 255.0 for channel in rgb)
    white = min(red, green, blue)
    red -= white
    green -= white
    blue -= white
    max_green = max(red, green, blue)
    yellow = min(red, green)
    red -= yellow
    green -= yellow
    if blue > 0 and green > 0:
        blue /= 2
        green /= 2
    yellow += green
    blue += green
    max_yellow = max(red, yellow, blue)
    if max_yellow > 0:
        scale = max_green / max_yellow
        red *= scale
        yellow *= scale
        blue *= scale
    return red + white, yellow + white, blue + white


def ryb_array_to_rgb(ryb_array: Any) -> Any:
    """Convert a NumPy RYB overlay array back to RGB values in the range 0..1.

    The inverse conversion is vectorized because overlay rendering works over
    whole image arrays rather than one pixel at a time.
    """

    red = ryb_array[:, :, 0].copy()
    yellow = ryb_array[:, :, 1].copy()
    blue = ryb_array[:, :, 2].copy()
    white = np.minimum(np.minimum(red, yellow), blue)
    red -= white
    yellow -= white
    blue -= white
    max_yellow = np.maximum(np.maximum(red, yellow), blue)
    green = np.minimum(yellow, blue)
    yellow -= green
    blue -= green
    blue *= 2
    green *= 2
    red += yellow
    green += yellow
    max_green = np.maximum(np.maximum(red, green), blue)
    scale = np.divide(
        max_yellow,
        max_green,
        out=np.zeros_like(max_yellow),
        where=max_green > 0,
    )
    red *= scale
    green *= scale
    blue *= scale
    red += white
    green += white
    blue += white
    return np.stack([red, green, blue], axis=2)
