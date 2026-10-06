"""CODEX: Access packaged schema, defaults, and image assets."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import as_file
from importlib.resources import files
from pathlib import Path

SCHEMA_FILENAME = "Teacup.sql"
PREFERENCE_DEFAULTS_FILENAME = "annotator_prefs.defaults.conf"
ICON_FILENAMES = (
    "archive.png",
    "config.png",
    "delete.png",
    "flag_off.png",
    "flag.png",
    "load.png",
    "logo.png",
    "logo_trans.png",
    "reset_zoom.png",
    "restore.png",
    "run.png",
    "save.png",
)


def read_schema_sql() -> str:
    """CODEX: Return the packaged SQLite schema for new databases."""

    return files(__name__).joinpath(SCHEMA_FILENAME).read_text(encoding="utf-8")


def read_preference_defaults_text() -> str:
    """CODEX: Return the packaged default preference template."""

    return (
        files(__name__)
        .joinpath(PREFERENCE_DEFAULTS_FILENAME)
        .read_text(encoding="utf-8")
    )


@contextmanager
def packaged_icon_path(filename: str) -> Iterator[Path]:
    """CODEX: Yield a filesystem path for a packaged icon or logo image."""

    with as_file(files("annotator").joinpath("icons", filename)) as path:
        yield path


def check_packaged_resources() -> None:
    """CODEX: Read required package resources for installation smoke tests."""

    read_schema_sql()
    read_preference_defaults_text()
    for filename in ICON_FILENAMES:
        with packaged_icon_path(filename) as path:
            path.read_bytes()
