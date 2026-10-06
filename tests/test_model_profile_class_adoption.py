"""Tests for adopting model-profile classes over an unused placeholder."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import unittest
from unittest import mock

from annotator.coco import CocoDocument
from annotator.gui.model.run import run_model
from annotator.model.workflow import ModelRunConfiguration
from tests.support import StatefulHost


MODEL_CLASS_NAMES = (
    "diagram_plot",
    "diagram_other",
    "map_image",
    "lithics",
    "map_illustration",
    "CMP",
    "photos",
    "photos_lithics",
    "table",
)
MODEL_CLASS_COLOURS = tuple(f"#{index:06x}" for index in range(1, 10))


def model_configuration() -> ModelRunConfiguration:
    """Return the selected model configuration from the reported profile."""

    return ModelRunConfiguration(
        weights_path=Path("detect_figs.pt"),
        model_type="detection",
        checkpoint_model_name="RFDETRMedium",
        input_resolution=1008,
        num_classes=8,
        threshold=0.3,
        class_names=dict(enumerate(MODEL_CLASS_NAMES)),
        threshold_source=Path("detect_figs.conf"),
    )


def model_run_host(placeholder_name: str = "object") -> StatefulHost:
    """Return an empty project whose only category is the default placeholder."""

    host = StatefulHost()
    image_path = Path("/images/image.jpg")
    host.root = mock.Mock()
    host.log = mock.Mock()
    host.project.folder = image_path.parent
    host.project.all_image_paths = [image_path]
    host.project.image_paths = [image_path]
    host.project.coco = CocoDocument(image_path.parent, [image_path])
    host.project.coco.categories = [
        {
            "id": 1,
            "name": placeholder_name,
            "supercategory": "object",
        }
    ]
    host.project.sql_connection = mock.Mock()
    host.project.session_model_values = {}
    host.project.session_class_names = ()
    host.project.session_class_colours = ()
    host.project.using_local_class_settings = False
    host.prefs = mock.Mock()
    host.prefs.values = {"default_class": "object"}
    host.prefs.get_default_class.return_value = "object"
    host.prefs.get_class_colours.return_value = MODEL_CLASS_COLOURS
    selected_class = {"value": "object"}
    host.session_default_class_var = mock.Mock()
    host.session_default_class_var.get.side_effect = lambda: selected_class["value"]
    host.session_default_class_var.set.side_effect = (
        lambda value: selected_class.update(value=value)
    )
    return host


def run_with_selected_model(
    host: StatefulHost,
) -> tuple[mock.Mock, mock.Mock, mock.Mock, mock.Mock, mock.Mock]:
    """Run preflight with GUI, persistence, and worker effects observed."""

    def save_classes(
        _host: StatefulHost,
        class_names: tuple[str, ...],
        class_colours: tuple[str, ...],
    ) -> bool:
        host.project.session_class_names = class_names
        host.project.session_class_colours = class_colours
        host.project.using_local_class_settings = True
        return True

    stack = ExitStack()
    stack.enter_context(
        mock.patch(
            "annotator.gui.model.run.prompt_for_weights",
            return_value=Path("detect_figs.pt"),
        )
    )
    stack.enter_context(
        mock.patch(
            "annotator.gui.model.run.configure_model_run",
            return_value=model_configuration(),
        )
    )
    stack.enter_context(
        mock.patch(
            "annotator.gui.model.run.active_class_colours",
            return_value=MODEL_CLASS_COLOURS,
            create=True,
        )
    )
    save = stack.enter_context(
        mock.patch(
            "annotator.gui.model.run.save_local_class_values",
            side_effect=save_classes,
            create=True,
        )
    )
    refresh = stack.enter_context(
        mock.patch(
            "annotator.gui.model.run.refresh_after_local_class_change",
            create=True,
        )
    )
    showerror = stack.enter_context(
        mock.patch("annotator.gui.model.run.messagebox.showerror")
    )
    confirm = stack.enter_context(
        mock.patch(
            "annotator.gui.model.run.messagebox.askokcancel",
            return_value=False,
        )
    )
    stack.enter_context(
        mock.patch(
            "annotator.gui.model.run.messagebox.askyesno",
            return_value=True,
        )
    )
    thread = stack.enter_context(
        mock.patch("annotator.gui.model.run.threading.Thread")
    )
    with stack:
        run_model(host)
    return save, refresh, showerror, confirm, thread


class ModelProfileClassAdoptionTests(unittest.TestCase):
    """Model preflight adopts classes only over an unused default vocabulary."""

    def test_unused_placeholder_adopts_profile_classes_in_file_order(self) -> None:
        """BUG-2026-09-28-RUN-MODEL-PROFILE-CLASSES: adopt all nine classes."""

        host = model_run_host()

        save, refresh, showerror, confirm, thread = run_with_selected_model(host)

        self.assertEqual(host.project.coco.category_names(), MODEL_CLASS_NAMES)
        self.assertEqual(
            [category["id"] for category in host.project.coco.categories],
            list(range(1, 10)),
        )
        self.assertEqual(host.session_default_class_var.get(), "diagram_plot")
        save.assert_called_once_with(host, MODEL_CLASS_NAMES, MODEL_CLASS_COLOURS)
        refresh.assert_called_once_with(host)
        showerror.assert_not_called()
        confirm.assert_called_once()
        thread.assert_not_called()

    def test_custom_classes_preserve_default_mismatch(self) -> None:
        """BUG-2026-09-28-RUN-MODEL-PROFILE-CLASSES: custom classes stay owned."""

        host = model_run_host()
        host.project.coco.categories = [
            {"id": 1, "name": "artifact", "supercategory": "object"}
        ]
        host.project.using_local_class_settings = True
        host.project.session_class_names = ("artifact",)
        host.session_default_class_var.set("artifact")

        save, refresh, showerror, confirm, thread = run_with_selected_model(host)

        self.assertEqual(host.project.coco.category_names(), ("artifact",))
        save.assert_not_called()
        refresh.assert_not_called()
        showerror.assert_called_once()
        confirm.assert_not_called()
        thread.assert_not_called()

    def test_reloaded_unused_placeholder_adopts_profile_classes(self) -> None:
        """BUG-2026-09-28-RUN-MODEL-PROFILE-CLASSES: ignore the loader proxy."""

        host = model_run_host()
        host.project.using_local_class_settings = True
        host.project.session_class_names = ("object",)

        save, refresh, showerror, confirm, thread = run_with_selected_model(host)

        self.assertEqual(host.project.coco.category_names(), MODEL_CLASS_NAMES)
        self.assertEqual(host.session_default_class_var.get(), "diagram_plot")
        save.assert_called_once_with(host, MODEL_CLASS_NAMES, MODEL_CLASS_COLOURS)
        refresh.assert_called_once_with(host)
        showerror.assert_not_called()
        confirm.assert_called_once()
        thread.assert_not_called()

    def test_persisted_unused_placeholder_adopts_profile_classes(self) -> None:
        """BUG-2026-10-05-PERSISTED-DEFAULT-CLASS: adopt over `__DEFAULT__`."""

        host = model_run_host("__DEFAULT__")
        host.prefs.values = {"default_class": "__DEFAULT__"}
        host.prefs.get_default_class.return_value = "__DEFAULT__"
        host.session_default_class_var.set("__DEFAULT__")

        save, refresh, showerror, confirm, thread = run_with_selected_model(host)

        self.assertEqual(host.project.coco.category_names(), MODEL_CLASS_NAMES)
        self.assertEqual(host.session_default_class_var.get(), "diagram_plot")
        save.assert_called_once_with(host, MODEL_CLASS_NAMES, MODEL_CLASS_COLOURS)
        refresh.assert_called_once_with(host)
        showerror.assert_not_called()
        confirm.assert_called_once()
        thread.assert_not_called()

    def test_used_persisted_placeholder_is_preserved(self) -> None:
        """BUG-2026-10-05-PERSISTED-DEFAULT-CLASS: keep referenced sentinel."""

        host = model_run_host("__DEFAULT__")
        host.prefs.values = {"default_class": "__DEFAULT__"}
        host.prefs.get_default_class.return_value = "__DEFAULT__"
        host.session_default_class_var.set("__DEFAULT__")
        host.project.coco.add_annotation(
            "image.jpg",
            [(1.0, 1.0), (5.0, 1.0), (5.0, 5.0), (1.0, 5.0)],
        )

        save, refresh, showerror, confirm, thread = run_with_selected_model(host)

        self.assertEqual(host.project.coco.category_names(), ("__DEFAULT__",))
        save.assert_not_called()
        refresh.assert_not_called()
        showerror.assert_called_once()
        confirm.assert_not_called()
        thread.assert_not_called()

    def test_used_placeholder_preserves_default_mismatch(self) -> None:
        """BUG-2026-09-28-RUN-MODEL-PROFILE-CLASSES: used classes stay owned."""

        host = model_run_host()
        host.project.coco.add_annotation(
            "image.jpg",
            [(1.0, 1.0), (5.0, 1.0), (5.0, 5.0), (1.0, 5.0)],
        )

        save, refresh, showerror, confirm, thread = run_with_selected_model(host)

        self.assertEqual(host.project.coco.category_names(), ("object",))
        save.assert_not_called()
        refresh.assert_not_called()
        showerror.assert_called_once()
        confirm.assert_not_called()
        thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
