"""Tests for structured project loading."""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from unittest import mock

from annotator.arrows import Arrow
from annotator.project.discovery import ProjectDiscovery
from annotator.project.loading import ProjectLoadPlan
from annotator.project.loading import load_project
from annotator.project.loading import prepare_project_load


class LoadProjectTests(unittest.TestCase):
    """Project loading returns complete values or closes its candidate database."""

    def test_preparation_resolves_metadata_and_migration_after_discovery(self) -> None:
        """The load plan records non-GUI facts needed by the progress boundary."""

        discovery = ProjectDiscovery(Path("/images"), [Path("/images/a.jpg")])
        with (
            mock.patch(
                "annotator.project.loading.read_project_metadata",
                return_value={"project_name": "Example"},
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.native_project_established",
                return_value=False,
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.json_sources_exist",
                return_value=True,
            ),
        ):
            plan = prepare_project_load(discovery, {"author_name": "A"})

        self.assertIs(plan.discovery, discovery)
        self.assertEqual(plan.project_metadata, {"project_name": "Example"})
        self.assertTrue(plan.migration_required)
        self.assertFalse(plan.native_project_established)

    def test_established_load_uses_sqlite_deletion_marks_not_legacy_file(self) -> None:
        """Known-bug regression deletion_marks_json_mutates_established_sqlite_state_2026-08-26."""

        folder = Path("/images")
        plan = ProjectLoadPlan(
            ProjectDiscovery(folder, [folder / "a.jpg"]),
            {"project_name": "Example"},
            False,
            True,
        )
        document = mock.Mock()
        connection = mock.Mock(spec=sqlite3.Connection)
        with (
            mock.patch(
                "annotator.project.loading.sql_backend.load_or_import_document",
                return_value=(document, connection),
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_arrows",
                return_value={
                    "a.jpg": [Arrow("arr:a", 1.0, 2.0, 3.0, 4.0)]
                },
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_annotation_orders",
                return_value={"arr:a": 1},
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_review_flags",
                return_value={"a.jpg"},
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_region_class_settings",
                return_value=(("flake",), ("#123456",)),
            ),
            mock.patch(
                "annotator.project.loading.load_deletion_marks",
                return_value={"old.jpg"},
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_pending_deletions",
                return_value={"db.jpg"},
            ),
            mock.patch("annotator.project.loading.save_deletion_marks") as save_marks,
            mock.patch("annotator.project.loading.project_file_path") as mark_path,
            mock.patch(
                "annotator.project.loading.read_audit_events",
                return_value=[{"action": "legacy"}],
            ) as read_audit,
            mock.patch(
                "annotator.project.loading.sql_backend.next_audit_event_id",
                return_value=7,
            ),
            mock.patch(
                "annotator.project.loading.sql_backend."
                "persist_image_deletion_state"
            ) as persist_deletion,
            mock.patch(
                "annotator.project.loading.sql_backend.import_audit_events_if_empty"
            ) as import_audit,
        ):
            mark_path.return_value.is_file.return_value = True
            result = load_project(plan, ("#123456",))

        self.assertIs(result.plan, plan)
        self.assertIs(result.document, document)
        self.assertIs(result.connection, connection)
        self.assertEqual(result.annotation_orders_by_uuid, {"arr:a": 1})
        self.assertEqual(result.review_flags, {"a.jpg"})
        self.assertEqual(result.deletion_marks, {"db.jpg"})
        self.assertEqual(result.class_names, ("flake",))
        self.assertEqual(result.class_colours, ("#123456",))
        self.assertEqual(result.next_audit_event_id, 7)
        persist_deletion.assert_not_called()
        save_marks.assert_called_once_with(folder, {"db.jpg"})
        read_audit.assert_not_called()
        import_audit.assert_not_called()

    def test_unestablished_load_imports_legacy_deletion_marks(self) -> None:
        """Known-bug regression deletion_marks_json_mutates_established_sqlite_state_2026-08-26."""

        folder = Path("/images")
        plan = ProjectLoadPlan(
            ProjectDiscovery(folder, [folder / "a.jpg"]),
            {"project_name": "Example"},
            True,
            False,
        )
        document = mock.Mock()
        connection = mock.Mock(spec=sqlite3.Connection)
        with (
            mock.patch(
                "annotator.project.loading.sql_backend.load_or_import_document",
                return_value=(document, connection),
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_arrows",
                return_value={},
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_annotation_orders",
                return_value={},
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_review_flags",
                return_value=set(),
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_region_class_settings",
                return_value=((), ()),
            ),
            mock.patch(
                "annotator.project.loading.load_deletion_marks",
                return_value={"old.jpg"},
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_pending_deletions",
                return_value={"old.jpg"},
            ),
            mock.patch(
                "annotator.project.loading.read_audit_events",
                return_value=[],
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.next_audit_event_id",
                return_value=1,
            ),
            mock.patch(
                "annotator.project.loading.sql_backend."
                "persist_image_deletion_state"
            ) as persist_deletion,
            mock.patch("annotator.project.loading.save_deletion_marks") as save_marks,
        ):
            result = load_project(plan, ())

        self.assertEqual(result.deletion_marks, {"old.jpg"})
        persist_deletion.assert_called_once_with(
            connection,
            {"old.jpg"},
            marked_for_deletion=True,
            moved_to_trash=False,
        )
        save_marks.assert_not_called()

    def test_load_removes_manually_restored_images_from_legacy_marks(self) -> None:
        """Known-bug regression restore_marked_image_button_clears_stale_deletion_2026-08-26 and deletion_marks_json_mutates_established_sqlite_state_2026-08-26."""

        folder = Path("/images")
        plan = ProjectLoadPlan(
            ProjectDiscovery(
                folder,
                [folder / "restored.jpg", folder / "pending.jpg"],
                restored_deletion_names=frozenset({"restored.jpg"}),
            ),
            {},
            False,
            True,
        )
        document = mock.Mock()
        connection = mock.Mock(spec=sqlite3.Connection)
        with (
            mock.patch(
                "annotator.project.loading.sql_backend.load_or_import_document",
                return_value=(document, connection),
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_arrows",
                return_value={},
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_annotation_orders",
                return_value={},
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_review_flags",
                return_value=set(),
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_region_class_settings",
                return_value=((), ()),
            ),
            mock.patch(
                "annotator.project.loading.load_deletion_marks",
                return_value={"pending.jpg", "restored.jpg"},
            ),
            mock.patch(
                "annotator.project.loading.save_deletion_marks"
            ) as save_marks,
            mock.patch(
                "annotator.project.loading.sql_backend.load_pending_deletions",
                return_value={"pending.jpg"},
            ),
            mock.patch("annotator.project.loading.project_file_path") as mark_path,
            mock.patch(
                "annotator.project.loading.read_audit_events",
                return_value=[],
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.next_audit_event_id",
                return_value=1,
            ),
            mock.patch(
                "annotator.project.loading.sql_backend."
                "persist_image_deletion_state"
            ) as persist_deletion,
        ):
            mark_path.return_value.is_file.return_value = True
            result = load_project(plan, ())

        save_marks.assert_called_once_with(folder, {"pending.jpg"})
        persist_deletion.assert_not_called()
        self.assertEqual(result.deletion_marks, {"pending.jpg"})

    def test_failure_after_database_open_closes_candidate(self) -> None:
        """A result that cannot be completed never leaks its open connection."""

        plan = ProjectLoadPlan(
            ProjectDiscovery(Path("/images"), [Path("/images/a.jpg")]),
            {},
            False,
            True,
        )
        connection = mock.Mock(spec=sqlite3.Connection)
        with (
            mock.patch(
                "annotator.project.loading.sql_backend.load_or_import_document",
                return_value=(mock.Mock(), connection),
            ),
            mock.patch(
                "annotator.project.loading.sql_backend.load_arrows",
                side_effect=sqlite3.OperationalError("failed"),
            ),
        ):
            with self.assertRaisesRegex(sqlite3.OperationalError, "failed"):
                load_project(plan, ())

        connection.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
