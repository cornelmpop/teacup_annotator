"""Tests for all-or-empty folder replacement."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from PIL import Image

from annotator.arrows import Arrow
from annotator.gui.application import close_sql_connection
from annotator.gui.display import FILTER_ALL
from annotator.gui.display import FILTER_NULL
from annotator.gui.local_class_actions import maybe_use_local_class_settings
from annotator.gui.project.folder_loading import load_folder
from tests.support import StatefulHost


def configured_folder_controller(old_folder: Path) -> StatefulHost:
    """Return a host with the state and UI hooks used by folder loading."""

    controller = StatefulHost()
    controller.root = mock.Mock()
    controller.prefs = mock.Mock()
    controller.prefs.values = {"image_folder": str(old_folder)}
    controller.prefs.get_class_colours.return_value = ("#123456",)

    def set_path(key: str, path: Path) -> None:
        controller.prefs.values[key] = str(path)

    controller.prefs.set_path.side_effect = set_path
    controller.project.project_metadata = {"project_name": "old"}
    controller.configuration_window = None
    controller.project.folder = old_folder
    controller.project.all_image_paths = [old_folder / "old.jpg"]
    controller.project.image_paths = list(controller.project.all_image_paths)
    controller.project.current_index = 0
    controller.project.coco = mock.Mock()
    controller.project.sql_connection = mock.Mock()
    controller.project.session_model_values = {"model_weights": "old.pt"}
    controller.project.session_class_names = ("old",)
    controller.project.session_class_colours = ("#abcdef",)
    controller.session_default_class_var = mock.Mock()
    controller.project.using_folder_model_conf = True
    controller.project.using_local_class_settings = True
    controller.view.current_image = mock.Mock()
    controller.photo_image = mock.Mock()
    controller.view.zoom = 2.0
    controller.view.display_size = (100, 100)
    controller.view.image_origin = (10.0, 10.0)
    controller.view.annotation_revision = 4
    controller.view.cursor_canvas_point = (20.0, 20.0)
    controller.project.undo_stack = [{"old": "undo"}]
    controller.project.pending_audit_events = [{"old": "audit"}]
    controller.project.next_audit_event_id = 8
    controller.project.last_audit_event_id = 7
    controller.interaction.temp_edge_insertions = [{"old": "edge"}]
    controller.interaction.drag_vertex_ref = (0, 0)
    controller.interaction.drag_vertex_original_point = (1.0, 1.0)
    controller.interaction.drag_shared_vertex_refs = [(0, 0, 0)]
    controller.interaction.drag_rectangle_context = {"old": "rectangle"}
    controller.interaction.drag_arrow_endpoint_index = 0
    controller.interaction.panning = True
    controller.project.arrows_by_image = {
        "old.jpg": [Arrow("arr:old", 1.0, 2.0, 3.0, 4.0)]
    }
    controller.project.deletion_marks = {"old.jpg"}
    controller.project.session_deletion_marks = {"old.jpg"}
    controller.project.review_flags = {"old.jpg"}
    controller.project.review_only = True
    controller.project.active_filter = "old"
    controller.project.filter_options = ("old",)
    controller.filter_var = mock.Mock()
    controller.project.dirty = True
    controller.view.annotation_overlap_key = ("old", "old.jpg", 4)
    controller.view.annotation_overlap_geometry = ([(1.0, 2.0)], [(3.0, 4.0)])

    def close_sql_connection() -> None:
        controller.project.sql_connection = None

    controller.close_sql_connection = mock.Mock(side_effect=close_sql_connection)
    controller.set_canvas_cursor = mock.Mock()
    controller.clear_view_interaction_state = mock.Mock()
    controller.load_current_image = mock.Mock()
    controller._update_buttons = mock.Mock()
    controller.import_legacy_audit_backup = mock.Mock()
    controller.refresh_filter_options = mock.Mock()
    controller.apply_image_filter = mock.Mock()
    controller.remembered_image_name_for_folder = mock.Mock(return_value=None)
    controller.remembered_image_index_for_folder = mock.Mock(return_value=0)
    controller.log = mock.Mock()
    return controller


@contextmanager
def quiet_folder_gui_effects():
    """Patch GUI refresh effects while preserving folder state transitions."""

    with (
        mock.patch("annotator.gui.project.folder_state.load_current_image"),
        mock.patch("annotator.gui.project.folder_state.update_buttons"),
        mock.patch("annotator.gui.project.folder_state.refresh_class_panel"),
        mock.patch("annotator.gui.project.folder_state.refresh_filter_options"),
        mock.patch("annotator.gui.project.folder_state.apply_image_filter"),
        mock.patch(
            "annotator.gui.project.folder_state.remembered_image_name_for_folder",
            return_value=None,
        ),
        mock.patch(
            "annotator.gui.project.folder_state.remembered_image_index_for_folder",
            return_value=0,
        ),
    ):
        yield


@contextmanager
def successful_backend(
    document: mock.Mock,
    connection: mock.Mock,
    *,
    native_project_established: bool = False,
    json_sources_exist: bool = False,
    annotation_orders_by_uuid: dict[str, int] | None = None,
):
    """Patch folder persistence dependencies for a successful database open."""

    with (
        mock.patch(
            "annotator.project.loading.read_project_metadata",
            return_value={"project_name": "new"},
        ),
        mock.patch(
            "annotator.project.loading.sql_backend.native_project_established",
            return_value=native_project_established,
        ),
        mock.patch(
            "annotator.project.loading.sql_backend.json_sources_exist",
            return_value=json_sources_exist,
        ),
        mock.patch(
            "annotator.project.loading.sql_backend.load_or_import_document",
            return_value=(document, connection),
        ),
        mock.patch(
            "annotator.project.loading.sql_backend.load_review_flags",
            return_value={"image.jpg"},
        ),
        mock.patch(
            "annotator.project.loading.sql_backend.load_region_class_settings",
            return_value=(("animal",), ("#123456",)),
        ),
        mock.patch(
            "annotator.project.loading.sql_backend.load_annotation_orders",
            return_value=annotation_orders_by_uuid or {},
        ),
        mock.patch(
            "annotator.project.loading.load_deletion_marks",
            return_value=set(),
        ),
        mock.patch(
            "annotator.project.loading.sql_backend.load_pending_deletions",
            return_value={"deleted.jpg"},
        ),
        mock.patch(
            "annotator.project.loading.sql_backend.next_audit_event_id",
            return_value=4,
        ),
        mock.patch(
            "annotator.gui.project.folder_state.sql_backend.persist_classes"
        ) as persist_classes,
    ):
        yield persist_classes


def loaded_document() -> mock.Mock:
    """Return a minimal loaded COCO document for controller tests."""

    document = mock.Mock()
    document.categories = [{"id": 1, "name": "animal"}]
    document.category_names.return_value = ("animal",)
    document.annotations_by_image = {"image.jpg": []}
    return document


class FolderLoadStateTransitionTests(unittest.TestCase):
    """Folder selection either installs the complete project or no project."""

    def test_successful_load_publishes_new_folder_after_initialization(self) -> None:
        """A complete candidate becomes the project and remembered folder."""

        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            old_folder = parent / "old"
            old_folder.mkdir()
            new_folder = parent / "new"
            new_folder.mkdir()
            Image.new("RGB", (10, 10), "white").save(new_folder / "image.jpg")
            controller = configured_folder_controller(old_folder)
            document = loaded_document()
            connection = mock.Mock(spec=sqlite3.Connection)

            with (
                successful_backend(document, connection) as persist_classes,
                mock.patch(
                    "annotator.project.loading."
                    "sql_backend.load_arrows",
                    return_value={
                        "image.jpg": [Arrow("arr:new", 1.0, 2.0, 3.0, 4.0)]
                    },
                ),
                mock.patch(
                    "annotator.gui.project.folder_loading.ErrorDetailsDialog"
                ) as error_dialog,
                mock.patch(
                    "annotator.gui.project.folder_state.maybe_use_folder_model_conf"
                ),
                mock.patch(
                    "annotator.gui.project.folder_state.active_class_names",
                    return_value=("animal",),
                ),
                mock.patch(
                    "annotator.gui.project.folder_state.active_class_colours",
                    return_value=("#123456",),
                ),
                quiet_folder_gui_effects(),
            ):
                load_folder(controller, new_folder)

        controller.close_sql_connection.assert_called_once_with()
        self.assertIs(controller.project.sql_connection, connection)
        self.assertEqual(controller.project.folder, new_folder)
        self.assertIs(controller.project.coco, document)
        self.assertEqual(controller.prefs.values["image_folder"], str(new_folder))
        controller.prefs.set_path.assert_called_once_with("image_folder", new_folder)
        controller.prefs.save.assert_not_called()
        self.assertEqual(controller.project.next_audit_event_id, 4)
        self.assertEqual(controller.project.last_audit_event_id, 3)
        self.assertEqual(controller.project.annotation_orders_by_uuid, {})
        persist_classes.assert_called_once_with(
            connection,
            document.categories,
            ("#123456",),
        )
        error_dialog.assert_not_called()

    def test_established_project_ignores_class_backup_during_open(self) -> None:
        """SQLite classes load without a classes.json prompt or startup rewrite."""

        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            old_folder = parent / "old"
            old_folder.mkdir()
            new_folder = parent / "new"
            new_folder.mkdir()
            Image.new("RGB", (10, 10), "white").save(new_folder / "image.jpg")
            project_folder = new_folder / "teacup"
            project_folder.mkdir()
            (project_folder / "classes.json").write_text(
                '{"classes": [{"name": "stale", "colour": "#ffffff"}]}',
                encoding="utf-8",
            )
            controller = configured_folder_controller(old_folder)
            document = loaded_document()
            connection = mock.Mock(spec=sqlite3.Connection)

            with (
                successful_backend(
                    document,
                    connection,
                    native_project_established=True,
                ) as persist_classes,
                mock.patch(
                    "annotator.project.loading.sql_backend.load_arrows",
                    return_value={},
                ),
                mock.patch(
                    "annotator.gui.project.folder_loading."
                    "maybe_use_local_class_settings"
                ) as class_prompt,
                mock.patch(
                    "annotator.gui.project.folder_state.maybe_use_folder_model_conf"
                ),
                quiet_folder_gui_effects(),
            ):
                load_folder(controller, new_folder)

        class_prompt.assert_not_called()
        persist_classes.assert_not_called()
        self.assertEqual(controller.project.session_class_names, ("animal",))
        self.assertEqual(controller.project.session_class_colours, ("#123456",))

    def test_accepted_image_reconciliation_saves_after_load(self) -> None:
        """Known-bug regression folder_load_reconciles_jpeg_files_with_sqlite_2026-08-26."""

        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            old_folder = parent / "old"
            old_folder.mkdir()
            new_folder = parent / "new"
            new_folder.mkdir()
            Image.new("RGB", (10, 10), "white").save(new_folder / "image.jpg")
            controller = configured_folder_controller(old_folder)
            document = loaded_document()
            connection = mock.Mock(spec=sqlite3.Connection)

            with (
                successful_backend(
                    document,
                    connection,
                    native_project_established=True,
                ),
                mock.patch(
                    "annotator.project.loading.sql_backend.load_arrows",
                    return_value={},
                ),
                mock.patch(
                    "annotator.gui.project.folder_loading."
                    "resolve_folder_image_reconciliation",
                    return_value=True,
                ),
                mock.patch(
                    "annotator.gui.project.folder_loading."
                    "save_reconciled_project"
                ) as save_reconciled,
                mock.patch(
                    "annotator.gui.project.folder_state.maybe_use_folder_model_conf"
                ),
                quiet_folder_gui_effects(),
            ):
                load_folder(controller, new_folder)

        self.assertEqual(controller.project.folder, new_folder)
        save_reconciled.assert_called_once_with(controller)

    def test_rejected_image_reconciliation_preserves_current_project(self) -> None:
        """Known-bug regression folder_load_reconciles_jpeg_files_with_sqlite_2026-08-26."""

        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            old_folder = parent / "old"
            old_folder.mkdir()
            new_folder = parent / "new"
            new_folder.mkdir()
            Image.new("RGB", (10, 10), "white").save(new_folder / "image.jpg")
            controller = configured_folder_controller(old_folder)
            old_connection = controller.project.sql_connection
            old_document = controller.project.coco

            with (
                successful_backend(loaded_document(), mock.Mock(spec=sqlite3.Connection)),
                mock.patch(
                    "annotator.gui.project.folder_loading."
                    "resolve_folder_image_reconciliation",
                    return_value=None,
                ),
                mock.patch(
                    "annotator.gui.project.folder_loading.load_project"
                ) as load_document,
                mock.patch(
                    "annotator.gui.project.folder_loading.save_reconciled_project"
                ) as save_reconciled,
            ):
                load_folder(controller, new_folder)

        controller.close_sql_connection.assert_not_called()
        self.assertEqual(controller.project.folder, old_folder)
        self.assertIs(controller.project.sql_connection, old_connection)
        self.assertIs(controller.project.coco, old_document)
        load_document.assert_not_called()
        save_reconciled.assert_not_called()

    def test_post_open_failure_closes_candidate_and_restores_empty_state(self) -> None:
        """A failed candidate leaves the last successful folder remembered."""

        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            old_folder = parent / "old"
            old_folder.mkdir()
            new_folder = parent / "new"
            new_folder.mkdir()
            Image.new("RGB", (10, 10), "white").save(new_folder / "image.jpg")
            controller = configured_folder_controller(old_folder)
            document = loaded_document()
            connection = mock.Mock(spec=sqlite3.Connection)

            with (
                successful_backend(document, connection),
                mock.patch(
                    "annotator.project.loading."
                    "sql_backend.load_arrows",
                    side_effect=sqlite3.OperationalError("arrow read failed"),
                ),
                mock.patch("annotator.gui.project.folder_loading.traceback.print_exc"),
                mock.patch(
                    "annotator.gui.project.folder_loading.ErrorDetailsDialog"
                ) as error_dialog,
                quiet_folder_gui_effects(),
            ):
                load_folder(controller, new_folder)

        connection.close.assert_called_once_with()
        self.assertIsNone(controller.project.sql_connection)
        self.assertIsNone(controller.project.folder)
        self.assertIsNone(controller.project.coco)
        self.assertEqual(controller.project.all_image_paths, [])
        self.assertEqual(controller.project.image_paths, [])
        self.assertEqual(controller.project.arrows_by_image, {})
        self.assertEqual(controller.project.review_flags, set())
        self.assertEqual(controller.project.deletion_marks, set())
        self.assertEqual(controller.project.next_audit_event_id, 1)
        self.assertIsNone(controller.project.last_audit_event_id)
        self.assertEqual(controller.project.active_filter, FILTER_ALL)
        self.assertEqual(controller.project.filter_options, (FILTER_ALL, FILTER_NULL))
        self.assertIsNone(controller.view.annotation_overlap_key)
        self.assertEqual(controller.view.annotation_overlap_geometry, ([], []))
        self.assertEqual(controller.prefs.values["image_folder"], str(old_folder))
        controller.prefs.set_path.assert_not_called()
        controller.prefs.save.assert_not_called()
        title, details = error_dialog.call_args.args[1:3]
        self.assertEqual(title, "Could not load folder")
        self.assertIn(str(new_folder), details)
        self.assertIn("No project is currently loaded.", details)
        self.assertIn("Traceback (most recent call last)", details)
        self.assertIn("sqlite3.OperationalError: arrow read failed", details)

    def test_invalid_folder_preserves_current_project(self) -> None:
        """A folder without JPEG images is rejected before unloading begins."""

        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            old_folder = parent / "old"
            old_folder.mkdir()
            empty_folder = parent / "empty"
            empty_folder.mkdir()
            controller = configured_folder_controller(old_folder)
            old_connection = controller.project.sql_connection
            old_document = controller.project.coco

            with (
                mock.patch(
                    "annotator.gui.project.folder_loading.messagebox.showwarning"
                ) as warning,
                mock.patch(
                    "annotator.gui.project.folder_loading.ErrorDetailsDialog"
                ) as error_dialog,
            ):
                load_folder(controller, empty_folder)

        controller.close_sql_connection.assert_not_called()
        self.assertEqual(controller.project.folder, old_folder)
        self.assertIs(controller.project.sql_connection, old_connection)
        self.assertIs(controller.project.coco, old_document)
        warning.assert_called_once()
        error_dialog.assert_not_called()

    def test_close_failure_still_leaves_a_clean_empty_state(self) -> None:
        """A close error keeps the prior folder remembered, but not loaded."""

        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            old_folder = parent / "old"
            old_folder.mkdir()
            new_folder = parent / "new"
            new_folder.mkdir()
            Image.new("RGB", (10, 10), "white").save(new_folder / "image.jpg")
            controller = configured_folder_controller(old_folder)
            controller.close_sql_connection.side_effect = sqlite3.OperationalError(
                "close failed"
            )

            with (
                mock.patch("annotator.gui.project.folder_loading.traceback.print_exc"),
                mock.patch(
                    "annotator.gui.project.folder_loading.ErrorDetailsDialog"
                ) as error_dialog,
                mock.patch(
                    "annotator.gui.project.folder_loading.load_project"
                ) as load_document,
                quiet_folder_gui_effects(),
            ):
                load_folder(controller, new_folder)

        load_document.assert_not_called()
        self.assertIsNone(controller.project.sql_connection)
        self.assertIsNone(controller.project.folder)
        self.assertIsNone(controller.project.coco)
        self.assertEqual(controller.project.all_image_paths, [])
        self.assertEqual(controller.prefs.values["image_folder"], str(old_folder))
        controller.prefs.set_path.assert_not_called()
        controller.prefs.save.assert_not_called()
        details = error_dialog.call_args.args[2]
        self.assertIn("No project is currently loaded.", details)
        self.assertIn("sqlite3.OperationalError: close failed", details)

    def test_commit_failure_during_replacement_closes_old_connection(self) -> None:
        """BUG-2026-10-04-APPLICATION-CLOSE-COMMIT-FAILURE: avoid lock leak."""

        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            old_folder = parent / "old"
            old_folder.mkdir()
            new_folder = parent / "new"
            new_folder.mkdir()
            Image.new("RGB", (10, 10), "white").save(new_folder / "image.jpg")
            controller = configured_folder_controller(old_folder)
            old_connection = sqlite3.connect(":memory:")
            old_connection.execute("PRAGMA foreign_keys = ON")
            old_connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
            old_connection.execute(
                "CREATE TABLE child ("
                "parent_id INTEGER REFERENCES parent(id) "
                "DEFERRABLE INITIALLY DEFERRED)"
            )
            old_connection.execute("BEGIN")
            old_connection.execute("INSERT INTO child VALUES (99)")
            controller.project.sql_connection = old_connection
            controller.close_sql_connection = mock.Mock(
                side_effect=lambda: close_sql_connection(controller)
            )

            with (
                mock.patch(
                    "annotator.gui.project.folder_loading.traceback.print_exc"
                ),
                mock.patch(
                    "annotator.gui.project.folder_loading.ErrorDetailsDialog"
                ) as error_dialog,
                mock.patch(
                    "annotator.gui.project.folder_loading.load_project"
                ) as load_document,
                quiet_folder_gui_effects(),
            ):
                load_folder(controller, new_folder)

        load_document.assert_not_called()
        self.assertIsNone(controller.project.sql_connection)
        self.assertIsNone(controller.project.folder)
        self.assertIsNone(controller.project.coco)
        error_dialog.assert_called_once()
        error_details = error_dialog.call_args.args[2]
        self.assertIn("FOREIGN KEY constraint failed", error_details)
        self.assertNotIn("Cannot operate on a closed database", error_details)
        with self.assertRaisesRegex(sqlite3.ProgrammingError, "closed"):
            old_connection.execute("SELECT 1")

    def test_selected_invalid_class_file_propagates_to_load_boundary(self) -> None:
        """A selected malformed classes.json is not silently replaced by defaults."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            project_folder = folder / "teacup"
            project_folder.mkdir()
            (project_folder / "classes.json").touch()
            controller = StatefulHost()
            controller.root = mock.Mock()
            controller.log = mock.Mock()
            controller.project.session_class_names = ("old",)
            controller.project.session_class_colours = ("#abcdef",)
            controller.project.using_local_class_settings = True
            source_dialog = mock.Mock()
            source_dialog.result = "custom"

            with (
                mock.patch(
                    "annotator.gui.local_class_actions.LocalClassSourceDialog",
                    return_value=source_dialog,
                ),
                mock.patch(
                    "annotator.gui.local_class_actions."
                    "read_local_class_settings",
                    side_effect=ValueError("invalid class file"),
                ),
                mock.patch(
                    "annotator.gui.local_class_actions.messagebox.showerror"
                ) as showerror,
            ):
                with self.assertRaisesRegex(ValueError, "invalid class file"):
                    maybe_use_local_class_settings(controller, folder)

        showerror.assert_not_called()


if __name__ == "__main__":
    unittest.main()
