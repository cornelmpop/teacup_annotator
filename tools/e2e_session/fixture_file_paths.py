"""CODEX: Translate fixture-owned file paths at the session boundary.

Recording owns the conversion from machine-specific native chooser results to
portable ``<fixture>/...`` tokens. Replay owns the inverse conversion into its
copied output project. Callers retain responsibility for whether a path must
already exist and for the application operation that consumes the file.
"""

from __future__ import annotations

from pathlib import Path
from pathlib import PurePosixPath


FIXTURE_FILE_PREFIX = "<fixture>/"


def fixture_file_token(selected_path: str, project_folder: Path) -> str:
    """CODEX: Return a portable token for a file inside the recorded project.

    ``selected_path`` comes from a native chooser or editable configuration
    field. The processed project is the only portable filesystem namespace in
    a single-fixture session, so paths outside it are rejected rather than
    serialized as machine-specific absolute names.
    """

    # CODEX: Native chooser paths are machine-specific input; only files inside
    # CODEX: the copied fixture have a replayable identity.
    project_root = project_folder.expanduser().resolve()
    selected = Path(selected_path).expanduser().resolve()
    try:
        relative = selected.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(
            "recorded file must be inside the processed fixture folder"
        ) from exc
    if not relative.parts:
        raise ValueError("recorded file choice must identify a file below the fixture")
    return FIXTURE_FILE_PREFIX + relative.as_posix()


def validate_fixture_file_token(token: str) -> PurePosixPath:
    """CODEX: Validate and return the relative portion of a file token.

    The session format always uses POSIX separators, including on platforms
    whose native paths use another separator. Empty paths, absolute paths, and
    parent traversal have no valid identity within the copied fixture.
    """

    if not token.startswith(FIXTURE_FILE_PREFIX):
        raise ValueError("file result must be <fixture>/PATH or cancel")
    raw_relative = token.removeprefix(FIXTURE_FILE_PREFIX)
    relative = PurePosixPath(raw_relative)
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("fixture file path must stay below the fixture folder")
    if relative.as_posix() != raw_relative:
        raise ValueError("fixture file path must use its canonical relative form")
    return relative


def resolve_fixture_file_token(token: str, project_folder: Path) -> Path:
    """CODEX: Map a validated fixture token into the replay output project.

    This function establishes path identity only. It deliberately does not
    check existence because open and save choosers have different filesystem
    contracts and their replay shims own those checks.
    """

    relative = validate_fixture_file_token(token)
    project_root = project_folder.resolve()
    resolved = project_root.joinpath(*relative.parts).resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise ValueError("fixture file path escapes the replay project") from exc
    return resolved
