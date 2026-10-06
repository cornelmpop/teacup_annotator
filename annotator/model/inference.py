"""CODEX: Run RF-DETR inference and convert outputs to model annotations.

This module owns the execution boundary after model-run configuration has been
resolved. It asks RF-DETR to load the checkpoint so the library can infer the
concrete model variant or constructs a profile-named class, prepares each image
with the supported square preprocessing, calls prediction with the active
confidence threshold, and maps normalized model outputs into image-space
``ModelAnnotation`` objects.

It does not read model configuration, choose thresholds, persist annotations,
write audit events, or decide GUI replacement behavior.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image

from annotator.coco import ModelAnnotation
from annotator.model.geometry import box_polygon
from annotator.model.geometry import map_model_input_polygon_to_image
from annotator.model.geometry import resize_to_square
from annotator.model.outputs import iter_detection_records
from annotator.model.outputs import polygons_from_detection

ProgressCallback = Callable[[int, str], None]


def run_model_on_images(
    image_paths: list[Path],
    weights_path: Path,
    model_type: str,
    threshold: float,
    model_class_names: dict[int, str],
    num_classes: int,
    model_input_size: int,
    progress: ProgressCallback | None = None,
    device: str = "cpu",
    direct_model_name: str | None = None,
) -> list[ModelAnnotation]:
    """CODEX: Run one RF-DETR checkpoint over all requested images.

    ``model_type`` is RF-DETR's checkpoint output family, currently
    ``detection`` for object-detection checkpoints or ``segmentation`` for
    segmentation checkpoints. ``direct_model_name`` names the RF-DETR class
    only when a same-stem profile had to supply omitted checkpoint architecture
    metadata. Progress callbacks receive coarse loading, per-image, and
    completion updates.

    Importing RF-DETR is delayed until this boundary so the rest of the app can
    load without the optional inference package.
    """

    try:
        # CODEX: Import here so non-inference workflows do not require RF-DETR at startup.
        import rfdetr
    except ImportError as exc:
        raise ImportError(
            "RF-DETR is not installed in this Python environment. "
            "Install Teacup Annotator with model support or install the "
            f"rfdetr package. Import error: {exc}"
        ) from exc

    if model_type not in {"detection", "segmentation"}:
        # CODEX: Keep unsupported model-family metadata explicit instead of guessing.
        raise ValueError(f"Unsupported RF-DETR model type: {model_type}")
    model_label = "object-detection" if model_type == "detection" else model_type
    emit(progress, 0, f"Loading RF-DETR {model_label} model")
    if direct_model_name is None:
        model = rfdetr.RFDETR.from_checkpoint(
            str(weights_path),
            device=device,
        )
    else:
        model_class = getattr(rfdetr, direct_model_name)
        model = model_class(
            pretrain_weights=str(weights_path),
            device=device,
            num_classes=num_classes,
            resolution=model_input_size,
        )

    results: list[ModelAnnotation] = []
    total = max(1, len(image_paths))
    for index, image_path in enumerate(image_paths, start=1):
        emit(
            progress,
            round((index - 1) * 100 / total),
            f"Running model on {image_path.name} ({index} of {len(image_paths)})",
        )
        results.extend(
            run_model_on_one_image(
                model,
                image_path,
                threshold,
                model_class_names,
                num_classes,
                model_input_size,
            )
        )
    # CODEX: Progress is image-based; final annotation count is known only after mapping.
    emit(progress, 100, f"Model complete: {len(results)} annotations")
    return results


def run_model_on_one_image(
    model: Any,
    image_path: Path,
    threshold: float,
    model_class_names: dict[int, str],
    num_classes: int,
    model_input_size: int,
) -> list[ModelAnnotation]:
    """CODEX: Run an already-loaded model on one image and return annotations.

    The image is converted to RGB, resized into the configured white square
    input, and passed to RF-DETR with an explicit ``shape`` matching that square.
    Output normalization is delegated to ``annotator.model.outputs``.

    The configured class mapping owns literal RF-DETR output IDs and may map
    ``num_classes`` for legacy platform checkpoints. An unmapped output at
    ``num_classes`` is RF-DETR's current background/no-object slot and is
    skipped. Every other returned class ID must exist in ``model_class_names``.
    Segmentation polygons are preserved when present, while box-only output
    becomes editable rectangle annotations.
    """

    with Image.open(image_path) as source:
        original = source.convert("RGB")
    model_input = resize_to_square(original, model_input_size)
    # CODEX: RF-DETR expects the same square size passed through the shape argument.
    model_output = model.predict(
        model_input,
        threshold=threshold,
        shape=(model_input_size, model_input_size),
    )

    annotations: list[ModelAnnotation] = []
    for detection in iter_detection_records(model_output):
        class_id = int(detection["class_id"])
        # CODEX: A literal profile mapping overrides the conventional background slot.
        if class_id == num_classes and class_id not in model_class_names:
            continue
        # CODEX: Deliberate lookup: missing IDs mean model settings do not match output.
        model_class_names[class_id]
        polygons = polygons_from_detection(detection)
        annotation_type = "polygon"
        if not polygons:
            # CODEX: Box-only object-detection results become editable rectangles.
            polygons = (box_polygon(detection["xyxy"]),)
            annotation_type = "rectangle"
        mapped_polygons = [
            mapped
            for polygon in polygons
            if (
                mapped := map_model_input_polygon_to_image(
                    polygon,
                    original.width,
                    original.height,
                    model_input_size,
                )
            )
        ]
        # CODEX: Drop outputs whose geometry maps entirely outside image content.
        if mapped_polygons:
            annotations.append(
                ModelAnnotation(
                    image_name=image_path.name,
                    category_id=class_id,
                    polygons=[list(polygon) for polygon in mapped_polygons],
                    score=float(detection["confidence"]),
                    annotation_type=annotation_type,
                )
            )
    return annotations


def emit(progress: ProgressCallback | None, value: int, message: str) -> None:
    """CODEX: Send one progress update when a callback was supplied.

    The inference layer treats progress as optional so tests and non-GUI callers
    can run without constructing Tk-facing state.
    """

    if progress is not None:
        progress(value, message)
