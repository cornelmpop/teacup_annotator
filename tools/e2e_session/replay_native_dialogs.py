"""CODEX: Supply recorded native chooser results during replay.

Replay maps fixture identities into its copied project and model-asset
identities into preflighted local checkpoints, without opening an operating-
system chooser. File consumers still own parsing and use of each artifact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.e2e_session.model_assets import resolve_file_token


class ReplayNativeDialogHooks:
    """CODEX: Provide native chooser replacements for ``ReplayRuntime``."""

    project_folder: Path
    model_assets: dict[str, Path]
    failures: list[str]

    def askopenfilename(self, *_args: Any, **kwargs: Any) -> str:
        """CODEX: Return a recorded existing fixture or model-asset file."""

        title = _required_title(kwargs)
        expected = self._next_dialog("askopenfilename", title)
        if expected is None:
            return ""
        expected.observed = True
        if expected.result == "cancel":
            return ""
        selected = resolve_file_token(
            expected.result,
            self.project_folder,
            self.model_assets,
        )
        if not selected.is_file():
            self.failures.append(f"recorded open file does not exist: {selected}")
            return ""
        # CODEX: Tk returns an untyped path string at the native-dialog boundary.
        return str(selected)

    def asksaveasfilename(self, *_args: Any, **kwargs: Any) -> str:
        """CODEX: Return a recorded save path inside the replay project."""

        title = _required_title(kwargs)
        expected = self._next_dialog("asksaveasfilename", title)
        if expected is None:
            return ""
        expected.observed = True
        if expected.result == "cancel":
            return ""
        selected = resolve_file_token(
            expected.result,
            self.project_folder,
            self.model_assets,
        )
        # CODEX: Tk returns an untyped path string at the native-dialog boundary.
        return str(selected)

    def configuration_colour_dialog(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> tuple[None, str | None]:
        """CODEX: Return the Configuration editor's recorded colour result."""

        expected = self._next_dialog(
            "configuration_colour",
            "Choose configuration colour",
        )
        if expected is None:
            return None, None
        expected.observed = True
        colour = None if expected.result == "cancel" else expected.result
        return None, colour


def _required_title(kwargs: dict[str, Any]) -> str:
    """CODEX: Return the title used to pair a chooser with its expectation."""

    title = kwargs.get("title")
    if not isinstance(title, str) or not title:
        raise ValueError("replayed native file chooser requires a nonempty title")
    return title
