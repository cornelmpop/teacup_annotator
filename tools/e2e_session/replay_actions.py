"""CODEX: Dispatch parsed session actions to Tk widgets and app effects."""

from __future__ import annotations

import re
import sys
import tkinter as tk
from tkinter import ttk
from typing import Any
from typing import cast

from tools.e2e_session.fixture_file_paths import validate_fixture_file_token
from tools.e2e_session.model_assets import MODEL_ASSET_PREFIX
from tools.e2e_session.model_assets import MODEL_WEIGHT_DIALOG_TITLES
from tools.e2e_session.model_assets import validate_model_asset_token
from tools.e2e_session.replay_assertions import assert_entry_observations
from tools.e2e_session.replay_assertions import assert_loaded_fields
from tools.e2e_session.replay_configuration import replay_configuration_choose
from tools.e2e_session.replay_configuration import replay_configuration_save
from tools.e2e_session.replay_runtime import ExpectedDialog
from tools.e2e_session.replay_runtime import ReplayRuntime
from tools.e2e_session.replay_setup import parse_size
from tools.e2e_session.replay_setup import ReplaySetup
from tools.e2e_session.session_action_registry import action_definition
from tools.e2e_session.session_action_registry import command_definition
from tools.e2e_session.session_format import SessionEntry
from tools.e2e_session.session_commands import dispatch_session_command


MODEL_FAILURE_DIALOG_TIMEOUT_MS = 30_000
WORKER_IDLE_TIMEOUT_MS = 30_000


class ReplayActionDispatcher:
    """CODEX: Execute session actions against one live application instance."""

    def __init__(
        self,
        app: Any,
        runtime: ReplayRuntime,
        setup: ReplaySetup,
        actions: tuple[SessionEntry, ...] = (),
    ) -> None:
        """CODEX: Store the live app, replay runtime, and setup facts."""

        self.app = app
        self.runtime = runtime
        self.setup = setup
        self.dialog_expectations = _queue_dialog_expectations(runtime, actions)

    def dispatch(self, entry: SessionEntry) -> None:
        """CODEX: Run one parsed action and then check its observations."""

        definition = action_definition("session", entry.verb)
        if definition is None or definition.replay_method is None:
            raise AssertionError(f"{entry.location}: unsupported action {entry.verb}")
        handler = getattr(self, definition.replay_method, None)
        if handler is None:
            raise AssertionError(
                f"{entry.location}: missing replay handler for {entry.verb}"
            )
        requires_idle = definition.waits_for_worker
        requires_command_idle = self._command_waits_for_worker(entry)
        if requires_idle or requires_command_idle:
            self.runtime.wait_until(
                lambda: not self.app.interaction.worker_running,
                entry.location,
                f"worker to finish before {entry.verb}",
                timeout_ms=WORKER_IDLE_TIMEOUT_MS,
            )
        handler(entry)
        if definition.pumps_after_dispatch:
            self.runtime.pump()
        self.runtime.raise_failures(entry.location)
        if definition.asserts_observations:
            assert_entry_observations(self.app, self.runtime, self.setup, entry)

    def _command_waits_for_worker(self, entry: SessionEntry) -> bool:
        """CODEX: Return whether one semantic command blocks during workers."""

        if entry.verb != "command" or len(entry.arguments) != 1:
            return False
        definition = command_definition(entry.arguments[0])
        return definition is not None and definition.waits_for_worker

    def _dispatch_dialog(self, entry: SessionEntry) -> None:
        """CODEX: Wait for one recorded dialog and return its recorded result."""

        expected = self.dialog_expectations.get(entry)
        if expected is None:
            kind, title, result, arguments = _dialog_spec(entry)
            expected = self.runtime.expect_dialog(kind, title, result, arguments)
        self.runtime.wait_until(
            lambda: expected.observed,
            entry.location,
            f"dialog {expected.title!r}",
            timeout_ms=_dialog_timeout_ms(expected),
        )

    def _dispatch_loaded(self, entry: SessionEntry) -> None:
        """CODEX: Wait for project load and assert the recorded loaded facts."""

        assert_loaded_fields(self.app, self.runtime, self.setup, entry)

    def _dispatch_resize(self, entry: SessionEntry) -> None:
        """CODEX: Apply recorded root geometry and wait for achieved sizes."""

        window_size, canvas_size = _resize_sizes(entry)
        self.app.root.geometry(f"{window_size[0]}x{window_size[1]}")
        self.runtime.wait_until(
            lambda: self.runtime.root_size() == window_size,
            entry.location,
            f"expected window size {_format_size(window_size)}",
            timeout_details=lambda: (
                f"achieved {_format_size(self.runtime.root_size())}"
            ),
        )
        if canvas_size is not None:
            canvas = self.app.widgets.viewer.canvas
            self.runtime.wait_until(
                lambda: self.runtime.canvas_size(canvas) == canvas_size,
                entry.location,
                f"expected canvas size {_format_size(canvas_size)}",
                timeout_details=lambda: (
                    f"achieved {_format_size(self.runtime.canvas_size(canvas))}"
                ),
            )

    def _dispatch_key(self, entry: SessionEntry) -> None:
        """CODEX: Generate one key press or release for the target widget."""

        if len(entry.arguments) != 3:
            raise AssertionError(f"{entry.location}: key requires target phase key")
        target, phase, key = entry.arguments
        if phase not in {"press", "release"}:
            raise AssertionError(f"{entry.location}: key phase must be press or release")
        widget = self._target_widget(target, entry)
        event_name = "KeyPress" if phase == "press" else "KeyRelease"
        if self._is_text_target(widget):
            self._focus_target(widget)
            widget.event_generate(f"<{event_name}>", keysym=key)
            return
        canvas = self.app.widgets.viewer.canvas
        canvas.focus_force()
        self.runtime.pump()
        canvas.event_generate(f"<{event_name}>", keysym=key)

    def _dispatch_submit(self, entry: SessionEntry) -> None:
        """CODEX: Submit a complete field value through its real app callback."""

        if len(entry.arguments) != 2:
            raise AssertionError(f"{entry.location}: submit requires target and value")
        target, value = entry.arguments
        widget = self._target_widget(target, entry)
        if widget != self.app.widgets.viewer.image_index_entry:
            raise AssertionError(
                f"{entry.location}: unsupported submit target {target!r}"
            )
        self.app.image_index_var.set(value)
        from annotator.gui.project.navigation import jump_to_image_index_from_entry

        jump_to_image_index_from_entry(self.app)

    def _dispatch_command(self, entry: SessionEntry) -> None:
        """CODEX: Execute one recorded semantic application command."""

        if len(entry.arguments) != 1:
            raise AssertionError(f"{entry.location}: command requires one name")
        if command_definition(entry.arguments[0]) is None:
            raise AssertionError(
                f"{entry.location}: unknown command action {entry.arguments[0]!r}"
            )
        dispatch_session_command(self.app, entry.arguments[0])

    def _dispatch_new_polygon_point(self, entry: SessionEntry) -> None:
        """CODEX: Add, remove, or close one polygon point semantically."""

        image_point, canvas_point = self._semantic_canvas_point(
            entry,
            "new_polygon_point",
        )
        from annotator.gui.new_polygon_points import add_new_polygon_point

        add_new_polygon_point(self.app, image_point, canvas_point)

    def _dispatch_arrow_point(self, entry: SessionEntry) -> None:
        """CODEX: Apply one arrow base or tip point semantically."""

        image_point, _canvas_point = self._semantic_canvas_point(
            entry,
            "arrow_point",
        )
        from annotator.gui.arrow_editing import handle_arrow_click

        handle_arrow_click(self.app, image_point)

    def _dispatch_scroll(self, entry: SessionEntry) -> None:
        """CODEX: Apply one semantic viewport scroll effect."""

        if len(entry.arguments) != 5:
            raise AssertionError(
                f"{entry.location}: scroll requires target axis direction space point"
            )
        target, axis, direction_text, coordinate_space, point_text = entry.arguments
        widget = self._target_widget(target, entry)
        if widget != self.app.widgets.viewer.canvas:
            raise AssertionError(
                f"{entry.location}: unsupported scroll target {target!r}"
            )
        if axis not in {"horizontal", "vertical"}:
            raise AssertionError(
                f"{entry.location}: scroll axis must be horizontal or vertical"
            )
        # CODEX: Session text is the loose interchange boundary for scroll units.
        direction = int(direction_text)
        self._event_point(
            coordinate_space,
            point_text,
            entry,
        )
        from annotator.gui.canvas_guides import CanvasGuideHost
        from annotator.gui.canvas_guides import draw_guides
        from annotator.gui.input.viewport import scroll_by_wheel

        scroll_by_wheel(self.app, horizontal=axis == "horizontal", direction=direction)
        draw_guides(cast(CanvasGuideHost, self.app))

    def _dispatch_zoom(self, entry: SessionEntry) -> None:
        """CODEX: Apply one semantic pointer-centered viewport zoom effect."""

        if len(entry.arguments) != 4:
            raise AssertionError(
                f"{entry.location}: zoom requires target direction space point"
            )
        target, direction_name, coordinate_space, point_text = entry.arguments
        widget = self._target_widget(target, entry)
        if widget != self.app.widgets.viewer.canvas:
            raise AssertionError(f"{entry.location}: unsupported zoom target {target!r}")
        if direction_name not in {"in", "out"}:
            raise AssertionError(f"{entry.location}: zoom direction must be in or out")
        event_x, event_y, canvas_point = self._event_point(
            coordinate_space,
            point_text,
            entry,
        )
        from annotator.gui.input.viewport import zoom_at

        direction = 1 if direction_name == "in" else -1
        with self.runtime.recorded_canvas_point(canvas_point):
            zoom_at(self.app, direction, event_x, event_y)

    def _dispatch_click(self, entry: SessionEntry) -> None:
        """CODEX: Generate a press and release for one pointer click."""

        if len(entry.arguments) != 4:
            raise AssertionError(
                f"{entry.location}: click requires target button space point"
            )
        target, button_name, coordinate_space, point_text = entry.arguments
        widget = self._target_widget(target, entry)
        x_coord, y_coord, canvas_point = self._event_point(
            coordinate_space,
            point_text,
            entry,
        )
        button = _button_number(button_name, entry)
        self._generate_canvas_event(
            widget,
            f"<ButtonPress-{button}>",
            x_coord,
            y_coord,
            canvas_point,
        )
        self.runtime.pump()
        self._generate_canvas_event(
            widget,
            f"<ButtonRelease-{button}>",
            x_coord,
            y_coord,
            canvas_point,
        )

    def _dispatch_drag(self, entry: SessionEntry) -> None:
        """CODEX: Generate a pointer drag from recorded motion to release."""

        if len(entry.arguments) < 6:
            raise AssertionError(f"{entry.location}: drag command is incomplete")
        target, button_name, coordinate_space, start_text = entry.arguments[:4]
        to_index = entry.arguments.index("to")
        end_text = entry.arguments[to_index + 1]
        via_points = _via_points(entry.arguments[to_index + 2 :])
        widget = self._target_widget(target, entry)
        button = _button_number(button_name, entry)
        start_x, start_y, start_point = self._event_point(
            coordinate_space,
            start_text,
            entry,
        )
        self._generate_canvas_event(
            widget,
            f"<ButtonPress-{button}>",
            start_x,
            start_y,
            start_point,
        )
        self.runtime.pump()
        for point_text in via_points:
            x_coord, y_coord, canvas_point = self._event_point(
                coordinate_space,
                point_text,
                entry,
            )
            self._generate_canvas_event(
                widget,
                f"<B{button}-Motion>",
                x_coord,
                y_coord,
                canvas_point,
            )
            self.runtime.pump()
        end_x, end_y, end_point = self._event_point(
            coordinate_space,
            end_text,
            entry,
        )
        if not via_points or via_points[-1] != end_text:
            # CODEX: `to` supplies final motion unless the recorder already
            # CODEX: captured that endpoint as the terminal `via` sample.
            self._generate_canvas_event(
                widget,
                f"<B{button}-Motion>",
                end_x,
                end_y,
                end_point,
            )
            self.runtime.pump()
        self._generate_canvas_event(
            widget,
            f"<ButtonRelease-{button}>",
            end_x,
            end_y,
            end_point,
        )

    def _dispatch_hover(self, entry: SessionEntry) -> None:
        """CODEX: Generate enter or leave for a widget target."""

        if len(entry.arguments) != 2:
            raise AssertionError(f"{entry.location}: hover requires target enter/leave")
        widget = self._target_widget(entry.arguments[0], entry)
        event_name = {"enter": "Enter", "leave": "Leave"}.get(entry.arguments[1])
        if event_name is None:
            raise AssertionError(f"{entry.location}: hover phase must be enter or leave")
        widget.event_generate(f"<{event_name}>")

    def _dispatch_wait(self, entry: SessionEntry) -> None:
        """CODEX: Pump events for a recorded duration."""

        if len(entry.arguments) != 1 or not entry.arguments[0].isdecimal():
            raise AssertionError(f"{entry.location}: wait requires milliseconds")
        self.runtime.pump_for(int(entry.arguments[0]))

    def _dispatch_invoke(self, entry: SessionEntry) -> None:
        """CODEX: Invoke a button-like widget command."""

        if len(entry.arguments) != 1:
            raise AssertionError(f"{entry.location}: invoke requires target")
        widget = self._target_widget(entry.arguments[0], entry)
        widget.invoke()

    def _dispatch_menu(self, entry: SessionEntry) -> None:
        """CODEX: Generate the pointer event that constructs a context menu."""

        if len(entry.arguments) < 4:
            raise AssertionError(
                f"{entry.location}: menu requires target button space point"
            )
        target, button_name, coordinate_space, point_text = entry.arguments[:4]
        snapshot_name, class_name = _menu_options(entry)
        widget = self._target_widget(target, entry)
        x_coord, y_coord, canvas_point = self._event_point(
            coordinate_space,
            point_text,
            entry,
        )
        button = _button_number(button_name, entry)
        self.runtime.posted_menu = None
        if class_name is None:
            self._generate_canvas_event(
                widget,
                f"<ButtonPress-{button}>",
                x_coord,
                y_coord,
                canvas_point,
                rootx=x_coord,
                rooty=y_coord,
            )
        else:
            _dispatch_class_panel_menu(self.app, entry, target, class_name)
        self.runtime.wait_until(
            lambda: self.runtime.posted_menu is not None,
            entry.location,
            "menu to open",
        )
        if snapshot_name is not None:
            self.runtime.record_menu_snapshot(snapshot_name, entry.location)

    def _dispatch_choose(self, entry: SessionEntry) -> None:
        """CODEX: Invoke an item from the last captured menu."""

        if len(entry.arguments) != 1:
            raise AssertionError(f"{entry.location}: choose requires one label")
        self.runtime.choose_menu(entry.arguments[0], entry.location)

    def _dispatch_select(self, entry: SessionEntry) -> None:
        """CODEX: Select one currently offered value in a dropdown target."""

        if len(entry.arguments) != 2:
            raise AssertionError(f"{entry.location}: select requires target value")
        target, value = entry.arguments
        widget = self._target_widget(target, entry)
        if isinstance(widget, ttk.Combobox):
            values = widget.cget("values")
        elif isinstance(widget, ttk.OptionMenu):
            menu = widget["menu"]
            end_index = menu.index("end")
            values = (
                ()
                if end_index is None
                else tuple(
                    menu.entrycget(index, "label")
                    for index in range(end_index + 1)
                )
            )
        else:
            raise AssertionError(
                f"{entry.location}: select target {target!r} is not a dropdown"
            )
        if value not in values:
            raise AssertionError(
                f"{entry.location}: dropdown value {value!r} was not found"
            )
        widget.setvar(widget.cget("textvariable"), value)
        if isinstance(widget, ttk.Combobox):
            widget.event_generate("<<ComboboxSelected>>")

    def _dispatch_config_choose(self, entry: SessionEntry) -> None:
        """CODEX: Invoke a semantic chooser in the open Configuration editor."""

        replay_configuration_choose(self.app, entry)

    def _dispatch_config_save(self, entry: SessionEntry) -> None:
        """CODEX: Apply complete Configuration fields through the real Save."""

        replay_configuration_save(self.app, self.setup, entry)

    def _dispatch_type(self, entry: SessionEntry) -> None:
        """CODEX: Insert text into a text-entry target while preserving focus."""

        if len(entry.arguments) != 2:
            raise AssertionError(f"{entry.location}: type requires target and text")
        widget = self._target_widget(entry.arguments[0], entry)
        self._focus_target(widget)
        widget.insert(tk.INSERT, entry.arguments[1])

    def _dispatch_close(self, entry: SessionEntry) -> None:
        """CODEX: Close the application through its lifecycle callback."""

        if entry.arguments:
            raise AssertionError(f"{entry.location}: close takes no arguments")
        self.app.on_close()

    def _target_widget(self, target: str, entry: SessionEntry) -> tk.Widget:
        """CODEX: Resolve a dotted session target to a live Tk widget."""

        if target == "root":
            return self.app.root
        parts = target.split(".")
        if len(parts) != 2:
            raise AssertionError(f"{entry.location}: unknown target {target!r}")
        group_name, widget_name = parts
        if not hasattr(self.app.widgets, group_name):
            raise AssertionError(f"{entry.location}: unknown widget group {group_name!r}")
        group = getattr(self.app.widgets, group_name)
        if not hasattr(group, widget_name):
            raise AssertionError(f"{entry.location}: unknown widget {target!r}")
        return getattr(group, widget_name)

    def _focus_target(self, widget: tk.Widget) -> None:
        """CODEX: Give keyboard ownership to the recorded target."""

        widget.focus_set()
        self.runtime.pump()

    def _is_text_target(self, widget: tk.Widget) -> bool:
        """CODEX: Return whether key events should stay on the target widget."""

        if widget == self.app.widgets.viewer.image_index_entry:
            return True
        return widget.winfo_class() in {
            "Entry",
            "TEntry",
            "Text",
            "Spinbox",
            "TSpinbox",
        }

    def _event_point(
        self,
        coordinate_space: str,
        point_text: str,
        entry: SessionEntry,
    ) -> tuple[int, int, tuple[float, float]]:
        """CODEX: Convert recorded canvas or image coordinates into event pixels."""

        point = _parse_point(point_text, entry)
        canvas = self.app.widgets.viewer.canvas
        if coordinate_space == "canvas":
            canvas_point = point
            from annotator.gui.view_geometry import image_point_from_canvas

            image_point = image_point_from_canvas(canvas_point, self.app.view)
        elif coordinate_space == "image":
            from annotator.gui.view_geometry import image_to_canvas_point

            image_point = point
            canvas_point = image_to_canvas_point(point, self.app.view)
        else:
            raise AssertionError(
                f"{entry.location}: coordinate space must be canvas or image"
            )
        self.runtime.last_canvas_point = canvas_point
        self.runtime.last_image_point = image_point
        # CODEX: Tk events carry integer widget coordinates; preserve the session's
        # CODEX: image-space point for hit-testing so zoom rounding cannot change the target.
        event_x = int(round(canvas_point[0] - canvas.canvasx(0)))
        event_y = int(round(canvas_point[1] - canvas.canvasy(0)))
        return event_x, event_y, canvas_point

    def _semantic_canvas_point(
        self,
        entry: SessionEntry,
        verb: str,
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        """CODEX: Return image and canvas coordinates for a semantic point action."""

        if len(entry.arguments) != 3:
            raise AssertionError(
                f"{entry.location}: {verb} requires target space point"
            )
        target, coordinate_space, point_text = entry.arguments
        widget = self._target_widget(target, entry)
        if widget != self.app.widgets.viewer.canvas:
            raise AssertionError(
                f"{entry.location}: unsupported {verb} target {target!r}"
            )
        _event_x, _event_y, canvas_point = self._event_point(
            coordinate_space,
            point_text,
            entry,
        )
        image_point = self.runtime.last_image_point
        if image_point is None:
            raise AssertionError(f"{entry.location}: {verb} point must be on the image")
        return image_point, canvas_point

    def _generate_canvas_event(
        self,
        widget: tk.Widget,
        sequence: str,
        x_coord: int,
        y_coord: int,
        canvas_point: tuple[float, float],
        **kwargs: Any,
    ) -> None:
        """CODEX: Generate one Tk event with its exact semantic canvas point."""

        with self.runtime.recorded_canvas_point(canvas_point):
            widget.event_generate(
                sequence,
                x=x_coord,
                y=y_coord,
                **kwargs,
            )


def _resize_sizes(entry: SessionEntry) -> tuple[tuple[int, int], tuple[int, int] | None]:
    """CODEX: Return requested root and optional canvas sizes from a resize line."""

    arguments = entry.arguments
    if len(arguments) < 2 or arguments[0] != "window":
        raise AssertionError(f"{entry.location}: resize requires window size")
    window_size = parse_size(arguments[1], entry)
    canvas_size = None
    if "canvas" in arguments:
        canvas_index = arguments.index("canvas")
        if canvas_index == len(arguments) - 1:
            raise AssertionError(f"{entry.location}: resize canvas size is incomplete")
        canvas_size = parse_size(arguments[canvas_index + 1], entry)
    return window_size, canvas_size


def _dispatch_class_panel_menu(
    app: Any,
    entry: SessionEntry,
    target: str,
    class_name: str,
) -> None:
    """CODEX: Reconstruct the context menu for one recorded class row.

    Require the stable class-list target and a row present in the live app so
    malformed session identity cannot silently construct a different menu.
    """

    if target != "controls.class_list_canvas":
        raise AssertionError(
            f"{entry.location}: class menu option requires controls.class_list_canvas"
        )
    if class_name not in app.class_panel_rows:
        raise AssertionError(f"{entry.location}: unknown class row {class_name!r}")
    event = tk.Event()
    event.widget = app.widgets.controls.class_list_canvas
    event.x_root = 0
    event.y_root = 0
    # CODEX: Import on dispatch so replay does not initialize GUI modules early.
    from annotator.gui.class_panel_input import show_class_panel_menu

    show_class_panel_menu(app, event, class_name=class_name)


def _menu_options(entry: SessionEntry) -> tuple[str | None, str | None]:
    """CODEX: Return optional snapshot and class-row facts from a menu line."""

    class_name = None
    snapshot_name = None
    for token in entry.arguments[4:]:
        key, separator, value = token.partition("=")
        if separator != "=":
            raise AssertionError(f"{entry.location}: unknown menu option {token!r}")
        if key == "class":
            if class_name is not None:
                raise AssertionError(f"{entry.location}: duplicate menu class option")
            if not value:
                raise AssertionError(f"{entry.location}: menu class option is empty")
            class_name = value
        elif key == "snapshot":
            if snapshot_name is not None:
                raise AssertionError(f"{entry.location}: duplicate menu snapshot option")
            snapshot_name = value
        else:
            raise AssertionError(f"{entry.location}: unknown menu option {token!r}")
    return snapshot_name, class_name


def _queue_dialog_expectations(
    runtime: ReplayRuntime,
    actions: tuple[SessionEntry, ...],
) -> dict[SessionEntry, ExpectedDialog]:
    """CODEX: Queue all recorded dialogs before callbacks start pumping."""

    expectations: dict[SessionEntry, ExpectedDialog] = {}
    for entry in actions:
        if entry.verb != "dialog":
            continue
        kind, title, result, arguments = _dialog_spec(entry)
        expectations[entry] = runtime.expect_dialog(
            kind,
            title,
            result,
            arguments,
        )
    return expectations


def _dialog_spec(entry: SessionEntry) -> tuple[str, str, str, tuple[str, ...]]:
    """CODEX: Return the recorded dialog kind, title, payload, and result."""

    if len(entry.arguments) < 2:
        raise AssertionError(f"{entry.location}: dialog requires kind and title")
    if len(entry.observations) != 1:
        raise AssertionError(f"{entry.location}: dialog requires one result")
    kind = entry.arguments[0]
    title = entry.arguments[1]
    arguments = entry.arguments[2:]
    result = entry.observations[0]
    if kind == "new_local_class":
        _validate_new_local_class_dialog(entry, result, arguments)
    elif kind == "local_class_source":
        _validate_local_class_source_dialog(entry, result, arguments)
    elif kind == "class_colour":
        _validate_class_colour_dialog(entry, result, arguments)
    elif kind == "configuration_colour":
        _validate_colour_dialog(entry, result, arguments, kind)
    elif kind == "askdirectory":
        _validate_askdirectory_dialog(entry, result, arguments)
    elif kind in {"askopenfilename", "asksaveasfilename"}:
        _validate_file_dialog(entry, result, arguments, kind, title)
    elif kind == "error_details":
        if arguments or result != "close":
            raise AssertionError(
                f"{entry.location}: error_details requires no payload and close result"
            )
    elif arguments:
        raise AssertionError(f"{entry.location}: {kind} dialog does not take payload")
    return kind, title, result, arguments


def _dialog_timeout_ms(expected: ExpectedDialog) -> int:
    """CODEX: Return the replay wait budget for one recorded dialog."""

    if expected.kind == "error_details" and expected.title == "Model failed":
        return MODEL_FAILURE_DIALOG_TIMEOUT_MS
    return 1000


def _validate_askdirectory_dialog(
    entry: SessionEntry,
    result: str,
    arguments: tuple[str, ...],
) -> None:
    """CODEX: Require the single-fixture folder-choice vocabulary."""

    if arguments:
        raise AssertionError(
            f"{entry.location}: askdirectory dialog does not take payload"
        )
    if result not in {"<fixture>", "cancel"}:
        raise AssertionError(
            f"{entry.location}: askdirectory result must be <fixture>/cancel"
        )


def _validate_local_class_source_dialog(
    entry: SessionEntry,
    result: str,
    arguments: tuple[str, ...],
) -> None:
    """CODEX: Enforce the explicit folder-class source decision."""

    if arguments:
        raise AssertionError(
            f"{entry.location}: local_class_source dialog does not take payload"
        )
    if result not in {"custom", "defaults", "cancel"}:
        raise AssertionError(
            f"{entry.location}: local_class_source result must be "
            "custom/defaults/cancel"
        )


def _validate_class_colour_dialog(
    entry: SessionEntry,
    result: str,
    arguments: tuple[str, ...],
) -> None:
    """CODEX: Enforce the system colour picker's recorded result shape."""

    _validate_colour_dialog(entry, result, arguments, "class_colour")


def _validate_colour_dialog(
    entry: SessionEntry,
    result: str,
    arguments: tuple[str, ...],
    kind: str,
) -> None:
    """CODEX: Enforce the shared native colour result vocabulary."""

    if arguments:
        raise AssertionError(
            f"{entry.location}: {kind} dialog does not take payload"
        )
    if result == "cancel":
        return
    if re.fullmatch(r"#[0-9a-fA-F]{6}", result) is None:
        raise AssertionError(
            f"{entry.location}: {kind} result must be #rrggbb/cancel"
        )


def _validate_file_dialog(
    entry: SessionEntry,
    result: str,
    arguments: tuple[str, ...],
    kind: str,
    title: str,
) -> None:
    """CODEX: Require cancellation or a chooser-appropriate portable file token."""

    if arguments:
        raise AssertionError(
            f"{entry.location}: {kind} dialog does not take payload"
        )
    if result == "cancel":
        return
    try:
        is_model_choice = (
            kind == "askopenfilename"
            and title in MODEL_WEIGHT_DIALOG_TITLES
            and result.startswith(MODEL_ASSET_PREFIX)
        )
        if is_model_choice:
            validate_model_asset_token(result)
        else:
            validate_fixture_file_token(result)
    except ValueError as exc:
        raise AssertionError(f"{entry.location}: {exc}") from exc


def _validate_new_local_class_dialog(
    entry: SessionEntry,
    result: str,
    arguments: tuple[str, ...],
) -> None:
    """CODEX: Enforce the recorded payload for folder-class dialogs."""

    if result == "cancel":
        if arguments:
            raise AssertionError(
                f"{entry.location}: cancelled new_local_class dialog takes no payload"
            )
        return
    if result != "ok":
        raise AssertionError(f"{entry.location}: new_local_class result must be ok/cancel")
    pairs = [token.partition("=") for token in arguments]
    keys = {key for key, separator, _value in pairs if separator == "="}
    if keys != {"name", "colour"} or len(pairs) != 2:
        raise AssertionError(
            f"{entry.location}: new_local_class requires name= and colour="
        )


def _button_number(button_name: str, entry: SessionEntry) -> int:
    """CODEX: Map recorded button names to the app's platform bindings."""

    if button_name == "left":
        return 1
    if button_name == "middle":
        return 3 if sys.platform == "darwin" else 2
    if button_name == "right":
        return 2 if sys.platform == "darwin" else 3
    raise AssertionError(f"{entry.location}: unknown pointer button {button_name!r}")


def _parse_point(point_text: str, entry: SessionEntry) -> tuple[float, float]:
    """CODEX: Parse one ``X,Y`` point token from a session action."""

    x_text, separator, y_text = point_text.partition(",")
    if separator != ",":
        raise AssertionError(f"{entry.location}: expected X,Y point")
    return float(x_text), float(y_text)


def _via_points(arguments: tuple[str, ...]) -> tuple[str, ...]:
    """CODEX: Return optional drag sample points from a compact via token."""

    if not arguments:
        return ()
    if len(arguments) != 2 or arguments[0] != "via":
        return ()
    raw_points = arguments[1].strip()
    if not raw_points.startswith("[") or not raw_points.endswith("]"):
        return ()
    inner = raw_points[1:-1].strip()
    if not inner:
        return ()
    return tuple(point.strip() for point in inner.split(";") if point.strip())


def _format_size(size: tuple[int, int]) -> str:
    """CODEX: Format a requested geometry size for wait diagnostics."""

    return f"{size[0]}x{size[1]}"
