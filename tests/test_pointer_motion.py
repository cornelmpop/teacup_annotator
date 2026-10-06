"""Tests for functional pointer motion, leave, and wheel adapters."""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest import mock

from tests.support import StatefulHost
from annotator.gui.input.pointer_motion import on_mouse_leave
from annotator.gui.input.pointer_motion import on_mouse_motion
from annotator.gui.input.pointer_motion import on_mouse_wheel
from annotator.gui.interactions import InputAction


def motion_pointer_host() -> StatefulHost:
    """Return a state owner with mocked motion widgets and rendering effects."""

    host = StatefulHost()
    canvas = mock.Mock()
    canvas.canvasx.side_effect = lambda value: float(value)
    canvas.canvasy.side_effect = lambda value: float(value)
    host.widgets = SimpleNamespace(viewer=SimpleNamespace(canvas=canvas))
    host.prefs = mock.Mock()
    host.prefs.get_bool.return_value = True
    for effect_name in ("set_canvas_cursor",):
        setattr(host, effect_name, mock.Mock(return_value=None))
    return host


class PointerMotionTests(unittest.TestCase):
    """Motion adapters coordinate transition state and view effects."""

    def test_on_mouse_motion_clears_preview_outside_unloaded_image(self) -> None:
        """Outside-image motion refreshes guides, cursor, and preview cleanup."""

        host = motion_pointer_host()

        with (
            mock.patch(
                "annotator.gui.input.pointer_motion.draw_guides"
            ) as draw_guides,
            mock.patch(
                "annotator.gui.input.pointer_motion.draw_snap_preview_dot"
            ) as draw_snap,
            mock.patch(
                "annotator.gui.input.pointer_motion.clear_zoom_preview"
            ) as clear_zoom,
        ):
            on_mouse_motion(host, SimpleNamespace(x=3, y=4))

        self.assertEqual(host.view.cursor_canvas_point, (3.0, 4.0))
        draw_guides.assert_called_once_with(host)
        draw_snap.assert_called_once_with(host)
        clear_zoom.assert_called_once_with(host)
        host.widgets.viewer.canvas.delete.assert_called_with("class_tooltip")

    def test_on_mouse_leave_clears_transient_display_and_redraws_new_mode(
        self,
    ) -> None:
        """Leaving the canvas removes transient art and redraws live polygons."""

        host = motion_pointer_host()
        host.interaction.mode = "new"
        host.view.cursor_canvas_point = (3.0, 4.0)

        with (
            mock.patch(
                "annotator.gui.input.pointer_motion.draw_guides"
            ),
            mock.patch(
                "annotator.gui.input.pointer_motion.clear_zoom_preview"
            ),
            mock.patch("annotator.gui.input.pointer_motion.redraw_canvas") as redraw,
        ):
            on_mouse_leave(host, SimpleNamespace())

        self.assertIsNone(host.view.cursor_canvas_point)
        host.widgets.viewer.canvas.delete.assert_any_call("snap_preview")
        host.widgets.viewer.canvas.delete.assert_any_call("class_tooltip")
        redraw.assert_called_once_with(host)

    def test_known_bug_regression_new_polygon_motion_avoids_full_redraw(
        self,
    ) -> None:
        """Known-bug regression: Adler2002_403_0_7 refreshes transient art only."""

        host = motion_pointer_host()
        host.interaction.mode = "new"
        host.view.current_image = mock.sentinel.image
        host.view.display_size = (100, 100)
        transition = SimpleNamespace(
            action=InputAction.MOTION_NEW_POLYGON,
            interaction=host.interaction,
        )

        with (
            mock.patch(
                "annotator.gui.input.pointer_motion.mouse_motion_transition",
                return_value=transition,
            ),
            mock.patch("annotator.gui.input.pointer_motion.draw_guides"),
            mock.patch("annotator.gui.input.pointer_motion.draw_snap_preview_dot"),
            mock.patch("annotator.gui.input.pointer_motion.draw_temp_polygon") as draw_temp,
            mock.patch(
                "annotator.gui.input.pointer_motion.draw_new_snap_context_vertices"
            ) as draw_context,
            mock.patch("annotator.gui.input.pointer_motion.redraw_canvas") as redraw,
            mock.patch("annotator.gui.input.pointer_motion.update_zoom_preview") as zoom,
            mock.patch(
                "annotator.gui.input.pointer_motion.update_hover_class_tooltip"
            ) as tooltip,
        ):
            on_mouse_motion(host, SimpleNamespace(x=3, y=4))

        redraw.assert_not_called()
        draw_temp.assert_called_once_with(host)
        draw_context.assert_called_once_with(host)
        zoom.assert_called_once_with(host, (3.0, 4.0))
        tooltip.assert_called_once_with(host, (3.0, 4.0), (3.0, 4.0))
        for tag in ("temp_polygon", "temp_vertex", "snap_context_vertex"):
            host.widgets.viewer.canvas.delete.assert_any_call(tag)

    def test_new_polygon_motion_outside_image_clears_preview_without_zoom(
        self,
    ) -> None:
        """New-polygon motion outside the image does not pass None to zoom."""

        host = motion_pointer_host()
        host.interaction.mode = "new"
        host.view.current_image = mock.sentinel.image
        host.view.display_size = (10, 10)

        with (
            mock.patch("annotator.gui.input.pointer_motion.draw_guides"),
            mock.patch("annotator.gui.input.pointer_motion.draw_snap_preview_dot"),
            mock.patch("annotator.gui.input.pointer_motion.draw_temp_polygon") as draw_temp,
            mock.patch(
                "annotator.gui.input.pointer_motion.draw_new_snap_context_vertices"
            ) as draw_context,
            mock.patch(
                "annotator.gui.input.pointer_motion.clear_zoom_preview"
            ) as clear_zoom,
            mock.patch("annotator.gui.input.pointer_motion.update_zoom_preview") as zoom,
            mock.patch(
                "annotator.gui.input.pointer_motion.update_hover_class_tooltip"
            ) as tooltip,
        ):
            on_mouse_motion(host, SimpleNamespace(x=50, y=50))

        draw_temp.assert_called_once_with(host)
        draw_context.assert_called_once_with(host)
        clear_zoom.assert_called_once_with(host)
        zoom.assert_not_called()
        tooltip.assert_not_called()

    def test_on_mouse_wheel_routes_zoom_and_scroll_effects(self) -> None:
        """Normalized wheel actions call the explicit viewport functions."""

        host = motion_pointer_host()
        event = SimpleNamespace(x=3, y=4)
        with (
            mock.patch(
                "annotator.gui.input.pointer_motion.wheel_axis_and_direction",
                return_value=(True, -1),
            ),
            mock.patch("annotator.gui.input.pointer_motion.zoom_at") as zoom,
            mock.patch(
                "annotator.gui.input.pointer_motion.scroll_by_wheel"
            ) as scroll,
            mock.patch(
                "annotator.gui.input.pointer_motion.draw_guides"
            ) as draw_guides,
        ):
            host.interaction.z_down = True
            self.assertEqual(on_mouse_wheel(host, event), "break")
            zoom.assert_called_once_with(host, 1, 3, 4)
            scroll.assert_not_called()

            host.interaction.z_down = False
            zoom.reset_mock()
            self.assertEqual(on_mouse_wheel(host, event), "break")
            scroll.assert_called_once_with(
                host,
                horizontal=True,
                direction=-1,
            )
            draw_guides.assert_called_once_with(host)

    def test_on_mouse_wheel_applies_horizontal_reverse_preference(self) -> None:
        """Main-viewer horizontal scrolling uses the configured direction."""

        host = motion_pointer_host()
        event = SimpleNamespace(x=3, y=4, delta=-120, num=None, state=1)
        with (
            mock.patch("annotator.gui.input.pointer_motion.scroll_by_wheel") as scroll,
            mock.patch("annotator.gui.input.pointer_motion.draw_guides"),
        ):
            host.prefs.get_bool.return_value = True
            on_mouse_wheel(host, event)
            host.prefs.get_bool.return_value = False
            on_mouse_wheel(host, event)

        self.assertEqual(
            [call.kwargs["direction"] for call in scroll.call_args_list],
            [-1, 1],
        )

    def test_horizontal_reverse_preference_applies_with_zoom_modifier(self) -> None:
        """The main viewer no longer bypasses horizontal reversal while zooming."""

        host = motion_pointer_host()
        host.interaction.z_down = True
        event = SimpleNamespace(x=3, y=4, delta=-120, num=None, state=1)
        with mock.patch("annotator.gui.input.pointer_motion.zoom_at") as zoom:
            host.prefs.get_bool.return_value = True
            on_mouse_wheel(host, event)
            host.prefs.get_bool.return_value = False
            on_mouse_wheel(host, event)

        self.assertEqual(
            [call.args[1] for call in zoom.call_args_list],
            [1, -1],
        )


if __name__ == "__main__":
    unittest.main()
