"""Encode individual region annotations and polygon measurements as COCO fields.

`annotation_payload` combines an `Annotation` with caller-selected numeric IDs.
`segmentation_payload` and `bbox_payload` provide the primitive polygon-field
encodings used by document serializers.

Document-wide filtering, ordering, ID policy, image and category records, and
geometry normalization belong to `annotator.coco.serialization`. Filesystem
publication belongs to `annotator.coco.io`. Arrow annotations have no COCO
encoding and do not pass through this module.
"""

from __future__ import annotations

from typing import Any

from annotator.coco.category_helpers import category_id_to_json
from annotator.coco.models import Annotation
from annotator.geom.polygon import area
from annotator.geom.polygon import bbox


def annotation_payload(
    annotation: Annotation,
    annotation_id: int,
    image_id: int,
) -> dict[str, Any]:
    """CODEX: Return one COCO row using caller-selected numeric IDs.

    Begin with a shallow copy of `annotation.raw` so portable imported and
    application-specific metadata is retained. Omit `model_run_class_id`
    because it is a foreign key into one SQLite database and the COCO backup
    does not contain its referenced model-run tables. Raw model class index,
    UUID, source wording, and other interchange metadata remain available.

    Overwrite `id` and `image_id` with the supplied arguments, use the
    translate the annotation's current internal `category_id` to its external
    JSON value, and recompute segmentation, bounding box, area, and `iscrowd`
    from its current polygon geometry. Regenerated standard COCO fields
    therefore take precedence over conflicting values in `raw`.

    When `annotation.score` is not `None`, it replaces any `score` from `raw`.
    Otherwise an existing raw score is preserved and no score is added. Nested
    values belonging to other raw metadata remain shared because the copy is
    shallow.

    This function does not mutate the annotation, normalize its geometry,
    select its numeric IDs, or include arrow annotations.
    """

    # CODEX: A database-local model-run foreign key cannot be restored from a
    # CODEX: COCO file that deliberately omits the referenced relational rows.
    payload = dict(annotation.raw)
    payload.pop("model_run_class_id", None)
    payload.update(
        {
            "id": annotation_id,
            "image_id": image_id,
            "category_id": category_id_to_json(annotation.category_id),
            "segmentation": segmentation_payload(annotation.polygons),
            "bbox": bbox_payload(annotation.polygons),
            "area": area(annotation.polygons),
            "iscrowd": 0,
        }
    )
    # Prefer parsed confidence when available; otherwise retain imported metadata.
    if annotation.score is not None:
        payload["score"] = annotation.score
    return payload


def segmentation_payload(polygons: list[list[tuple[float, float]]]) -> list[list[float]]:
    """Return COCO flattened coordinate arrays for usable polygon outlines.

    Preserve polygon order, vertex order, and coordinate values. Omit an
    outline when it contains fewer than three vertices, as COCO polygon
    segmentation requires at least three coordinate pairs.

    This function does not close outlines, coerce coordinates, combine
    polygons, remove duplicates, or validate geometry.
    """

    # A short outline cannot represent a COCO polygon segmentation.
    return [
        [coordinate for point in polygon for coordinate in (point[0], point[1])]
        for polygon in polygons
        if len(polygon) >= 3
    ]


def bbox_payload(polygons: list[list[tuple[float, float]]]) -> list[float]:
    """Return one COCO `[x, y, width, height]` box spanning all polygon points.

    Multiple polygons share one axis-aligned bounding box. An empty collection
    returns `[0.0, 0.0, 0.0, 0.0]` through the generic geometry helper.

    Unlike `segmentation_payload`, this calculation includes points from
    outlines with fewer than three vertices. It does not clip coordinates or
    validate the geometry.
    """

    return bbox(polygons)
