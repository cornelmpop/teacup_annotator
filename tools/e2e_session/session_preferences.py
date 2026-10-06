"""CODEX: Isolate and materialize preferences for GUI session tools.

Recording and replay bind Annotator's import-time preference path to temporary
storage. This module also owns path-valued session keys and persistence of the
complete replay preference mapping.
"""

from __future__ import annotations

from collections.abc import Iterator
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import NamedTuple

from tools.e2e_session.model_assets import MODEL_ASSET_PREFIX
from tools.e2e_session.model_assets import resolve_file_token


PATH_PREFERENCE_KEYS = frozenset(
    {"image_folder", "last_image_folder", "model_weights"}
)


class EnvironmentSetting(NamedTuple):
    """CODEX: Preserve one environment variable while preferences bind paths."""

    key: str
    previous_value: str | None


@dataclass(frozen=True, slots=True)
class SessionPreferenceScope:
    """CODEX: Expose the temporary preference root used by one session-tool run."""

    root: Path
    preference_path: Path


def write_replay_preferences(
    overrides: dict[str, str],
) -> tuple[dict[str, str], Path]:
    """CODEX: Merge replay overrides with packaged defaults and persist them.

    Return the complete effective values and the temporary preference-file path
    used by Annotator during this session-tool run.
    """

    from annotator.preferences import DEFAULT_PREFERENCE_VALUES
    from annotator.preferences.files import PREFS_PATH
    from annotator.preferences.files import save_preference_values

    # CODEX: Copy packaged defaults so session overrides cannot mutate their
    # CODEX: authoritative in-memory mapping.
    values = dict(DEFAULT_PREFERENCE_VALUES)
    values.update(overrides)
    save_preference_values(PREFS_PATH, values)
    return values, PREFS_PATH


def replay_preference_value(
    key: str,
    value: str,
    project_folder: Path,
    model_assets: Mapping[str, Path],
) -> str:
    """CODEX: Resolve one stored value at the replay preference text boundary.

    Model weights may use a preflighted asset identity. Other path keys expand
    the copied-fixture placeholder before Annotator reads the preference file.
    """

    if key == "model_weights" and value.startswith(MODEL_ASSET_PREFIX):
        # CODEX: Preference files own path text, while preflight owns the verified Path.
        return str(resolve_file_token(value, project_folder, model_assets))
    rewritten = value.replace("<fixture>", str(project_folder))
    if key in PATH_PREFERENCE_KEYS and rewritten:
        return str(Path(rewritten).expanduser())
    return rewritten


@contextmanager
def session_preferences(
    project_folder: Path,
) -> Iterator[SessionPreferenceScope]:
    """CODEX: Bind Annotator preferences to a temporary session-tool config root.

    Recording and standalone replay must not read or mutate the user's global
    preferences. This context fixes Annotator's import-time ``PREFS_PATH`` to a
    temporary root and seeds the requested project as the startup folder.
    Recorder uses that seed directly; replay replaces it with the session's
    complete preference block before constructing the application.
    """

    if _preferences_already_imported():
        raise RuntimeError(
            "session preferences must be prepared before Annotator imports"
        )

    root = Path(tempfile.mkdtemp(prefix="teacup-session-prefs-")).resolve()
    setting = _set_config_root(root)
    try:
        from annotator.preferences import DEFAULT_PREFERENCE_VALUES
        from annotator.preferences.files import PREFS_PATH
        from annotator.preferences.files import save_preference_values

        values = dict(DEFAULT_PREFERENCE_VALUES)
        # CODEX: Convert the project Path at the text preference-file boundary.
        project_path = str(project_folder.expanduser().resolve())
        values["image_folder"] = project_path
        values["last_image_folder"] = project_path
        save_preference_values(PREFS_PATH, values)
        scope = SessionPreferenceScope(root=root, preference_path=PREFS_PATH)
    finally:
        _restore_environment(setting)

    try:
        yield scope
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _preferences_already_imported() -> bool:
    """CODEX: Return whether Annotator preference paths are already fixed."""

    return (
        "annotator.preferences" in sys.modules
        or "annotator.preferences.files" in sys.modules
    )


def _set_config_root(root: Path) -> EnvironmentSetting:
    """CODEX: Point the platform preference resolver at a temporary root."""

    key = _config_environment_key()
    previous_value = os.environ.get(key)
    # CODEX: Environment variables require text at the operating-system boundary.
    os.environ[key] = str(root)
    return EnvironmentSetting(key, previous_value)


def _restore_environment(setting: EnvironmentSetting) -> None:
    """CODEX: Restore the caller's environment after preference-path binding."""

    if setting.previous_value is None:
        os.environ.pop(setting.key, None)
        return
    os.environ[setting.key] = setting.previous_value


def _config_environment_key() -> str:
    """CODEX: Return the platform variable that owns the user config root."""

    if sys.platform == "darwin":
        return "HOME"
    if sys.platform == "win32":
        return "APPDATA"
    return "XDG_CONFIG_HOME"
