"""Normalize RF-DETR output containers into Teacup detection records.

This module owns the adapter boundary between RF-DETR's prediction objects and
the simpler dictionaries consumed by inference mapping. It locates box,
class-ID, confidence, mask, and polygon data across the output shapes RF-DETR
has exposed, then normalizes segmentation geometry when present.

It does not run inference, map model-input coordinates back to image pixels,
validate model class names, or persist annotations.
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterator
from typing import Any

DetectionRecord = dict[str, Any]
Polygon = tuple[tuple[float, float], ...]


def iter_detection_records(detections: Any) -> Iterator[DetectionRecord]:
    """Yield one normalized record for each RF-DETR detection.

    Boxes may be exposed directly as ``detections.xyxy`` or under
    ``detections.boxes.xyxy``. ``class_id`` and ``confidence`` are required
    parallel arrays and are allowed to raise naturally when missing, short, or
    malformed. Mask and polygon arrays are optional because detection-only
    outputs can still become rectangle annotations.
    """

    # RF-DETR releases and wrappers have exposed boxes in both locations.
    xyxy_values = getattr(detections, "xyxy", None)
    if xyxy_values is None:
        boxes = getattr(detections, "boxes", None)
        xyxy_values = getattr(boxes, "xyxy", None)
    if xyxy_values is None:
        return

    # Class IDs and confidences define the detection contract; missing values
    # should surface as natural model-output errors rather than silent records.
    class_ids = detections.class_id
    confidences = detections.confidence
    # Geometry channels are optional and have used singular/plural names.
    masks = getattr(detections, "mask", None)
    if masks is None:
        masks = getattr(detections, "masks", None)
    polygons = getattr(detections, "polygons", None)
    if polygons is None:
        polygons = getattr(detections, "polygon", None)

    for index, box in enumerate(xyxy_values):
        yield {
            "xyxy": tuple(float(value) for value in box[:4]),
            "class_id": int(class_ids[index]),
            "confidence": float(confidences[index]),
            "mask": sequence_value(masks, index, None, lambda value: value),
            "polygons": sequence_value(polygons, index, None, lambda value: value),
        }


def sequence_value(
    sequence: Any,
    index: int,
    default: Any,
    convert: Callable[[Any], Any],
) -> Any:
    """Return one item from an optional parallel model-output sequence.

    This helper is intentionally forgiving because masks and polygons enrich a
    detection but do not decide whether the box itself exists.
    """

    if sequence is None:
        return default
    try:
        return convert(sequence[index])
    except (IndexError, KeyError, TypeError, ValueError):
        return default


def polygons_from_detection(
    detection: DetectionRecord,
) -> tuple[Polygon, ...]:
    """Return model-input polygons from explicit polygons or masks.

    Explicit polygon output takes precedence because it is already vector
    geometry. Mask conversion is the fallback for segmentation outputs that
    provide raster masks only; OpenCV and NumPy are imported here so manual
    annotation workflows do not depend on model-only packages at startup.
    """

    explicit_polygons = detection.get("polygons")
    if explicit_polygons is not None:
        return normalize_polygons(explicit_polygons)

    mask = detection.get("mask")
    if mask is None:
        return ()
    # Defer model-only dependencies until a caller actually needs mask contours.
    import cv2
    import numpy as np

    mask_array = np.asarray(mask)
    # RF-DETR masks can carry singleton dimensions; contours require a 2-D plane.
    if mask_array.ndim > 2:
        mask_array = np.squeeze(mask_array)
    if mask_array.ndim != 2:
        return ()
    # Teacup stores annotation outlines, so internal mask hierarchy is ignored.
    contours, _hierarchy = cv2.findContours(
        (mask_array > 0).astype("uint8"),
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    polygons: list[Polygon] = []
    for contour in contours:
        points = contour.reshape(-1, 2)
        # COCO polygons and Teacup annotations both require at least a triangle.
        if len(points) >= 3:
            polygons.append(tuple((float(x), float(y)) for x, y in points))
    return tuple(polygons)


def normalize_polygons(value: Any) -> tuple[Polygon, ...]:
    """Normalize model polygon encodings to tuple-of-point-tuples.

    Supported inputs are NumPy arrays, COCO-style flat coordinate lists, one
    polygon represented as coordinate pairs, or multiple polygons in either
    shape. Values that cannot produce at least three numeric points are omitted
    rather than guessed into geometry.
    """

    import numpy as np

    if isinstance(value, np.ndarray):
        value = value.tolist()
    if not value:
        return ()
    # Treat a single polygon as a one-item polygon collection below.
    if is_flat_polygon(value) or is_point_polygon(value):
        value = [value]

    polygons: list[Polygon] = []
    for polygon in value:
        points: list[tuple[float, float]] = []
        iterator = (
            zip(polygon[0::2], polygon[1::2])
            if is_flat_polygon(polygon)
            else polygon
        )
        for point in iterator:
            if len(point) >= 2:
                points.append((float(point[0]), float(point[1])))
        if len(points) >= 3:
            polygons.append(tuple(points))
    return tuple(polygons)


def is_flat_polygon(value: Any) -> bool:
    """Return whether ``value`` is one COCO-style flat polygon.

    The predicate is deliberately narrow: only numeric list/tuple coordinates
    are accepted, so malformed output is omitted by normalization.
    """

    return (
        isinstance(value, (list, tuple))
        and len(value) >= 6
        and len(value) % 2 == 0
        and all(isinstance(item, (int, float)) for item in value)
    )


def is_point_polygon(value: Any) -> bool:
    """Return whether ``value`` is one polygon made of coordinate pairs.

    Extra point dimensions are tolerated by callers, but the first two
    coordinates must be numeric to form image geometry.
    """

    return (
        isinstance(value, (list, tuple))
        and len(value) >= 3
        and all(
            isinstance(point, (list, tuple))
            and len(point) >= 2
            and isinstance(point[0], (int, float))
            and isinstance(point[1], (int, float))
            for point in value
        )
    )
