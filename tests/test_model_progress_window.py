"""Tests for the model progress-window lifecycle."""

from __future__ import annotations

import queue
import unittest
from pathlib import Path
from unittest import mock

from tests.support import StatefulHost
from annotator.gui.model.run import run_model
from annotator.gui.model.worker import poll_worker_queue
from annotator.gui.model.worker import run_model_worker
from annotator.gui.model.worker import set_model_progress
from annotator.model.workflow import ModelRunConfiguration


class ModelProgressWindowTests(unittest.TestCase):
    """Model progress updates one popup and closes it when processing ends."""

    def test_model_run_opens_progress_window(self) -> None:
        """Starting the worker opens the shared progress window."""

        host = StatefulHost()
        host.project.folder = Path("/images")
        host.project.coco = mock.Mock()
        host.project.coco.annotations_for.return_value = []
        host.project.coco.category_names.return_value = ("object", "table")
        host.project.coco.annotations_by_image = {"image.jpg": []}
        host.project.all_image_paths = [Path("image.jpg")]
        host.project.using_folder_model_conf = True
        host.project.session_model_values = {"default_threshold": "0.63"}
        host.prefs = mock.Mock()
        host.session_default_class_var = mock.Mock()
        host.session_default_class_var.get.return_value = "object"
        host.root = mock.Mock()
        host.log = mock.Mock()
        host.interaction.worker_running = False
        configuration = ModelRunConfiguration(
            weights_path=Path("model.pt"),
            model_type="detection",
            checkpoint_model_name="RFDETRMedium",
            input_resolution=1024,
            num_classes=1,
            threshold=0.63,
            class_names={1: "object"},
            threshold_source=Path("/images/model.conf"),
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
                "annotator.gui.model.run.configure_model_run",
                return_value=configuration,
            ),
            mock.patch(
                "annotator.gui.model.run.messagebox.askokcancel",
                return_value=True,
            ) as confirmation_dialog,
            mock.patch("annotator.gui.model.run.ProgressDialog") as progress_dialog,
            mock.patch("annotator.gui.model.run.threading.Thread") as thread,
            mock.patch("annotator.gui.model.run.redraw_canvas") as redraw,
            mock.patch(
                "annotator.gui.model.run.clear_view_interaction_state",
                side_effect=lambda host: self.assertFalse(
                    host.interaction.worker_running
                ),
            ) as clear_interaction,
            mock.patch("annotator.gui.model.run.update_buttons") as buttons,
        ):
            run_model(host)

        progress_dialog.assert_called_once_with(
            host.root,
            "RF-DETR object-detection",
            "Running object-detection model — editing disabled",
            "Starting object-detection model",
        )
        clear_interaction.assert_called_once_with(host)
        redraw.assert_called_once_with(host)
        buttons.assert_called_once_with(host)
        confirmation = confirmation_dialog.call_args.args[1]
        self.assertIn("1024 x 1024", confirmation)
        self.assertIn("only mode currently supported", confirmation)
        self.assertIn("confidence threshold of 0.63", confirmation)
        self.assertIn("/images/model.conf", confirmation)
        worker_args = thread.call_args.kwargs["args"]
        self.assertEqual(worker_args, (host, configuration))
        thread.return_value.start.assert_called_once_with()

    def test_missing_model_sidecar_reports_gui_and_terminal_error(self) -> None:
        """A preflight configuration failure is visible in both interfaces."""

        host = StatefulHost()
        host.project.folder = Path("/images")
        host.project.coco = mock.Mock()
        host.project.coco.annotations_for.return_value = []
        host.project.coco.category_names.return_value = ("object",)
        host.project.coco.annotations_by_image = {"image.jpg": []}
        host.project.all_image_paths = [Path("image.jpg")]
        host.project.session_model_values = {}
        host.root = mock.Mock()

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
                "annotator.gui.model.run.configure_model_run",
                side_effect=FileNotFoundError("model.conf"),
            ),
            mock.patch("annotator.gui.model.run.traceback.print_exc") as print_exc,
            mock.patch("annotator.gui.model.run.ErrorDetailsDialog") as error_dialog,
            mock.patch("annotator.gui.model.run.threading.Thread") as thread,
        ):
            run_model(host)

        print_exc.assert_called_once_with()
        details = error_dialog.call_args.args[2]
        self.assertIn("Traceback (most recent call last)", details)
        self.assertIn("FileNotFoundError: model.conf", details)
        thread.assert_not_called()

    def test_worker_key_error_reaches_scrollable_dialog_as_traceback(self) -> None:
        """Runtime exceptions retain their traceback through the GUI boundary."""

        host = StatefulHost()
        host.project.all_image_paths = [Path("image.jpg")]
        host.worker_queue = queue.Queue()
        host.interaction.worker_running = True
        host.root = mock.Mock()
        host.model_progress_dialog = mock.Mock()
        host.log = mock.Mock()
        configuration = ModelRunConfiguration(
            weights_path=Path("model.pt"),
            model_type="detection",
            checkpoint_model_name="RFDETRMedium",
            input_resolution=1024,
            num_classes=1,
            threshold=0.5,
            class_names={1: "object"},
            threshold_source=Path("model.conf"),
        )

        with (
            mock.patch(
                "annotator.gui.model.worker.execute_model_run",
                side_effect=KeyError(9),
            ),
            mock.patch("annotator.gui.model.worker.traceback.print_exc"),
        ):
            run_model_worker(host, configuration)

        finish_result = mock.Mock()
        with (
            mock.patch("annotator.gui.model.worker.ErrorDetailsDialog") as error_dialog,
            mock.patch("annotator.gui.model.worker.update_buttons") as buttons,
        ):
            poll_worker_queue(host, finish_result)

        details = error_dialog.call_args.args[2]
        self.assertIn("Traceback (most recent call last)", details)
        self.assertIn("KeyError: 9", details)
        buttons.assert_called_once_with(host)

    def test_successful_worker_progress_and_result_reach_tk_poll(self) -> None:
        """Worker progress and completion are delivered in queue order."""

        host = StatefulHost()
        host.project.all_image_paths = [Path("image.jpg")]
        host.worker_queue = queue.Queue()
        host.root = mock.Mock()
        host.model_progress_dialog = mock.Mock()
        host.log = mock.Mock()
        configuration = mock.sentinel.configuration

        def execute(_paths, _configuration, progress):
            """Publish one progress update before returning a result."""

            progress(50, "Detecting image.jpg")
            return mock.sentinel.result

        with mock.patch(
            "annotator.gui.model.worker.execute_model_run",
            side_effect=execute,
        ):
            run_model_worker(host, configuration)

        finish_result = mock.Mock()
        poll_worker_queue(host, finish_result)

        host.model_progress_dialog.update_progress.assert_called_once_with(
            50,
            "Detecting image.jpg",
        )
        host.log.assert_called_once_with("Detecting image.jpg")
        finish_result.assert_called_once_with(host, mock.sentinel.result)
        host.root.after.assert_called_once_with(
            100,
            poll_worker_queue,
            host,
            finish_result,
        )

    def test_progress_window_updates_and_closes(self) -> None:
        """Progress messages update the window; no message closes it."""

        host = StatefulHost()
        host.model_progress_dialog = mock.Mock()
        dialog = host.model_progress_dialog

        set_model_progress(host, 25, "Loading model")
        dialog.update_progress.assert_called_once_with(25, "Loading model")

        set_model_progress(host, 100)
        dialog.close.assert_called_once_with()
        self.assertIsNone(host.model_progress_dialog)
