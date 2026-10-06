"""Tests for project status and control synchronization."""

from __future__ import annotations

from functools import partial
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.support import StatefulHost
from annotator.gui.project.deletion import mark_current_image_for_deletion
from annotator.gui.project.deletion import restore_current_image_from_trash
from annotator.gui.project.status import update_buttons
from annotator.gui.project.status import update_image_status


class ProjectStatusTests(unittest.TestCase):
    """Status helpers synchronize labels, entries, and enabled controls."""

    def test_update_image_status_reports_empty_filtered_result(self) -> None:
        """A loaded folder with no visible images names the active filter."""

        host = StatefulHost()
        host.root = mock.Mock()
        host.root.focus_get.return_value = None
        host.image_index_var = mock.Mock()
        host.image_index_var.get.return_value = "1"
        host.project.all_image_paths = [Path("a.jpg")]
        host.project.image_paths = []
        host.project.active_filter = "animal"
        host.widgets = SimpleNamespace(
            viewer=SimpleNamespace(
                image_count_label=mock.Mock(),
                image_status=mock.Mock(),
                image_index_entry=mock.Mock(),
            )
        )

        update_image_status(host)

        host.image_index_var.set.assert_called_once_with("")
        host.widgets.viewer.image_count_label.configure.assert_called_once_with(
            text="/ 0 filtered of 1"
        )
        host.widgets.viewer.image_status.configure.assert_called_once_with(
            text="No images match filter: animal"
        )

    def test_update_buttons_disables_image_actions_without_visible_images(self) -> None:
        """Toolbar and navigation controls follow loaded and visible image state."""

        host = StatefulHost()
        host.project.all_image_paths = [Path("a.jpg")]
        host.project.image_paths = []
        host.interaction.worker_running = False
        host.toolbar_icons = {
            "delete": mock.sentinel.delete,
            "flag": mock.Mock(),
            "flag_off": mock.Mock(),
            "restore": mock.sentinel.restore,
        }
        toolbar = SimpleNamespace(
            load_button=mock.Mock(),
            run_button=mock.Mock(),
            save_button=mock.Mock(),
            archive_button=mock.Mock(),
            config_button=mock.Mock(),
            filter_button=mock.Mock(),
            filter_dropdown=mock.Mock(),
            delete_image_button=mock.Mock(),
            delete_image_tooltip=mock.Mock(),
            reset_zoom_button=mock.Mock(),
            flag_review_button=mock.Mock(),
            view_flagged_button=mock.Mock(),
        )
        viewer = SimpleNamespace(
            previous_button=mock.Mock(),
            next_button=mock.Mock(),
            image_index_entry=mock.Mock(),
        )
        host.widgets = SimpleNamespace(toolbar=toolbar, viewer=viewer)

        with mock.patch(
            "annotator.gui.input.viewport.update_canvas_cursor"
        ) as update_cursor:
            update_buttons(host)

        toolbar.load_button.configure.assert_called_once_with(state=tk.NORMAL)
        toolbar.run_button.configure.assert_called_once_with(state=tk.NORMAL)
        delete_call = toolbar.delete_image_button.configure.call_args.kwargs
        self.assertEqual(delete_call["image"], host.toolbar_icons["delete"])
        self.assertEqual(delete_call["state"], tk.DISABLED)
        self.assertIsInstance(delete_call["command"], partial)
        self.assertIs(delete_call["command"].func, mark_current_image_for_deletion)
        self.assertEqual(delete_call["command"].args, (host,))
        toolbar.delete_image_tooltip.set_text.assert_called_once_with("Delete")
        viewer.previous_button.configure.assert_called_once_with(state=tk.DISABLED)
        viewer.next_button.configure.assert_called_once_with(state=tk.DISABLED)
        viewer.image_index_entry.configure.assert_called_once_with(
            state=tk.DISABLED
        )
        toolbar.flag_review_button.configure.assert_called_once_with(
            image=host.toolbar_icons["flag"],
            state="disabled",
        )
        toolbar.view_flagged_button.configure.assert_called_once_with(
            text="View flagged",
            state="normal",
        )
        update_cursor.assert_called_once_with(host)

    def test_update_buttons_switches_marked_image_to_restore_action(self) -> None:
        """Known-bug regression restore_marked_image_button_clears_stale_deletion_2026-08-26."""

        host = StatefulHost()
        host.project.all_image_paths = [Path("/images/a.jpg")]
        host.project.image_paths = [Path("/images/a.jpg")]
        host.project.deletion_marks = {"a.jpg"}
        host.project.current_index = 0
        host.interaction.worker_running = False
        host.toolbar_icons = {
            "delete": mock.sentinel.delete,
            "flag": mock.Mock(),
            "flag_off": mock.Mock(),
            "restore": mock.sentinel.restore,
        }
        toolbar = SimpleNamespace(
            load_button=mock.Mock(),
            run_button=mock.Mock(),
            save_button=mock.Mock(),
            archive_button=mock.Mock(),
            config_button=mock.Mock(),
            filter_button=mock.Mock(),
            filter_dropdown=mock.Mock(),
            delete_image_button=mock.Mock(),
            delete_image_tooltip=mock.Mock(),
            reset_zoom_button=mock.Mock(),
            flag_review_button=mock.Mock(),
            view_flagged_button=mock.Mock(),
        )
        viewer = SimpleNamespace(
            previous_button=mock.Mock(),
            next_button=mock.Mock(),
            image_index_entry=mock.Mock(),
        )
        host.widgets = SimpleNamespace(toolbar=toolbar, viewer=viewer)

        with mock.patch("annotator.gui.input.viewport.update_canvas_cursor"):
            update_buttons(host)

        delete_call = toolbar.delete_image_button.configure.call_args.kwargs
        self.assertEqual(delete_call["image"], host.toolbar_icons["restore"])
        self.assertEqual(delete_call["state"], tk.NORMAL)
        self.assertIsInstance(delete_call["command"], partial)
        self.assertIs(delete_call["command"].func, restore_current_image_from_trash)
        self.assertEqual(delete_call["command"].args, (host,))
        toolbar.delete_image_tooltip.set_text.assert_called_once_with(
            "Restore from trash"
        )


if __name__ == "__main__":
    unittest.main()
