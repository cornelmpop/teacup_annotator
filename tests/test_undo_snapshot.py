"""CODEX: Test image-owned and project-wide Undo snapshot scope."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from annotator.arrows import Arrow
from annotator.coco import CocoDocument
from annotator.gui.audit.undo import push_undo
from tests.support import StatefulHost


def test_local_push_undo_copies_only_its_image() -> None:
    """CODEX: Known-bug regression project_wide_undo_snapshot_stalls_image_local_edits_2026-09-01."""

    folder = Path("/images")
    image_paths = [folder / "a.jpg", folder / "b.jpg"]
    document = CocoDocument(folder, image_paths)
    annotation_a = document.add_annotation(
        "a.jpg",
        [(1, 1), (5, 1), (5, 5), (1, 5)],
    )
    annotation_a.raw["annotation_uuid"] = "ann:a"
    annotation_b = document.add_annotation(
        "b.jpg",
        [(10, 10), (15, 10), (15, 15), (10, 15)],
    )
    annotation_b.raw["annotation_uuid"] = "ann:b"
    arrow_a = Arrow("arr:a", 1.0, 2.0, 3.0, 4.0)
    arrow_b = Arrow("arr:b", 11.0, 12.0, 13.0, 14.0)
    host = StatefulHost()
    host.project.coco = document
    host.project.image_paths = image_paths
    host.project.current_index = 0
    host.project.arrows_by_image = {
        "a.jpg": [arrow_a],
        "b.jpg": [arrow_b],
    }
    host.project.annotation_orders_by_uuid = {
        "ann:a": 0,
        "arr:a": 1,
        "ann:b": 0,
        "arr:b": 1,
    }

    with mock.patch.object(
        document,
        "snapshot",
        wraps=document.snapshot,
    ) as complete_snapshot:
        push_undo(host, action="move_vertex", annotation_index=0)

    snapshot = host.project.undo_stack[0]
    complete_snapshot.assert_not_called()
    assert snapshot["image_name"] == "a.jpg"
    assert set(snapshot["coco_snapshot"]["annotations_by_image"]) == {"a.jpg"}
    assert set(snapshot["coco_snapshot"]["image_records"]) == {"a.jpg"}
    assert snapshot["arrows_by_image"] == {"a.jpg": [arrow_a]}
    assert snapshot["annotation_orders_by_uuid"] == {
        "ann:a": 0,
        "arr:a": 1,
    }


def test_all_images_push_undo_retains_complete_project_snapshot() -> None:
    """CODEX: Known-bug regression project_wide_undo_snapshot_stalls_image_local_edits_2026-09-01."""

    folder = Path("/images")
    image_paths = [folder / "a.jpg", folder / "b.jpg"]
    document = CocoDocument(folder, image_paths)
    host = StatefulHost()
    host.project.coco = document
    host.project.image_paths = image_paths
    host.project.arrows_by_image = {
        "a.jpg": [Arrow("arr:a", 1.0, 2.0, 3.0, 4.0)],
        "b.jpg": [Arrow("arr:b", 11.0, 12.0, 13.0, 14.0)],
    }
    host.project.annotation_orders_by_uuid = {"arr:a": 0, "arr:b": 0}

    with mock.patch.object(
        document,
        "snapshot",
        wraps=document.snapshot,
    ) as complete_snapshot:
        push_undo(host, action="run_model", all_images=True)

    snapshot = host.project.undo_stack[0]
    complete_snapshot.assert_called_once_with()
    assert set(snapshot["coco_snapshot"]["annotations_by_image"]) == {
        "a.jpg",
        "b.jpg",
    }
    assert set(snapshot["arrows_by_image"]) == {"a.jpg", "b.jpg"}
    assert snapshot["annotation_orders_by_uuid"] == {"arr:a": 0, "arr:b": 0}
