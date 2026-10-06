"""CODEX: Reconcile active-document region rows with SQLite by durable UUID.

The active ``CocoDocument`` supplies the desired polygon and rectangle state
for its loaded images. Synchronization deletes only stored UUIDs absent from
that scope, inserts new UUIDs, updates changed rows, and preserves unchanged
row identity. Images outside the document, including images moved to trash,
are not modified.

Callers own transaction completion, audit records, and optional JSON output.
"""

from __future__ import annotations

import sqlite3

from annotator.coco import CocoDocument
from annotator.sqlite.annotations import _delete_unused_classes
from annotator.sqlite.connect import _ensure_session
from annotator.sqlite.json import _ensure_project_image_row
from annotator.sqlite.json import _json_dumps
from annotator.sqlite.json import _synchronize_region_annotations_for_image
from annotator.sqlite.json import _upsert_class_rows
from annotator.sqlite.queries import _set_coco_info_json
from annotator.sqlite.time import _unix_time


def _synchronize_document_regions(
    connection: sqlite3.Connection,
    document: CocoDocument,
    class_colours: tuple[str, ...] = (),
    annotation_orders_by_uuid: dict[str, int] | None = None,
) -> None:
    """CODEX: Synchronize active-image regions without replacing unchanged rows.

    Normalize the document's current geometry, synchronize its class vocabulary
    and COCO metadata, and reconcile every loaded image by annotation UUID.
    Existing image-local order values are preserved by UUID, while newly
    introduced UUIDs append after the image's current maximum stored order.

    Stored active-image region UUIDs absent from the document are deleted. New
    UUIDs are inserted, changed UUIDs are updated, and unchanged rows retain
    their database identity, creation metadata, and provenance. Region and
    arrow rows belonging to images outside ``document.image_paths`` remain
    untouched.

    This function neither commits nor writes JSON files.
    """

    document.ensure_image_records()
    document.normalize_single_polygons()
    _set_coco_info_json(connection, _json_dumps(document.info), _unix_time())
    session_id = _ensure_session(connection)
    class_id_by_category_id = _upsert_class_rows(
        connection,
        document.categories,
        class_colours,
    )
    for image_index, image_path in enumerate(document.image_paths):
        project_image = _ensure_project_image_row(
            connection,
            document,
            image_path,
            image_index,
        )
        _synchronize_region_annotations_for_image(
            connection,
            document,
            image_path.name,
            int(project_image["image_id"]),
            session_id,
            class_id_by_category_id,
            annotation_orders_by_uuid,
        )
    _delete_unused_classes(connection, document.categories)
