"""CODEX: Build JSON-friendly annotation and document audit state."""

from __future__ import annotations

from typing import Any
from typing import Protocol

from annotator.arrows import Arrow
from annotator.gui.selection import current_annotations
from annotator.gui.state import ProjectState
from annotator.log.audit import annotation_audit_state
from annotator.log.audit import arrow_audit_state


class AuditStateHost(Protocol):
    """CODEX: Project state required to describe the current audit scope."""

    project: ProjectState

# CMP: TODO - clarify why a valid annotation with no UUID produces "" instead of
# a None or an error (given the docstring).

def annotation_uuid_at(
    host: AuditStateHost,
    annotation_index: int | None,
) -> str | None:
    """CODEX: Return the durable UUID for an annotation index."""

    if annotation_index is None:
        return None
    annotations = current_annotations(host.project)

    # CMP: TODO - What valid application state would lead to this condition?
    if not (0 <= annotation_index < len(annotations)):
        return None
    return str(annotations[annotation_index].raw.get("annotation_uuid", ""))

# CMP: TODO - Clarify docstring - what a snapshot is.

def image_audit_state_from_snapshot(
    host: AuditStateHost,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """CODEX: Return the owning image's annotation state from a snapshot."""

    image_name = snapshot.get("image_name")
    if image_name is None:
        if not host.project.image_paths:
            return {}
        from annotator.gui.project.navigation import current_image_name

        image_name = current_image_name(host)
    if not image_name:
        return {}

    coco_snapshot = snapshot.get("coco_snapshot", snapshot)
    annotations = coco_snapshot["annotations_by_image"].get(image_name, [])
    categories = coco_snapshot.get("categories", [])
    arrows_by_image = snapshot.get("arrows_by_image", host.project.arrows_by_image)
    return image_audit_state_from_annotations(
        image_name,
        annotations,
        categories,
        arrows_by_image.get(image_name, []),
    )

# CMP: TODO - the name of this function is very close to the one above.
# clarify relationship.

def audit_state_from_snapshot(
    host: AuditStateHost,
    snapshot: dict[str, Any],
    all_images: bool,
) -> dict[str, Any]:
    """CODEX: Return the affected audit scope from an undo snapshot."""

    if not all_images:
        return image_audit_state_from_snapshot(host, snapshot)
    coco_snapshot = snapshot.get("coco_snapshot", snapshot)
    return document_audit_state_from_annotations(
        coco_snapshot["annotations_by_image"],
        coco_snapshot.get("categories", []),
        snapshot.get("arrows_by_image", host.project.arrows_by_image),
    )


def image_audit_state(
    host: AuditStateHost,
    image_name: str,
) -> dict[str, Any]:
    """CODEX: Return JSON-friendly annotation state for the named image."""

    if host.project.coco is None:
        return {}
    return image_audit_state_from_annotations(
        image_name,
        host.project.coco.annotations_by_image.get(image_name, []),
        host.project.coco.categories,
        host.project.arrows_by_image.get(image_name, []),
    )


def current_image_audit_state(host: AuditStateHost) -> dict[str, Any]:
    """CODEX: Return JSON-friendly current-image annotation state."""

    if host.project.coco is None or not host.project.image_paths:
        return {}

    # CMP: Why are we doing the import here?
    from annotator.gui.project.navigation import current_image_name

    return image_audit_state(host, current_image_name(host))


def current_audit_state(
    host: AuditStateHost,
    all_images: bool,
    image_name: str | None = None,
) -> dict[str, Any]:
    """CODEX: Return current annotation state for one named image or the folder."""

    if not all_images:
        if image_name is not None:
            return image_audit_state(host, image_name)
        return current_image_audit_state(host)
    if host.project.coco is None:
        return {}
    return document_audit_state_from_annotations(
        host.project.coco.annotations_by_image,
        host.project.coco.categories,
        host.project.arrows_by_image,
    )


def document_audit_state_from_annotations(
    annotations_by_image: dict[str, list[Any]],
    categories: list[dict[str, Any]],
    arrows_by_image: dict[str, list[Arrow]],
) -> dict[str, Any]:
    """CODEX: Return JSON-friendly audit state for every folder image."""

    image_names = sorted(annotations_by_image.keys() | arrows_by_image.keys())
    return {
        "source_table": "annotations",
        "images": [
            image_audit_state_from_annotations(
                image_name,
                annotations_by_image.get(image_name, []),
                categories,
                arrows_by_image.get(image_name, []),
            )
            for image_name in image_names
        ],
    }


def image_audit_state_from_annotations(
    image_name: str,
    annotations: list[Any],
    categories: list[dict[str, Any]],
    arrows: list[Arrow] | None = None,
) -> dict[str, Any]:
    """CODEX: Return an audit state compatible with native annotation rows."""

    return {
        "image_name": image_name,
        "source_table": "annotations",
        "annotations": [
            annotation_audit_state(annotation, index, categories)
            for index, annotation in enumerate(annotations)
        ],
        "arrows": [
            arrow_audit_state(arrow, index) for index, arrow in enumerate(arrows or [])
        ],
    }
