"""Integration tests for UUID-delta autosave and human provenance."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import annotator.sqlite as sql_backend
from annotator.coco import CocoDocument
from annotator.gui.audit.state import current_image_audit_state
from annotator.gui.audit.undo import push_undo
from annotator.gui.audit.undo import undo
from annotator.gui.persistence import autosave_current_image
from annotator.overlays import mixed_annotation_overlay
from tests.support import StatefulHost


def annotation_rows(
    connection: sqlite3.Connection,
) -> dict[str, dict[str, object]]:
    """Return live annotation rows keyed by durable UUID."""

    rows = connection.execute(
        """
        SELECT annotation_uuid, annotation_id, annotation_order, session_id,
               entry_time, model_run_class_id, model_confidence,
               annotation_source, geometry_json, metadata_json
        FROM annotations
        WHERE annotation_role = ''
        ORDER BY annotation_order
        """
    ).fetchall()
    return {row["annotation_uuid"]: dict(row) for row in rows}


def visual_projection(
    document: CocoDocument,
    image_name: str,
) -> tuple[list[tuple[object, ...]], bytes]:
    """Return ordered outline inputs and deterministic additive fill pixels."""

    fills_by_category = {
        1: (220, 40, 40, 72),
        2: (40, 80, 220, 72),
    }
    annotations = document.annotations_for(image_name)
    outline_inputs = [
        (
            annotation.raw["annotation_uuid"],
            annotation.category_id,
            tuple(tuple(point) for point in annotation.polygons[0]),
        )
        for annotation in annotations
    ]
    polygon_fills = [
        (annotation.polygons[0], fills_by_category[annotation.category_id])
        for annotation in annotations
    ]
    overlay = mixed_annotation_overlay((40, 40), polygon_fills)
    if overlay is None:
        raise AssertionError("Five valid polygons must produce a visible overlay")
    return outline_inputs, overlay.tobytes()


class AutosaveAnnotationDeltaTests(unittest.TestCase):
    """Autosave writes the actual edit delta without changing visual output."""

    def test_two_of_five_changes_preserve_rows_render_audit_and_undo(self) -> None:
        """CODEX: Regression whole_image_autosave_churns_annotation_rows_2026-08-31.

        This also guards the human-source and exact-source Undo contract in
        model_rerun_destructively_replaces_prior_model_output_2026-08-31.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (40, 40), "white").save(image_path)
            document = CocoDocument(folder, [image_path])
            flake_category_id = document.category_id_for_name("flake")
            polygons = [
                [(1, 1), (12, 1), (12, 12), (1, 12)],
                [(8, 1), (19, 1), (19, 12), (8, 12)],
                [(21, 1), (32, 1), (32, 12), (21, 12)],
                [(1, 16), (12, 16), (12, 27), (1, 27)],
                [(8, 16), (19, 16), (19, 27), (8, 27)],
            ]
            category_ids = [1, flake_category_id, 1, flake_category_id, 1]
            annotations = []
            for index, (polygon, category_id) in enumerate(
                zip(polygons, category_ids)
            ):
                annotation = document.add_annotation(
                    image_path.name,
                    polygon,
                    category_id=category_id,
                )
                annotation.raw["annotation_uuid"] = f"ann:{index}"
                annotation.raw["entry_type"] = "automatic"
                annotation.score = 0.51 + index / 100
                annotations.append(annotation)

            connection = sql_backend.connect_database(folder)
            try:
                model_class_rows = sql_backend.record_model_run(
                    connection,
                    weights_path=folder / "model.pt",
                    model_md5sum="model-md5",
                    model_type="segmentation",
                    checkpoint_model_name="model",
                    checkpoint_resolution=40,
                    checkpoint_class_count=2,
                    confidence_threshold=0.5,
                    confidence_threshold_source="model_settings_file",
                    preprocessing={"target_size": [40, 40]},
                    class_names={4: "object", 9: "flake"},
                    project_category_ids={4: 1, 9: flake_category_id},
                    commit=False,
                )
                for annotation in annotations:
                    model_class_index = 4 if annotation.category_id == 1 else 9
                    annotation.raw["model_run_class_id"] = model_class_rows[
                        model_class_index
                    ]
                sql_backend.persist_document(
                    connection,
                    document,
                    write_json_backups=False,
                )
                original_rows = annotation_rows(connection)

                host = StatefulHost()
                host.project.folder = folder
                host.project.all_image_paths = [image_path]
                host.project.image_paths = [image_path]
                host.project.coco = document
                host.project.sql_connection = connection
                host.project.annotation_orders_by_uuid = (
                    sql_backend.load_annotation_orders(connection)
                )
                host.prefs = mock.Mock()
                host.prefs.values = {}
                host.prefs.get_bool.return_value = False
                host.prefs.get_class_colours.return_value = (
                    "#dc2828",
                    "#2850dc",
                )
                host.log = mock.Mock()
                host.annotation_overlay_key = None
                host.annotation_overlay_photo = None
                host.zoom_photo = None

                push_undo(
                    host,
                    action="move_vertex",
                    annotation_index=1,
                    details={"shared_annotation_indexes": [1, 3]},
                )
                annotations[1].polygons[0][0] = (7, 2)
                annotations[3].polygons[0][0] = (2, 15)

                self.assertTrue(autosave_current_image(host))
                expected_outlines, expected_pixels = visual_projection(
                    document,
                    image_path.name,
                )
                current_rows = annotation_rows(connection)
                reloaded = sql_backend.document_from_database(
                    connection,
                    folder,
                    [image_path],
                )
                actual_outlines, actual_pixels = visual_projection(
                    reloaded,
                    image_path.name,
                )

                self.assertEqual(actual_outlines, expected_outlines)
                self.assertEqual(actual_pixels, expected_pixels)
                for annotation_uuid in original_rows:
                    for field in (
                        "annotation_id",
                        "annotation_order",
                        "session_id",
                        "entry_time",
                        "model_run_class_id",
                        "model_confidence",
                    ):
                        self.assertEqual(
                            current_rows[annotation_uuid][field],
                            original_rows[annotation_uuid][field],
                        )
                self.assertEqual(
                    {
                        annotation_uuid: row["annotation_source"]
                        for annotation_uuid, row in current_rows.items()
                    },
                    {
                        "ann:0": "model",
                        "ann:1": "manual",
                        "ann:2": "model",
                        "ann:3": "manual",
                        "ann:4": "model",
                    },
                )

                audit_event_id = sql_backend.read_audit_events(connection)[0][
                    "audit_event_id"
                ]
                associations = connection.execute(
                    """
                    SELECT annotation_uuid, change_type, before_state_json,
                           after_state_json
                    FROM audit_event_annotations
                    WHERE audit_event_id = ?
                    ORDER BY annotation_uuid
                    """,
                    (audit_event_id,),
                ).fetchall()
                self.assertEqual(
                    [
                        (row["annotation_uuid"], row["change_type"])
                        for row in associations
                    ],
                    [("ann:1", "updated"), ("ann:3", "updated")],
                )
                self.assertEqual(
                    [
                        json.loads(row["before_state_json"])["entry_type"]
                        for row in associations
                    ],
                    ["automatic", "automatic"],
                )
                self.assertEqual(
                    [
                        json.loads(row["after_state_json"])["entry_type"]
                        for row in associations
                    ],
                    ["manual", "manual"],
                )

                with mock.patch("annotator.gui.audit.undo.redraw_canvas"):
                    undo(host)

                restored_rows = annotation_rows(connection)
                self.assertEqual(
                    {
                        annotation_uuid: row["annotation_source"]
                        for annotation_uuid, row in restored_rows.items()
                    },
                    {f"ann:{index}": "model" for index in range(5)},
                )
                self.assertEqual(
                    visual_projection(host.project.coco, image_path.name),
                    visual_projection(
                        sql_backend.document_from_database(
                            connection,
                            folder,
                            [image_path],
                        ),
                        image_path.name,
                    ),
                )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
