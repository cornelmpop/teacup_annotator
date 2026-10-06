"""Tests for the typed navigation and canvas builder."""

from __future__ import annotations

from functools import partial
import tkinter as tk
import unittest
from unittest import mock

from annotator.gui.project.navigation import jump_to_image_index_from_entry
from annotator.gui.project.navigation import next_image
from annotator.gui.project.navigation import previous_image
from annotator.gui.window.state import ViewerWidgets
from annotator.gui.window.viewer import build_viewer


class WindowViewerTests(unittest.TestCase):
    """Viewer construction returns the controls used by semantic controllers."""

    def test_build_viewer_returns_navigation_and_canvas_widgets(self) -> None:
        """CODEX: BUG-2026-10-04-TK9-VIEWER-GEOMETRY.

        CODEX: The viewer owns stable scrollbar pixels and publishes its widgets.
        """

        host = mock.Mock()
        host.image_index_var = mock.sentinel.image_index_var
        frames = [mock.Mock(name=f"frame_{index}") for index in range(4)]
        previous_button = mock.Mock()
        next_button = mock.Mock()
        image_index_entry = mock.Mock()
        image_count_label = mock.Mock()
        image_status = mock.Mock()
        canvas = mock.Mock()
        scrollbars = [mock.Mock(), mock.Mock()]

        with (
            mock.patch(
                "annotator.gui.window.viewer.ttk.Frame",
                side_effect=frames,
            ),
            mock.patch(
                "annotator.gui.window.viewer.ttk.Button",
                side_effect=[previous_button, next_button],
            ) as button_factory,
            mock.patch(
                "annotator.gui.window.viewer.ttk.Entry",
                return_value=image_index_entry,
            ),
            mock.patch(
                "annotator.gui.window.viewer.ttk.Label",
                side_effect=[image_count_label, image_status],
            ),
            mock.patch(
                "annotator.gui.window.viewer.tk.Canvas",
                return_value=canvas,
            ),
            mock.patch(
                "annotator.gui.window.viewer.tk.Scrollbar",
                side_effect=scrollbars,
            ) as scrollbar_factory,
            mock.patch(
                "annotator.gui.window.viewer.ttk.Scrollbar",
                side_effect=scrollbars,
            ) as themed_scrollbar_factory,
        ):
            widgets = build_viewer(host, mock.sentinel.parent)

        self.assertIsInstance(widgets, ViewerWidgets)
        self.assertEqual(
            widgets,
            ViewerWidgets(
                previous_button=previous_button,
                next_button=next_button,
                image_index_entry=image_index_entry,
                image_count_label=image_count_label,
                image_status=image_status,
                canvas=canvas,
            ),
        )
        previous_command = button_factory.call_args_list[0].kwargs["command"]
        next_command = button_factory.call_args_list[1].kwargs["command"]
        self.assertIsInstance(previous_command, partial)
        self.assertIs(previous_command.func, previous_image)
        self.assertEqual(previous_command.args, (host,))
        self.assertIsInstance(next_command, partial)
        self.assertIs(next_command.func, next_image)
        self.assertEqual(next_command.args, (host,))
        return_bind = image_index_entry.bind.call_args_list[0].args[1]
        keypad_bind = image_index_entry.bind.call_args_list[1].args[1]
        self.assertIsInstance(return_bind, partial)
        self.assertIs(return_bind.func, jump_to_image_index_from_entry)
        self.assertEqual(return_bind.args, (host,))
        self.assertIsInstance(keypad_bind, partial)
        self.assertIs(keypad_bind.func, jump_to_image_index_from_entry)
        self.assertEqual(keypad_bind.args, (host,))
        self.assertEqual(
            [call.args[0] for call in image_index_entry.bind.call_args_list],
            ["<Return>", "<KP_Enter>"],
        )
        self.assertEqual(
            scrollbar_factory.call_args_list,
            [
                mock.call(
                    frames[3],
                    orient=tk.HORIZONTAL,
                    command=canvas.xview,
                    width=14,
                ),
                mock.call(
                    frames[3],
                    orient=tk.VERTICAL,
                    command=canvas.yview,
                    width=14,
                ),
            ],
        )
        themed_scrollbar_factory.assert_not_called()
        canvas.configure.assert_called_once_with(
            xscrollcommand=scrollbars[0].set,
            yscrollcommand=scrollbars[1].set,
        )


if __name__ == "__main__":
    unittest.main()
