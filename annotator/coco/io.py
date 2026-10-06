"""Read and write COCO JSON backups and split exports for `CocoDocument`.

This module coordinates COCO serialization with filesystem paths, output
publication, and per-image overlay order. SQLite remains authoritative in the
application. These JSON files contain polygon and rectangle region annotations;
arrow annotations remain in SQLite.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from typing import TYPE_CHECKING
import json
import os

from annotator.coco.annotation_editing import normalize_image_polygons
from annotator.coco.annotation_editing import normalize_single_polygons
from annotator.coco.category_helpers import annotation_category_ids_from_json
from annotator.coco.category_helpers import categories_from_json
from annotator.coco.constants import SPLIT_ANNOTATION_FILENAMES
from annotator.coco.image_records import _image_records_by_name
from annotator.coco.image_records import ensure_image_records
from annotator.coco.serialization import _load_annotations
from annotator.coco.serialization import to_image_payload
from annotator.coco.serialization import to_payload
from annotator.project.json_identity_migration import migrate_coco_json_file
from annotator.project.paths import per_image_json_folder
from annotator.project.paths import project_data_folder

if TYPE_CHECKING:
    from annotator.coco.document import CocoDocument


def image_annotation_path(folder: Path, image_name: str) -> Path:
    """Return the per-image JSON backup path for `image_name`.

    Backups live under `teacup/pi_json/`. Directory components are discarded,
    while the complete basename and source extension are retained before
    `.json`, keeping same-stem `.jpg` and `.jpeg` images distinct.
    """

    return per_image_json_folder(folder) / f"{Path(image_name).name}.json"


def save(self: CocoDocument) -> None:
    """Write the complete COCO backup and type-specific region exports.

    Ensure image records exist and normalize all region geometry before writing
    project-root `annotations.json`, followed by the nonempty polygon-only and
    rectangle-only files under `teacup/`. This method does not write per-image
    backups.

    SQLite remains authoritative in the application. Outputs are written
    sequentially, so a later split-export failure does not roll back an earlier
    write. Arrow annotations are excluded.
    """

    ensure_image_records(self)
    normalize_single_polygons(self)
    _write_payload(self, self.path, to_payload(self))
    save_split_annotations(self)


def save_split_annotations(self: CocoDocument) -> dict[str, Path]:
    """Write and return the nonempty type-specific COCO export paths.

    An explicitly marked rectangle enters the rectangle export. Every other
    COCO region annotation enters the polygon export, retaining imported model
    polygons and older JSON rows that were not recognized as rectangles during
    load. Each payload includes only images containing the selected type.

    Delete a stale export when its type has no annotations, and omit that type
    from the returned mapping. Arrow annotations are outside COCO region state
    and are never included.
    """

    ensure_image_records(self)
    normalize_single_polygons(self)
    output_folder = project_data_folder(self.folder)
    output_folder.mkdir(exist_ok=True)
    written_paths: dict[str, Path] = {}
    for annotation_type, filename in SPLIT_ANNOTATION_FILENAMES.items():
        output_path = output_folder / filename
        payload = to_payload(self, annotation_type_filter=annotation_type)
        # An absent type must not leave a stale export that appears current.
        if not payload["annotations"]:
            if output_path.exists():
                output_path.unlink()
            continue
        _write_payload(self, output_path, payload)
        written_paths[annotation_type] = output_path
    return written_paths


def _write_payload(
    self: CocoDocument,
    output_path: Path,
    payload: dict[str, Any],
) -> None:
    """CODEX: Atomically replace one COCO JSON backup from ``payload``.

    Write indented UTF-8 JSON with a final newline to a dot-prefixed sibling,
    then publish the completed file with ``os.replace``. Serialization, write,
    and replacement errors propagate; failure before replacement preserves the
    previous destination.
    """

    temp_path = output_path.with_name(f".{output_path.name}.tmp")
    # CODEX: Keep staging beside the destination so replacement stays atomic.
    with temp_path.open("w", encoding="utf-8") as annotation_file:
        json.dump(payload, annotation_file, indent=2)
        annotation_file.write("\n")
    os.replace(temp_path, output_path)


def save_image(self: CocoDocument, image_name: str) -> Path:
    """Atomically replace one image's COCO JSON backup and return its path.

    Ensure image records exist, normalize only the requested image, and
    serialize its image record, region annotations, and current categories.
    Write a dot-prefixed temporary file beside the destination, then publish it
    with `os.replace`; a write failure before replacement leaves the previous
    backup untouched.
    """

    ensure_image_records(self)
    # Per-image autosave must not mutate unrelated images' editable geometry.
    normalize_image_polygons(self, image_name)
    output_path = image_annotation_path(self.folder, image_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = to_image_payload(self, image_name)
    _write_payload(self, output_path, payload)
    return output_path


def save_all_images(
    self: CocoDocument,
    progress: Callable[[int, int], None] | None = None,
) -> None:
    """Write a per-image COCO JSON backup for every loaded image.

    Follow `image_paths` order and report `(completed, total)` only after each
    atomic replacement succeeds. An empty project makes no callback. An error
    stops the loop without rolling back files already written; combined and
    split outputs are not written here.
    """

    total = len(self.image_paths)
    for index, image_path in enumerate(self.image_paths, start=1):
        save_image(self, image_path.name)
        # Count only backups that have been published successfully.
        if progress is not None:
            progress(index, total)


def load_image_annotation_files(self: CocoDocument) -> None:
    """CODEX: Overlay per-image backups during initial COCO JSON import.

    `annotations.json` supplies the complete baseline, but the application
    refreshes it only during explicit Save. With JSON backups enabled, a
    completed region edit refreshes the corresponding per-image file sooner.
    Per-image files therefore replace their baseline image state so import can
    recover edits made after the last full save.

    No timestamps are compared. A stale per-image file still takes precedence
    and must be removed before import when `annotations.json` should win. Once
    SQLite contains a document, normal project loading bypasses this JSON
    import path.

    Visit only loaded images, in `image_paths` order. Existing files are first
    passed through the explicit JSON identity migration. Their project-relative
    paths label any import notices. Missing backups are ignored, unmatched files
    under `teacup/pi_json/` are not loaded, and JSON or filesystem errors
    propagate to the project-loading boundary.
    """

    for image_path in self.image_paths:
        annotation_path = image_annotation_path(self.folder, image_path.name)
        # Per-image backups are optional, and only loaded names participate.
        if not annotation_path.is_file():
            continue
        migrate_coco_json_file(annotation_path)
        with annotation_path.open("r", encoding="utf-8") as annotation_file:
            payload = json.load(annotation_file)
        source_name = annotation_path.relative_to(self.folder).as_posix()
        load_image_payload(
            self,
            image_path.name,
            payload,
            source_name=source_name,
        )


def load_image_payload(
    self: CocoDocument,
    image_name: str,
    payload: dict[str, Any],
    *,
    source_name: str | None = None,
) -> None:
    """CODEX: Replace one image's imported state from a per-image COCO payload.

    This is the image-local overlay applied after the `annotations.json`
    baseline during initial JSON import. A non-dictionary payload leaves the
    document unchanged. If the baseline supplied no valid categories, adopt
    valid categories from this payload. Replace the requested image record when
    one is supplied; otherwise retain or create its current record.

    For a dictionary payload, translate external category IDs into the internal
    application domain, clear the image's existing region annotations, and load
    only valid annotations whose `image_id` matches that record. When
    ``source_name`` is supplied, append conversion and rejection notices under
    that label. Other image buckets remain untouched, and natural conversion
    errors for the chosen image record propagate.
    """

    if not isinstance(payload, dict):
        return
    categories = categories_from_json(payload.get("categories"))
    # Project-root categories stay authoritative across per-image overlays.
    if categories and not self.has_shared_categories:
        self.categories = categories
    image_records = _image_records_by_name(self, payload.get("images"))
    if image_name in image_records:
        self.image_records[image_name] = image_records[image_name]
    ensure_image_records(self)
    image_id = int(self.image_records[image_name]["id"])
    # Bind only this image ID so payload rows cannot populate other buckets.
    image_name_by_id = {image_id: image_name}
    # Overlay semantics replace this image completely, even with no valid rows.
    self.annotations_by_image[image_name] = []
    _load_annotations(
        self,
        annotation_category_ids_from_json(payload.get("annotations") or []),
        image_name_by_id,
        source_name=source_name,
    )
