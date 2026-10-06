"""CODEX: Protect deterministic application startup during GUI replay."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from annotator.gui import application
from tools.e2e_session.replay_runtime import ReplayRuntime


class FakeRoot:
    """CODEX: Execute ordinary Tk callbacks when replay pumps this fake root."""

    def __init__(self) -> None:
        """CODEX: Start with no callbacks waiting for an event-loop turn."""

        self.scheduled: list[tuple[Callable[..., Any], tuple[Any, ...]]] = []

    def after(
        self,
        _ms: int,
        func: Callable[..., Any] | None = None,
        *args: Any,
    ) -> str:
        """CODEX: Queue callable work as Tk would for a later update."""

        if func is not None:
            self.scheduled.append((func, args))
        return "tk-after"

    def update_idletasks(self) -> None:
        """CODEX: Provide replay's idle-layout boundary without extra work."""

    def update(self) -> None:
        """CODEX: Run callbacks that were scheduled before this event turn."""

        scheduled = tuple(self.scheduled)
        self.scheduled.clear()
        for func, args in scheduled:
            func(*args)


def test_replay_holds_startup_until_dialog_expectations_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUG-2026-10-04-GUI-REPLAY-STARTUP: hold startup through setup pumps."""

    root = FakeRoot()
    runtime = ReplayRuntime(root, project_folder=tmp_path)
    startup_results: list[bool] = []

    def startup(_host: object) -> None:
        """CODEX: Exercise the dialog boundary reached by saved-folder startup."""

        result = runtime.askokcancel("Open last folder", "Open it?")
        startup_results.append(result)

    monkeypatch.setattr(application, "load_saved_folder", startup)

    with runtime:
        root.after(150, application.load_saved_folder, object())

        runtime.pump(5)

        assert startup_results == []
        assert runtime.failures == []

        expected = runtime.expect_dialog("askokcancel", "Open last folder", "ok")
        runtime.release_startup()

        assert startup_results == [True]
        assert expected.observed is True
        assert runtime.expected_dialogs == []

        runtime.pump(5)
        assert startup_results == [True]
