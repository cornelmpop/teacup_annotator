"""CODEX: Translate between COCO payload dictionaries and document regions.

Exports produce complete, annotation-type-filtered, and per-image payloads;
imports append supported COCO rows to document image buckets. Both directions
normalize polygon geometry at their document boundary and preserve
application-specific annotation metadata where possible. File imports record
detected lossy geometry normalization and rows skipped by this parser.

Numeric COCO annotation IDs are export-local and may be reassigned. Durable
region identity lives in `annotation_uuid`. Arrow annotations remain outside
COCO state. Filesystem I/O lives in `annotator.coco.io`; primitive annotation
field encoding lives in `annotator.coco.serialize`.
"""

from __future__ import annotations

from annotator.coco.annotation_editing import annotations_for
from annotator.coco.annotation_editing import normalize_image_polygons
from annotator.coco.annotation_editing import normalize_single_polygons
from annotator.coco.category_helpers import categories_to_json
from annotator.coco.image_helpers import image_size
from annotator.coco.models import Annotation
from annotator.coco.parse import annotation_polygons
from annotator.coco.parse import optional_float
from annotator.coco.serialize import annotation_payload
from annotator.coco.type_helpers import annotation_matches_export_filter
from annotator.coco.type_helpers import annotation_type_from_polygons
from annotator.geom.polygon.union import polygon_union_has_hole
from annotator.geom.polygon import single_polygon_list
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from annotator.coco.document import CocoDocument


def to_payload(
    self: CocoDocument,
    annotation_type_filter: str | None = None,
) -> dict[str, Any]:
    """Return a complete or annotation-type-filtered COCO payload.

    Normalize every region annotation in place before serialization. Copy the
    document `info`, supply its default description when absent, and set
    `date_modified` to the current UTC time. A complete payload includes every
    loaded image and region annotation. A filtered payload includes only
    matching regions and images containing at least one match, and records the
    filter in `info`.

    Image records are shallow-copied, their `file_name` is reset to the loaded
    basename, and readable source dimensions replace their width and height.
    Existing dimensions remain when the source image cannot be read. Annotation
    payloads preserve application-specific `raw` metadata while regenerating
    standard COCO fields. Category and annotation references are copied and
    translated from internal IDs to external JSON IDs.

    A complete payload assigns compact annotation IDs starting at one in
    `image_paths` and image-local order, updating each annotation's in-memory
    `annotation_id` and `image_id`. A filtered payload uses compact IDs only in
    the emitted dictionaries and leaves working IDs untouched. COCO image IDs
    continue to come from the document's image records.

    This function does not write files or include arrow annotations.
    """

    # Every export variant consumes the same normalized editable geometry.
    normalize_single_polygons(self)
    # Add volatile export metadata to a copy, leaving document-owned info untouched.
    info = dict(self.info)
    info.setdefault("description", "Image annotations")
    if annotation_type_filter is not None:
        info["annotation_type_filter"] = annotation_type_filter
    info["date_modified"] = (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )

    images = []
    image_paths_by_name = {image_path.name: image_path for image_path in self.image_paths}
    for image_path in self.image_paths:
        image_name = image_path.name
        # A split export lists only images represented by selected annotations.
        if annotation_type_filter is not None and not any(
            annotation_matches_export_filter(annotation, annotation_type_filter)
            for annotation in annotations_for(self, image_name)
        ):
            continue
        record = dict(self.image_records[image_name])
        record["file_name"] = image_name
        width, height = image_size(image_paths_by_name[image_name])
        # Preserve imported dimensions when the source header cannot be read.
        if width and height:
            record["width"] = width
            record["height"] = height
        images.append(record)

    annotations_payload = []
    next_id = 1
    for image_path in self.image_paths:
        image_name = image_path.name
        image_id = int(self.image_records[image_name]["id"])
        for annotation in annotations_for(self, image_name):
            if not annotation_matches_export_filter(annotation, annotation_type_filter):
                continue
            # Complete exports synchronize working numeric IDs; split exports
            # use output-only IDs so a convenience file cannot renumber the document.
            if annotation_type_filter is None:
                annotation.annotation_id = next_id
                annotation.image_id = image_id
            payload = annotation_payload(annotation, next_id, image_id)
            annotations_payload.append(payload)
            next_id += 1

    payload = {
        "info": info,
        "images": images,
        "annotations": annotations_payload,
        "categories": categories_to_json(self.categories),
    }
    return payload


def to_image_payload(self: CocoDocument, image_name: str) -> dict[str, Any]:
    """CODEX: Return one image's COCO backup without renumbering annotations.

    Normalize only the requested image. Shallow-copy its image record, reset
    `file_name` to the loaded basename, and refresh its dimensions when the
    source image is readable. Existing dimensions remain when it is not.

    For each region annotation, update the in-memory `image_id` to the current
    image-record ID while preserving its `annotation_id`. The shared annotation
    encoder preserves portable `raw` metadata and regenerates standard COCO
    geometry, identity, category, area, crowd, and detector-confidence fields.
    It omits the database-local `model_run_class_id`, whose referenced model-run
    tables are not part of a COCO backup.

    The payload receives fresh image-specific `info` rather than copying the
    document's project-level `info`. Its `categories` value is the
    document-owned list. An unknown image name raises its natural lookup error.

    This function supports image-local backup generation; it does not write the
    file, normalize unrelated images, or include arrow annotations.
    """

    # Per-image autosave must not normalize geometry belonging to other images.
    normalize_image_polygons(self, image_name)
    image_path_by_name = {image_path.name: image_path for image_path in self.image_paths}
    image_path = image_path_by_name[image_name]
    image_id = int(self.image_records[image_name]["id"])
    image_record = dict(self.image_records[image_name])
    image_record["file_name"] = image_name
    width, height = image_size(image_path)
    if width and height:
        image_record["width"] = width
        image_record["height"] = height

    annotations_payload = []
    for annotation in annotations_for(self, image_name):
        # Keep the annotation ID stable while repairing its current image reference.
        annotation.image_id = image_id
        payload = annotation_payload(annotation, annotation.annotation_id, image_id)
        annotations_payload.append(payload)

    payload = {
        "info": {
            "description": f"Image annotations for {image_name}",
            "date_modified": (
                datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            ),
        },
        "images": [image_record],
        "annotations": annotations_payload,
        "categories": categories_to_json(self.categories),
    }
    return payload


def _load_annotations(
    self: CocoDocument,
    annotations_value: Any,
    image_name_by_id: dict[int, str] | None = None,
    *,
    source_name: str | None = None,
) -> None:
    """CODEX: Append supported COCO rows and record file-import notices.

    A non-list value leaves the document unchanged. When `image_name_by_id` is
    omitted, derive the mapping from the document's image records; conversion
    errors in those records propagate. A supplied mapping constrains loading to
    the image IDs selected by the caller, as required by per-image overlays.

    For each dictionary row, coerce its numeric image, annotation, and category
    IDs. Missing annotation and category IDs default to zero and one. Skip rows
    with unconvertible IDs, unknown image IDs, unsupported geometry, or no
    geometry remaining after editable normalization. When ``source_name`` is
    supplied, append a one-based, source-labelled notice for each such skip and
    for multipart or hole-flattening normalization. Existing image buckets are
    not cleared; the caller owns replacement versus append semantics.

    Shallow-copy each accepted source row as `raw` metadata. Preserve explicitly
    supplied annotation type, annotation UUID, and entry provenance. When those
    keys are absent, infer the region type from normalized geometry, generate a
    durable annotation UUID, and infer automatic entry provenance from a
    non-`None` score. An unusable optional score becomes `None` without
    discarding valid geometry.

    Accepted annotations are appended in input order. Arrow annotations are
    outside this import path.
    """

    if not isinstance(annotations_value, list):
        return
    # Build the full mapping only when the caller did not constrain an overlay.
    if image_name_by_id is None:
        image_name_by_id = {
            int(record.get("id", -1)): image_name
            for image_name, record in self.image_records.items()
            if "id" in record
        }
    # Isolate malformed annotation rows so the remainder of the payload can load.
    for row_number, raw_annotation in enumerate(annotations_value, start=1):
        if not isinstance(raw_annotation, dict):
            continue
        try:
            image_id = int(raw_annotation.get("image_id", -1))
            annotation_id = int(raw_annotation.get("id", 0))
            category_id = int(raw_annotation.get("category_id", 1))
        except (TypeError, ValueError):
            if source_name is not None:
                self.import_notices.append(
                    f"{source_name} row {row_number}: rejected because image, "
                    "annotation, or category IDs are not integers."
                )
            continue
        image_name = image_name_by_id.get(image_id)
        if image_name is None:
            if source_name is not None:
                self.import_notices.append(
                    f"{source_name} row {row_number}: rejected because image_id "
                    f"{image_id} does not match a loaded image."
                )
            continue
        polygons = annotation_polygons(raw_annotation)
        if not polygons:
            if source_name is not None:
                self.import_notices.append(
                    f"{source_name} row {row_number}: rejected because it has no "
                    "supported editable segmentation, polygons_xy, or bbox "
                    "geometry."
                )
            continue
        source_polygon_count = len(polygons)
        flattened_holes = (
            source_polygon_count > 1 and polygon_union_has_hole(polygons)
        )
        polygons = single_polygon_list(polygons)
        if not polygons:
            if source_name is not None:
                self.import_notices.append(
                    f"{source_name} row {row_number}: rejected because no editable "
                    "geometry remained after normalization."
                )
            continue
        if source_name is not None and source_polygon_count > 1:
            notice = (
                f"{source_name} row {row_number}: combined {source_polygon_count} "
                "source polygons into one editable outline (disconnected parts "
                "use their convex hull)"
            )
            if flattened_holes:
                notice += "; flattened interior holes."
            else:
                notice += "."
            self.import_notices.append(notice)
        raw = dict(raw_annotation)
        # Preserve imported identity and provenance, filling fields only when absent.
        raw.setdefault("annotation_type", annotation_type_from_polygons(polygons))
        raw.setdefault("annotation_uuid", f"ann:{uuid.uuid4()}")
        raw.setdefault(
            "entry_type",
            "automatic" if raw.get("score") is not None else "manual",
        )
        annotation = Annotation(
            annotation_id=annotation_id,
            image_id=image_id,
            category_id=category_id,
            polygons=polygons,
            score=optional_float(raw_annotation.get("score")),
            raw=raw,
        )
        annotations_for(self, image_name).append(annotation)
