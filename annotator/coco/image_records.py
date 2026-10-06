"""Manage COCO image records and numeric IDs for region annotations.

`CocoDocument` keys image records by source-image basename. The functions here
preserve imported records and IDs, allocate IDs for newly loaded images and
region annotations, and adapt COCO `images` arrays to that basename-keyed state.

Arrow annotations use separate durable UUIDs and are outside this module.
Serialization and persistence live in their owning modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from annotator.coco.document import CocoDocument


def image_id_for(self: CocoDocument, image_name: str) -> int:
    """Return the COCO image ID stored under an exact image basename.

    First create records for any loaded images that lack them. The requested
    name must then exist in `image_records`; an unknown name raises `KeyError`,
    while an invalid stored ID raises its natural conversion error.
    """

    ensure_image_records(self)
    return int(self.image_records[image_name]["id"])


def next_annotation_id(self: CocoDocument) -> int:
    """Return one greater than the greatest in-memory region-annotation ID.

    Scan every image bucket and return 1 when no region annotations exist. Gaps
    are not reused, and existing IDs are not renumbered. Full combined
    serialization may later assign compact COCO IDs, so the component UUID—not
    this number—is the region annotation's durable identity.
    """

    # Allocate above the current maximum without rewriting IDs held by existing
    # in-memory region annotations.
    current_ids = [
        annotation.annotation_id
        for annotations in self.annotations_by_image.values()
        for annotation in annotations
    ]
    return max(current_ids, default=0) + 1


def ensure_image_records(self: CocoDocument) -> None:
    """Add a COCO image record for each loaded basename that lacks one.

    Existing records, IDs, and metadata remain untouched, including records not
    in `image_paths`. New IDs begin above the greatest positive stored ID and
    follow `image_paths` order; gaps are not reused. Each new record initially
    contains only `id` and the basename-valued `file_name`.

    This function does not validate, repair, or deduplicate imported records.
    """

    # Allocate above imported positive IDs so adding images never renumbers
    # existing COCO image references.
    used_ids = {
        int(record.get("id", 0))
        for record in self.image_records.values()
        if int(record.get("id", 0)) > 0
    }
    next_id = max(used_ids, default=0) + 1
    for image_path in self.image_paths:
        if image_path.name in self.image_records:
            continue
        self.image_records[image_path.name] = {
            "id": next_id,
            "file_name": image_path.name,
        }
        next_id += 1


def _image_records_by_name(
    self: CocoDocument,
    images_value: Any,
) -> dict[str, dict[str, Any]]:
    """Return shallow-copied COCO image records indexed by basename.

    A non-list value returns an empty mapping. Non-dictionary entries and
    records without `file_name` are ignored. Directory components are removed
    so imported relative or absolute names use the same basename namespace as
    loaded images.

    All other fields are preserved as supplied. If multiple records reduce to
    the same basename, the later record replaces the earlier one. This function
    does not filter records to currently loaded images or validate their IDs.
    """

    records: dict[str, dict[str, Any]] = {}
    if not isinstance(images_value, list):
        return records
    for image in images_value:
        if not isinstance(image, dict):
            continue
        file_name = str(image.get("file_name") or "")
        if not file_name:
            continue
        # Loaded project images share one basename namespace, regardless of
        # directory components retained in imported COCO `file_name` values.
        records[Path(file_name).name] = dict(image)
    return records
