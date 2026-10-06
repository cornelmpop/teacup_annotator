"""CODEX: Resolve session-relative fixtures, geometry, and replay preferences."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import shutil

from tools.e2e_session.session_format import SessionDocument
from tools.e2e_session.session_format import SessionEntry
from tools.e2e_session.session_preferences import replay_preference_value
from tools.e2e_session.session_preferences import write_replay_preferences


Size = tuple[int, int]


@dataclass(frozen=True, slots=True)
class ReplaySetup:
    """CODEX: Materialized fixture, preference, and initial geometry state."""

    fixture_name: str
    fixture_source: Path
    project_folder: Path
    window_size: Size | None
    canvas_size: Size | None
    preference_values: dict[str, str]
    preference_path: Path
    model_assets: dict[str, Path]


def prepare_replay_setup(
    document: SessionDocument,
    *,
    fixture_base: Path,
    project_folder: Path,
    model_assets: Mapping[str, Path] | None = None,
) -> ReplaySetup:
    """CODEX: Resolve and copy the fixture into the exact replay project folder.

    The fixture entry is a relative path interpreted against ``fixture_base``;
    file replay supplies the session directory as that base. This function
    materializes the source at the caller's path, rewrites ``<fixture>`` and
    preflighted model-asset preferences, and writes the isolated preferences
    read by ``AnnotatorApp``.
    """

    resolved_model_assets = {} if model_assets is None else dict(model_assets)
    fixture_entry = _single_setup_entry(document, "fixture")
    fixture_reference = _single_argument(fixture_entry)
    # CODEX: Session text is the loose interchange boundary; convert its token
    # CODEX: to the authoritative path representation only while resolving it.
    fixture_path = Path(fixture_reference)
    if fixture_path.is_absolute():
        raise AssertionError(
            f"{fixture_entry.location}: fixture path must be relative to the session"
        )
    fixture_source = (fixture_base / fixture_path).resolve()
    if not fixture_source.is_dir():
        raise AssertionError(
            f"{fixture_entry.location}: fixture path does not resolve to an "
            f"existing directory: {fixture_reference!r}"
        )

    fixture_name = fixture_source.name
    resolved_fixture_source = fixture_source
    resolved_project_folder = project_folder.resolve()
    if (
        resolved_project_folder == resolved_fixture_source
        or resolved_fixture_source in resolved_project_folder.parents
    ):
        raise AssertionError(
            f"{fixture_entry.location}: replay project folder must be outside "
            f"fixture {fixture_source}"
        )
    shutil.copytree(fixture_source, project_folder)

    window_size, canvas_size = _setup_window_size(document)
    preference_overrides = _setup_preferences(
        document,
        project_folder,
        resolved_model_assets,
    )
    preference_values, preference_path = write_replay_preferences(
        preference_overrides
    )

    return ReplaySetup(
        fixture_name=fixture_name,
        fixture_source=fixture_source,
        project_folder=project_folder,
        window_size=window_size,
        canvas_size=canvas_size,
        preference_values=preference_values,
        preference_path=preference_path,
        model_assets=resolved_model_assets,
    )


def _single_setup_entry(
    document: SessionDocument,
    verb: str,
) -> SessionEntry:
    """CODEX: Return the one required setup entry for ``verb``."""

    matches = [entry for entry in document.setup if entry.verb == verb]
    if not matches:
        raise AssertionError(f"{document.source_name}:1: missing {verb} setup")
    if len(matches) > 1:
        raise AssertionError(f"{matches[1].location}: duplicate {verb} setup")
    return matches[0]


def _single_argument(entry: SessionEntry) -> str:
    """CODEX: Return the one argument required by a setup entry."""

    if len(entry.arguments) != 1:
        raise AssertionError(f"{entry.location}: expected one argument for {entry.verb}")
    return entry.arguments[0]


def _setup_window_size(document: SessionDocument) -> tuple[Size | None, Size | None]:
    """CODEX: Return optional startup root and canvas size requests."""

    matches = [entry for entry in document.setup if entry.verb == "window"]
    if not matches:
        return None, None
    if len(matches) > 1:
        raise AssertionError(f"{matches[1].location}: duplicate window setup")

    entry = matches[0]
    if not entry.arguments:
        raise AssertionError(f"{entry.location}: window setup requires a size")
    window_size = parse_size(entry.arguments[0], entry)
    canvas_size = None
    if "canvas" in entry.arguments:
        canvas_index = entry.arguments.index("canvas")
        if canvas_index == len(entry.arguments) - 1:
            raise AssertionError(f"{entry.location}: canvas setup size is incomplete")
        canvas_size = parse_size(entry.arguments[canvas_index + 1], entry)
    return window_size, canvas_size


def _setup_preferences(
    document: SessionDocument,
    project_folder: Path,
    model_assets: Mapping[str, Path],
) -> dict[str, str]:
    """CODEX: Return setup preference overrides with fixture paths rewritten."""

    values: dict[str, str] = {}
    for entry in document.setup:
        if entry.verb != "prefs":
            continue
        for token in entry.arguments:
            key, separator, raw_value = token.partition("=")
            if separator != "=" or not key:
                raise AssertionError(f"{entry.location}: prefs require key=value tokens")
            values[key] = replay_preference_value(
                key,
                raw_value,
                project_folder,
                model_assets,
            )
    return values
def parse_size(token: str, entry: SessionEntry) -> Size:
    """CODEX: Parse one positive ``WIDTHxHEIGHT`` token for replay."""

    width_text, separator, height_text = token.partition("x")
    if (
        separator != "x"
        or not width_text.isdecimal()
        or not height_text.isdecimal()
    ):
        raise AssertionError(f"{entry.location}: expected WIDTHxHEIGHT size")
    width = int(width_text)
    height = int(height_text)
    if width <= 0 or height <= 0:
        raise AssertionError(f"{entry.location}: size values must be positive")
    return width, height
