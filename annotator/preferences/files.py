"""Locate, read, and write raw preference text.

This module owns the filesystem boundary for global application preferences:
the platform-specific config directory, packaged default text, raw string
loading, and normalized `[prefs]` INI writing.

It deliberately does not interpret preference types, validate editable values,
materialize missing defaults, apply live GUI effects, or manage folder-local
model settings. `annotator.preferences.values` owns typed interpretation, and
`Preferences` owns the mutable application-facing handle.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path
import sys
from typing import Mapping

from annotator.release_identity import APP_ID
from annotator.resources import read_preference_defaults_text


PREFS_FILENAME = "annotator_prefs.conf"


def platform_config_dir() -> Path:
    """Return the per-user config directory for Teacup preferences.

    Preferences live outside project folders so author metadata,
    recent-folder state, key bindings, display settings, and model defaults
    survive across datasets. The path follows macOS Application Support,
    Windows APPDATA/Roaming, and XDG config conventions.
    """

    # Follow each platform's normal per-user application config location rather
    # than storing global preferences beside whichever project is open.
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_ID
    if sys.platform == "win32":
        # APPDATA is the writable roaming preference root on Windows.
        base = os.environ.get("APPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Roaming") / APP_ID
    # Linux and other platforms follow XDG_CONFIG_HOME, falling back to ~/.config.
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / APP_ID


def platform_preferences_path() -> Path:
    """Return the writable `annotator_prefs.conf` path.

    Keeping the filename construction in one place makes startup, configuration
    editing, and installation documentation use the same storage contract.
    """

    return platform_config_dir() / PREFS_FILENAME


PREFS_PATH: Path = platform_preferences_path()


def read_configured_preference_values(path: Path = PREFS_PATH) -> dict[str, str]:
    """Return packaged defaults overlaid by raw user preferences.

    This bootstraps `DEFAULT_PREFERENCE_VALUES` before a `Preferences` instance
    exists. Packaged defaults define the current schema, and any readable user
    file overlays those raw strings so early callers see the same fallback map
    the application will use during startup.
    """

    values = read_loose_key_value_text(read_preference_defaults_text())
    # User preferences intentionally overlay packaged values so global helpers
    # see the same defaults the running app will materialize on startup.
    values.update(read_loose_key_value_file(path))
    return values


def read_loose_key_value_text(text: str) -> dict[str, str]:
    """Parse `key = value` lines from preference-style text.

    The parser intentionally ignores comments, blank lines, and non-assignment
    lines. It splits only on the first equals sign and returns stripped raw
    strings, which keeps lightweight config text usable without turning this
    module into a typed validation layer.
    """

    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def read_loose_key_value_file(path: Path) -> dict[str, str]:
    """Read a loose `key = value` configuration file when it exists.

    Missing files return an empty mapping because callers decide whether absence
    means "use defaults", "no folder override", or an error at a higher layer.
    """

    if not path.is_file():
        return {}
    return read_loose_key_value_text(path.read_text(encoding="utf-8"))


def load_preference_values(path: Path) -> dict[str, str]:
    """Load preference values from an INI or loose key/value file.

    Teacup writes normalized files with a `[prefs]` section. Headerless
    `key = value` text remains readable so older or hand-edited preference
    files can be loaded and normalized on the next save.

    Loading returns raw strings only; filling defaults and interpreting types
    are separate steps so each rule can be tested without touching the
    filesystem.

    CODEX: INI values are literal text; percent signs are not interpolation
    syntax.
    """

    if not path.is_file():
        return {}
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error:
        # A file that is invalid as INI may still be valid loose config text;
        # let the shared lightweight parser handle that format boundary.
        return read_loose_key_value_file(path)
    if parser.has_section("prefs"):
        # App-written files are authoritative only for the normalized section.
        return dict(parser.items("prefs"))
    # Headerless preference-style files are parsed the same way model `.conf`
    # files are, then normalized to `[prefs]` on the next save.
    return read_loose_key_value_file(path)


def save_preference_values(path: Path, values: Mapping[str, str]) -> None:
    """Write preference values as the normalized `[prefs]` INI file.

    Saving owns parent-directory creation and output format normalization.
    Callers own which keys and raw string values should be persisted.

    CODEX: Values are written literally, including percent signs.
    """

    parser = configparser.ConfigParser(interpolation=None)
    parser["prefs"] = dict(values)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as prefs_file:
        parser.write(prefs_file)
