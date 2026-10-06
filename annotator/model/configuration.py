"""CODEX: Read and write model configuration used by RF-DETR workflows.

This module owns three configuration inputs: the loaded folder's
``teacup/model.conf`` settings file, RF-DETR checkpoint metadata required before
model construction, and the same-stem ``.conf`` file next to model weights that
provides inference settings plus explicit architecture metadata when a platform
checkpoint omits it.

It does not run inference, validate the selected default class against a model
profile, choose session overrides, or persist project state beyond the folder
model settings file.
"""

from __future__ import annotations

import argparse
import configparser
from pathlib import Path
from typing import NotRequired
from typing import TypedDict

from annotator.class_names import class_name_error
from annotator.preferences.files import read_loose_key_value_file
from annotator.project.paths import project_data_folder
from annotator.project.paths import project_file_path

MODEL_CONF_FILENAME = "model.conf"
MODEL_CONF_KEYS = (
    "model_weights",
    "default_class",
)
FOLDER_MODEL_CONF_KEYS = (*MODEL_CONF_KEYS, "default_threshold", "class_order")


class RFDetrCheckpointMetadata(TypedDict):
    """CODEX: RF-DETR checkpoint values required before constructing the model.

    ``model_type`` records the object-detection versus segmentation output
    family, ``input_resolution`` controls preprocessing size, ``num_classes``
    identifies RF-DETR's foreground class count, and ``checkpoint_model_name``
    stores the best model-name value present in checkpoint arguments.
    """

    model_type: str
    input_resolution: int
    num_classes: int
    checkpoint_model_name: str
    direct_model_name: NotRequired[str]


def read_model_conf(folder: Path) -> dict[str, str]:
    """CODEX: Read persisted folder model settings from ``teacup/model.conf``.

    The current file format is a ``[model]`` section, while older files may use
    ``[prefs]`` or loose ``key = value`` lines. Keys are normalized to
    lowercase, values are stripped, and only known non-empty folder model keys
    are returned.

    A missing file returns an empty dictionary. The class-name domain validates
    a supplied ``default_class`` here, where external folder configuration
    enters runtime state. The caller owns prompts and default preference
    handling. Values are literal text; percent signs are not interpolation
    syntax.
    """

    path = project_file_path(folder, MODEL_CONF_FILENAME)
    if not path.is_file():
        return {}
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error:
        # CODEX: Loose key/value parsing keeps hand-authored model.conf files readable.
        values = read_loose_key_value_file(path)
    else:
        # CODEX: Current files use [model]; older preference-derived files used [prefs].
        if parser.has_section("model"):
            values = dict(parser.items("model"))
        elif parser.has_section("prefs"):
            values = dict(parser.items("prefs"))
        else:
            # CODEX: Sectionless files are treated as loose key/value model settings.
            values = read_loose_key_value_file(path)
    values = {key.lower(): value for key, value in values.items()}
    # CODEX: Return only settings this folder-level profile is allowed to restore.
    settings = {
        key: values[key].strip()
        for key in FOLDER_MODEL_CONF_KEYS
        if values.get(key, "").strip()
    }
    default_class = settings.get("default_class")
    if default_class is not None:
        error = class_name_error((default_class,))
        if error is not None:
            raise ValueError(error)
    return settings


def save_model_conf(folder: Path, values: dict[str, str]) -> Path:
    """CODEX: Write active folder model settings to ``teacup/model.conf``.

    Only folder-restorable model keys are emitted under the ``[model]`` section.
    Missing values are written as empty strings so the file keeps a stable shape
    for manual review and future saves. Values are written literally, including
    percent signs.
    """

    project_data_folder(folder).mkdir(exist_ok=True)
    path = project_file_path(folder, MODEL_CONF_FILENAME)
    parser = configparser.ConfigParser(interpolation=None)
    parser["model"] = {key: values.get(key, "") for key in FOLDER_MODEL_CONF_KEYS}
    with path.open("w", encoding="utf-8") as model_file:
        parser.write(model_file)
    return path


def read_rf_detr_checkpoint_metadata(
    weights_path: Path,
) -> RFDetrCheckpointMetadata:
    """CODEX: Return RF-DETR metadata needed before loading inference classes.

    Self-describing checkpoints contain ``args.segmentation_head``,
    ``args.resolution``, and ``args.num_classes`` as a dictionary or
    ``argparse.Namespace``. When ``segmentation_head`` is absent, a
    ``[checkpoint]`` section in the same-stem model profile supplies the model
    name, output family, preprocessing size, and constructor class count.
    Profile values are literal text; percent signs are not interpolation syntax.

    PyTorch owns checkpoint deserialization. This helper translates missing or
    ill-typed required metadata into focused ``ValueError`` messages for the
    model run workflow.
    """

    try:
        import torch
    except ImportError as exc:
        raise ImportError(
            "PyTorch is required to inspect RF-DETR model weights."
        ) from exc
    try:
        with torch.serialization.safe_globals([argparse.Namespace]):
            checkpoint = torch.load(
                weights_path,
                map_location="cpu",
                weights_only=True,
            )
    except Exception as exc:
        raise ValueError(f"Could not inspect RF-DETR checkpoint: {exc}") from exc
    if not isinstance(checkpoint, dict):
        raise ValueError("RF-DETR checkpoint does not contain model metadata.")
    arguments = checkpoint.get("args")
    # CODEX: RF-DETR checkpoints store training arguments as either a dict or Namespace.
    if isinstance(arguments, dict):
        argument_values = arguments
    elif isinstance(arguments, argparse.Namespace):
        argument_values = vars(arguments)
    else:
        raise ValueError("RF-DETR checkpoint does not contain model arguments.")
    segmentation_head = argument_values.get("segmentation_head")
    if segmentation_head is None:
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(weights_path.with_suffix(".conf"), encoding="utf-8")
        if parser.has_section("checkpoint"):
            profile = parser["checkpoint"]
            model_name = (
                checkpoint.get("model_name")
                or argument_values.get("model_name")
                or profile["model_name"]
            )
            return {
                "model_type": profile["model_type"],
                "input_resolution": profile.getint("input_resolution"),
                "num_classes": profile.getint("num_classes"),
                "checkpoint_model_name": model_name,
                "direct_model_name": model_name,
            }
    if not isinstance(segmentation_head, bool):
        raise ValueError(
            "RF-DETR checkpoint does not identify whether it uses a "
            "object-detection or segmentation head."
        )
    resolution = argument_values.get("resolution")
    # CODEX: Booleans are ints in Python, so reject them explicitly for numeric fields.
    if (
        isinstance(resolution, bool)
        or not isinstance(resolution, int)
        or resolution <= 0
    ):
        raise ValueError(
            "RF-DETR checkpoint does not identify a valid input resolution."
        )
    num_classes = argument_values.get("num_classes")
    # CODEX: Booleans are ints in Python, so reject them explicitly for numeric fields.
    if (
        isinstance(num_classes, bool)
        or not isinstance(num_classes, int)
        or num_classes <= 0
    ):
        raise ValueError("RF-DETR checkpoint does not identify a valid class count.")
    return {
        "model_type": "segmentation" if segmentation_head else "detection",
        "input_resolution": resolution,
        "num_classes": num_classes,
        "checkpoint_model_name": _checkpoint_model_name(
            argument_values,
            weights_path,
        ),
    }


def read_model_configuration(model_path: Path) -> tuple[float, dict[int, str]]:
    """CODEX: Read inference threshold and raw class-ID names next to ``model_path``.

    The same-stem ``.conf`` file is required by model execution.
    ``[inference]`` provides the confidence threshold, and ``[classes]`` maps the
    model's literal numeric class IDs to class names without reindexing.
    Profile values are literal text; percent signs are not interpolation syntax.

    The class-name domain owns name syntax and case-insensitive uniqueness.
    ``configparser`` owns all other file and option errors so missing or
    malformed model profiles surface naturally to the caller.
    """

    parser = configparser.ConfigParser(interpolation=None)
    with model_path.with_suffix(".conf").open(encoding="utf-8") as config_file:
        parser.read_file(config_file)
    class_names = {
        int(class_id): class_name
        for class_id, class_name in parser["classes"].items()
    }
    error = class_name_error(class_names.values())
    if error is not None:
        raise ValueError(error)
    return parser.getfloat("inference", "threshold"), class_names


def _checkpoint_model_name(
    argument_values: dict[str, object],
    weights_path: Path,
) -> str:
    """CODEX: Return the best available checkpoint model-name label."""

    for key in ("checkpoint_model_name", "model_name", "modelname", "model"):
        value = str(argument_values.get(key) or "").strip()
        if value:
            return value
    return weights_path.stem
