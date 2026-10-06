"""Regression tests for publishing the completed COCO import report."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from annotator.gui.project.folder_loading import load_folder
from tests.test_folder_load_state_transition import configured_folder_controller
from tests.test_folder_load_state_transition import loaded_document
from tests.test_folder_load_state_transition import quiet_folder_gui_effects
from tests.test_folder_load_state_transition import successful_backend


IMPORT_NOTICE = (
    "annotations.json row 1: combined 2 source polygons into one editable "
    "outline (disconnected parts use their convex hull)."
)


class FolderImportReportTests(unittest.TestCase):
    """Successful JSON migration publishes its report after folder loading."""

    def _load_import(
        self,
        parent: Path,
        notices: list[str],
    ) -> tuple[mock.Mock, mock.Mock]:
        old_folder = parent / "old"
        old_folder.mkdir()
        new_folder = parent / "new"
        new_folder.mkdir()
        Image.new("RGB", (10, 10), "white").save(new_folder / "image.jpg")
        controller = configured_folder_controller(old_folder)
        config_folder = parent / "config"
        config_folder.mkdir()
        controller.prefs.path = config_folder / "annotator_prefs.conf"
        document = loaded_document()
        document.import_notices = notices
        connection = mock.Mock()

        with (
            successful_backend(
                document,
                connection,
                json_sources_exist=True,
            ),
            mock.patch(
                "annotator.gui.project.folder_loading.ProgressDialog"
            ) as progress_dialog,
            mock.patch(
                "annotator.gui.project.folder_loading.ErrorDetailsDialog"
            ) as details_dialog,
            mock.patch(
                "annotator.project.loading.sql_backend.load_arrows",
                return_value={},
            ),
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

        progress_dialog.return_value.close.assert_called_once_with()
        return controller, details_dialog

    def test_conversion_report_is_written_and_displayed(self) -> None:
        """BUG-2026-10-05-LOSSY-COCO-IMPORT-NOT-REPORTED: publish report."""

        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            controller, details_dialog = self._load_import(parent, [IMPORT_NOTICE])
            report_path = (
                controller.prefs.path.parent / "last_coco_import_report.txt"
            )
            expected_report = (
                "Teacup COCO Import Report\n"
                "Project: new\n\n"
                f"- {IMPORT_NOTICE}\n"
            )

            self.assertEqual(
                report_path.read_text(encoding="utf-8"),
                expected_report,
            )
            details_dialog.assert_called_once_with(
                controller.root,
                "COCO Import Report",
                (
                    "Some annotations were converted or rejected during COCO "
                    "import.\n\n"
                    f"A copy of this report was saved to:\n{report_path}\n\n"
                    f"{expected_report}"
                ),
                copy_button_text="Copy report",
            )

    def test_clean_import_replaces_report_without_opening_dialog(self) -> None:
        """BUG-2026-10-05-LOSSY-COCO-IMPORT-NOT-REPORTED: clean import."""

        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            controller, details_dialog = self._load_import(parent, [])
            report_path = (
                controller.prefs.path.parent / "last_coco_import_report.txt"
            )

            self.assertEqual(
                report_path.read_text(encoding="utf-8"),
                (
                    "Teacup COCO Import Report\n"
                    "Project: new\n\n"
                    "No geometry conversions or rejected annotation rows were "
                    "detected.\n"
                ),
            )
            details_dialog.assert_not_called()

    def test_report_write_failure_does_not_invalidate_loaded_project(self) -> None:
        """BUG-2026-10-05-LOSSY-COCO-IMPORT-NOT-REPORTED: write failure."""

        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            with (
                mock.patch(
                    "pathlib.Path.write_text",
                    side_effect=OSError("report disk full"),
                ),
                mock.patch(
                    "annotator.gui.project.folder_loading.messagebox.showwarning"
                ) as warning,
            ):
                controller, details_dialog = self._load_import(
                    parent,
                    [IMPORT_NOTICE],
                )

            self.assertEqual(controller.project.folder, parent / "new")
            warning.assert_called_once()
            self.assertIn("report disk full", warning.call_args.args[1])
            details_dialog.assert_called_once()
            self.assertIn(
                "The report could not be written. Copy it from this dialog.",
                details_dialog.call_args.args[2],
            )


if __name__ == "__main__":
    unittest.main()
