"""CODEX: Generate class-local annotation crops from authoritative region state.

CODEX: Explicit Save rebuilds ``teacup/crops`` with one maximum-quality JPEG
per polygon or rectangle annotation and one crop-coordinate COCO file per class.
This module owns crop naming, source-bound clipping, collision detection, COCO
assembly, and complete-folder publication. Shared geometry owns coordinate
translation; callers own preferences, GUI error reporting, and Save workflow
ordering. Arrow annotations remain outside the region document and therefore
outside crop exports.
"""

from __future__ import annotations

from collections.abc import Callable
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any

from PIL import Image

import annotator.sqlite as sql_backend
from annotator.class_names import class_name_error
from annotator.coco.category_helpers import categories_to_json
from annotator.coco.document import CocoDocument
from annotator.coco.models import Annotation
from annotator.coco.serialize import annotation_payload
from annotator.geom.coordinates import map_polygon_between_spaces
from annotator.project.paths import crops_folder
from annotator.project.paths import project_data_folder


CropProgress = Callable[[int, int], None]
CropSpecification = tuple[Annotation, Path, dict[str, Any]]


def write_annotation_crops_from_database(
    connection: sqlite3.Connection,
    folder: Path,
    image_paths: list[Path],
    padding_px: int,
    progress: CropProgress | None = None,
) -> Path:
    """CODEX: Rebuild crop exports from the authoritative SQLite projection.

    ``image_paths`` defines source order and project scope. Region classes and
    annotations are read from ``connection`` before delegating filesystem work
    to ``write_annotation_crops``. SQLite values are already typed and are not
    normalized again here. Database, image, and filesystem errors propagate to
    the caller's Save boundary.
    """

    document = sql_backend.document_from_database(connection, folder, image_paths)
    return write_annotation_crops(document, padding_px, progress)


def write_annotation_crops(
    document: CocoDocument,
    padding_px: int,
    progress: CropProgress | None = None,
) -> Path:
    """CODEX: Replace ``teacup/crops`` with current class-local crop exports.

    Follow document image and annotation order. Number crops from one for each
    source-image/class pair, write them beside that class's ``annotations.json``,
    and remap the one represented annotation into crop coordinates. Build the
    complete result in a sibling temporary directory so a collision or write
    failure leaves the previous published export available.

    Return the published crops directory. A document without region annotations
    publishes an empty directory. ``padding_px`` is expected to be nonnegative;
    the typed preference boundary owns that constraint.
    """

    specifications = _crop_specifications(document)
    output_folder = crops_folder(document.folder)
    temporary_folder = project_data_folder(document.folder) / ".crops.tmp"
    if temporary_folder.exists():
        shutil.rmtree(temporary_folder)
    temporary_folder.mkdir(parents=True)

    total = sum(len(items) for items in specifications.values())
    completed = 0
    payloads: dict[str, dict[str, Any]] = {}
    for image_path, image_specifications in specifications.items():
        with Image.open(image_path) as source_image:
            image = source_image.convert("RGB")
        for annotation, relative_path, category in image_specifications:
            bounds = crop_bounds(
                annotation.polygons,
                image.width,
                image.height,
                padding_px,
            )
            left, top, right, bottom = bounds
            crop = image.crop(bounds)
            crop_path = temporary_folder / relative_path
            crop_path.parent.mkdir(parents=True, exist_ok=True)
            crop.save(crop_path, "JPEG", quality=100, subsampling=0)

            class_key = relative_path.parent.as_posix()
            payload = payloads.setdefault(
                class_key,
                {
                    "info": {"description": f"Annotation crops for {category['name']}"},
                    "images": [],
                    "annotations": [],
                    "categories": categories_to_json([category]),
                },
            )
            image_id = len(payload["images"]) + 1
            payload["images"].append(
                {
                    "id": image_id,
                    "file_name": relative_path.name,
                    "width": right - left,
                    "height": bottom - top,
                }
            )
            translated_annotation = annotation.clone()
            translated_annotation.polygons = [
                map_polygon_between_spaces(
                    polygon,
                    source_origin=(left, top),
                )
                for polygon in annotation.polygons
            ]
            payload["annotations"].append(
                annotation_payload(translated_annotation, image_id, image_id)
            )
            completed += 1
            if progress is not None:
                progress(completed, total)

    for class_key, payload in payloads.items():
        annotation_path = temporary_folder / class_key / "annotations.json"
        with annotation_path.open("w", encoding="utf-8") as annotation_file:
            json.dump(payload, annotation_file, indent=2)
            annotation_file.write("\n")

    # CODEX: Publish only after every class export succeeds so stale crops are
    # CODEX: removed together and a failed build leaves the previous result intact.
    if output_folder.exists():
        shutil.rmtree(output_folder)
    os.replace(temporary_folder, output_folder)
    return output_folder


def _crop_specifications(
    document: CocoDocument,
) -> dict[Path, list[CropSpecification]]:
    """CODEX: Return ordered crop targets and reject ambiguous output paths.

    Crop numbering restarts for each source-image/class pair, matching the
    Lithics2D convention. Case-insensitive path comparison also protects the
    common macOS and exFAT targets used by Teacup. A collision raises before the
    temporary export directory is touched and names both sources plus the target.
    """

    categories_by_id = {category["id"]: category for category in document.categories}
    specifications: dict[Path, list[CropSpecification]] = {}
    output_sources: dict[str, str] = {}
    class_names_by_folder: dict[str, str] = {}
    for image_path in document.image_paths:
        class_counts: dict[str, int] = {}
        image_specifications: list[CropSpecification] = []
        for annotation in document.annotations_for(image_path.name):
            category = categories_by_id[annotation.category_id]
            class_name = category["name"]
            class_folder = safe_class_folder_name(class_name)
            folded_class_folder = class_folder.casefold()
            previous_class_name = class_names_by_folder.setdefault(
                folded_class_folder,
                class_name,
            )
            if previous_class_name != class_name:
                raise ValueError(
                    "Crop class-folder collision for "
                    f"{previous_class_name!r} and {class_name!r}: {class_folder}"
                )
            class_counts[class_name] = class_counts.get(class_name, 0) + 1
            crop_number = class_counts[class_name]
            relative_path = Path(class_folder) / f"{image_path.stem}_{crop_number}.jpg"
            collision_key = relative_path.as_posix().casefold()
            previous_source = output_sources.setdefault(collision_key, image_path.name)
            if previous_source != image_path.name:
                raise ValueError(
                    "Crop filename collision for "
                    f"{previous_source} and {image_path.name}: "
                    f"{relative_path.as_posix()}"
                )
            image_specifications.append((annotation, relative_path, category))
        specifications[image_path] = image_specifications
    return specifications


def crop_bounds(
    polygons: list[list[tuple[float, float]]],
    image_width: int,
    image_height: int,
    padding_px: int,
) -> tuple[int, int, int, int]:
    """CODEX: Return padded integer bounds clipped to the source image.

    Floor the minimum and ceil the maximum after padding so fractional region
    coordinates remain enclosed. The returned right and bottom coordinates use
    Pillow's exclusive crop convention. Empty polygon input raises the natural
    ``ValueError`` from ``min`` rather than inventing an unusable crop.
    """

    points = [point for polygon in polygons for point in polygon]
    left = max(0, math.floor(min(point[0] for point in points) - padding_px))
    top = max(0, math.floor(min(point[1] for point in points) - padding_px))
    right = min(
        image_width,
        math.ceil(max(point[0] for point in points) + padding_px),
    )
    bottom = min(
        image_height,
        math.ceil(max(point[1] for point in points) + padding_px),
    )
    return left, top, right, bottom


def safe_class_folder_name(class_name: str) -> str:
    """CODEX: Return a class name that is safe as one crop path component.

    Existing SQLite documents can bypass JSON and GUI validation. Crop target
    construction therefore applies the shared class-name contract before any
    temporary or published output is touched. Invalid names raise the domain's
    ``ValueError`` rather than being rewritten into a different class identity.
    """

    error = class_name_error((class_name,))
    if error is not None:
        raise ValueError(error)
    return class_name
