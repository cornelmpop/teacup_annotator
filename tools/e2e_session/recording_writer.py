"""CODEX: Build human-readable session files from recorded GUI actions."""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping
from pathlib import Path
import shlex

from tools.e2e_session.session_preferences import PATH_PREFERENCE_KEYS


PREFS_PER_LINE = 4


class RecordingSessionWriter:
    """CODEX: Accumulate setup, action, and expectation lines for one recording."""

    def __init__(
        self,
        fixture_reference: str,
        *,
        expect_outputs: str | None = None,
    ) -> None:
        """CODEX: Start a session for one fixture path relative to its file."""

        self.fixture_reference = fixture_reference
        self.expect_outputs = expect_outputs
        self.window_line: str | None = None
        self.preference_lines: list[str] = []
        self.action_lines: list[str] = []

    def set_window(
        self,
        window_size: tuple[int, int],
        canvas_size: tuple[int, int] | None = None,
    ) -> None:
        """CODEX: Record the startup geometry requested by replay."""

        tokens = ["window", format_size(window_size)]
        if canvas_size is not None:
            tokens.extend(("canvas", format_size(canvas_size)))
        self.window_line = _format_command(tokens)

    def set_preferences(
        self,
        values: Mapping[str, str],
        *,
        project_folder: Path | None = None,
    ) -> None:
        """CODEX: Record the complete effective preference map for replay."""

        tokens = [
            _preference_token(key, value, project_folder=project_folder)
            for key, value in sorted(values.items())
        ]
        self.preference_lines = [
            _format_command(("prefs", *group))
            for group in _chunk(tokens, PREFS_PER_LINE)
        ]

    def add_action(
        self,
        verb: str,
        *arguments: str,
        observations: Iterable[str] = (),
    ) -> None:
        """CODEX: Append one replayable session action line."""

        self.action_lines.append(_format_action((verb, *arguments), tuple(observations)))

    def add_dialog(
        self,
        kind: str,
        title: str,
        result: str,
        *arguments: str,
    ) -> None:
        """CODEX: Append one modal interaction after the user answers it."""

        self.add_action("dialog", kind, title, *arguments, observations=(result,))

    def add_loaded(self, observations: Iterable[str]) -> None:
        """CODEX: Append the first loaded-project checkpoint."""

        self.action_lines.append(_format_command(("loaded", *tuple(observations))))

    def add_resize(
        self,
        window_size: tuple[int, int],
        canvas_size: tuple[int, int] | None,
        observations: Iterable[str],
    ) -> None:
        """CODEX: Append one settled window resize action."""

        arguments = ["window", format_size(window_size)]
        if canvas_size is not None:
            arguments.extend(("canvas", format_size(canvas_size)))
        self.add_action("resize", *arguments, observations=observations)

    def text(self) -> str:
        """CODEX: Return the full session file text with stable section order."""

        setup_lines = [_format_command(("fixture", self.fixture_reference))]
        if self.window_line is not None:
            setup_lines.append(self.window_line)
        setup_lines.extend(self.preference_lines)

        lines = ["setup"]
        lines.extend(f"  {line}" for line in setup_lines)
        lines.append("")
        lines.append("session")
        lines.extend(f"  {line}" for line in self.action_lines)
        lines.append("")
        lines.append("expect")
        if self.expect_outputs is not None:
            lines.append(f"  {_format_command(('outputs', self.expect_outputs))}")
        return "\n".join(lines) + "\n"

    def write(self, path: Path) -> None:
        """CODEX: Persist the recorded session where the CLI requested it."""

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.text(), encoding="utf-8")


def normalized_preference_value(
    key: str,
    value: str,
    *,
    project_folder: Path | None = None,
) -> str:
    """CODEX: Expand path preferences and relativize fixture-local paths."""

    if key not in PATH_PREFERENCE_KEYS or not value:
        return value
    expanded = Path(value).expanduser()
    if project_folder is None:
        return str(expanded)

    project_root = project_folder.expanduser().resolve()
    resolved = expanded.resolve()
    try:
        relative_path = resolved.relative_to(project_root)
    except ValueError:
        return str(resolved)
    if not relative_path.parts:
        return "<fixture>"
    return str(Path("<fixture>") / relative_path)


def format_point(point: tuple[float, float]) -> str:
    """CODEX: Format one point compactly for the line-oriented session syntax."""

    return f"{format_number(point[0])},{format_number(point[1])}"


def format_size(size: tuple[int, int]) -> str:
    """CODEX: Format a width-height pair for session setup or resize lines."""

    return f"{size[0]}x{size[1]}"


def format_number(value: float) -> str:
    """CODEX: Keep recorded numeric facts compact without losing replay state."""

    return f"{value:.6f}".rstrip("0").rstrip(".")


def _preference_token(
    key: str,
    value: str,
    *,
    project_folder: Path | None,
) -> str:
    """CODEX: Return one ``key=value`` setup token after path normalization."""

    return f"{key}={normalized_preference_value(key, value, project_folder=project_folder)}"


def _format_action(
    command_tokens: tuple[str, ...],
    observations: tuple[str, ...],
) -> str:
    """CODEX: Serialize one action and optional observation arrow."""

    command = _format_command(command_tokens)
    if not observations:
        return command
    return f"{command} -> {_format_command(observations)}"


def _format_command(tokens: Iterable[str]) -> str:
    """CODEX: Quote session tokens using the parser's shell-like grammar."""

    return shlex.join(tuple(tokens))


def _chunk(values: list[str], size: int) -> Iterable[tuple[str, ...]]:
    """CODEX: Yield fixed-size groups for readable multi-line prefs blocks."""

    for index in range(0, len(values), size):
        yield tuple(values[index : index + size])
