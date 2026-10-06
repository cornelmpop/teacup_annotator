"""Regression tests for Windows-reserved region-class names."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import annotator.sqlite as sql_backend
from annotator.class_names import class_name_error
from annotator.coco import CocoDocument
from annotator.coco.category_helpers import categories_from_json
from annotator.dialogs import NewLocalClassDialog
from annotator.preferences.validation import validate_default_class
from annotator.project.crops import safe_class_folder_name


BUG_ID = "BUG-2026-10-05-WINDOWS-RESERVED-CLASS-NAMES"
RESERVED_ERROR = "Class names may not use Windows reserved file names."


class WindowsReservedClassNameTests(unittest.TestCase):
    """Windows device names cannot become portable class path components."""

    def test_official_reserved_names_are_rejected_case_insensitively(self) -> None:
        """BUG-2026-10-05-WINDOWS-RESERVED-CLASS-NAMES: reject device names."""

        reserved_names = (
            "CON",
            "prn",
            "Aux",
            "NUL",
            *(f"COM{suffix}" for suffix in "123456789¹²³"),
            *(f"lpt{suffix}" for suffix in "123456789¹²³"),
        )

        for reserved_name in reserved_names:
            with self.subTest(reserved_name=reserved_name):
                self.assertEqual(
                    class_name_error((reserved_name,)),
                    RESERVED_ERROR,
                )

    def test_similar_portable_names_remain_valid(self) -> None:
        """BUG-2026-10-05-WINDOWS-RESERVED-CLASS-NAMES: allow near misses."""

        for class_name in (
            "COM0",
            "COM10",
            "LPT0",
            "LPT10",
            "NUL_value",
            "CONTOUR",
            "auxiliary",
        ):
            with self.subTest(class_name=class_name):
                self.assertIsNone(class_name_error((class_name,)))

    def test_input_boundaries_share_the_reserved_name_error(self) -> None:
        """BUG-2026-10-05-WINDOWS-RESERVED-CLASS-NAMES: validate inputs."""

        with self.assertRaisesRegex(ValueError, RESERVED_ERROR):
            categories_from_json([{"id": 0, "name": "NUL"}])
        self.assertEqual(validate_default_class("NUL"), RESERVED_ERROR)

        dialog = object.__new__(NewLocalClassDialog)
        dialog.existing_names = ()
        dialog.name_var = mock.Mock()
        dialog.name_var.get.return_value = "NUL"
        dialog.colour_var = mock.Mock()
        dialog.colour_var.get.return_value = "#123456"
        with mock.patch("annotator.dialogs.messagebox.showerror") as showerror:
            self.assertFalse(dialog.validate())
        showerror.assert_called_once_with(
            "Invalid class name",
            RESERVED_ERROR,
            parent=dialog,
        )

    def test_existing_database_is_rejected_without_repair(self) -> None:
        """BUG-2026-10-05-WINDOWS-RESERVED-CLASS-NAMES: reject stored names."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (10, 10), "white").save(image_path)
            document = CocoDocument(folder, [image_path])
            connection = sql_backend.connect_database(folder)
            try:
                sql_backend.replace_database_from_document(connection, document)
                connection.execute(
                    "UPDATE annotation_classes SET class_name = 'NUL' "
                    "WHERE annotation_family = 'region'"
                )
                connection.commit()
                changes_before_load = connection.total_changes

                with self.assertRaisesRegex(ValueError, RESERVED_ERROR):
                    sql_backend.document_from_database(
                        connection,
                        folder,
                        [image_path],
                    )

                stored_name = connection.execute(
                    "SELECT class_name FROM annotation_classes "
                    "WHERE annotation_family = 'region'"
                ).fetchone()["class_name"]
                self.assertEqual(stored_name, "NUL")
                self.assertEqual(connection.total_changes, changes_before_load)
            finally:
                connection.close()

    def test_crop_output_rejects_reserved_component(self) -> None:
        """BUG-2026-10-05-WINDOWS-RESERVED-CLASS-NAMES: guard crop output."""

        with self.assertRaisesRegex(ValueError, RESERVED_ERROR):
            safe_class_folder_name("NUL")


if __name__ == "__main__":
    unittest.main()
