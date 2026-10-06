"""CODEX: Own portable syntax and case-insensitive region-class identity."""

from collections.abc import Iterable


WINDOWS_RESERVED_CLASS_NAMES = frozenset(
    {"aux", "con", "nul", "prn"}
    | {
        f"{prefix}{suffix}"
        for prefix in ("com", "lpt")
        for suffix in "123456789¹²³"
    }
)

DEFAULT_CLASS_NAME = "__DEFAULT__"
LEGACY_DEFAULT_CLASS_NAME = "object"


def class_name_key(class_name: str) -> str:
    """CODEX: Return the identity key without changing display spelling."""
    return class_name.casefold()


def class_name_error(class_names: Iterable[str]) -> str | None:
    """CODEX: Return the portable-name or duplicate error, if any."""
    identities: set[str] = set()
    for class_name in class_names:
        allowed = class_name and all(
            character.isalnum() or character in "_-" for character in class_name
        )
        if not allowed:
            return "Class names may contain only alphanumeric characters, _ and -."
        identity = class_name_key(class_name)
        if identity in WINDOWS_RESERVED_CLASS_NAMES:
            return "Class names may not use Windows reserved file names."
        if identity in identities:
            return "Class names must be unique without regard to case."
        identities.add(identity)
    return None
