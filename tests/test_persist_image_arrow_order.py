"""CODEX: Regress image-region replacement beside shared-table arrows."""

from __future__ import annotations

import copy
from pathlib import Path

from PIL import Image

import annotator.sqlite as sql_backend
from annotator.arrows import Arrow
from annotator.coco import CocoDocument


def test_persist_image_deletes_region_without_reordering_arrow(
    tmp_path: Path,
) -> None:
    """Known-bug regression mixed_selection_region_delete_reorders_arrows_2026-08-26."""

    project = tmp_path / "project"
    project.mkdir()
    image_path = project / "image.jpg"
    Image.new("RGB", (20, 20), "white").save(image_path)
    document = CocoDocument(project, [image_path])
    first = document.add_annotation(
        image_path.name,
        [(1, 1), (5, 1), (5, 5), (1, 5)],
    )
    first.raw["annotation_uuid"] = "ann:first"
    second = document.add_annotation(
        image_path.name,
        [(10, 10), (15, 10), (15, 15), (10, 15)],
    )
    second.raw["annotation_uuid"] = "ann:second"
    arrow = Arrow("arr:one", 2.0, 3.0, 16.0, 17.0)

    connection = sql_backend.connect_database(project)
    try:
        sql_backend.persist_image(
            connection,
            document,
            image_path.name,
            write_json_backup=False,
        )
        sql_backend.persist_arrows(
            connection,
            {image_path.name: [arrow]},
        )

        document.delete_annotation(image_path.name, 1)
        sql_backend.persist_image(
            connection,
            document,
            image_path.name,
            write_json_backup=False,
        )

        rows = connection.execute(
            """
            SELECT annotation_uuid, annotation_role, annotation_order
            FROM annotations
            ORDER BY annotation_order
            """
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("ann:first", "", 0),
            ("arr:one", "arrow", 2),
        ]
        assert sql_backend.load_arrows(connection) == {image_path.name: [arrow]}
    finally:
        connection.close()


def test_persist_image_undo_restores_deleted_regions_to_original_orders(
    tmp_path: Path,
) -> None:
    """Known-bug regression mixed_selection_region_delete_reorders_arrows_2026-08-26."""

    project = tmp_path / "project"
    project.mkdir()
    image_path = project / "image.jpg"
    Image.new("RGB", (20, 20), "white").save(image_path)
    document = CocoDocument(project, [image_path])
    first = document.add_annotation(
        image_path.name,
        [(1, 1), (5, 1), (5, 5), (1, 5)],
    )
    first.raw["annotation_uuid"] = "ann:first"
    second = document.add_annotation(
        image_path.name,
        [(10, 10), (15, 10), (15, 15), (10, 15)],
    )
    second.raw["annotation_uuid"] = "ann:second"
    arrow = Arrow("arr:one", 2.0, 3.0, 16.0, 17.0)

    connection = sql_backend.connect_database(project)
    try:
        sql_backend.persist_image(
            connection,
            document,
            image_path.name,
            write_json_backup=False,
        )
        sql_backend.persist_arrows(
            connection,
            {image_path.name: [arrow]},
        )
        order_snapshot = sql_backend.load_annotation_orders(connection)
        document_snapshot = document.snapshot()

        document.delete_annotation(image_path.name, 1)
        document.delete_annotation(image_path.name, 0)
        current_orders = copy.deepcopy(order_snapshot)
        sql_backend.persist_image(
            connection,
            document,
            image_path.name,
            write_json_backup=False,
            annotation_orders_by_uuid=current_orders,
        )

        rows_after_delete = connection.execute(
            """
            SELECT annotation_uuid, annotation_role, annotation_order
            FROM annotations
            ORDER BY annotation_order
            """
        ).fetchall()
        assert [tuple(row) for row in rows_after_delete] == [
            ("arr:one", "arrow", 2),
        ]
        assert current_orders == {"arr:one": 2}

        document.restore(document_snapshot)
        restored_orders = copy.deepcopy(order_snapshot)
        sql_backend.persist_image(
            connection,
            document,
            image_path.name,
            write_json_backup=False,
            annotation_orders_by_uuid=restored_orders,
        )

        rows_after_undo = connection.execute(
            """
            SELECT annotation_uuid, annotation_role, annotation_order
            FROM annotations
            ORDER BY annotation_order
            """
        ).fetchall()
        assert [tuple(row) for row in rows_after_undo] == [
            ("ann:first", "", 0),
            ("ann:second", "", 1),
            ("arr:one", "arrow", 2),
        ]
        assert restored_orders == {
            "ann:first": 0,
            "ann:second": 1,
            "arr:one": 2,
        }
    finally:
        connection.close()
