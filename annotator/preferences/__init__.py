"""Provide the mutable preference handle and active app default map.

This package facade intentionally stays small: `annotator.preferences.files`
owns raw file persistence, `annotator.preferences.values` owns typed
interpretation, and `Preferences` ties those pieces together for GUI code that
expects an object with a path, mutable values, and save-on-set methods.
"""

from __future__ import annotations

from pathlib import Path

from annotator.preferences.files import load_preference_values
from annotator.preferences.files import PREFS_PATH
from annotator.preferences.files import read_configured_preference_values
from annotator.preferences.files import save_preference_values
from annotator.preferences.values import fill_preference_defaults
from annotator.preferences.values import preference_bool
from annotator.preferences.values import preference_class_colours
from annotator.preferences.values import preference_default_class
from annotator.preferences.values import preference_float
from annotator.preferences.values import preference_int
from annotator.preferences.values import preference_path
from annotator.release_identity import APP_VERSION


__all__ = [
    "DEFAULT_PREFERENCE_VALUES",
    "PREFS_PATH",
    "Preferences",
]


DEFAULT_PREFERENCE_VALUES = read_configured_preference_values()


class Preferences:
    """Mutable handle for one `annotator_prefs.conf` file.

    The class keeps the object-shaped API expected by GUI code while delegating
    parsing, default filling, and typed interpretation to module-level helpers.
    That keeps persistent state (`path` plus `values`) separate from the rules
    used to read and interpret that state.
    """

    def __init__(self, path: Path) -> None:
        """Load one preference file and materialize missing defaults.

        Construction normalizes the in-memory schema immediately because GUI
        callers read preferences during startup and should not each repeat
        missing-key checks.
        """

        self.path = path
        self.values = load_preference_values(path)
        if fill_preference_defaults(
            self.values,
            DEFAULT_PREFERENCE_VALUES,
            APP_VERSION,
        ):
            self.save()

    def load(self) -> None:
        """Reload raw preference values without materializing defaults.

        This method exists for callers that explicitly need to discard in-memory
        edits. Normal construction fills defaults immediately so the application
        starts with a complete schema.
        """

        self.values = load_preference_values(self.path)

    def save(self) -> None:
        """Persist the current values using the normalized preference format."""

        save_preference_values(self.path, self.values)

    def ensure_defaults(self) -> None:
        """Fill missing schema defaults and save when values changed."""

        if fill_preference_defaults(
            self.values,
            DEFAULT_PREFERENCE_VALUES,
            APP_VERSION,
        ):
            self.save()

    def get_path(self, key: str) -> Path | None:
        """Return an expanded path preference, or None when unset."""

        return preference_path(self.values, key)

    def set_path(self, key: str, path: Path) -> None:
        """Persist a path preference as editable text."""

        self.values[key] = str(path)
        self.save()

    def get_int(self, key: str, default: int, minimum: int | None = None) -> int:
        """Return an integer preference using a caller-supplied fallback."""

        return preference_int(self.values, key, default, minimum)

    def get_float(
        self,
        key: str,
        default: float,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        """Return a float preference using caller-supplied bounds."""

        return preference_float(self.values, key, default, minimum, maximum)

    def get_bool(self, key: str, default: bool) -> bool:
        """Return a boolean preference using the shared text vocabulary."""

        return preference_bool(self.values, key, default)

    def set_bool(self, key: str, value: bool) -> None:
        """Persist a boolean preference in the normalized text form."""

        self.values[key] = "true" if value else "false"
        self.save()

    def get_default_class(self) -> str:
        """Return the class assigned to new manual annotations by default."""

        return preference_default_class(self.values, DEFAULT_PREFERENCE_VALUES)

    def get_class_colours(self) -> tuple[str, ...]:
        """Return configured class colours in active class order."""

        return preference_class_colours(self.values, DEFAULT_PREFERENCE_VALUES)

    def get_crop_padding_px(self) -> int:
        """CODEX: Return nonnegative crop padding from global preferences.

        CODEX: Malformed or negative editable text uses the packaged default;
        zero is valid when crops should end at the annotation bounds.
        """

        # CODEX: Packaged preference text crosses into the integer domain at
        # CODEX: this typed application-preference boundary.
        default = int(DEFAULT_PREFERENCE_VALUES["crop_padding_px"])
        return self.get_int("crop_padding_px", default, minimum=0)
