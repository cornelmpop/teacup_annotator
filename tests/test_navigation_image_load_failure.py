"""Regression tests for navigation to an unreadable image."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from annotator.gui.project.navigation import jump_to_image_index_from_entry
from annotator.gui.project.navigation import next_image
from annotator.gui.project.navigation import previous_image
from tests.support import StatefulHost

INVALID_IMAGE_BYTES = b"not a JPEG"
TEMP_POLYGON = [(1.0, 2.0)]


def _host_with_unreadable_target(
    folder: Path,
    current_index: int,
    target_index: int,
) -> tuple[StatefulHost, Image.Image]:
    """Return an editing host whose requested navigation target is unreadable."""

    image_paths = [folder / "a.jpg", folder / "b.jpg"]
    for index, image_path in enumerate(image_paths):
        if index == target_index:
            image_path.write_bytes(INVALID_IMAGE_BYTES)
        else:
            Image.new("RGB", (8, 6), "white").save(image_path)

    host = StatefulHost()
    host.project.image_paths = image_paths
    host.project.current_index = current_index
    displayed_image = Image.new("RGB", (8, 6), "red")
    host.view.current_image = displayed_image
    host.interaction.selected_annotation_index = 2
    host.interaction.selected_annotation_indices = {2}
    host.interaction.mode = "polygon"
    host.interaction.temp_polygon = list(TEMP_POLYGON)
    return host, displayed_image


class NavigationImageLoadFailureTests(unittest.TestCase):
    """Failed navigation keeps the current pixels and editing target aligned."""

    def assert_editing_target_preserved(
        self,
        host: StatefulHost,
        displayed_image: Image.Image,
        expected_index: int,
    ) -> None:
        """Assert the exact index, pixels, selection, and draft edit survive."""

        self.assertEqual(host.project.current_index, expected_index)
        self.assertIs(host.view.current_image, displayed_image)
        self.assertEqual(host.interaction.selected_annotation_index, 2)
        self.assertEqual(host.interaction.selected_annotation_indices, {2})
        self.assertEqual(host.interaction.mode, "polygon")
        self.assertEqual(host.interaction.temp_polygon, TEMP_POLYGON)

    def test_next_image_failure_preserves_current_editing_target(self) -> None:
        """Known-bug regression BUG-2026-09-29-NAVIGATION-IMAGE-LOAD-TARGET."""

        with tempfile.TemporaryDirectory() as temp_dir:
            host, displayed_image = _host_with_unreadable_target(
                Path(temp_dir),
                current_index=0,
                target_index=1,
            )
            with mock.patch(
                "annotator.gui.project.image_loading.messagebox.showerror"
            ) as show_error:
                next_image(host)

        show_error.assert_called_once()
        self.assertEqual(show_error.call_args.args[0], "Could not open image")
        self.assert_editing_target_preserved(host, displayed_image, 0)

    def test_previous_image_failure_preserves_current_editing_target(self) -> None:
        """Known-bug regression BUG-2026-09-29-NAVIGATION-IMAGE-LOAD-TARGET."""

        with tempfile.TemporaryDirectory() as temp_dir:
            host, displayed_image = _host_with_unreadable_target(
                Path(temp_dir),
                current_index=1,
                target_index=0,
            )
            with mock.patch(
                "annotator.gui.project.image_loading.messagebox.showerror"
            ) as show_error:
                previous_image(host)

        show_error.assert_called_once()
        self.assertEqual(show_error.call_args.args[0], "Could not open image")
        self.assert_editing_target_preserved(host, displayed_image, 1)

    def test_index_entry_failure_preserves_current_editing_target(self) -> None:
        """Known-bug regression BUG-2026-09-29-NAVIGATION-IMAGE-LOAD-TARGET."""

        with tempfile.TemporaryDirectory() as temp_dir:
            host, displayed_image = _host_with_unreadable_target(
                Path(temp_dir),
                current_index=0,
                target_index=1,
            )
            host.image_index_var = mock.Mock()
            host.image_index_var.get.return_value = "2"
            host.root = mock.Mock()
            with mock.patch(
                "annotator.gui.project.image_loading.messagebox.showerror"
            ) as show_error:
                result = jump_to_image_index_from_entry(host)

        self.assertEqual(result, "break")
        host.root.bell.assert_not_called()
        show_error.assert_called_once()
        self.assertEqual(show_error.call_args.args[0], "Could not open image")
        self.assert_editing_target_preserved(host, displayed_image, 0)


if __name__ == "__main__":
    unittest.main()
