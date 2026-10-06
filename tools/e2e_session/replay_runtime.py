"""CODEX: Own replay-time Tk shims, dialogs, menu capture, and event pumping."""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterator
from collections.abc import Mapping
from contextlib import contextmanager
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import time
import tkinter as tk
from typing import Any
from unittest import mock

from tools.e2e_session.menu_snapshots import menu_snapshot
from tools.e2e_session.replay_native_dialogs import ReplayNativeDialogHooks
from tools.e2e_session.session_format import SourceLocation


@dataclass(slots=True)
class ExpectedDialog:
    """CODEX: Track one dialog result requested by the session file."""

    kind: str
    title: str
    result: str
    arguments: tuple[str, ...] = ()
    observed: bool = False


@dataclass(frozen=True, slots=True)
class DialogResult:
    """CODEX: Stand in for patched modal dialog classes during replay."""

    result: Any


class RootAfterShim:
    """CODEX: Defer replay-controlled root callbacks by identity."""

    def __init__(
        self,
        root: tk.Tk,
        deferred_callbacks: set[Callable[..., Any]],
        *,
        pumped_callbacks: set[Callable[..., Any]] | None = None,
        held_callbacks: set[Callable[..., Any]] | None = None,
    ) -> None:
        """CODEX: Store intercepted, automatically pumped, and held callbacks.

        By default every deferred callback is pumped, preserving correctness
        replay behavior. Performance replay can leave selected recurring work
        pending, while startup remains held for an explicit lifecycle release.
        """

        self.root = root
        self.deferred_callbacks = deferred_callbacks
        self.pumped_callbacks = (
            deferred_callbacks if pumped_callbacks is None else pumped_callbacks
        )
        self.held_callbacks = set() if held_callbacks is None else held_callbacks
        self.original_after = root.after
        self.pending: dict[Callable[..., Any], tuple[Any, ...]] = {}

    def install(self) -> None:
        """CODEX: Shadow this root's ``after`` method without touching widgets."""

        setattr(self.root, "after", self.after)

    def uninstall(self) -> None:
        """CODEX: Restore the root's original ``after`` method."""

        setattr(self.root, "after", self.original_after)

    def after(
        self,
        ms: int,
        func: Callable[..., Any] | None = None,
        *args: Any,
    ) -> Any:
        """CODEX: Record deferred callbacks and pass one-shots to Tk."""

        if func in self.deferred_callbacks:
            self.pending[func] = args
            return f"replay-after-{func.__name__}"
        if func is None:
            return self.original_after(ms)
        return self.original_after(ms, func, *args)

    def run_pending(self, func: Callable[..., Any]) -> None:
        """CODEX: Run the latest pending call for one deferred callback."""

        args = self.pending.pop(func)
        func(*args)

    def run_pending_callbacks(self) -> None:
        """CODEX: Run callbacks pending at the start of one replay pump turn."""

        pending_callbacks = tuple(self.pending)
        for func in pending_callbacks:
            if (
                func in self.pending
                and func in self.pumped_callbacks
                and func not in self.held_callbacks
            ):
                self.run_pending(func)


class ReplayRuntime(ReplayNativeDialogHooks):
    """CODEX: Hold replay patches and event-loop helpers for one Tk root."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        project_folder: Path,
        model_assets: Mapping[str, Path] | None = None,
        pump_statistics_callbacks: bool = True,
    ) -> None:
        """CODEX: Prepare replay state and its recurring-callback policy."""

        self.root = root
        self.project_folder = project_folder.resolve()
        self.model_assets = {} if model_assets is None else dict(model_assets)
        self.pump_statistics_callbacks = pump_statistics_callbacks
        self.stack = ExitStack()
        self.after_shim: RootAfterShim | None = None
        self.expected_dialogs: list[ExpectedDialog] = []
        self.failures: list[str] = []
        self.posted_menu: tk.Menu | None = None
        self.menu_snapshots: dict[str, list[dict[str, Any]]] = {}
        self.last_canvas_point: tuple[float, float] | None = None
        self.last_image_point: tuple[float, float] | None = None
        self.event_canvas_point: tuple[float, float] | None = None
        self.before_reconciled_save: Callable[[Any], None] | None = None

    def __enter__(self) -> "ReplayRuntime":
        """CODEX: Install replay patches before ``AnnotatorApp`` schedules work."""

        from annotator.gui.application import load_saved_folder
        from annotator.gui.model.worker import poll_worker_queue
        from annotator.gui.session_statistics import refresh_session_statistics
        from annotator.gui.project import folder_loading

        pumped_callbacks = {poll_worker_queue}
        if self.pump_statistics_callbacks:
            pumped_callbacks.add(refresh_session_statistics)
        self.after_shim = RootAfterShim(
            self.root,
            {load_saved_folder, poll_worker_queue, refresh_session_statistics},
            pumped_callbacks=pumped_callbacks,
            held_callbacks={load_saved_folder},
        )
        self.after_shim.install()
        self.stack.enter_context(
            mock.patch("tkinter.messagebox.askokcancel", self.askokcancel)
        )
        self.stack.enter_context(
            mock.patch("tkinter.messagebox.askyesno", self.askyesno)
        )
        self.stack.enter_context(
            mock.patch("tkinter.messagebox.showerror", self.showerror)
        )
        self.stack.enter_context(
            mock.patch("tkinter.messagebox.showinfo", self.showinfo)
        )
        self.stack.enter_context(
            mock.patch("tkinter.messagebox.showwarning", self.showwarning)
        )
        # CODEX: The recorded fixture token denotes this replay's copied output
        # CODEX: project, so Load remains testable without opening a native chooser.
        self.stack.enter_context(
            mock.patch(
                "annotator.gui.project.folder_loading.filedialog",
                SimpleNamespace(askdirectory=self.askdirectory),
            )
        )
        self.stack.enter_context(
            mock.patch(
                "annotator.gui.config_window.choices.filedialog",
                SimpleNamespace(askopenfilename=self.askopenfilename),
            )
        )
        self.stack.enter_context(
            mock.patch(
                "annotator.gui.model.run.filedialog",
                SimpleNamespace(askopenfilename=self.askopenfilename),
            )
        )
        self.stack.enter_context(
            mock.patch(
                "annotator.gui.project.archive.filedialog",
                SimpleNamespace(asksaveasfilename=self.asksaveasfilename),
            )
        )
        self.stack.enter_context(
            mock.patch(
                "annotator.gui.config_window.choices.colorchooser",
                SimpleNamespace(askcolor=self.configuration_colour_dialog),
            )
        )
        # CODEX: Mirror recorder scope because NewLocalClassDialog replays its final
        # CODEX: name and colour directly; its nested picker must never consume a
        # CODEX: second expectation for the same recorded choice.
        self.stack.enter_context(
            mock.patch(
                "annotator.gui.local_class_actions.colorchooser",
                SimpleNamespace(askcolor=self.class_colour_dialog),
            )
        )
        self.stack.enter_context(
            mock.patch(
                "annotator.gui.local_class_actions.LocalClassSourceDialog",
                self.local_class_source_dialog,
            )
        )
        self.stack.enter_context(
            mock.patch(
                "annotator.gui.local_class_actions.NewLocalClassDialog",
                self.new_local_class_dialog,
            )
        )
        for module_name in (
            "annotator.gui.model.run",
            "annotator.gui.model.worker",
            "annotator.gui.project.folder_loading",
            "annotator.gui.project.archive",
        ):
            self.stack.enter_context(
                mock.patch(
                    f"{module_name}.ErrorDetailsDialog",
                    self.error_details_dialog,
                )
            )
        for module_name in (
            "annotator.gui.input.pointer_primary",
            "annotator.gui.input.pointer_drag",
            "annotator.gui.input.pointer_menu",
            "annotator.gui.input.pointer_motion",
            "annotator.gui.context_menus",
        ):
            self.stack.enter_context(
                mock.patch(
                    f"{module_name}.canvas_event_point",
                    self.canvas_event_point,
                )
            )
        for module_name in (
            "annotator.gui.context_menus",
            "annotator.gui.annotation_delete_menu",
            "annotator.gui.vertex_selection_menu",
            "annotator.gui.class_panel_input",
            "annotator.gui.menu_support",
        ):
            self.stack.enter_context(
                mock.patch(f"{module_name}.post_menu", self.capture_menu)
            )
        self.stack.enter_context(
            mock.patch.object(
                folder_loading,
                "save_reconciled_project",
                self.replay_reconciled_save(folder_loading.save_reconciled_project),
            )
        )
        return self

    def __exit__(self, *exc_info: object) -> None:
        """CODEX: Restore patched functions and the original root scheduler."""

        self.stack.close()
        if self.after_shim is not None:
            self.after_shim.uninstall()

    def release_startup(self) -> None:
        """CODEX: Release the app startup callback after replay expectations exist."""

        from annotator.gui.application import load_saved_folder

        self.after_shim.run_pending(load_saved_folder)

    def expect_dialog(
        self,
        kind: str,
        title: str,
        result: str,
        arguments: tuple[str, ...] = (),
    ) -> ExpectedDialog:
        """CODEX: Queue one dialog the replay pump should encounter."""

        expected = ExpectedDialog(
            kind=kind,
            title=title,
            result=result,
            arguments=arguments,
        )
        self.expected_dialogs.append(expected)
        return expected

    def askokcancel(
        self,
        title: str,
        _message: str,
        **_kwargs: Any,
    ) -> bool:
        """CODEX: Return the recorded askokcancel result during replay."""

        expected = self._next_dialog("askokcancel", title)
        if expected is None:
            return False
        expected.observed = True
        return expected.result == "ok"

    def askyesno(
        self,
        title: str,
        _message: str,
        **_kwargs: Any,
    ) -> bool:
        """CODEX: Return the recorded askyesno result during replay."""

        expected = self._next_dialog("askyesno", title)
        if expected is None:
            return False
        expected.observed = True
        return expected.result == "yes"

    def showerror(self, title: str, _message: str = "", **_kwargs: Any) -> str:
        """CODEX: Return the recorded showerror result during replay."""

        return self._message_dialog("showerror", title)

    def showinfo(self, title: str, _message: str = "", **_kwargs: Any) -> str:
        """CODEX: Return the recorded showinfo result during replay."""

        return self._message_dialog("showinfo", title)

    def showwarning(self, title: str, _message: str = "", **_kwargs: Any) -> str:
        """CODEX: Return the recorded showwarning result during replay."""

        return self._message_dialog("showwarning", title)

    def askdirectory(self, *_args: Any, **_kwargs: Any) -> str:
        """CODEX: Return the replay output folder for a recorded Load choice."""

        expected = self._next_dialog("askdirectory", "Load image folder")
        if expected is None:
            return ""
        expected.observed = True
        if expected.result == "cancel":
            return ""
        # CODEX: Tk's native chooser contract returns a filesystem string, while
        # CODEX: replay keeps the authoritative output location as a typed path.
        return str(self.project_folder)

    def new_local_class_dialog(self, *_args: Any, **_kwargs: Any) -> DialogResult:
        """CODEX: Return the recorded folder-class dialog result."""

        expected = self._next_dialog("new_local_class", "Add annotation class")
        if expected is None:
            return DialogResult(None)
        expected.observed = True
        if expected.result == "cancel":
            return DialogResult(None)
        return DialogResult(_new_local_class_result(expected.arguments))

    def local_class_source_dialog(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> DialogResult:
        """CODEX: Return the recorded folder-class source choice."""

        expected = self._next_dialog(
            "local_class_source",
            "Choose annotation classes",
        )
        if expected is None:
            return DialogResult(None)
        expected.observed = True
        result = None if expected.result == "cancel" else expected.result
        return DialogResult(result)

    def class_colour_dialog(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> tuple[None, str | None]:
        """CODEX: Return the recorded annotation-class colour choice."""

        expected = self._next_dialog(
            "class_colour",
            "Choose annotation class colour",
        )
        if expected is None:
            return None, None
        expected.observed = True
        colour = None if expected.result == "cancel" else expected.result
        return None, colour

    def error_details_dialog(
        self,
        _root: tk.Tk,
        title: str,
        _details: str,
    ) -> DialogResult:
        """CODEX: Observe a recorded error-details window without blocking."""

        expected = self._next_dialog("error_details", title)
        if expected is None:
            return DialogResult(None)
        expected.observed = True
        return DialogResult(None)

    @contextmanager
    def recorded_canvas_point(
        self,
        point: tuple[float, float],
    ) -> Iterator[None]:
        """CODEX: Scope exact semantic coordinates to one generated Tk event."""

        previous = self.event_canvas_point
        self.event_canvas_point = point
        try:
            yield
        finally:
            self.event_canvas_point = previous

    def canvas_event_point(
        self,
        canvas: tk.Canvas,
        event: tk.Event,
    ) -> tuple[float, float]:
        """CODEX: Return the current semantic point or the real Tk conversion."""

        if self.event_canvas_point is not None:
            return self.event_canvas_point
        from annotator.gui.view_geometry import canvas_event_point

        return canvas_event_point(canvas, event)

    def _message_dialog(self, kind: str, title: str) -> str:
        """CODEX: Match one recorded messagebox-style dialog."""

        expected = self._next_dialog(kind, title)
        if expected is None:
            return "ok"
        expected.observed = True
        return expected.result

    def _next_dialog(self, kind: str, title: str) -> ExpectedDialog | None:
        """CODEX: Match the next queued dialog against an application prompt."""

        if not self.expected_dialogs:
            self.failures.append(f"unexpected {kind} dialog {title!r}")
            return None
        expected = self.expected_dialogs[0]
        if expected.kind != kind or expected.title != title:
            self.failures.append(
                f"expected {expected.kind} dialog {expected.title!r}, "
                f"got {kind} {title!r}"
            )
            return None
        return self.expected_dialogs.pop(0)

    def capture_menu(self, menu: tk.Menu, _x_root: int, _y_root: int) -> None:
        """CODEX: Remember the constructed menu without posting it natively."""

        self.posted_menu = menu

    def replay_reconciled_save(
        self,
        save_reconciled_project: Callable[[Any], Any],
    ) -> Callable[[Any], Any]:
        """CODEX: Wrap load-time reconciliation saves for baseline capture.

        Folder-load reconciliation publishes the loaded project, then performs a
        save that writes workflow output logs before the recorded ``loaded`` line
        is dispatched. The callback lets replay capture the same baseline the
        recorder captured immediately before that save.
        """

        def wrapped(host: Any) -> Any:
            """CODEX: Capture replay baseline before the reconciled save mutates logs."""

            if self.before_reconciled_save is not None:
                self.before_reconciled_save(host)
            return save_reconciled_project(host)

        return wrapped

    def record_menu_snapshot(self, name: str, location: SourceLocation) -> None:
        """CODEX: Store one named menu snapshot for golden comparison."""

        if not name:
            raise AssertionError(f"{location}: menu snapshot name cannot be empty")
        if name in self.menu_snapshots:
            raise AssertionError(f"{location}: duplicate menu snapshot {name!r}")
        if self.posted_menu is None:
            raise AssertionError(f"{location}: no menu is available to snapshot")
        self.menu_snapshots[name] = menu_snapshot(self.posted_menu)

    def choose_menu(self, label: str, location: SourceLocation) -> None:
        """CODEX: Invoke the unique matching command in a captured menu tree."""

        if self.posted_menu is None:
            raise AssertionError(f"{location}: no menu is available")
        matches = _menu_command_matches(self.posted_menu, label)
        if not matches:
            raise AssertionError(f"{location}: menu item {label!r} was not found")
        if len(matches) > 1:
            raise AssertionError(f"{location}: menu item {label!r} is ambiguous")
        menu, index, enabled = matches[0]
        if not enabled:
            raise AssertionError(f"{location}: menu item {label!r} is disabled")
        menu.invoke(index)
        self.posted_menu = None

    def pump(self, cycles: int = 3) -> None:
        """CODEX: Let Tk process pending redraws and callbacks."""

        for _ in range(cycles):
            self.root.update_idletasks()
            self.root.update()
            if self.after_shim is not None:
                self.after_shim.run_pending_callbacks()

    def pump_for(self, ms: int) -> None:
        """CODEX: Pump Tk events for an explicit recorded wait."""

        deadline = time.monotonic() + ms / 1000
        while time.monotonic() < deadline:
            self.pump(1)
            time.sleep(0.005)

    def wait_until(
        self,
        predicate: Callable[[], bool],
        location: SourceLocation,
        description: str,
        *,
        timeout_ms: int = 1000,
        timeout_details: Callable[[], str] | None = None,
    ) -> None:
        """CODEX: Pump Tk until a predicate succeeds, reporting timeout state."""

        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            self.pump(1)
            self.raise_failures(location)
            if predicate():
                return
            time.sleep(0.005)
        message = f"{location}: timed out waiting for {description}"
        if timeout_details is not None:
            message = f"{message}; {timeout_details()}"
        raise AssertionError(message)

    def raise_failures(self, location: SourceLocation) -> None:
        """CODEX: Raise and clear any asynchronous replay failure."""

        if self.failures:
            message = "; ".join(self.failures)
            self.failures.clear()
            raise AssertionError(f"{location}: {message}")

    def root_size(self) -> tuple[int, int]:
        """CODEX: Return the achieved Tk root content size."""

        return self.root.winfo_width(), self.root.winfo_height()

    def canvas_size(self, canvas: tk.Canvas) -> tuple[int, int]:
        """CODEX: Return the achieved canvas size used by pointer replay."""

        return canvas.winfo_width(), canvas.winfo_height()


def _new_local_class_result(arguments: tuple[str, ...]) -> tuple[str, str]:
    """CODEX: Decode the recorded folder-class dialog payload."""

    values: dict[str, str] = {}
    for token in arguments:
        key, separator, value = token.partition("=")
        if separator != "=":
            raise AssertionError("new_local_class dialog arguments require key=value")
        values[key] = value
    return values["name"], values["colour"]


def _menu_command_matches(
    menu: tk.Menu,
    label: str,
    ancestors_enabled: bool = True,
) -> list[tuple[tk.Menu, int, bool]]:
    """CODEX: Find command leaves with an exact label through Tk cascades."""

    end_index = menu.index("end")
    if end_index is None:
        return []
    matches = []
    for index in range(end_index + 1):
        # CODEX: Tk option queries cross Tcl's loosely typed object boundary.
        entry_type = str(menu.type(index))
        if entry_type in {"separator", "tearoff"}:
            continue
        entry_enabled = menu.entrycget(index, "state") != tk.DISABLED
        enabled = ancestors_enabled and entry_enabled
        if entry_type == "cascade":
            # CODEX: nametowidget requires the Tcl widget path as Python text.
            submenu_name = str(menu.entrycget(index, "menu"))
            submenu = menu.nametowidget(submenu_name)
            # CODEX: The session names the chosen leaf; cascades only navigate to it,
            # CODEX: so replay traverses their commands without invoking the container.
            matches.extend(_menu_command_matches(submenu, label, enabled))
            continue
        if menu.entrycget(index, "label") == label:
            matches.append((menu, index, enabled))
    return matches
