"""Prepare model inputs and map RF-DETR coordinates back to image space.

RF-DETR runs on square RGB images. This module owns the supported preprocessing
mode: preserve aspect ratio, resize with Pillow LANCZOS, center the image on a
white square canvas, and translate model-output coordinates back through that
same padding and scale.

It does not run inference, parse model outputs, decide class IDs, or persist
annotations. Callers provide already-selected model input size and consume
image-space polygons/boxes.
"""

from __future__ import annotations

from PIL import Image

from annotator.geom.coordinates import map_point_between_spaces

Point = tuple[float, float]


def resize_to_square(image: Image.Image, size: int) -> Image.Image:
    """Return an RGB square model input with preserved image aspect ratio.

    The original image is resized to fit within ``size`` and pasted onto
    centered white margins. This matches the preprocessing provenance recorded
    for model runs and is the inverse geometry used by the mapping helpers
    below.
    """

    resized_width, resized_height, left, top = resize_geometry(
        image.width,
        image.height,
        size,
    )
    resized = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), "white")
    canvas.paste(resized, (left, top))
    return canvas


def map_model_input_box_to_image(
    box: tuple[float, float, float, float],
    image_width: int,
    image_height: int,
    model_input_size: int = 1000,
) -> tuple[float, float, float, float] | None:
    """Map one model-space ``xyxy`` box back to original image pixels.

    Boxes are first mapped by their two opposite corners. If either corner
    falls in the white padding, the box coordinates are limited to the
    non-padding content bounds and mapped again. Boxes that still cannot produce
    a positive-area image-space rectangle return ``None``.
    """

    x1, y1, x2, y2 = box
    points = [
        map_model_input_point_to_image(
            x1,
            y1,
            image_width,
            image_height,
            model_input_size,
        ),
        map_model_input_point_to_image(
            x2,
            y2,
            image_width,
            image_height,
            model_input_size,
        ),
    ]
    if any(point is None for point in points):
        # Model boxes can overlap white padding; keep only their image-content part.
        left, top, right, bottom = padded_content_bounds(
            image_width,
            image_height,
            model_input_size,
        )
        x1 = max(left, min(right, x1))
        x2 = max(left, min(right, x2))
        y1 = max(top, min(bottom, y1))
        y2 = max(top, min(bottom, y2))
        points = [
            map_model_input_point_to_image(
                x1,
                y1,
                image_width,
                image_height,
                model_input_size,
            ),
            map_model_input_point_to_image(
                x2,
                y2,
                image_width,
                image_height,
                model_input_size,
            ),
        ]
    if any(point is None for point in points):
        return None
    first, second = points
    if first is None or second is None:
        return None
    left, right = sorted((first[0], second[0]))
    top, bottom = sorted((first[1], second[1]))
    # Degenerate boxes after padding removal are not useful annotations.
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def map_model_input_polygon_to_image(
    polygon: tuple[Point, ...],
    image_width: int,
    image_height: int,
    model_input_size: int = 1000,
) -> tuple[Point, ...] | None:
    """Map a model-space polygon back to original image pixels.

    Each vertex is limited to the non-padding content bounds before mapping, so
    segmentation outlines that spill into white margins are pulled back to the
    image edge rather than discarded wholesale. Return ``None`` when fewer than
    three image-space vertices remain.
    """

    left, top, right, bottom = padded_content_bounds(
        image_width,
        image_height,
        model_input_size,
    )
    mapped_points: list[Point] = []
    for x_coord, y_coord in polygon:
        # Preserve partially padded masks by moving margin vertices to the image edge.
        mapped = map_model_input_point_to_image(
            max(left, min(right, x_coord)),
            max(top, min(bottom, y_coord)),
            image_width,
            image_height,
            model_input_size,
        )
        if mapped is not None:
            mapped_points.append(mapped)
    return tuple(mapped_points) if len(mapped_points) >= 3 else None


def map_model_input_point_to_image(
    x_coord: float,
    y_coord: float,
    image_width: int,
    image_height: int,
    model_input_size: int = 1000,
) -> Point | None:
    """Map one model-input point to original image pixels.

    Points outside the resized image content return ``None`` because they belong
    to the white padding rather than the source image. Points on the content
    boundary are accepted and may map to ``image_width`` or ``image_height`` at
    the far edge.
    """

    resized_width, resized_height, left, top = resize_geometry(
        image_width,
        image_height,
        model_input_size,
    )
    if (
        x_coord < left
        or x_coord > left + resized_width
        or y_coord < top
        or y_coord > top + resized_height
    ):
        return None
    return map_point_between_spaces(
        (x_coord, y_coord),
        source_origin=(left, top),
        scale=(image_width / resized_width, image_height / resized_height),
    )


def resize_geometry(
    image_width: int,
    image_height: int,
    size: int = 1000,
) -> tuple[int, int, int, int]:
    """Return resized content dimensions and centered origin inside square input.

    One source dimension fills ``size`` and the other is scaled proportionally
    with a minimum of one pixel. The returned ``left`` and ``top`` offsets
    locate the resized image content inside the white square canvas.
    """

    # Fill the longer image dimension and center the shorter one in white margins.
    if image_width >= image_height:
        resized_width = size
        resized_height = max(1, round(image_height * size / image_width))
    else:
        resized_height = size
        resized_width = max(1, round(image_width * size / image_height))
    left = (size - resized_width) // 2
    top = (size - resized_height) // 2
    return resized_width, resized_height, left, top


def padded_content_bounds(
    image_width: int,
    image_height: int,
    model_input_size: int = 1000,
) -> tuple[float, float, float, float]:
    """Return model-input bounds occupied by source image content.

    The returned ``left, top, right, bottom`` values describe the resized image
    inside the square canvas. Coordinates outside these bounds are preprocessing
    padding, not source-image pixels.
    """

    resized_width, resized_height, left, top = resize_geometry(
        image_width,
        image_height,
        model_input_size,
    )
    return (
        float(left),
        float(top),
        float(left + resized_width),
        float(top + resized_height),
    )


def box_polygon(
    box: tuple[float, float, float, float],
) -> tuple[Point, ...]:
    """Return a four-corner rectangular polygon for an ``xyxy`` image-space box.

    Detection-only RF-DETR results use this to become editable rectangle
    annotations after coordinate mapping.
    """

    left, top, right, bottom = box
    return ((left, top), (right, top), (right, bottom), (left, bottom))
