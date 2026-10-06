"""CODEX: Capture and restore Undo state at its owning image or project scope.

CODEX: Local entries retain only the annotations, arrows, ordering, image record,
and category vocabulary needed to restore one image. Project-wide entries retain
the complete historical snapshot used by global edits. Callers own persistence,
audit-event creation, redraws, and user feedback after restoration.
"""

from __future__ import annotations

import copy
from typing import Any

from annotator.gui.state import ProjectState


def capture_undo_snapshot(
    project: ProjectState,
    image_name: str | None,
    all_images: bool,
    action: str,
) -> dict[str, Any]:
    """CODEX: Return the state needed to undo one edit at its declared scope.

    CODEX: Project-wide edits preserve the complete COCO projection, every arrow,
    and the complete explicit order map. Image-local edits preserve only the
    named image and its relevant order entries, while copying the full category
    vocabulary because restored annotations refer to category identifiers.
    ``image_name`` is required by the image-local caller contract.
    """
    coco = project.coco
    if coco is None:
        raise RuntimeError("No COCO document is loaded")

    if all_images:
        return {
            "coco_snapshot": coco.snapshot(),
            "arrows_by_image": copy.deepcopy(project.arrows_by_image),
            "annotation_orders_by_uuid": copy.deepcopy(
                project.annotation_orders_by_uuid
            ),
            "all_images": True,
            "action": action,
        }

    annotations = copy.deepcopy(coco.annotations_by_image.get(image_name, []))
    arrows = copy.deepcopy(project.arrows_by_image.get(image_name, []))
    order_keys = [
        annotation.raw.get("annotation_uuid") for annotation in annotations
    ]
    order_keys.extend(arrow.arrow_uuid for arrow in arrows)
    image_orders = {
        annotation_uuid: project.annotation_orders_by_uuid[annotation_uuid]
        for annotation_uuid in order_keys
        if annotation_uuid in project.annotation_orders_by_uuid
    }

    image_records = {}
    if image_name in coco.image_records:
        image_records[image_name] = copy.deepcopy(coco.image_records[image_name])

    return {
        "coco_snapshot": {
            "annotations_by_image": {image_name: annotations},
            "image_records": image_records,
            "categories": copy.deepcopy(coco.categories),
        },
        "arrows_by_image": {image_name: arrows},
        "annotation_orders_by_uuid": image_orders,
        "all_images": False,
        "image_name": image_name,
        "action": action,
    }


def restore_undo_snapshot(
    project: ProjectState,
    snapshot: dict[str, Any],
) -> tuple[str | None, bool]:
    """CODEX: Restore an Undo entry and report its image and arrow impact.

    CODEX: A project-wide entry replaces the complete in-memory projection. An
    image-local entry replaces only its owning image, category vocabulary, and
    relevant ordering entries so the displayed image and every unrelated image
    remain unchanged. The returned image name is ``None`` for project-wide
    restoration; the Boolean reports whether persisted arrows need updating.
    """
    coco = project.coco
    if coco is None:
        raise RuntimeError("No COCO document is loaded")

    if snapshot["all_images"]:
        arrows_changed = project.arrows_by_image != snapshot["arrows_by_image"]
        coco.restore(snapshot["coco_snapshot"])
        project.arrows_by_image = copy.deepcopy(snapshot["arrows_by_image"])
        if "annotation_orders_by_uuid" in snapshot:
            project.annotation_orders_by_uuid = copy.deepcopy(
                snapshot["annotation_orders_by_uuid"]
            )
        return None, arrows_changed

    image_name = snapshot["image_name"]
    current_annotations = coco.annotations_by_image.get(image_name, [])
    current_arrows = project.arrows_by_image.get(image_name, [])
    current_order_keys = [
        annotation.raw.get("annotation_uuid")
        for annotation in current_annotations
    ]
    current_order_keys.extend(arrow.arrow_uuid for arrow in current_arrows)

    for annotation_uuid in current_order_keys:
        project.annotation_orders_by_uuid.pop(annotation_uuid, None)

    coco_snapshot = snapshot["coco_snapshot"]
    coco.annotations_by_image[image_name] = copy.deepcopy(
        coco_snapshot["annotations_by_image"][image_name]
    )
    if image_name in coco_snapshot["image_records"]:
        coco.image_records[image_name] = copy.deepcopy(
            coco_snapshot["image_records"][image_name]
        )
    coco.categories = copy.deepcopy(coco_snapshot["categories"])

    restored_arrows = copy.deepcopy(snapshot["arrows_by_image"][image_name])
    if restored_arrows:
        project.arrows_by_image[image_name] = restored_arrows
    else:
        project.arrows_by_image.pop(image_name, None)
    project.annotation_orders_by_uuid.update(
        copy.deepcopy(snapshot["annotation_orders_by_uuid"])
    )

    arrows_changed = current_arrows != restored_arrows
    return image_name, arrows_changed
