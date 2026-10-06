"""Validate editable preference and class-setting fields before saving.

This module owns user-facing validation messages for configuration-window
fields and folder-local class settings. Lower-level preference parsing works
with raw strings, and runtime preference readers decide their own fallbacks;
this layer explains invalid editable text before it is persisted.

It does not load preferences, fill missing defaults, interpret typed runtime
values, write settings files, or apply live GUI effects.
"""

from __future__ import annotations

from annotator.class_names import class_name_error


def validate_default_class(value: str) -> str | None:
    """CODEX: Return UI-facing validation text for the default class field.

    ``default_class`` is the scalar manual-annotation class assigned to new
    regions. It follows the shared class-name syntax; comma-separated lists
    belong in class-order settings rather than this single-value preference.
    """

    error = class_name_error((value.strip(),))
    if error is None:
        return None
    if not value.strip():
        return "default_class must contain one class name."
    if "," in value:
        return (
            "default_class must contain one class name, "
            "not a comma-separated list."
        )
    return error


def validate_class_colour_config(
    class_names: tuple[str, ...],
    class_colours: tuple[str, ...],
) -> str | None:
    """Return UI-facing validation text when class names and colours diverge.

    Colours align positionally with class names because class order drives
    labels, buttons, and annotation display colours throughout the UI. The same
    helper is shared by folder-local ``classes.json`` reading/writing and
    preference validation.

    Returning text instead of raising lets GUI callers show a dialog directly,
    while file readers and writers can wrap the same message in ``ValueError``.
    """

    # Positional colour assignment requires one colour per class.
    if len(class_colours) != len(class_names):
        return (
            "class_colours must contain the same number of comma-separated "
            "values as class_names.\n\n"
            f"class_names: {len(class_names)} values\n"
            f"class_colours: {len(class_colours)} values"
        )
    invalid = [colour for colour in class_colours if not is_hex_colour(colour)]
    if invalid:
        # Keep saved colours portable by rejecting named or toolkit-specific text.
        return (
            "class_colours must use hex colour values such as #16a34a.\n\n"
            f"Invalid values: {', '.join(invalid)}"
        )
    return None


def is_hex_colour(value: str) -> bool:
    """Return whether text is a supported CSS-style hex colour.

    The GUI uses Tk-compatible colour strings, so preferences accept the short
    ``#rgb`` and long ``#rrggbb`` forms users are most likely to paste from
    colour pickers. Surrounding whitespace is ignored. Named colours are
    intentionally rejected so persisted values stay portable across Tk widgets
    and CSS-like documentation.
    """

    stripped = value.strip()
    # Hex colours must include the marker and exactly three or six digits.
    if not stripped.startswith("#") or len(stripped) not in {4, 7}:
        return False
    # The accepted syntax is deliberately narrow; callers own fallback colours.
    return all(character in "0123456789abcdefABCDEF" for character in stripped[1:])
