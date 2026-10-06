"""Tests for applying a class backup before first SQLite initialization."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from annotator.coco import CocoDocument
from annotator.sqlite.annotations import _apply_initial_class_settings


class ApplyInitialClassSettingsTests(unittest.TestCase):
    """Initial settings lead the imported vocabulary without losing used classes."""

    def test_replaces_unannotated_placeholder_with_selected_classes(self) -> None:
        """A pristine document stores exactly the human-selected backup order."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            document = CocoDocument(folder, [folder / "a.jpg"])

            colours = _apply_initial_class_settings(
                document,
                ("#aaaaaa",),
                (("figure", "table"), ("#112233", "#445566")),
            )

        self.assertEqual(document.category_names(), ("figure", "table"))
        self.assertEqual(colours, ("#112233", "#445566"))

    def test_retains_imported_annotated_class_after_selected_classes(self) -> None:
        """A class referenced by recovery JSON remains with a palette colour."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            document = CocoDocument(folder, [folder / "a.jpg"])
            document.categories = [
                {"id": 1, "name": "object", "supercategory": "object"}
            ]
            document.add_annotation(
                "a.jpg",
                [(1.0, 1.0), (5.0, 1.0), (5.0, 4.0), (1.0, 4.0)],
            )

            colours = _apply_initial_class_settings(
                document,
                ("#aaaaaa", "#bbbbbb"),
                (("figure",), ("#112233",)),
            )

        self.assertEqual(document.category_names(), ("figure", "object"))
        self.assertEqual(colours, ("#112233", "#bbbbbb"))


if __name__ == "__main__":
    unittest.main()
