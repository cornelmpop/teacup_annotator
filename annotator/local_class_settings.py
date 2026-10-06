"""Read and write the optional folder-local class settings file.

This module owns only the `teacup/classes.json` format for ordered annotation
class names and display colours. GUI prompting lives in
`annotator.gui.local_class_*`, and SQLite remains the authoritative class store
after a folder is loaded.
"""

from __future__ import annotations

import json
from pathlib import Path

from annotator.class_names import class_name_error
from annotator.preferences.validation import validate_class_colour_config
from annotator.project.paths import project_data_folder
from annotator.project.paths import project_file_path


# The filename is stable because project metadata, prompts, and compatibility
# notes refer to the user-visible `teacup/classes.json` settings file.
LOCAL_CLASS_SETTINGS_FILENAME = "classes.json"


def read_local_class_settings(
    folder: Path,
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """CODEX: Read validated folder-local class names and colours when present.

    A missing file returns `None` because local classes are optional. A present
    but malformed file raises `ValueError` so choosing folder classes cannot
    silently fall back to defaults or produce categories without aligned display
    colours.
    """

    path = project_file_path(folder, LOCAL_CLASS_SETTINGS_FILENAME)
    # Absence means "no folder-local override"; malformed presence is handled
    # below.
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("classes"), list):
        raise ValueError("classes.json must contain a 'classes' list.")

    names: list[str] = []
    colours: list[str] = []
    # Preserve file order because it drives class display order and shortcuts.
    for entry in payload["classes"]:
        if not isinstance(entry, dict):
            raise ValueError("Each classes.json entry must contain a name and colour.")
        name_value = entry.get("name")
        colour_value = entry.get("colour")
        if not isinstance(name_value, str) or not isinstance(colour_value, str):
            raise ValueError("Each classes.json name and colour must be text.")
        name = name_value.strip()
        colour = colour_value.strip()
        names.append(name)
        colours.append(colour)

    if not names:
        raise ValueError("classes.json must define at least one class.")
    name_error = class_name_error(names)
    if name_error is not None:
        raise ValueError(name_error)
    error = validate_class_colour_config(tuple(names), tuple(colours))
    if error is not None:
        raise ValueError(error)
    return tuple(names), tuple(colours)


def write_local_class_settings(
    folder: Path,
    class_names: tuple[str, ...],
    class_colours: tuple[str, ...],
) -> Path:
    """CODEX: Validate and atomically write ordered class names and colours.

    Callers may arrive from manual class editing or model-profile import, so
    the writer enforces the same JSON contract as the reader before publishing
    the settings file under `teacup/`.
    """

    # Mirror reader validation before writing so this file never publishes a
    # `classes.json` that the application would reject on the next load.
    if not class_names:
        raise ValueError("At least one annotation class is required.")
    name_error = class_name_error(name.strip() for name in class_names)
    if name_error is not None:
        raise ValueError(name_error)
    error = validate_class_colour_config(class_names, class_colours)
    if error is not None:
        raise ValueError(error)

    project_folder = project_data_folder(folder)
    project_folder.mkdir(exist_ok=True)
    path = project_folder / LOCAL_CLASS_SETTINGS_FILENAME
    # Write through a hidden sibling file so interruption cannot leave a
    # partial JSON payload at the user-visible path.
    temporary_path = project_folder / f".{LOCAL_CLASS_SETTINGS_FILENAME}.tmp"
    payload = {
        "classes": [
            {"name": name.strip(), "colour": colour.strip()}
            for name, colour in zip(class_names, class_colours)
        ]
    }
    # Keep the settings file ASCII-only and consistently formatted for
    # portability and straightforward human inspection.
    temporary_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return path
