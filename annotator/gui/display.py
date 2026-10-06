"""Image-list filtering helpers for the GUI."""

from __future__ import annotations

from pathlib import Path

from annotator.coco import CocoDocument

# CMP: Filters for special conditions not matching specific classes.
FILTER_ALL = "all"
FILTER_NULL = "null"


def filtered_image_paths(
    image_paths: list[Path],
    coco: CocoDocument | None,
    selected_filter: str,
) -> list[Path]:
    """Return image paths matching an annotation class filter."""

    if selected_filter == FILTER_ALL or coco is None:
        return list(image_paths)
    if selected_filter == FILTER_NULL:
        return [
            image_path
            for image_path in image_paths
            if not coco.annotations_for(image_path.name)
        ]
    return [
        image_path
        for image_path in image_paths
        if image_has_annotation_class(coco, image_path.name, selected_filter)
    ]


def image_has_annotation_class(
    coco: CocoDocument,
    image_name: str,
    class_name: str,
) -> bool:
    """Return True when an image has at least one annotation of a class."""

    return any(
        coco.category_name_for_id(annotation.category_id) == class_name
        for annotation in coco.annotations_for(image_name)
    )
