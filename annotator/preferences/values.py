"""Interpret raw preference strings without owning file persistence.

Preference files store editable text. This module materializes the current raw
schema and centralizes how those strings become paths, numbers, booleans, class
names, and colour lists. GUI code can then share runtime interpretation rules
without knowing how ``annotator_prefs.conf`` is loaded or saved.

It does not read or write files, show edit-time validation messages, verify
path existence, mutate stored values during typed reads, or apply live GUI
effects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from annotator.class_names import class_name_error


def fill_preference_defaults(
    values: dict[str, str],
    defaults: Mapping[str, str],
    app_version: object,
) -> bool:
    """Materialize missing current preference keys in `values`.

    This is the mutating helper in this module. It fills the supplied raw
    mapping with the active schema and returns whether a save is needed.
    Existing non-empty values are preserved because explicit user choices should
    survive version bumps. Blank values are replaced only when the schema
    default is non-blank, so intentionally blank metadata fields remain
    complete without forcing a save on every startup.
    """

    changed = False
    for key, value in defaults.items():
        current = values.get(key)
        # Missing keys must be added even when their default is blank so a saved
        # preference file records the complete current schema.
        if current is None:
            values[key] = value
            changed = True
            continue
        # Blank user values are filled only when the default has useful content;
        # blank metadata defaults are valid completed values.
        if not current.strip() and value.strip():
            values[key] = value
            changed = True
    release_version = str(app_version)
    # The version marker records that this file has been checked against the
    # running release's default schema without performing legacy migrations.
    if values.get("prefs_version", "").strip() != release_version:
        values["prefs_version"] = release_version
        changed = True
    return changed


def preference_path(values: Mapping[str, str], key: str) -> Path | None:
    """Return an expanded path preference, or None when the key is blank.

    The path may contain ``~`` and is not required to exist here. Callers own
    whether a missing project folder, image folder, or model path is acceptable
    for the workflow they are about to run.
    """

    value = values.get(key, "").strip()
    return Path(value).expanduser() if value else None


def preference_int(
    values: Mapping[str, str],
    key: str,
    default: int,
    minimum: int | None = None,
) -> int:
    """Return an integer preference with a caller-owned fallback.

    Preferences are user-editable text, so typed readers treat malformed values
    as unusable and return the runtime default supplied by the caller instead of
    silently changing the stored mapping. The optional minimum is a runtime
    acceptability rule, not file validation.
    """

    try:
        value = int(values.get(key, "").strip())
    except ValueError:
        # Typed reads never repair raw preference text.
        return default
    # Callers choose the lowest acceptable value for their own workflow.
    if minimum is not None and value < minimum:
        return default
    return value


def preference_float(
    values: Mapping[str, str],
    key: str,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Return a float preference with caller-defined bounds.

    Bounds are enforced at read time because different consumers may have
    different safe runtime ranges while sharing the same text preference store.
    Malformed or out-of-range text falls back without rewriting preferences.
    """

    try:
        value = float(values.get(key, "").strip())
    except ValueError:
        # Malformed text stays visible in the editable preference file.
        return default
    # Runtime callers own the acceptable numeric range for each use.
    if minimum is not None and value < minimum:
        return default
    if maximum is not None and value > maximum:
        return default
    return value


def preference_bool(values: Mapping[str, str], key: str, default: bool) -> bool:
    """Return a boolean preference using the accepted text spellings.

    Boolean parsing is centralized so menu handlers, startup defaults, and live
    controls agree on the same true/false vocabulary while leaving unknown text
    to the caller's runtime fallback. Accepted true values are ``1``, ``yes``,
    ``true``, and ``on``; accepted false values are ``0``, ``no``, ``false``,
    and ``off``.
    """

    value = values.get(key, "").strip().lower()
    if value in {"1", "yes", "true", "on"}:
        # Multiple human-editable spellings map to the same checkbox state.
        return True
    if value in {"0", "no", "false", "off"}:
        return False
    # Unknown text is a runtime read problem, not a file rewrite request.
    return default


def preference_default_class(
    values: Mapping[str, str],
    defaults: Mapping[str, str],
) -> str:
    """CODEX: Return the validated default manual annotation class.

    A blank configured value falls back to the active defaults so new annotation
    workflows always have a class name even before the configuration window has
    saved a complete preference file. The class-name domain validates the
    selected value here, where editable preference text enters runtime state.
    """

    value = values.get("default_class", "").strip()
    default_class = value or defaults["default_class"].strip()
    error = class_name_error((default_class,))
    if error is not None:
        raise ValueError(error)
    return default_class


def preference_class_colours(
    values: Mapping[str, str],
    defaults: Mapping[str, str],
) -> tuple[str, ...]:
    """Return display colours parsed from the configured class colour list.

    Colours are positional rather than keyed because the rest of the app maps
    them onto the active class order. Empty list items are ignored to match the
    lightweight comma-separated preference format and support hand-edited text.
    """

    return parse_comma_separated_values(
        values.get("class_colours", defaults["class_colours"])
    )


def parse_comma_separated_values(raw_value: str) -> tuple[str, ...]:
    """Return stripped comma-separated values.

    Empty items are skipped so users can format preference lists with spaces or
    trailing commas without creating blank class names, colour entries, or
    model class-order items.
    """

    return tuple(value.strip() for value in raw_value.split(",") if value.strip())
