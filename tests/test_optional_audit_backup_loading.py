"""Regression contract for optional audit backup handling during project load."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

import annotator.sqlite as sql_backend
from annotator.project.discovery import discover_project
from annotator.project.loading import load_project
from annotator.project.loading import prepare_project_load


class OptionalAuditBackupLoadingTests(unittest.TestCase):
    """Authoritative audit rows make an optional JSONL backup irrelevant."""

    def test_truncated_backup_does_not_block_authoritative_sql_audit(self) -> None:
        """BUG-2026-09-29-OPTIONAL-AUDIT-BACKUP: reopen from healthy SQL."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            Image.new("RGB", (20, 20), "white").save(folder / "image.jpg")

            first_plan = prepare_project_load(discover_project(folder), {})
            first_load = load_project(first_plan, ())
            try:
                sql_backend.append_audit_event(
                    first_load.connection,
                    {
                        "action": "view_image",
                        "event_time": 10_000,
                    },
                )
            finally:
                first_load.connection.close()

            backup_path = folder / "teacup" / "audit_events.jsonl"
            truncated_backup = '{"audit_event_id": 2'
            backup_path.write_text(truncated_backup, encoding="utf-8")

            second_plan = prepare_project_load(discover_project(folder), {})
            second_load = load_project(second_plan, ())
            try:
                audit_event_ids = [
                    event["audit_event_id"]
                    for event in sql_backend.read_audit_events(
                        second_load.connection
                    )
                ]
                self.assertEqual(audit_event_ids, [1])
                self.assertEqual(second_load.next_audit_event_id, 2)
                self.assertEqual(
                    backup_path.read_text(encoding="utf-8"),
                    truncated_backup,
                )
            finally:
                second_load.connection.close()


if __name__ == "__main__":
    unittest.main()
