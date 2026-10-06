"""CODEX: Prepare COCO categories and placeholder semantics at boundaries.

COCO categories classify polygon and rectangle region annotations; arrow
annotations have no categories. This module filters the outer payload value,
owns the persisted default-category contract used when a document has none,
and translates category IDs between external JSON and internal state.
"""

from __future__ import annotations

from typing import Any

from annotator.class_names import DEFAULT_CLASS_NAME
from annotator.class_names import LEGACY_DEFAULT_CLASS_NAME
from annotator.class_names import class_name_error
from annotator.coco.constants import COCO_JSON_CATEGORY_ID_OFFSET


def category_id_from_json(category_id: int, json_field: str) -> int:
    """CODEX: Return one external JSON category ID in the internal ID domain.

    Reject a negative external ID because adding the fixed offset could place it
    in Teacup's reserved internal range. ``json_field`` identifies the source
    field in the natural ``ValueError`` reported at the project-load boundary.
    """

    if category_id < 0:
        raise ValueError(
            f"COCO JSON {json_field} must be greater than or equal to zero: "
            f"{category_id}"
        )
    return category_id + COCO_JSON_CATEGORY_ID_OFFSET


def category_id_to_json(category_id: int) -> int:
    """CODEX: Return one internal category ID in the external JSON domain."""

    return category_id - COCO_JSON_CATEGORY_ID_OFFSET


def categories_from_json(value: Any) -> list[dict[str, Any]]:
    """CODEX: Return copied category rows with external IDs made internal.

    Preserve the established category-list filtering and malformed-ID behavior.
    This JSON boundary owns class-name validation and the reserved-ID invariant.
    """

    categories = valid_categories(value)
    class_names: list[str] = []
    for category in categories:
        class_name = category.get("name")
        if not isinstance(class_name, str):
            raise ValueError("COCO JSON category names must be text.")
        class_names.append(class_name)
    name_error = class_name_error(class_names)
    if name_error is not None:
        raise ValueError(name_error)
    for category in categories:
        if "id" not in category:
            continue
        try:
            # CODEX: External JSON is the normalization boundary for loose IDs.
            category_id = int(category["id"])
        except (TypeError, ValueError):
            continue
        category["id"] = category_id_from_json(category_id, "categories[].id")
    return categories


def annotation_category_ids_from_json(value: Any) -> Any:
    """CODEX: Copy JSON annotation rows and make category references internal.

    Preserve non-list values, non-dictionary rows, missing references, and
    references that cannot be converted to integers so the established
    annotation parser retains ownership of skipping malformed rows.
    """

    if not isinstance(value, list):
        return value
    annotations = []
    for annotation in value:
        if not isinstance(annotation, dict) or "category_id" not in annotation:
            annotations.append(annotation)
            continue
        copied_annotation = dict(annotation)
        try:
            # CODEX: External JSON is the normalization boundary for loose IDs.
            category_id = int(annotation["category_id"])
        except (TypeError, ValueError):
            annotations.append(copied_annotation)
            continue
        copied_annotation["category_id"] = category_id_from_json(
            category_id,
            "annotations[].category_id",
        )
        annotations.append(copied_annotation)
    return annotations


def categories_to_json(
    categories: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """CODEX: Copy internal category rows and expose their external JSON IDs."""

    output = [dict(category) for category in categories]
    for category in output:
        if "id" in category:
            category["id"] = category_id_to_json(category["id"])
    return output


def valid_categories(value: Any) -> list[dict[str, Any]]:
    """Return shallow copies of dictionary entries in a category list.

    A missing, empty, or non-list value returns an empty list. Non-dictionary
    list members are ignored. The empty result lets the caller either install
    the default category vocabulary or retain categories loaded from another
    COCO file.

    Fields such as `id`, `name`, and `supercategory` are trusted as supplied and
    are not normalized or validated here.
    """

    # Keep absence distinct from the default vocabulary: document construction
    # and per-image overlays make different fallback decisions.
    if isinstance(value, list) and value:
        return [dict(category) for category in value if isinstance(category, dict)]
    return []


def default_categories() -> list[dict[str, Any]]:
    """CODEX: Return a fresh persisted vocabulary for an empty document.

    The placeholder gives region annotations COCO category ID 1 and the name
    ``__DEFAULT__`` until callers extend or replace the vocabulary. Its COCO
    supercategory remains ``object`` because that field groups categories and
    is not the user-facing class name. Each call returns new mutable objects so
    ``CocoDocument`` instances do not share category state.
    """

    return [
        {
            "id": 1,
            "name": DEFAULT_CLASS_NAME,
            "supercategory": "object",
        }
    ]


def is_unused_default_category(
    category_names: tuple[str, ...],
    has_annotations: bool,
) -> bool:
    """CODEX: Return whether the category vocabulary is unused setup state.

    The current ``__DEFAULT__`` name and the pre-release ``object`` name are
    placeholders only when they are the sole category and no region annotation
    exists. Any referenced or non-sole category is user-owned project data.
    """

    has_one_category = len(category_names) == 1
    has_placeholder_name = has_one_category and category_names[0] in {
        DEFAULT_CLASS_NAME,
        LEGACY_DEFAULT_CLASS_NAME,
    }
    unused_placeholder = has_placeholder_name and not has_annotations
    return unused_placeholder
