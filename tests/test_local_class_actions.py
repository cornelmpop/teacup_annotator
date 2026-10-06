"""Tests for folder-local class action workflows."""

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from annotator.arrows import ARROW_SPEC_CLASS_NAME
from annotator.coco.models import Annotation
from tests.support import StatefulHost
from annotator.gui.local_class_actions import add_local_class
from annotator.gui.local_class_actions import change_local_class_colour
from annotator.gui.local_class_actions import delete_local_class
from annotator.gui.local_class_actions import maybe_use_local_class_settings


def action_host() -> StatefulHost:
    """Return loaded class state and observable action effects."""

    host = StatefulHost()
    host.root = mock.sentinel.root
    host.project.folder = Path("/project")
    host.project.coco = mock.Mock()
    host.project.coco.categories = [
        {"id": 1, "name": "flake"},
        {"id": 2, "name": "core"},
    ]
    host.project.coco.category_names.return_value = ("flake", "core")
    host.project.coco.annotations_by_image = {}
    host.project.session_class_names = ("flake", "core")
    host.project.session_class_colours = ("#123456", "#abcdef")
    host.project.using_local_class_settings = True
    host.prefs = mock.Mock()
    host.prefs.values = {}
    host.prefs.get_class_colours.return_value = ("#123456", "#abcdef")
    host.prefs.get_default_class.return_value = "flake"
    host.session_default_class_var = mock.Mock()
    host.session_default_class_var.get.return_value = ""
    host.log = mock.Mock()
    return host


class LocalClassActionTests(unittest.TestCase):
    """Class actions publish only successful, immediately saved changes."""

    def test_custom_and_default_sources_replace_only_class_session_values(
        self,
    ) -> None:
        """Folder choice preserves unrelated accepted model settings."""

        host = action_host()
        host.project.session_model_values = {"model_weights": "folder.pt"}
        dialog = mock.Mock(result="custom")
        with (
            mock.patch(
                "annotator.gui.local_class_actions.Path.is_file",
                return_value=True,
            ),
            mock.patch(
                "annotator.gui.local_class_actions.LocalClassSourceDialog",
                return_value=dialog,
            ),
            mock.patch(
                "annotator.gui.local_class_actions.read_local_class_settings",
                return_value=(("custom",), ("#010203",)),
            ),
        ):
            maybe_use_local_class_settings(host, host.project.folder)

        self.assertEqual(host.project.session_class_names, ("custom",))
        self.assertTrue(host.project.using_local_class_settings)
        self.assertEqual(
            host.project.session_model_values,
            {"model_weights": "folder.pt"},
        )

        dialog.result = "defaults"
        with (
            mock.patch(
                "annotator.gui.local_class_actions.Path.is_file",
                return_value=True,
            ),
            mock.patch(
                "annotator.gui.local_class_actions.LocalClassSourceDialog",
                return_value=dialog,
            ),
        ):
            maybe_use_local_class_settings(host, host.project.folder)

        self.assertEqual(host.project.session_class_names, ())
        self.assertFalse(host.project.using_local_class_settings)

    def test_add_class_creates_category_then_saves_and_refreshes(self) -> None:
        """A completed dialog appends the class and colour exactly once."""

        host = action_host()
        dialog = mock.Mock(result=("tool", "#fedcba"))
        with (
            mock.patch(
                "annotator.gui.local_class_actions.NewLocalClassDialog",
                return_value=dialog,
            ),
            mock.patch(
                "annotator.gui.local_class_actions.save_local_class_values",
                return_value=True,
            ) as save,
            mock.patch(
                "annotator.gui.local_class_actions."
                "refresh_after_local_class_change"
            ) as refresh,
        ):
            add_local_class(host)

        host.project.coco.category_id_for_name.assert_called_once_with("tool")
        save.assert_called_once_with(
            host,
            ("flake", "core", "tool"),
            ("#123456", "#abcdef", "#fedcba"),
        )
        refresh.assert_called_once_with(host)
        host.log.assert_called_once_with("Added annotation class: tool")

    def test_add_class_reserves_hidden_arrow_class_name(self) -> None:
        """BUG-2026-08-26-CLASS-COCO-CATEGORY-COLLISION: users cannot create the hidden arrow class."""

        host = action_host()
        dialog = mock.Mock(result=None)
        with mock.patch(
            "annotator.gui.local_class_actions.NewLocalClassDialog",
            return_value=dialog,
        ) as dialog_type:
            add_local_class(host)

        dialog_type.assert_called_once_with(
            host.root,
            ("flake", "core", ARROW_SPEC_CLASS_NAME),
            "#123456",
        )
        host.project.coco.category_id_for_name.assert_not_called()

    def test_colour_change_replaces_only_the_selected_class_colour(self) -> None:
        """A chosen colour keeps class order and saves the aligned palette."""

        host = action_host()
        with (
            mock.patch(
                "annotator.gui.local_class_actions.colorchooser.askcolor",
                return_value=((1, 2, 3), "#010203"),
            ),
            mock.patch(
                "annotator.gui.local_class_actions.save_local_class_values",
                return_value=True,
            ) as save,
            mock.patch(
                "annotator.gui.local_class_actions."
                "refresh_after_local_class_change"
            ) as refresh,
        ):
            change_local_class_colour(host, "core")

        save.assert_called_once_with(
            host,
            ("flake", "core"),
            ("#123456", "#010203"),
        )
        refresh.assert_called_once_with(host)

    def test_delete_refuses_an_in_use_class(self) -> None:
        """Existing annotation category ids prevent dangling references."""

        host = action_host()
        host.project.coco.annotations_by_image = {
            "image.jpg": [Annotation(1, 1, 1, [])]
        }
        with (
            mock.patch(
                "annotator.gui.local_class_actions.messagebox.showwarning"
            ) as warning,
            mock.patch(
                "annotator.gui.local_class_actions.save_local_class_values"
            ) as save,
        ):
            delete_local_class(host, "flake")

        warning.assert_called_once()
        save.assert_not_called()

    def test_confirmed_delete_removes_category_and_saves_remaining_values(
        self,
    ) -> None:
        """An unused class is removed from document and folder settings."""

        host = action_host()
        with (
            mock.patch(
                "annotator.gui.local_class_actions.messagebox.askyesno",
                return_value=True,
            ),
            mock.patch(
                "annotator.gui.local_class_actions.save_local_class_values",
                return_value=True,
            ) as save,
            mock.patch(
                "annotator.gui.local_class_actions."
                "refresh_after_local_class_change"
            ) as refresh,
        ):
            delete_local_class(host, "core")

        self.assertEqual(host.project.coco.categories, [{"id": 1, "name": "flake"}])
        save.assert_called_once_with(host, ("flake",), ("#123456",))
        refresh.assert_called_once_with(host)


if __name__ == "__main__":
    unittest.main()
