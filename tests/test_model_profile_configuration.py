"""Tests for configuring a folder from a model sidecar without weights."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from annotator.config_window import ConfigurationWindow
from annotator.coco import CocoDocument
from annotator.model.configuration import FOLDER_MODEL_CONF_KEYS
from annotator.model.configuration import read_model_conf
from annotator.release_identity import APP_VERSION


def model_editor(folder: Path) -> ConfigurationWindow:
    """Return a configuration editor with folder persistence dependencies."""

    editor = ConfigurationWindow.__new__(ConfigurationWindow)
    editor.window = mock.Mock()
    editor.app_version = APP_VERSION
    editor.fallback_preferences = {}
    editor.model_conf_keys = FOLDER_MODEL_CONF_KEYS
    editor.validate_default_class = mock.Mock(return_value=None)
    editor.vars = {
        key: mock.Mock(**{"get.return_value": ""})
        for key in (
            *ConfigurationWindow.MODEL_KEYS,
            *ConfigurationWindow.PROJECT_LINE_KEYS,
        )
    }
    editor.vars["default_class"].get.return_value = "lithics"
    editor.bool_vars = {
        key: mock.Mock(**{"get.return_value": False})
        for key in ConfigurationWindow.BOOLEAN_KEYS
    }
    editor.project_text_widgets = {
        key: mock.Mock(**{"get.return_value": ""})
        for key in ConfigurationWindow.PROJECT_TEXT_KEYS
    }
    editor.default_class_combo = mock.Mock()
    editor.model_profile_class_names = ()
    editor.loaded_model_values = {
        key: editor.vars[key].get() for key in ConfigurationWindow.MODEL_KEYS
    }
    editor.app = SimpleNamespace(
        prefs=SimpleNamespace(
            values={},
            save=mock.Mock(),
            get_bool=mock.Mock(return_value=False),
        ),
        project=SimpleNamespace(
            folder=folder,
            project_metadata={},
            session_model_values={},
            using_folder_model_conf=False,
            coco=CocoDocument(folder, [folder / "image.jpg"]),
        ),
        session_default_class_var=mock.Mock(),
        class_colour_map=mock.Mock(return_value={"lithics": "#123456"}),
        active_class_colours=mock.Mock(return_value=("#123456", "#abcdef")),
        apply_runtime_preferences=mock.Mock(),
        log=mock.Mock(),
    )
    return editor


class ModelProfileConfigurationTests(unittest.TestCase):
    """Model profiles configure manual classes without opening weights."""

    def test_profile_import_populates_order_threshold_and_default_dropdown(
        self,
    ) -> None:
        """A selected .conf is sufficient to stage model-aware folder settings."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            profile = folder / "stage_4_v1.conf"
            profile.write_text(
                "[inference]\nthreshold = 0.61\n\n"
                "[classes]\n0 = lithics\n1 = core\n",
                encoding="utf-8",
            )
            editor = model_editor(folder)
            editor.vars["default_class"].get.return_value = "unrelated"

            with mock.patch(
                "annotator.gui.config_window.choices.filedialog.askopenfilename",
                return_value=str(profile),
            ):
                editor.choose_model_profile()

        self.assertEqual(editor.model_profile_class_names, ("lithics", "core"))
        editor.vars["default_threshold"].set.assert_called_once_with("0.61")
        editor.vars["class_order"].set.assert_called_once_with("lithics, core")
        editor.vars["default_class"].set.assert_called_once_with("lithics")
        editor.default_class_combo.configure.assert_called_once_with(
            values=("lithics", "core")
        )

    def test_save_writes_folder_model_conf_and_profile_classes(self) -> None:
        """Configuration Save persists staged model settings without weights."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            editor = model_editor(folder)
            editor.model_profile_class_names = ("lithics", "core")
            editor.vars["default_threshold"].get.return_value = "0.61"
            editor.vars["class_order"].get.return_value = "lithics, core"

            with (
                mock.patch(
                    "annotator.gui.config_window.effects.save_local_class_values",
                    return_value=True,
                ) as save_classes,
                mock.patch(
                    "annotator.gui.config_window.effects.refresh_after_local_class_change"
                ),
                mock.patch(
                    "annotator.gui.config_window.effects.class_colour_map",
                    return_value={"lithics": "#123456"},
                ),
                mock.patch(
                    "annotator.gui.config_window.effects.active_class_colours",
                    return_value=("#123456", "#abcdef"),
                ),
                mock.patch(
                    "annotator.gui.config_window.effects.apply_runtime_preferences"
                ),
            ):
                editor.save()

            self.assertEqual(
                read_model_conf(folder),
                {
                    "default_class": "lithics",
                    "default_threshold": "0.61",
                    "class_order": "lithics, core",
                },
            )

        save_classes.assert_called_once_with(
            editor.app,
            ("lithics", "core"),
            ("#123456", "#abcdef"),
        )
        self.assertTrue(editor.app.project.using_folder_model_conf)
        self.assertEqual(editor.model_profile_class_names, ())

    def test_save_replaces_placeholder_and_publishes_selected_default(self) -> None:
        """BUG-2026-10-05-PERSISTED-DEFAULT-CLASS: publish saved profile state."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            editor = model_editor(folder)
            editor.app.project.coco.categories = [
                {
                    "id": 1,
                    "name": "__DEFAULT__",
                    "supercategory": "object",
                }
            ]
            editor.model_profile_class_names = ("lithics", "core")
            editor.vars["default_class"].get.return_value = "core"
            editor.vars["default_threshold"].get.return_value = "0.61"
            editor.vars["class_order"].get.return_value = "lithics, core"

            with (
                mock.patch(
                    "annotator.gui.config_window.effects.save_local_class_values",
                    return_value=True,
                ),
                mock.patch(
                    "annotator.gui.config_window.effects.refresh_after_local_class_change"
                ),
                mock.patch(
                    "annotator.gui.config_window.effects.class_colour_map",
                    return_value={},
                ),
                mock.patch(
                    "annotator.gui.config_window.effects.active_class_colours",
                    return_value=("#123456", "#abcdef"),
                ),
                mock.patch(
                    "annotator.gui.config_window.effects.apply_runtime_preferences"
                ),
            ):
                editor.save()

            self.assertEqual(
                editor.app.project.coco.category_names(),
                ("lithics", "core"),
            )
            self.assertEqual(
                read_model_conf(folder)["default_class"],
                "core",
            )
            editor.app.session_default_class_var.set.assert_called_once_with(
                "core"
            )

    def test_unrelated_configuration_save_does_not_create_model_conf(self) -> None:
        """Saving project data alone leaves an unconfigured folder unchanged."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            editor = model_editor(folder)

            with mock.patch(
                "annotator.gui.config_window.effects.apply_runtime_preferences"
            ):
                editor.save()

            self.assertFalse((folder / "teacup" / "model.conf").exists())
