"""Tests for validating the manual default against a model sidecar."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from tests.support import StatefulHost
from annotator.gui.model.run import run_model
from annotator.model.workflow import ModelRunConfiguration


class ModelDefaultClassValidationTests(unittest.TestCase):
    """A model run cannot start with an unsupported manual default class."""

    def test_mismatch_lists_model_classes_and_stops_before_confirmation(self) -> None:
        """The user receives actionable sidecar class information."""

        host = StatefulHost()
        host.project.folder = Path("/images")
        host.project.coco = mock.Mock()
        host.project.coco.annotations_for.return_value = []
        host.project.coco.category_names.return_value = ("lithics",)
        host.project.coco.annotations_by_image = {"image.jpg": []}
        host.project.all_image_paths = [Path("image.jpg")]
        host.project.session_model_values = {}
        configuration = ModelRunConfiguration(
            weights_path=Path("model.pt"),
            model_type="detection",
            checkpoint_model_name="RFDETRMedium",
            input_resolution=1024,
            num_classes=2,
            threshold=0.5,
            class_names={1: "table", 2: "photo"},
            threshold_source=Path("model.conf"),
        )

        with (
            mock.patch(
                "annotator.gui.model.run.active_model_weights_path",
                return_value=None,
            ),
            mock.patch(
                "annotator.gui.model.run.prompt_for_weights",
                return_value=Path("model.pt"),
            ),
            mock.patch(
                "annotator.gui.model.run.active_default_class",
                return_value="lithics",
            ),
            mock.patch(
                "annotator.gui.model.run.configure_model_run",
                return_value=configuration,
            ),
            mock.patch("annotator.gui.model.run.messagebox.showerror") as showerror,
            mock.patch("annotator.gui.model.run.messagebox.askokcancel") as confirm,
            mock.patch("annotator.gui.model.run.threading.Thread") as thread,
        ):
            run_model(host)

        message = showerror.call_args.args[1]
        self.assertIn("'lithics'", message)
        self.assertIn("table, photo", message)
        self.assertIn("Configuration > Model", message)
        self.assertIn("Default class", message)
        confirm.assert_not_called()
        thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
