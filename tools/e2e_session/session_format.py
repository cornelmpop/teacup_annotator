"""CODEX: Parse and write line-oriented GUI replay session files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex

from tools.e2e_session.session_action_registry import action_definition
from tools.e2e_session.session_action_registry import command_definition


SECTION_ORDER = ("setup", "session", "expect")
SECTION_INDEX = {section: index for index, section in enumerate(SECTION_ORDER)}


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """CODEX: Identify the source line that produced a parsed session entry."""

    source_name: str
    line_number: int

    def __str__(self) -> str:
        """CODEX: Return the human-readable ``file:line`` location."""

        return f"{self.source_name}:{self.line_number}"


@dataclass(frozen=True, slots=True)
class SessionEntry:
    """CODEX: Represent one parsed setup, action, or expectation line."""

    location: SourceLocation
    section: str
    verb: str
    arguments: tuple[str, ...]
    observations: tuple[str, ...]
    raw: str

    @property
    def tokens(self) -> tuple[str, ...]:
        """CODEX: Return the command tokens before any observation arrow."""

        return (self.verb, *self.arguments)


@dataclass(frozen=True, slots=True)
class SessionDocument:
    """CODEX: Hold the parsed semantic entries and original text lines."""

    source_name: str
    setup: tuple[SessionEntry, ...]
    actions: tuple[SessionEntry, ...]
    expectations: tuple[SessionEntry, ...]
    lines: tuple[str, ...]
    trailing_newline: bool

    @property
    def entries(self) -> tuple[SessionEntry, ...]:
        """CODEX: Return all parsed entries in file order."""

        return (*self.setup, *self.actions, *self.expectations)


class SessionParseError(ValueError):
    """CODEX: Report session syntax failures with the offending source line."""

    def __init__(self, location: SourceLocation, message: str) -> None:
        """CODEX: Store the exact source location and parser diagnostic."""

        self.location = location
        self.message = message
        super().__init__(f"{location}: {message}")


def parse_session_file(path: Path) -> SessionDocument:
    """CODEX: Parse a session file without importing Tk or application code."""

    return parse_session_text(path.read_text(encoding="utf-8"), source_name=str(path))


def parse_session_text(
    text: str,
    *,
    source_name: str = "<session>",
) -> SessionDocument:
    """CODEX: Parse one line-oriented session document into dataclasses.

    This layer owns only syntax: section order, shell-like tokenization,
    observation splitting, known command verbs, and drag endpoint structure.
    Replay dispatch, fixture resolution, Tk events, and golden comparison are
    later-stage responsibilities.
    """

    lines = tuple(text.splitlines())
    trailing_newline = text.endswith("\n")
    current_section: str | None = None
    next_section_index = 0
    entries_by_section: dict[str, list[SessionEntry]] = {
        section: [] for section in SECTION_ORDER
    }

    for line_number, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        location = SourceLocation(source_name, line_number)
        if not stripped or stripped.startswith("#"):
            continue
        if stripped in SECTION_INDEX:
            current_section, next_section_index = _advance_section(
                stripped,
                next_section_index,
                location,
            )
            continue
        if current_section is None:
            raise SessionParseError(location, "expected setup section before entries")
        entry = _parse_entry(raw_line, current_section, location)
        entries_by_section[current_section].append(entry)

    if next_section_index != len(SECTION_ORDER):
        missing_section = SECTION_ORDER[next_section_index]
        eof_location = SourceLocation(source_name, len(lines) + 1)
        raise SessionParseError(
            eof_location,
            f"missing {missing_section} section",
        )

    return SessionDocument(
        source_name=source_name,
        setup=tuple(entries_by_section["setup"]),
        actions=tuple(entries_by_section["session"]),
        expectations=tuple(entries_by_section["expect"]),
        lines=lines,
        trailing_newline=trailing_newline,
    )


def write_session_text(document: SessionDocument) -> str:
    """CODEX: Serialize a parsed session document back to its stored text."""

    text = "\n".join(document.lines)
    if document.trailing_newline:
        text += "\n"
    return text


def _advance_section(
    section: str,
    next_section_index: int,
    location: SourceLocation,
) -> tuple[str, int]:
    """CODEX: Enforce the required setup, session, expect section order."""

    if next_section_index >= len(SECTION_ORDER):
        raise SessionParseError(location, f"unexpected {section} section")
    expected_section = SECTION_ORDER[next_section_index]
    if section != expected_section:
        raise SessionParseError(
            location,
            f"expected {expected_section} section before {section}",
        )
    return section, next_section_index + 1


def _parse_entry(
    raw_line: str,
    section: str,
    location: SourceLocation,
) -> SessionEntry:
    """CODEX: Tokenize and validate one non-section session line."""

    try:
        tokens = tuple(shlex.split(raw_line, comments=False, posix=True))
    except ValueError as exc:
        raise SessionParseError(location, str(exc)) from exc
    if not tokens:
        raise SessionParseError(location, "empty command line")
    if tokens.count("->") > 1:
        raise SessionParseError(location, "multiple observation arrows")

    arrow_index = tokens.index("->") if "->" in tokens else len(tokens)
    command_tokens = tokens[:arrow_index]
    observations = tokens[arrow_index + 1 :]
    if not command_tokens:
        raise SessionParseError(location, "missing command before observations")
    if "->" in tokens and not observations:
        raise SessionParseError(location, "missing observations after arrow")
    if observations and section != "session":
        raise SessionParseError(location, "observations are allowed only in session")

    verb = command_tokens[0]
    definition = action_definition(section, verb)
    if definition is None:
        raise SessionParseError(location, f"unknown {section} verb {verb!r}")

    validator = definition.validator
    if validator == "drag":
        _validate_drag(command_tokens, location)
    elif validator == "resize":
        _validate_resize(command_tokens, location)
    elif validator == "submit":
        _validate_submit(command_tokens, location)
    elif validator == "command":
        _validate_command(command_tokens, location)
    elif validator == "scroll":
        _validate_scroll(command_tokens, location)
    elif validator == "zoom":
        _validate_zoom(command_tokens, location)
    elif validator == "semantic_point":
        _validate_semantic_point(command_tokens, location, verb)

    return SessionEntry(
        location=location,
        section=section,
        verb=verb,
        arguments=command_tokens[1:],
        observations=observations,
        raw=raw_line,
    )


def _validate_drag(
    command_tokens: tuple[str, ...],
    location: SourceLocation,
) -> None:
    """CODEX: Require drag commands to name their endpoint with ``to``."""

    to_count = command_tokens.count("to")
    if to_count != 1:
        raise SessionParseError(location, "drag commands require one to endpoint")
    to_index = command_tokens.index("to")
    if to_index == 1 or to_index == len(command_tokens) - 1:
        raise SessionParseError(location, "drag to endpoint is incomplete")


def _validate_resize(
    command_tokens: tuple[str, ...],
    location: SourceLocation,
) -> None:
    """CODEX: Require resize commands to carry requested window geometry."""

    if len(command_tokens) < 3 or command_tokens[1] != "window":
        raise SessionParseError(location, "resize commands require window size")
    if not _is_size_token(command_tokens[2]):
        raise SessionParseError(location, "resize window size must be WIDTHxHEIGHT")
    if "canvas" in command_tokens:
        canvas_index = command_tokens.index("canvas")
        if canvas_index == len(command_tokens) - 1:
            raise SessionParseError(location, "resize canvas size is incomplete")
        if not _is_size_token(command_tokens[canvas_index + 1]):
            raise SessionParseError(
                location,
                "resize canvas size must be WIDTHxHEIGHT",
            )


def _validate_submit(
    command_tokens: tuple[str, ...],
    location: SourceLocation,
) -> None:
    """CODEX: Require a semantic field submission target and final value."""

    if len(command_tokens) != 3:
        raise SessionParseError(
            location,
            "submit commands require target and value",
        )


def _validate_command(
    command_tokens: tuple[str, ...],
    location: SourceLocation,
) -> None:
    """CODEX: Require a known semantic command name."""

    if len(command_tokens) != 2:
        raise SessionParseError(location, "command actions require a command name")

    if command_definition(command_tokens[1]) is None:
        raise SessionParseError(
            location,
            f"unknown command action {command_tokens[1]!r}",
        )


def _validate_scroll(
    command_tokens: tuple[str, ...],
    location: SourceLocation,
) -> None:
    """CODEX: Require normalized scroll axis, direction, and pointer location."""

    if len(command_tokens) != 6:
        raise SessionParseError(
            location,
            "scroll commands require target axis direction space point",
        )
    if command_tokens[2] not in {"horizontal", "vertical"}:
        raise SessionParseError(location, "scroll axis must be horizontal or vertical")
    direction = command_tokens[3]
    if direction == "0" or not direction.lstrip("-").isdecimal():
        raise SessionParseError(location, "scroll direction must be a non-zero integer")
    if command_tokens[4] not in {"canvas", "image"}:
        raise SessionParseError(location, "scroll space must be canvas or image")


def _validate_zoom(
    command_tokens: tuple[str, ...],
    location: SourceLocation,
) -> None:
    """CODEX: Require a zoom direction and pointer location."""

    if len(command_tokens) != 5:
        raise SessionParseError(
            location,
            "zoom commands require target direction space point",
        )
    if command_tokens[2] not in {"in", "out"}:
        raise SessionParseError(location, "zoom direction must be in or out")
    if command_tokens[3] not in {"canvas", "image"}:
        raise SessionParseError(location, "zoom space must be canvas or image")


def _validate_semantic_point(
    command_tokens: tuple[str, ...],
    location: SourceLocation,
    verb: str,
) -> None:
    """CODEX: Require target, coordinate space, and point for semantic clicks."""

    if len(command_tokens) != 4:
        raise SessionParseError(
            location,
            f"{verb} actions require target space point",
        )
    if command_tokens[2] not in {"canvas", "image"}:
        raise SessionParseError(location, f"{verb} space must be canvas or image")


def _is_size_token(token: str) -> bool:
    """CODEX: Return whether a token has positive integer size syntax."""

    width_text, separator, height_text = token.partition("x")
    if separator != "x":
        return False
    if not width_text.isdecimal() or not height_text.isdecimal():
        return False
    return int(width_text) > 0 and int(height_text) > 0
