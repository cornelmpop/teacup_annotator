"""Contract tests for region-class name syntax and identity."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from annotator.class_names import class_name_error
from annotator.class_names import class_name_key
from annotator.coco import CocoDocument
from annotator.coco.category_helpers import categories_from_json
from annotator.local_class_settings import read_local_class_settings
from annotator.model.configuration import read_model_configuration
from annotator.preferences.validation import validate_default_class


BUG_ID = "BUG-2026-09-29-CLASS-NAME-VALIDATION-AND-IDENTITY"


class ClassNameValidationTests(unittest.TestCase):
    """Class names share one syntax and case-insensitive identity contract."""

    def test_allowed_and_disallowed_characters(self) -> None:
        """BUG-2026-09-29-CLASS-NAME-VALIDATION-AND-IDENTITY: enforce syntax."""

        self.assertIsNone(
            class_name_error(("Object2", "map_image", "map-image", "Éclair"))
        )
        for invalid_name in ("", "map image", "map.image", "object!"):
            with self.subTest(invalid_name=invalid_name):
                self.assertIn(
                    "alphanumeric",
                    class_name_error((invalid_name,)) or "",
                )

    def test_case_only_duplicate_is_rejected(self) -> None:
        """BUG-2026-09-29-CLASS-NAME-VALIDATION-AND-IDENTITY: reject aliases."""

        self.assertEqual(class_name_key("Object"), "object")
        self.assertIn("case", class_name_error(("object", "Object")) or "")

    def test_category_lookup_preserves_first_spelling(self) -> None:
        """BUG-2026-09-29-CLASS-NAME-VALIDATION-AND-IDENTITY: reuse category."""

        document = CocoDocument(Path("."), [])
        document.categories = [
            {"id": 1, "name": "object", "supercategory": "object"}
        ]

        self.assertEqual(document.category_id_for_name("Object"), 1)
        self.assertEqual(document.category_names(), ("object",))

    def test_coco_json_rejects_invalid_or_duplicate_names(self) -> None:
        """BUG-2026-09-29-CLASS-NAME-VALIDATION-AND-IDENTITY: validate JSON."""

        with self.assertRaisesRegex(ValueError, "alphanumeric"):
            categories_from_json([{"id": 0, "name": "map image"}])
        with self.assertRaisesRegex(ValueError, "case"):
            categories_from_json(
                [
                    {"id": 0, "name": "object"},
                    {"id": 1, "name": "Object"},
                ]
            )

    def test_classes_json_rejects_invalid_name(self) -> None:
        """BUG-2026-09-29-CLASS-NAME-VALIDATION-AND-IDENTITY: validate settings."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            settings_folder = folder / "teacup"
            settings_folder.mkdir()
            (settings_folder / "classes.json").write_text(
                json.dumps(
                    {"classes": [{"name": "map image", "colour": "#123456"}]}
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "alphanumeric"):
                read_local_class_settings(folder)

    def test_model_profile_rejects_case_only_duplicate(self) -> None:
        """BUG-2026-09-29-CLASS-NAME-VALIDATION-AND-IDENTITY: validate profile."""

        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "model.pt"
            model_path.with_suffix(".conf").write_text(
                "[inference]\nthreshold = 0.5\n\n"
                "[classes]\n0 = object\n1 = Object\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "case"):
                read_model_configuration(model_path)

    def test_default_class_rejects_invalid_name(self) -> None:
        """BUG-2026-09-29-CLASS-NAME-VALIDATION-AND-IDENTITY: validate default."""

        self.assertIn("alphanumeric", validate_default_class("map image") or "")


if __name__ == "__main__":
    unittest.main()
