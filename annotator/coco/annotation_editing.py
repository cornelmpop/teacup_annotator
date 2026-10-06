"""CODEX: Edit the rectangle and polygon region annotations in `CocoDocument`.

Annotator also treats arrows as annotations, but arrows are not COCO region
geometry. Arrow-annotation editing lives in `annotator.gui.arrow_editing`, and
arrow persistence lives under `annotator.sqlite`.

The functions here mutate in-memory region state and normalize its geometry.
Callers own undo records, auditing, durable writes, and GUI effects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import uuid

from annotator.coco.image_records import image_id_for
from annotator.coco.image_records import next_annotation_id
from annotator.coco.models import Annotation
from annotator.coco.models import ModelAnnotation
from annotator.coco.type_helpers import annotation_export_type
from annotator.geom.polygon import single_polygon_list
from annotator.geom.polygon.union import polygon_union_has_hole
from annotator.geom.rectangle import rectangle_corners_from_polygon

if TYPE_CHECKING:
    from annotator.coco.document import CocoDocument


def annotations_for(self: CocoDocument, image_name: str) -> list[Annotation]:
    """CODEX: Return the mutable annotation list for an image.

    Create and store an empty list if the image does not yet have one.
    """

    return self.annotations_by_image.setdefault(image_name, [])


def add_annotation(
    self: CocoDocument,
    image_name: str,
    polygon: list[tuple[float, float]],
    category_id: int = 1,
    annotation_type: str = "polygon",
) -> Annotation:
    """CODEX: Create and append one manually entered region annotation.

    The caller supplies its geometry, category, and rectangle/polygon type.
    This method assigns its COCO ids and durable annotation identity. It does not
    normalize or persist the supplied geometry.
    """

    # CODEX: COCO ids may be renumbered during full export. Audit and SQLite
    # CODEX: use the annotation UUID as the region annotation's durable identity.
    annotation = Annotation(
        annotation_id=next_annotation_id(self),
        image_id=image_id_for(self, image_name),
        category_id=category_id,
        polygons=[polygon],
        raw={
            "annotation_type": annotation_type,
            "annotation_uuid": f"ann:{uuid.uuid4()}",
            "entry_type": "manual",
        },
    )
    annotations_for(self, image_name).append(annotation)
    return annotation


def delete_annotation(self: CocoDocument, image_name: str, index: int) -> None:
    """CODEX: Delete an image-local region annotation when its index is valid.

    An invalid index leaves the document unchanged.
    """

    annotations = annotations_for(self, image_name)
    if 0 <= index < len(annotations):
        del annotations[index]


def merge_annotations(
    self: CocoDocument,
    image_name: str,
    primary_index: int,
    secondary_index: int,
) -> int | None:
    """CODEX: Merge two region annotations and return the surviving primary index.

    Two rectangles become their enclosing axis-aligned rectangle so the result
    remains rectangle-editable. Any polygon input uses editable polygon-union
    normalization. Hole-forming polygon merges return `None` because Annotator
    cannot store the result as one editable outline without filling the center.

    The primary keeps its component identity and category. Its detector score
    falls back to the secondary score when the primary has none. Invalid or
    self-merge requests return `None` without mutation. A successful return
    accounts for any index shift caused by deleting the secondary annotation.
    """

    annotations = annotations_for(self, image_name)
    # CODEX: A no-mutation result lets GUI orchestration abandon an
    # CODEX: invalid merge without persisting or selecting a nonexistent result.
    if (
        primary_index < 0
        or secondary_index < 0
        or primary_index >= len(annotations)
        or secondary_index >= len(annotations)
        or primary_index == secondary_index
    ):
        return None
    primary = annotations[primary_index]
    secondary = annotations[secondary_index]
    # CODEX: Preserve constrained rectangle editing by enclosing two
    # CODEX: rectangles in an axis-aligned box rather than replacing them
    # CODEX: with a free polygon union.
    if all(
        annotation_export_type(annotation) == "rectangle"
        for annotation in (primary, secondary)
    ):
        points = [*primary.polygons[0], *secondary.polygons[0]]
        primary.polygons = [rectangle_corners_from_polygon(points)]
        primary.raw["annotation_type"] = "rectangle"
    else:
        polygons = primary.polygons + secondary.polygons
        # CODEX: Ring-like unions must remain separate annotations rather than
        # CODEX: becoming multipart gaps or a center-filling exterior.
        if polygon_union_has_hole(polygons):
            return None
        # CODEX: Any polygon input removes rectangle constraints and normalizes
        # CODEX: to one editable exterior outline.
        primary.polygons = single_polygon_list(polygons)
        primary.raw["annotation_type"] = "polygon"
    # CODEX: The typed score is authoritative; remove a stale raw copy and
    # CODEX: preserve the secondary score only when the survivor has none.
    primary.raw.pop("score", None)
    primary.score = primary.score if primary.score is not None else secondary.score
    del annotations[secondary_index]
    # CODEX: Deleting an earlier secondary shifts the surviving primary index left.
    if secondary_index < primary_index:
        return primary_index - 1
    return primary_index


def delete_vertices(
    self: CocoDocument,
    image_name: str,
    annotation_index: int,
    vertex_refs: set[tuple[int, int]],
) -> None:
    """CODEX: Delete selected vertices from one region annotation.

    Each reference is a `(polygon_index, vertex_index)` pair. Components with
    fewer than three remaining vertices are discarded. Surviving components
    are re-normalized, and the annotation is removed when none remain. An
    invalid annotation index leaves the document unchanged.
    """

    annotations = annotations_for(self, image_name)
    if annotation_index < 0 or annotation_index >= len(annotations):
        return
    annotation = annotations[annotation_index]
    next_polygons: list[list[tuple[float, float]]] = []
    for polygon_index, polygon in enumerate(annotation.polygons):
        next_polygon = [
            point
            for vertex_index, point in enumerate(polygon)
            if (polygon_index, vertex_index) not in vertex_refs
        ]
        # CODEX: COCO polygon segmentation requires at least three vertices.
        if len(next_polygon) >= 3:
            next_polygons.append(next_polygon)
    if next_polygons:
        # CODEX: Re-normalize survivors before rendering or persistence consumes them.
        annotation.polygons = single_polygon_list(next_polygons)
    else:
        del annotations[annotation_index]


def replace_with_model_annotations(
    self: CocoDocument,
    model_annotations: list[ModelAnnotation],
    category_names: dict[int, str],
) -> tuple[dict[int, int], list[Annotation]]:
    """CODEX: Replace current model output while retaining human-owned regions.

    For every loaded image, remove annotations that retain model source and a
    ``model_run_class_id``. Preserve manual and imported annotations, including
    human-corrected model-derived annotations whose current source is manual,
    in their existing relative order and with their model lineage intact.

    Map each raw model class index to a stable project category by exact class
    name, adding a project category only when that name is absent. Append
    accepted model results after retained regions, assigning new COCO IDs,
    durable UUIDs, raw model-class indices, confidence values, geometry type,
    and automatic provenance. Ignore results for unloaded images or without
    usable geometry.

    Return the raw-model-index to project-category-ID mapping and the exact new
    annotations that need links to the completed model run.
    """

    project_category_ids = {
        model_category_id: self.category_id_for_name(category_name)
        for model_category_id, category_name in category_names.items()
    }
    for image_path in self.image_paths:
        retained_annotations: list[Annotation] = []
        for annotation in annotations_for(self, image_path.name):
            # CODEX: Current source, rather than retained model lineage, determines
            # CODEX: whether a human-reviewed annotation survives the next run.
            is_current_model_output = (
                annotation.raw.get("model_run_class_id") is not None
                and annotation.raw.get("entry_type") == "automatic"
            )
            if not is_current_model_output:
                retained_annotations.append(annotation)
        self.annotations_by_image[image_path.name] = retained_annotations

    next_id = next_annotation_id(self)
    installed_annotations: list[Annotation] = []
    for result in model_annotations:
        # CODEX: Output outside the loaded folder cannot attach to a document image.
        if result.image_name not in self.annotations_by_image:
            continue
        polygons = single_polygon_list(result.polygons)
        # CODEX: Empty normalized output is not an annotation and consumes no COCO id.
        if not polygons:
            continue
        # CODEX: Each accepted model output is a new durable region annotation
        # CODEX: with automatic provenance, independent of the replaced generation.
        annotation = Annotation(
            annotation_id=next_id,
            image_id=image_id_for(self, result.image_name),
            category_id=project_category_ids[result.category_id],
            polygons=polygons,
            score=result.score,
            raw={
                "annotation_type": result.annotation_type,
                "annotation_uuid": f"ann:{uuid.uuid4()}",
                "entry_type": "automatic",
                "model_class_index": result.category_id,
            },
        )
        self.annotations_by_image[result.image_name].append(annotation)
        installed_annotations.append(annotation)
        next_id += 1
    return project_category_ids, installed_annotations


def normalize_single_polygons(self: CocoDocument) -> None:
    """CODEX: Normalize every region annotation's editable geometry in place.

    Full-document serialization uses this boundary to union overlapping
    components into the one-outline shape the editable annotation model stores.
    """

    for image_annotations in self.annotations_by_image.values():
        for annotation in image_annotations:
            annotation.polygons = single_polygon_list(annotation.polygons)


def normalize_image_polygons(
    self: CocoDocument,
    image_name: str,
) -> None:
    """CODEX: Normalize one image's region-annotation geometry in place.

    Per-image serialization and SQLite writes use this narrower boundary so
    unrelated image geometry is not touched.
    """

    for annotation in annotations_for(self, image_name):
        annotation.polygons = single_polygon_list(annotation.polygons)
