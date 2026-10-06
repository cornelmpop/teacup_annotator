"""CODEX: Tests for the reserved SQLite arrow annotation class."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import annotator.sqlite as sql_backend
from annotator.arrows import ARROW_SPEC_CLASS_ID
from annotator.arrows import ARROW_SPEC_CLASS_NAME
from annotator.arrows import ARROW_SPEC_CLASS_ORDER
from annotator.arrows import ARROW_SPEC_COCO_CATEGORY_ID
from annotator.arrows import Arrow
from annotator.coco import CocoDocument
from annotator.resources import read_schema_sql


def _legacy_schema_connection() -> sqlite3.Connection:
    """CODEX: Return a pre-seed schema connection for migration tests."""

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(read_schema_sql())
    connection.execute(
        """
        INSERT INTO sessions(
            session_id, app_version, started_time, session_timezone,
            hostname, host_type, os
        )
        VALUES('session:test', '1.9.4', 1, 'UTC', 'host', 'test', 'test-os')
        """
    )
    return connection


class ArrowSpecClassTests(unittest.TestCase):
    """The hidden arrow class owns the reserved SQLite class/category slot."""

    def test_new_schema_seeds_arrow_class_before_visible_classes(self) -> None:
        """BUG-2026-08-26-CLASS-COCO-CATEGORY-COLLISION: visible rows start after the reserved arrow row."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (10, 10), "white").save(image_path)
            document = CocoDocument(folder, [image_path])
            document.categories = [
                {"id": 1, "name": "object", "supercategory": "object"}
            ]
            connection = sql_backend.connect_database(folder)
            try:
                sql_backend.replace_database_from_document(connection, document)
                rows = connection.execute(
                    """
                    SELECT class_id, class_name, class_list_order,
                           annotation_family, coco_category_id
                    FROM annotation_classes
                    ORDER BY class_id
                    """
                ).fetchall()
            finally:
                connection.close()

        self.assertEqual(
            [tuple(row) for row in rows],
            [
                (
                    ARROW_SPEC_CLASS_ID,
                    ARROW_SPEC_CLASS_NAME,
                    ARROW_SPEC_CLASS_ORDER,
                    "keypoints",
                    ARROW_SPEC_COCO_CATEGORY_ID,
                ),
                (1, "object", 1, "region", 1),
            ],
        )

    def test_legacy_arrow_class_migrates_to_reserved_row(self) -> None:
        """BUG-2026-08-26-CLASS-COCO-CATEGORY-COLLISION: legacy lazy arrow rows stop consuming visible IDs."""

        connection = _legacy_schema_connection()
        try:
            connection.execute(
                """
                INSERT INTO annotation_classes(
                    class_id, class_uuid, class_name, class_list_order,
                    annotation_family, class_source, supercategory, session_id,
                    entry_time, coco_category_id
                )
                VALUES(1, 'class:region', 'lithics', 0, 'region', 'import',
                       'object', 'session:test', 1, 2)
                """
            )
            connection.execute(
                """
                INSERT INTO annotation_classes(
                    class_id, class_uuid, class_name, class_list_order,
                    annotation_family, class_source, keypoint_labels_json,
                    session_id, entry_time, source_reference, coco_category_id
                )
                VALUES(2, 'class:legacy-arrow', 'arrow', 1, 'keypoints',
                       'teacup_internal', '["base","tip"]', 'session:test',
                       1, 'Teacup arrow annotations', 5)
                """
            )
            image_id = connection.execute(
                """
                INSERT INTO project_images(
                    image_name, image_path, image_md5sum, coco_image_id,
                    image_sequence_index
                )
                VALUES('image.jpg', '/project/image.jpg', 'md5', 1, 0)
                RETURNING image_id
                """
            ).fetchone()["image_id"]
            connection.execute(
                """
                INSERT INTO annotations(
                    annotation_uuid, image_id, class_id, session_id,
                    entry_time, annotation_type, annotation_role,
                    annotation_order, geometry_json, annotation_source
                )
                VALUES('arr:legacy', ?, 2, 'session:test', 1, 'keypoints',
                       'arrow', 0,
                       '{"labels":["base","tip"],"points":[[1,2],[3,4]]}',
                       'manual')
                """,
                (image_id,),
            )

            sql_backend.ensure_schema(connection)
            class_rows = connection.execute(
                """
                SELECT class_id, class_name, class_list_order,
                       annotation_family, coco_category_id
                FROM annotation_classes
                ORDER BY class_id
                """
            ).fetchall()
            arrow_class_id = connection.execute(
                """
                SELECT class_id
                FROM annotations
                WHERE annotation_uuid = 'arr:legacy'
                """
            ).fetchone()["class_id"]
        finally:
            connection.close()

        self.assertEqual(
            [tuple(row) for row in class_rows],
            [
                (
                    ARROW_SPEC_CLASS_ID,
                    ARROW_SPEC_CLASS_NAME,
                    ARROW_SPEC_CLASS_ORDER,
                    "keypoints",
                    ARROW_SPEC_COCO_CATEGORY_ID,
                ),
                (1, "lithics", 1, "region", 2),
            ],
        )
        self.assertEqual(arrow_class_id, ARROW_SPEC_CLASS_ID)

    def test_reserved_class_id_zero_rejects_visible_class_state(self) -> None:
        """BUG-2026-08-26-CLASS-COCO-CATEGORY-COLLISION: malformed reserved row use fails loudly."""

        connection = _legacy_schema_connection()
        try:
            connection.execute(
                """
                INSERT INTO annotation_classes(
                    class_id, class_uuid, class_name, class_list_order,
                    annotation_family, class_source, supercategory, session_id,
                    entry_time, coco_category_id
                )
                VALUES(0, 'class:bad', 'lithics', 0, 'region', 'import',
                       'object', 'session:test', 1, 7)
                """
            )

            with self.assertRaisesRegex(
                sqlite3.DatabaseError,
                "Reserved arrow annotation class row",
            ):
                sql_backend.ensure_schema(connection)
        finally:
            connection.close()

    def test_persist_arrows_uses_reserved_arrow_class(self) -> None:
        """BUG-2026-08-26-CLASS-COCO-CATEGORY-COLLISION: arrow persistence does not create an ad hoc class."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (10, 10), "white").save(image_path)
            document = CocoDocument(folder, [image_path])
            document.categories = [
                {"id": 1, "name": "object", "supercategory": "object"}
            ]
            connection = sql_backend.connect_database(folder)
            try:
                sql_backend.replace_database_from_document(connection, document)
                sql_backend.persist_arrows(
                    connection,
                    {image_path.name: [Arrow("arr:test", 1, 2, 3, 4)]},
                )
                class_rows = connection.execute(
                    """
                    SELECT class_id, class_name, annotation_family,
                           coco_category_id
                    FROM annotation_classes
                    ORDER BY class_id
                    """
                ).fetchall()
                arrow_row = connection.execute(
                    """
                    SELECT class_id
                    FROM annotations
                    WHERE annotation_uuid = 'arr:test'
                    """
                ).fetchone()
            finally:
                connection.close()

        self.assertEqual(arrow_row["class_id"], ARROW_SPEC_CLASS_ID)
        self.assertEqual(
            [tuple(row) for row in class_rows],
            [
                (
                    ARROW_SPEC_CLASS_ID,
                    ARROW_SPEC_CLASS_NAME,
                    "keypoints",
                    ARROW_SPEC_COCO_CATEGORY_ID,
                ),
                (1, "object", "region", 1),
            ],
        )


if __name__ == "__main__":
    unittest.main()
