"""CODEX: Regress UUID-delta persistence for project-wide arrow mappings."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest import mock

from PIL import Image

import annotator.sqlite as sql_backend
import annotator.sqlite.connect as sqlite_connect
import annotator.sqlite.doc_updates as doc_updates
from annotator.arrows import Arrow
from annotator.coco import CocoDocument


def _arrow_rows(
    connection: sqlite3.Connection,
) -> dict[str, dict[str, object]]:
    """CODEX: Return complete live arrow rows keyed by durable UUID."""

    rows = connection.execute(
        """
        SELECT *
        FROM annotations
        WHERE annotation_type = 'keypoints' AND annotation_role = 'arrow'
        ORDER BY annotation_uuid
        """
    ).fetchall()
    return {row["annotation_uuid"]: dict(row) for row in rows}


def test_persist_arrows_updates_only_the_changed_uuid(tmp_path: Path) -> None:
    """CODEX: Regression arrow_persistence_churns_project_wide_rows_2026-08-31."""

    project = tmp_path / "project"
    project.mkdir()
    image_paths = [project / "a.jpg", project / "b.jpg"]
    for image_path in image_paths:
        Image.new("RGB", (20, 20), "white").save(image_path)
    document = CocoDocument(project, image_paths)
    arrows = {
        "a.jpg": [Arrow("arr:a", 1.0, 1.0, 8.0, 8.0)],
        "b.jpg": [Arrow("arr:b", 2.0, 2.0, 7.0, 7.0)],
    }

    connection = sql_backend.connect_database(project)
    try:
        sql_backend.persist_document(
            connection,
            document,
            write_json_backups=False,
        )
        with mock.patch.object(doc_updates, "_unix_time", return_value=100):
            sql_backend.persist_arrows(connection, arrows)
        original_rows = _arrow_rows(connection)
        original_sequence = connection.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'annotations'"
        ).fetchone()["seq"]

        changes_before_noop = connection.total_changes
        with mock.patch.object(doc_updates, "_unix_time", return_value=150):
            sql_backend.persist_arrows(connection, arrows)
        assert connection.total_changes == changes_before_noop
        assert _arrow_rows(connection) == original_rows
        assert connection.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'annotations'"
        ).fetchone()["seq"] == original_sequence

        edited_arrows = {
            "a.jpg": [Arrow("arr:a", 1.0, 1.0, 9.0, 9.0)],
            "b.jpg": arrows["b.jpg"],
        }
        later_session_id = "00000000-0000-4000-8000-000000000002"
        with (
            mock.patch.object(
                sqlite_connect,
                "APPLICATION_SESSION_ID",
                later_session_id,
            ),
            mock.patch.object(doc_updates, "_unix_time", return_value=200),
        ):
            sql_backend.persist_arrows(connection, edited_arrows)

        current_rows = _arrow_rows(connection)
        assert connection.execute(
            "SELECT session_id FROM sessions WHERE session_id = ?",
            (later_session_id,),
        ).fetchone() is not None
        assert current_rows["arr:b"] == original_rows["arr:b"]
        for field in (
            "annotation_id",
            "annotation_order",
            "session_id",
            "entry_time",
        ):
            assert current_rows["arr:a"][field] == original_rows["arr:a"][field]
        assert (
            current_rows["arr:a"]["geometry_json"]
            != original_rows["arr:a"]["geometry_json"]
        )
        assert (
            current_rows["arr:a"]["metadata_json"]
            != original_rows["arr:a"]["metadata_json"]
        )
        assert sql_backend.load_arrows(connection) == edited_arrows
    finally:
        connection.close()


def test_persist_arrows_deletes_and_inserts_only_the_uuid_delta(
    tmp_path: Path,
) -> None:
    """CODEX: Regression arrow_persistence_churns_project_wide_rows_2026-08-31."""

    project = tmp_path / "project"
    project.mkdir()
    image_path = project / "image.jpg"
    Image.new("RGB", (20, 20), "white").save(image_path)
    document = CocoDocument(project, [image_path])
    region = document.add_annotation(
        image_path.name,
        [(1, 1), (6, 1), (6, 6), (1, 6)],
    )
    region.raw["annotation_uuid"] = "ann:region"
    removed_arrow = Arrow("arr:remove", 2.0, 3.0, 15.0, 16.0)
    retained_arrow = Arrow("arr:retain", 3.0, 4.0, 16.0, 17.0)
    new_arrow = Arrow("arr:new", 4.0, 5.0, 17.0, 18.0)

    connection = sql_backend.connect_database(project)
    try:
        sql_backend.persist_image(
            connection,
            document,
            image_path.name,
            write_json_backup=False,
        )
        annotation_orders = sql_backend.load_annotation_orders(connection)
        sql_backend.persist_arrows(
            connection,
            {image_path.name: [removed_arrow, retained_arrow]},
            annotation_orders_by_uuid=annotation_orders,
        )
        original_region = dict(
            connection.execute(
                "SELECT * FROM annotations WHERE annotation_uuid = 'ann:region'"
            ).fetchone()
        )
        original_retained_arrow = _arrow_rows(connection)["arr:retain"]

        sql_backend.persist_arrows(
            connection,
            {image_path.name: [retained_arrow, new_arrow]},
            annotation_orders_by_uuid=annotation_orders,
        )

        current_region = dict(
            connection.execute(
                "SELECT * FROM annotations WHERE annotation_uuid = 'ann:region'"
            ).fetchone()
        )
        current_arrows = _arrow_rows(connection)
        ordered_rows = connection.execute(
            """
            SELECT annotation_uuid, annotation_order
            FROM annotations
            ORDER BY annotation_order
            """
        ).fetchall()
        assert current_region == original_region
        assert current_arrows["arr:retain"] == original_retained_arrow
        assert "arr:remove" not in current_arrows
        assert current_arrows["arr:new"]["annotation_id"] != (
            original_retained_arrow["annotation_id"]
        )
        assert [tuple(row) for row in ordered_rows] == [
            ("ann:region", 0),
            ("arr:retain", 2),
            ("arr:new", 3),
        ]
        assert annotation_orders == {
            "ann:region": 0,
            "arr:retain": 2,
            "arr:new": 3,
        }
        assert sql_backend.load_arrows(connection) == {
            image_path.name: [retained_arrow, new_arrow]
        }
    finally:
        connection.close()
