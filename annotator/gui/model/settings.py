"""Resolve active model, class, colour, and default settings for GUI workflows."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from typing import Any
from typing import cast
from typing import Protocol

from annotator.coco.category_helpers import is_unused_default_category
from annotator.gui.constants import ANNOTATION_OUTLINE
from annotator.gui.state import ProjectState
from annotator.preferences import Preferences
from annotator.preferences.validation import is_hex_colour
from annotator.preferences.values import parse_comma_separated_values


class ModelSettingsHost(Protocol):
    """Project, preferences, and session choice used by model settings."""

    project: ProjectState
    prefs: Preferences
    session_default_class_var: tk.StringVar


def active_model_value(host: ModelSettingsHost, key: str) -> str:
    """Return a model setting from session overrides or preferences."""

    session_value = host.project.session_model_values.get(key, "").strip()
    if session_value:
        return session_value
    return host.prefs.values.get(key, "").strip()


def configured_default_class(host: ModelSettingsHost) -> str:
    """Return the persisted folder or application default class."""

    return active_model_value(host, "default_class") or host.prefs.get_default_class()


def active_default_class(host: ModelSettingsHost) -> str:
    """Return the volatile session choice used for new annotations."""

    session_class = host.session_default_class_var.get().strip()
    return session_class or configured_default_class(host)

# CMP: TODO - fix the return - it should be a simple, readable statement,
#      which this one is not.
def active_class_names(host: ModelSettingsHost) -> tuple[str, ...]:
    """CODEX: Return display classes without leaking unused setup state."""

    document_names: tuple[str, ...] = ()
    if host.project.coco is not None:
        candidate_names = host.project.coco.category_names()
        has_annotations = any(host.project.coco.annotations_by_image.values())

        # CMP: TODO - Check why we are giving 'object' special treatment. 'object' could be a
        # valid class name.
        if not is_unused_default_category(candidate_names, has_annotations):
            document_names = candidate_names
    if host.project.using_local_class_settings and host.project.session_class_names:
        extras = tuple(
            name
            for name in document_names
            if name not in host.project.session_class_names
        )
        class_names = (*host.project.session_class_names, *extras)
    else:
        class_names = document_names or (active_default_class(host),)
    class_order = parse_comma_separated_values(
        host.project.session_model_values.get("class_order", "")
    )
    return tuple(name for name in class_order if name in class_names) + tuple(
        name for name in class_names if name not in class_order
    )


def active_class_colours(host: ModelSettingsHost) -> tuple[str, ...]:
    """Return one display colour for each active annotation class."""

    class_names = active_class_names(host)
    local_colours = dict(
        zip(
            host.project.session_class_names,
            host.project.session_class_colours,
        )
    )
    palette = host.prefs.get_class_colours() or (ANNOTATION_OUTLINE,)
    return tuple(
        local_colours.get(class_name, palette[index % len(palette)])
        for index, class_name in enumerate(class_names)
    )


def class_colour_map(host: ModelSettingsHost) -> dict[str, str]:
    """Return configured editable class colours keyed by class name."""

    return dict(zip(active_class_names(host), active_class_colours(host)))


def configured_colour(
    host: ModelSettingsHost,
    key: str,
    default: str,
) -> str:
    """Return a validated hex colour preference."""

    colour = host.prefs.values.get(key, default).strip()
    return colour if is_hex_colour(colour) else default


def default_annotation_category_id(host: ModelSettingsHost) -> int:
    """Return the default category ID for a newly created annotation."""

    if host.project.coco is None:
        return 1
    class_names = active_class_names(host)
    default_class = active_default_class(host)
    if default_class in class_names:
        return host.project.coco.category_id_for_name(default_class)
    if class_names:
        return host.project.coco.category_id_for_name(class_names[0])
    categories = host.project.coco.categories
    if categories:
        return int(cast(Any, categories[0].get("id", 1)))
    return 1


def active_model_weights_path(host: ModelSettingsHost) -> Path | None:
    """Return the active model weights path when configured."""

    raw_value = active_model_value(host, "model_weights")
    if not raw_value:
        return None
    path = Path(raw_value).expanduser()
    if not path.is_absolute() and host.project.folder is not None:
        path = host.project.folder / path
    return path


def active_model_config_values(host: ModelSettingsHost) -> dict[str, str]:
    """Return active model settings for writing model.conf."""

    weights_path = active_model_weights_path(host)
    return {
        "model_weights": str(weights_path) if weights_path else "",
        "default_threshold": host.project.session_model_values.get(
            "default_threshold", ""
        ),
        "class_order": host.project.session_model_values.get("class_order", ""),
        "default_class": configured_default_class(host),
    }
