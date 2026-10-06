"""Tests for configured and interactive model-weights selection."""

import unittest
from pathlib import Path
from unittest import mock

from tests.support import StatefulHost
from annotator.gui.model.run import run_model
from annotator.model.workflow import ModelRunConfiguration


class ModelWeightsSelectionTests(unittest.TestCase):
    @staticmethod
    def model_host() -> StatefulHost:
        """Return an empty loaded project that can reach model confirmation."""

        host = StatefulHost()
        host.project.folder = Path("/project")
        host.project.all_image_paths = [Path("/project/image.jpg")]
        host.project.session_model_values = {
            "model_weights": "weights/configured.pt",
            "default_class": "table",
        }
        host.project.coco = mock.Mock()
        host.project.coco.annotations_for.return_value = []
        host.project.coco.category_names.return_value = ("table",)
        host.project.coco.annotations_by_image = {"image.jpg": []}
        host.session_default_class_var = mock.Mock()
        host.session_default_class_var.get.return_value = "table"
        host.root = mock.Mock()
        return host

    @staticmethod
    def configuration(weights_path: Path) -> ModelRunConfiguration:
        """Return a valid configuration that stops at confirmation."""

        return ModelRunConfiguration(
            weights_path=weights_path,
            model_type="detection",
            checkpoint_model_name="RFDETRMedium",
            input_resolution=1024,
            num_classes=1,
            threshold=0.5,
            class_names={0: "table"},
            threshold_source=weights_path.with_suffix(".conf"),
        )

    def test_configured_weights_bypass_picker(self) -> None:
        """BUG-2026-10-05-CONFIGURED-MODEL-WEIGHTS: reuse configuration."""

        host = self.model_host()
        configured = Path("/project/weights/configured.pt")

        with (
            mock.patch(
                "annotator.gui.model.run.active_model_weights_path",
                return_value=configured,
            ),
            mock.patch(
                "annotator.gui.model.run.prompt_for_weights",
                return_value=configured,
            ) as picker,
            mock.patch(
                "annotator.gui.model.run.configure_model_run",
                return_value=self.configuration(configured),
            ) as configure,
            mock.patch(
                "annotator.gui.model.run.messagebox.askokcancel",
                return_value=False,
            ),
        ):
            run_model(host)

        picker.assert_not_called()
        self.assertEqual(configure.call_args.args[0], configured)

    def test_missing_configuration_uses_picker_selection(self) -> None:
        """No configured path retains interactive weights selection."""

        host = self.model_host()
        selected = Path("/chosen/model.pt")

        with (
            mock.patch(
                "annotator.gui.model.run.active_model_weights_path",
                return_value=None,
            ),
            mock.patch(
                "annotator.gui.model.run.prompt_for_weights",
                return_value=selected,
            ) as picker,
            mock.patch(
                "annotator.gui.model.run.configure_model_run",
                return_value=self.configuration(selected),
            ) as configure,
            mock.patch(
                "annotator.gui.model.run.messagebox.askokcancel",
                return_value=False,
            ),
        ):
            run_model(host)

        picker.assert_called_once_with(host)
        self.assertEqual(configure.call_args.args[0], selected)

    def test_invalid_configured_path_reports_error_without_picker(self) -> None:
        """BUG-2026-10-05-CONFIGURED-MODEL-WEIGHTS: do not reprompt on error."""

        host = self.model_host()
        configured = Path("/missing/model.pt")

        with (
            mock.patch(
                "annotator.gui.model.run.active_model_weights_path",
                return_value=configured,
            ),
            mock.patch(
                "annotator.gui.model.run.prompt_for_weights"
            ) as picker,
            mock.patch(
                "annotator.gui.model.run.configure_model_run",
                side_effect=FileNotFoundError(configured),
            ),
            mock.patch("annotator.gui.model.run.traceback.print_exc"),
            mock.patch(
                "annotator.gui.model.run.ErrorDetailsDialog"
            ) as error_dialog,
        ):
            run_model(host)

        picker.assert_not_called()
        error_dialog.assert_called_once()
        self.assertIn("FileNotFoundError", error_dialog.call_args.args[2])
