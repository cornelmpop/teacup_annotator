"""CODEX: Seed app-owned internal annotation classes in SQLite.

The packaged schema defines the class table shape, while this module owns
application-reserved class rows whose data values are part of the current
runtime contract. User-visible region class synchronization remains in
``annotator.sqlite.json.classes``.

The current internal class is the hidden arrow class. Existing databases may
contain the older lazy ``arrow`` keypoint class; this module promotes arrow
annotation rows to the reserved class and removes the unreferenced legacy row.
Malformed uses of the reserved id or category fail rather than being repaired.
"""

from __future__ import annotations

import json
import sqlite3
import uuid

from annotator.arrows import ARROW_SPEC_CLASS_ID
from annotator.arrows import ARROW_SPEC_CLASS_NAME
from annotator.arrows import ARROW_SPEC_CLASS_ORDER
from annotator.arrows import ARROW_SPEC_COCO_CATEGORY_ID
from annotator.sqlite.time import _unix_time

CLASS_ORDER_SEED_OFFSET = 1_000_000
ARROW_SPEC_KEYPOINT_LABELS = ["base", "tip"]
ARROW_SPEC_KEYPOINT_LABELS_JSON = json.dumps(
    ARROW_SPEC_KEYPOINT_LABELS,
    separators=(",", ":"),
)


def seed_internal_annotation_classes(connection: sqlite3.Connection) -> None:
    """CODEX: Ensure arrows own the reserved hidden annotation-class row.

    The app-level contract reserves class id, visible order, and COCO category
    id ``0`` for SQLite arrow rows. Existing databases created before that
    contract may contain a lazy ``arrow`` keypoint class; this seed promotes
    arrow annotation rows to the reserved class and deletes the unreferenced
    legacy row. Malformed uses of the reserved row or category id fail through
    SQLite constraints or the explicit row check below.
    """

    row = connection.execute(
        """
        SELECT class_name, class_list_order, annotation_family, class_source,
               keypoint_labels_json, coco_category_id
        FROM annotation_classes
        WHERE class_id = ?
        """,
        (ARROW_SPEC_CLASS_ID,),
    ).fetchone()
    if row is not None:
        _validate_arrow_spec_class_row(row)
        _migrate_legacy_arrow_class(connection)
        return

    _shift_class_orders_for_arrow_spec(connection)
    _insert_arrow_spec_class(connection)
    _migrate_legacy_arrow_class(connection)


def _validate_arrow_spec_class_row(row: sqlite3.Row | tuple[object, ...]) -> None:
    """CODEX: Raise when the reserved class id stores non-arrow semantics."""

    expected_values = (
        ARROW_SPEC_CLASS_NAME,
        ARROW_SPEC_CLASS_ORDER,
        "keypoints",
        "teacup_internal",
        ARROW_SPEC_KEYPOINT_LABELS_JSON,
        ARROW_SPEC_COCO_CATEGORY_ID,
    )
    if tuple(row) == expected_values:
        return
    raise sqlite3.DatabaseError(
        "Reserved arrow annotation class row class_id=0 does not match "
        "the required __ARROW_SPEC_CLASS__ contract"
    )


def _shift_class_orders_for_arrow_spec(connection: sqlite3.Connection) -> None:
    """CODEX: Move existing class orders up so reserved order zero is free."""

    connection.execute(
        """
        UPDATE annotation_classes
        SET class_list_order = class_list_order + ?
        WHERE class_list_order >= ?
        """,
        (CLASS_ORDER_SEED_OFFSET, ARROW_SPEC_CLASS_ORDER),
    )
    connection.execute(
        """
        UPDATE annotation_classes
        SET class_list_order = class_list_order - ?
        WHERE class_list_order >= ?
        """,
        (
            CLASS_ORDER_SEED_OFFSET - 1,
            CLASS_ORDER_SEED_OFFSET + ARROW_SPEC_CLASS_ORDER,
        ),
    )


def _insert_arrow_spec_class(connection: sqlite3.Connection) -> None:
    """CODEX: Insert the fixed hidden class row for arrow annotation rows."""

    from annotator.sqlite.connect import _ensure_session

    session_id = _ensure_session(connection)
    now = _unix_time()
    connection.execute(
        """
        INSERT INTO annotation_classes(
            class_id, class_uuid, class_name, class_list_order,
            annotation_family, class_source, keypoint_labels_json, session_id,
            entry_time, source_reference, coco_category_id
        )
        VALUES(?, ?, ?, ?, 'keypoints', 'teacup_internal', ?, ?, ?, ?, ?)
        """,
        (
            ARROW_SPEC_CLASS_ID,
            f"class:{uuid.uuid4()}",
            ARROW_SPEC_CLASS_NAME,
            ARROW_SPEC_CLASS_ORDER,
            ARROW_SPEC_KEYPOINT_LABELS_JSON,
            session_id,
            now,
            "Teacup arrow annotations",
            ARROW_SPEC_COCO_CATEGORY_ID,
        ),
    )


def _migrate_legacy_arrow_class(connection: sqlite3.Connection) -> None:
    """CODEX: Point legacy arrow rows at the reserved class and drop old class."""

    connection.execute(
        """
        UPDATE annotations
        SET class_id = ?
        WHERE annotation_type = 'keypoints'
          AND annotation_role = 'arrow'
          AND class_id <> ?
        """,
        (ARROW_SPEC_CLASS_ID, ARROW_SPEC_CLASS_ID),
    )
    connection.execute(
        """
        DELETE FROM annotation_classes
        WHERE class_name = 'arrow'
          AND annotation_family = 'keypoints'
          AND class_id <> ?
          AND class_id NOT IN (
              SELECT class_id FROM annotations WHERE class_id IS NOT NULL
          )
        """,
        (ARROW_SPEC_CLASS_ID,),
    )
