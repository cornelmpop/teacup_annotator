"""Regression contracts for class-name validation at crop input boundaries."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from annotator.coco import CocoDocument
from annotator.model.configuration import read_model_conf
from annotator.preferences.values import preference_default_class
from annotator.project.crops import safe_class_folder_name
from annotator.project.crops import write_annotation_crops


class CropPathSafetyTests(unittest.TestCase):
    """Unsafe class components cannot escape the crop publication directory."""

    def test_folder_default_rejects_unsafe_class_name(self) -> None:
        """BUG-2026-09-29-CROP-PATH-SAFETY: reject ``..`` in model.conf."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            project_folder = folder / "teacup"
            project_folder.mkdir()
            (project_folder / "model.conf").write_text(
                "[model]\ndefault_class = ..\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "alphanumeric"):
                read_model_conf(folder)

    def test_global_default_rejects_unsafe_class_name(self) -> None:
        """BUG-2026-09-29-CROP-PATH-SAFETY: reject spaced preferences."""

        with self.assertRaisesRegex(ValueError, "alphanumeric"):
            preference_default_class(
                {"default_class": "traffic light"},
                {"default_class": "object"},
            )

    def test_valid_class_name_is_preserved_at_each_boundary(self) -> None:
        """BUG-2026-09-29-CROP-PATH-SAFETY: preserve a valid class exactly."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            project_folder = folder / "teacup"
            project_folder.mkdir()
            (project_folder / "model.conf").write_text(
                "[model]\ndefault_class = valid_class\n",
                encoding="utf-8",
            )

            self.assertEqual(
                read_model_conf(folder),
                {"default_class": "valid_class"},
            )
            self.assertEqual(
                preference_default_class(
                    {"default_class": "valid_class"},
                    {"default_class": "object"},
                ),
                "valid_class",
            )
            self.assertEqual(safe_class_folder_name("valid_class"), "valid_class")

    def test_existing_database_class_stops_before_crop_publication(self) -> None:
        """BUG-2026-09-29-CROP-PATH-SAFETY: preserve prior crop output."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (20, 20), "white").save(image_path)
            document = CocoDocument(folder, [image_path])
            document.categories = [
                {"id": 1, "name": "..", "supercategory": "object"}
            ]
            document.add_annotation(
                image_path.name,
                [(2, 2), (10, 2), (10, 10), (2, 10)],
                category_id=1,
            )
            crops_folder = folder / "teacup" / "crops"
            crops_folder.mkdir(parents=True)
            marker = crops_folder / "previous.txt"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "alphanumeric"):
                write_annotation_crops(document, 0)

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertFalse((folder / "teacup" / "image_1.jpg").exists())
            self.assertFalse((folder / "teacup" / "annotations.json").exists())
            self.assertFalse((folder / "teacup" / ".crops.tmp").exists())


if __name__ == "__main__":
    unittest.main()
