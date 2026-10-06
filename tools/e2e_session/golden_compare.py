"""CODEX: Compare canonical replay outputs with committed goldens."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from tools.e2e_session.golden_semantics import semantic_json_mismatch
from tools.e2e_session.session_format import SessionDocument
from tools.e2e_session.session_format import SessionEntry


def compare_golden_outputs(
    document: SessionDocument,
    actual_files: dict[str, str],
) -> None:
    """CODEX: Compare the replay's canonical files with expected outputs."""

    outputs_entry = _outputs_entry(document)
    if outputs_entry is None:
        return
    expected_dir = _expected_directory(document, outputs_entry)
    if not expected_dir.is_dir():
        raise AssertionError(
            f"{outputs_entry.location}: expected output directory does not exist: "
            f"{expected_dir}"
        )
    expected_files = _read_expected_files(expected_dir)
    _assert_file_set(outputs_entry, expected_files, actual_files)
    for relative_path in sorted(actual_files):
        expected = expected_files[relative_path]
        actual = actual_files[relative_path]
        mismatch = _content_mismatch(relative_path, expected, actual)
        if mismatch is not None:
            diff = "".join(
                difflib.unified_diff(
                    expected.splitlines(keepends=True),
                    actual.splitlines(keepends=True),
                    fromfile=f"expected/{relative_path}",
                    tofile=f"actual/{relative_path}",
                )
            )
            raise AssertionError(
                f"{outputs_entry.location}: output mismatch in {relative_path}: "
                f"{mismatch}\n{diff}"
            )


def _content_mismatch(
    relative_path: str,
    expected: str,
    actual: str,
) -> str | None:
    """CODEX: Compare JSON semantically and other canonical files exactly."""

    if not relative_path.endswith(".json"):
        return None if expected == actual else "text differs"
    return semantic_json_mismatch(json.loads(expected), json.loads(actual))


def _outputs_entry(document: SessionDocument) -> SessionEntry | None:
    """CODEX: Return the one optional outputs expectation."""

    outputs_entries = [
        entry for entry in document.expectations if entry.verb == "outputs"
    ]
    if not outputs_entries:
        return None
    if len(outputs_entries) > 1:
        raise AssertionError(
            f"{outputs_entries[1].location}: duplicate outputs expectation"
        )
    entry = outputs_entries[0]
    if len(entry.arguments) != 1:
        raise AssertionError(f"{entry.location}: expect outputs requires one path")
    return entry


def _expected_directory(
    document: SessionDocument,
    entry: SessionEntry,
) -> Path:
    """CODEX: Resolve expected output paths relative to the session file."""

    path = Path(entry.arguments[0])
    if path.is_absolute():
        return path
    source_path = Path(document.source_name)
    if document.source_name.startswith("<"):
        return path.resolve()
    return (source_path.parent / path).resolve()


def _read_expected_files(expected_dir: Path) -> dict[str, str]:
    """CODEX: Read expected golden files beneath one directory."""

    files = {}
    for path in sorted(expected_dir.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(expected_dir).as_posix()
        files[relative_path] = path.read_text(encoding="utf-8")
    return files


def _assert_file_set(
    entry: SessionEntry,
    expected_files: dict[str, str],
    actual_files: dict[str, str],
) -> None:
    """CODEX: Fail when expected and actual canonical file sets differ."""

    expected_names = set(expected_files)
    actual_names = set(actual_files)
    if expected_names == actual_names:
        return
    missing = sorted(actual_names - expected_names)
    extra = sorted(expected_names - actual_names)
    parts = []
    if missing:
        parts.append(f"missing expected files: {', '.join(missing)}")
    if extra:
        parts.append(f"extra expected files: {', '.join(extra)}")
    raise AssertionError(f"{entry.location}: {'; '.join(parts)}")
