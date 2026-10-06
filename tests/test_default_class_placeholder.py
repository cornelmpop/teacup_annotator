"""Contract tests for the persisted default annotation class."""

from __future__ import annotations

from pathlib import Path
import unittest

from annotator.coco import CocoDocument
from annotator.coco import category_helpers
from annotator.preferences.values import fill_preference_defaults
from annotator.resources import read_preference_defaults_text


BUG_ID = "BUG-2026-10-05-PERSISTED-DEFAULT-CLASS"


class DefaultClassPlaceholderTests(unittest.TestCase):
    """The persisted placeholder remains distinguishable from real classes."""

    def test_empty_document_starts_with_persisted_default_class(self) -> None:
        """BUG-2026-10-05-PERSISTED-DEFAULT-CLASS: seed `__DEFAULT__`."""

        document = CocoDocument(Path("/project"), [])

        self.assertEqual(
            document.categories,
            [
                {
                    "id": 1,
                    "name": "__DEFAULT__",
                    "supercategory": "object",
                }
            ],
        )

    def test_packaged_preference_uses_persisted_default_class(self) -> None:
        """BUG-2026-10-05-PERSISTED-DEFAULT-CLASS: ship the new default."""

        preference_text = read_preference_defaults_text()

        self.assertIn("default_class = __DEFAULT__", preference_text.splitlines())

    def test_existing_object_preference_is_not_migrated(self) -> None:
        """BUG-2026-10-05-PERSISTED-DEFAULT-CLASS: preserve explicit prefs."""

        values = {"default_class": "object", "prefs_version": "test"}

        changed = fill_preference_defaults(
            values,
            {"default_class": "__DEFAULT__", "prefs_version": "test"},
            "test",
        )

        self.assertFalse(changed)
        self.assertEqual(values["default_class"], "object")

    def test_current_and_legacy_unused_names_are_placeholders(self) -> None:
        """BUG-2026-10-05-PERSISTED-DEFAULT-CLASS: recognize both names."""

        is_unused_placeholder = getattr(
            category_helpers,
            "is_unused_default_category",
            None,
        )

        self.assertIsNotNone(is_unused_placeholder)
        assert is_unused_placeholder is not None
        self.assertTrue(is_unused_placeholder(("__DEFAULT__",), False))
        self.assertTrue(is_unused_placeholder(("object",), False))

    def test_used_or_nonsole_names_are_not_placeholders(self) -> None:
        """BUG-2026-10-05-PERSISTED-DEFAULT-CLASS: preserve project data."""

        is_unused_placeholder = getattr(
            category_helpers,
            "is_unused_default_category",
            None,
        )

        self.assertIsNotNone(is_unused_placeholder)
        assert is_unused_placeholder is not None
        self.assertFalse(is_unused_placeholder(("__DEFAULT__",), True))
        self.assertFalse(is_unused_placeholder(("object",), True))
        self.assertFalse(
            is_unused_placeholder(("object", "table"), False)
        )


if __name__ == "__main__":
    unittest.main()
