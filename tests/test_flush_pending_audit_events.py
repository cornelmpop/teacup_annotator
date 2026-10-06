"""CODEX: Test committed audit-event linkage to staged Undo entries."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from PIL import Image

import annotator.sqlite as sql_backend
from annotator.coco import CocoDocument
from annotator.gui.audit.events import flush_pending_audit_events
from annotator.gui.audit.undo import push_undo
from tests.support import StatefulHost


def test_committed_edit_id_is_bound_to_its_undo_entry(tmp_path: Path) -> None:
    """CODEX: Known-bug regression project_wide_undo_snapshot_stalls_image_local_edits_2026-09-01."""

    image_path = tmp_path / "a.jpg"
    Image.new("RGB", (20, 20), "white").save(image_path)
    document = CocoDocument(tmp_path, [image_path])
    annotation = document.add_annotation(
        image_path.name,
        [(1, 1), (5, 1), (5, 5), (1, 5)],
    )
    annotation.raw["annotation_uuid"] = "ann:a"
    connection = sql_backend.connect_database(tmp_path)
    try:
        sql_backend.persist_image(
            connection,
            document,
            image_path.name,
            write_json_backup=False,
        )
        host = StatefulHost()
        host.project.folder = tmp_path
        host.project.all_image_paths = [image_path]
        host.project.image_paths = [image_path]
        host.project.coco = document
        host.project.sql_connection = connection
        host.prefs = mock.Mock()
        host.prefs.get_bool.return_value = False
        host.log = mock.Mock()

        push_undo(host, action="move_vertex", annotation_index=0)
        with mock.patch("annotator.gui.project.status.update_edit_summary"):
            flush_pending_audit_events(host)

        committed_event = sql_backend.read_audit_events(connection)[0]
        assert host.project.undo_stack[0]["audit_event_id"] == committed_event[
            "audit_event_id"
        ]
    finally:
        connection.close()
