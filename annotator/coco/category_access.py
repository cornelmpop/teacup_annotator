"""Access the COCO class vocabulary for region annotations.

COCO categories classify polygon and rectangle region annotations. Arrow
annotations do not have categories and are outside this module.

The functions here read or extend `CocoDocument.categories` in memory. Callers
own persistence and GUI synchronization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from annotator.class_names import class_name_key

if TYPE_CHECKING:
    from annotator.coco.document import CocoDocument


def category_id_for_name(self: CocoDocument, class_name: str) -> int:
    """CODEX: Return the ID for a case-insensitive region-class name.

    Preserve the stored spelling when a case-only variant matches. If no
    category matches, append one whose ID is one greater than the greatest
    existing ID and whose supercategory is `object`. Existing category IDs are
    preserved. This function does not persist the mutation.
    """

    requested_identity = class_name_key(class_name)
    for category in self.categories:
        if class_name_key(category.get("name", "")) == requested_identity:
            return int(category.get("id", 1))
    # COCO IDs are stable and may be sparse, so extend the greatest existing ID
    # rather than using list length or renumbering categories.
    category_id = max(
        (int(category.get("id", 0)) for category in self.categories),
        default=0,
    ) + 1
    self.categories.append(
        {"id": category_id, "name": class_name, "supercategory": "object"}
    )
    return category_id


def category_name_for_id(self: CocoDocument, category_id: int) -> str:
    """Return the region-class name for a COCO category ID.

    Return `object` if no category has the ID or the matching category omits its
    name. The lookup does not mutate document categories.
    """

    for category in self.categories:
        if int(category.get("id", -1)) == category_id:
            return str(category.get("name", "object"))
    return "object"


def category_names(self: CocoDocument) -> tuple[str, ...]:
    """Return nonblank region-class names in document category order.

    The GUI uses this tuple as the document-side class order for display and
    shortcuts. Blank names are omitted; all other names retain their stored
    spelling and order.
    """

    return tuple(
        str(category.get("name", "object"))
        for category in self.categories
        if str(category.get("name", "")).strip()
    )
