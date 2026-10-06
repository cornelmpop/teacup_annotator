"""CODEX: Resolve, execute, and package one RF-DETR model run.

This module owns the reusable domain workflow between GUI preflight and result
installation. It resolves checkpoint and model settings into an immutable run
configuration, executes inference with that configuration, and returns
annotations with enough provenance to reproduce or audit the run.

It does not prompt the user, launch worker threads, parse RF-DETR output
containers, map model coordinates, install annotations into COCO state, write
SQLite rows, or emit audit events.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from annotator.coco import ModelAnnotation
from annotator.model.configuration import read_model_configuration
from annotator.model.configuration import read_rf_detr_checkpoint_metadata
from annotator.model.inference import run_model_on_images


@dataclass(frozen=True, slots=True)
class ModelRunConfiguration:
    """CODEX: Immutable handoff describing one model run before execution.

    The GUI constructs this after weights selection and default-class preflight,
    then passes it to the background worker. ``frozen`` prevents accidental
    mutation across GUI/worker/result boundaries, and ``slots`` keeps the
    record explicit and lightweight.
    """

    weights_path: Path
    model_type: str
    checkpoint_model_name: str
    input_resolution: int
    num_classes: int
    threshold: float
    class_names: dict[int, str]
    threshold_source: Path
    direct_model_name: str | None = None


@dataclass(frozen=True, slots=True)
class ModelRunResult:
    """CODEX: Immutable worker result returned to GUI result installation.

    The result groups generated annotations with the exact configuration,
    weights checksum, and reproducibility metadata. It is still only a handoff
    value; persistence and audit publication belong to the GUI result layer.
    """

    configuration: ModelRunConfiguration
    annotations: list[ModelAnnotation]
    model_md5sum: str
    provenance: dict[str, Any]


def configure_model_run(
    weights_path: Path,
    folder_threshold: str,
    folder_threshold_source: Path,
) -> ModelRunConfiguration:
    """CODEX: Resolve checkpoint, threshold, class, and preprocessing settings.

    Checkpoint metadata normally supplies the output family, input resolution,
    and foreground class count. The same-stem model settings file supplies
    those values when a platform checkpoint omits them, as well as the
    confidence threshold and raw class-ID names. A non-empty loaded-folder
    threshold overrides only the threshold, not the class mapping.

    Parsing and filesystem errors are allowed to propagate naturally to the GUI
    configuration error boundary.
    """

    checkpoint = read_rf_detr_checkpoint_metadata(weights_path)
    model_threshold, class_names = read_model_configuration(weights_path)
    # CODEX: Loaded-folder configuration may override the threshold without changing IDs.
    threshold = float(folder_threshold or model_threshold)
    return ModelRunConfiguration(
        weights_path=weights_path,
        model_type=str(checkpoint["model_type"]),
        checkpoint_model_name=str(checkpoint["checkpoint_model_name"]),
        input_resolution=int(checkpoint["input_resolution"]),
        num_classes=int(checkpoint["num_classes"]),
        threshold=threshold,
        class_names=class_names,
        direct_model_name=checkpoint.get("direct_model_name"),
        # CODEX: The confirmation dialog reports where the active threshold came from.
        threshold_source=(
            folder_threshold_source
            if folder_threshold
            else weights_path.with_suffix(".conf")
        ),
    )


def execute_model_run(
    image_paths: list[Path],
    configuration: ModelRunConfiguration,
    progress: Callable[[int, str], None] | None = None,
) -> ModelRunResult:
    """CODEX: Execute a resolved model run and return annotations with provenance.

    ``configuration`` is assumed to be ready for execution: threshold, class
    names, checkpoint metadata, and preprocessing size have already been
    resolved. This function computes the weights checksum, delegates model
    loading/prediction/mapping to ``run_model_on_images``, and packages the
    provenance that downstream persistence records after a successful install.
    """

    # CODEX: Hash the exact weights bytes used for this run before inference starts.
    with configuration.weights_path.open("rb") as weights_file:
        model_md5sum = hashlib.file_digest(weights_file, "md5").hexdigest()
    # CODEX: Only profile-backed checkpoints need to bypass RF-DETR's own loader.
    model_options: dict[str, str] = {}
    if configuration.direct_model_name is not None:
        model_options["direct_model_name"] = configuration.direct_model_name
    annotations = run_model_on_images(
        image_paths,
        configuration.weights_path,
        configuration.model_type,
        threshold=configuration.threshold,
        model_class_names=configuration.class_names,
        num_classes=configuration.num_classes,
        model_input_size=configuration.input_resolution,
        progress=progress,
        **model_options,
    )
    input_size = configuration.input_resolution
    # CODEX: Persistence layers store this provenance after annotations are installed.
    provenance = {
        "source": "Teacup Annotator model inference",
        "model_type": configuration.model_type,
        "checkpoint_model_name": configuration.checkpoint_model_name,
        "threshold": configuration.threshold,
        "class_names_by_id": configuration.class_names,
        "input_preprocessing": {
            "operation": "aspect-ratio-preserving resize",
            "target_size": [input_size, input_size],
            "resampling": "Pillow LANCZOS",
            "colour_mode": "RGB",
            "padding": "centered white margins",
        },
    }
    return ModelRunResult(
        configuration=configuration,
        annotations=annotations,
        model_md5sum=model_md5sum,
        provenance=provenance,
    )
