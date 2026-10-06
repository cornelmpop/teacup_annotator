"""Tests for annotation-class sources used by the GUI."""

from __future__ import annotations

import unittest
from unittest import mock

from tests.support import StatefulHost
from annotator.gui.model.settings import active_class_colours
from annotator.gui.model.settings import active_class_names
from annotator.gui.model.settings import active_default_class


class ActiveClassNamesTests(unittest.TestCase):
    """Annotation classes stay independent from model configuration."""

    @staticmethod
    def make_host() -> StatefulHost:
        """Return the minimum controller state needed to resolve class settings."""

        host = StatefulHost()
        host.project.session_model_values = {}
        host.project.session_class_names = ()
        host.project.session_class_colours = ()
        host.session_default_class_var = mock.Mock()
        host.session_default_class_var.get.return_value = ""
        host.project.using_local_class_settings = False
        host.prefs = mock.Mock()
        host.prefs.values = {"default_class": "lithics"}
        host.prefs.get_default_class.return_value = "lithics"
        host.prefs.get_class_colours.return_value = ("#123456",)
        return host

    def test_empty_document_uses_default_class_instead_of_placeholder(self) -> None:
        """The internal COCO object placeholder does not leak into the class panel."""

        host = self.make_host()
        host.project.coco = mock.Mock()
        host.project.coco.category_names.return_value = ("object",)
        host.project.coco.annotations_by_image = {"a.jpg": []}

        self.assertEqual(active_class_names(host), ("lithics",))

    def test_persisted_placeholder_uses_configured_default_class(self) -> None:
        """BUG-2026-10-05-PERSISTED-DEFAULT-CLASS: hide setup state."""

        host = self.make_host()
        host.project.coco = mock.Mock()
        host.project.coco.category_names.return_value = ("__DEFAULT__",)
        host.project.coco.annotations_by_image = {"a.jpg": []}

        self.assertEqual(active_class_names(host), ("lithics",))

    def test_folder_model_conf_overrides_master_default_class(self) -> None:
        """The accepted folder scalar controls new manual annotations."""

        host = self.make_host()
        host.project.session_model_values = {"default_class": "table"}

        self.assertEqual(active_default_class(host), "table")

    def test_local_classes_are_followed_by_document_only_classes(self) -> None:
        """Model-produced document classes remain visible beside folder classes."""

        host = self.make_host()
        host.project.using_local_class_settings = True
        host.project.session_class_names = ("lithics",)
        host.project.session_class_colours = ("#abcdef",)
        host.project.coco = mock.Mock()
        host.project.coco.category_names.return_value = ("lithics", "table")
        host.project.coco.annotations_by_image = {"a.jpg": [mock.Mock()]}

        self.assertEqual(active_class_names(host), ("lithics", "table"))
        self.assertEqual(
            active_class_colours(host),
            ("#abcdef", "#123456"),
        )

    def test_folder_class_order_changes_display_order_only(self) -> None:
        """Folder order leads the GUI while preserving unlisted model classes."""

        host = self.make_host()
        host.project.session_model_values = {"class_order": "table, lithics"}
        host.project.coco = mock.Mock()
        host.project.coco.category_names.return_value = (
            "lithics",
            "photo",
            "table",
        )
        host.project.coco.annotations_by_image = {"a.jpg": [mock.Mock()]}

        self.assertEqual(
            active_class_names(host),
            ("table", "lithics", "photo"),
        )
        host.project.coco.category_names.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
