"""CODEX: Define the in-memory root for COCO region-annotation state.

`CocoDocument` ties a loaded image folder to its polygon and rectangle region
annotations, category vocabulary, COCO image records, and `info` metadata.
Arrow annotations live separately in project state and SQLite.

Focused modules implement editing, category access, image-record management,
JSON I/O, and serialization. This module binds those functions to the document
API and owns state initialization, JSON loading order, import notices, and Undo
snapshots.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from annotator.coco.annotation_editing import add_annotation as _add_annotation
from annotator.coco.annotation_editing import annotations_for as _annotations_for
from annotator.coco.annotation_editing import delete_annotation as _delete_annotation
from annotator.coco.annotation_editing import delete_vertices as _delete_vertices
from annotator.coco.annotation_editing import merge_annotations as _merge_annotations
from annotator.coco.annotation_editing import (
    normalize_image_polygons as _normalize_image_polygons,
)
from annotator.coco.annotation_editing import (
    normalize_single_polygons as _normalize_single_polygons,
)
from annotator.coco.annotation_editing import (
    replace_with_model_annotations as _replace_with_model_annotations,
)
from annotator.coco.category_access import (
    category_id_for_name as _category_id_for_name,
)
from annotator.coco.category_access import (
    category_name_for_id as _category_name_for_id,
)
from annotator.coco.category_access import category_names as _category_names
from annotator.coco.category_helpers import annotation_category_ids_from_json
from annotator.coco.category_helpers import categories_from_json
from annotator.coco.category_helpers import default_categories
from annotator.coco.category_helpers import valid_categories
from annotator.coco.constants import ANNOTATION_FILENAME
from annotator.coco.image_records import (
    _image_records_by_name as _image_records_by_name_method,
)
from annotator.coco.image_records import ensure_image_records as _ensure_image_records
from annotator.coco.image_records import image_id_for as _image_id_for
from annotator.coco.image_records import next_annotation_id as _next_annotation_id
from annotator.coco.io import _write_payload as _write_payload_method
from annotator.coco.io import load_image_annotation_files as _load_image_annotation_files
from annotator.coco.io import load_image_payload as _load_image_payload
from annotator.coco.io import save as _save
from annotator.coco.io import save_all_images as _save_all_images
from annotator.coco.io import save_image as _save_image
from annotator.coco.io import save_split_annotations as _save_split_annotations
from annotator.coco.models import Annotation
from annotator.coco.serialization import _load_annotations as _load_annotations_method
from annotator.coco.serialization import to_image_payload as _to_image_payload
from annotator.coco.serialization import to_payload as _to_payload
from annotator.project.json_identity_migration import migrate_coco_json_file


class CocoDocument:
    """CODEX: Mutable COCO region-annotation document for one image folder.

    `image_paths` defines the loaded project images. Region annotations are
    grouped by image basename, while categories and `info` apply to the whole
    document. File imports retain user-facing geometry conversion and rejection
    notices. Callers own SQLite persistence, arrow-annotation state, audit
    records, report publication, and GUI effects.
    """

    # Keep each responsibility in its semantic module while preserving the
    # document-oriented API used by GUI, persistence, and archive workflows.
    category_id_for_name = _category_id_for_name
    category_name_for_id = _category_name_for_id
    category_names = _category_names
    image_id_for = _image_id_for
    next_annotation_id = _next_annotation_id
    ensure_image_records = _ensure_image_records
    _image_records_by_name = _image_records_by_name_method
    annotations_for = _annotations_for
    add_annotation = _add_annotation
    delete_annotation = _delete_annotation
    merge_annotations = _merge_annotations
    delete_vertices = _delete_vertices
    replace_with_model_annotations = _replace_with_model_annotations
    normalize_single_polygons = _normalize_single_polygons
    normalize_image_polygons = _normalize_image_polygons
    save = _save
    save_split_annotations = _save_split_annotations
    _write_payload = _write_payload_method
    save_image = _save_image
    save_all_images = _save_all_images
    load_image_annotation_files = _load_image_annotation_files
    load_image_payload = _load_image_payload
    to_payload = _to_payload
    to_image_payload = _to_image_payload
    _load_annotations = _load_annotations_method

    def __init__(
        self,
        folder: Path,
        image_paths: list[Path],
        payload: dict[str, Any] | None = None,
        *,
        import_source_name: str | None = None,
    ) -> None:
        """CODEX: Initialize state from an optional in-memory COCO payload.

        The payload may supply `info`, categories, image records, and region
        annotations. A document without supplied categories receives a fresh
        persisted ``__DEFAULT__`` vocabulary. Missing image records are then
        created for the loaded paths. When ``import_source_name`` is supplied, skipped
        rows and detected lossy geometry normalization are appended to
        ``import_notices`` with that source label.

        Construction does not read project files or persist the resulting
        state; `load()` owns JSON discovery and overlay order.
        """

        self.folder: Path = folder
        self.image_paths: list[Path] = image_paths
        self.path: Path = folder / ANNOTATION_FILENAME
        self.payload: dict[str, Any] = payload or {}
        self.info: dict[str, Any] = dict(self.payload.get("info") or {})
        # Remember whether the project-root payload supplied categories because
        # per-image files may supply them only when no shared vocabulary exists.
        payload_categories = valid_categories(self.payload.get("categories"))
        self.has_shared_categories: bool = bool(payload_categories)
        self.categories: list[dict[str, Any]] = (
            payload_categories or default_categories()
        )
        self.image_records: dict[str, dict[str, Any]] = (
            self._image_records_by_name(self.payload.get("images"))
        )
        self.annotations_by_image: dict[str, list[Annotation]] = {
            image_path.name: [] for image_path in self.image_paths
        }
        self.import_notices: list[str] = []
        self._load_annotations(
            self.payload.get("annotations") or [],
            source_name=import_source_name,
        )
        self.ensure_image_records()

    @classmethod
    def load(cls, folder: Path, image_paths: list[Path]) -> "CocoDocument":
        """CODEX: Load project-root and per-image COCO JSON into a document.

        Read `annotations.json` first when present. Per-image files under
        `teacup/pi_json/` then replace the corresponding image record and region
        annotations. A nonempty project-root category vocabulary remains shared;
        otherwise per-image payloads may supply categories.

        Existing files are first passed through the explicit JSON identity
        migration. External category IDs then enter the internal application
        domain through the fixed JSON offset. Imported files contribute source-
        labelled conversion and rejection notices. Missing optional files
        produce an empty/default document. JSON, decoding, category-ID, and
        filesystem errors propagate to the existing project-load boundary.
        """

        path = folder / ANNOTATION_FILENAME
        payload: dict[str, Any] | None = None
        import_source_name: str | None = None
        if path.is_file():
            import_source_name = path.name
            migrate_coco_json_file(path)
            with path.open("r", encoding="utf-8") as annotation_file:
                json_payload = json.load(annotation_file)
            payload = dict(json_payload)
            payload["categories"] = categories_from_json(
                json_payload.get("categories")
            )
            payload["annotations"] = annotation_category_ids_from_json(
                json_payload.get("annotations")
            )
        document = cls(
            folder,
            image_paths,
            payload,
            import_source_name=import_source_name,
        )
        document.load_image_annotation_files()
        return document

    @property
    def annotation_file_exists(self) -> bool:
        """Return whether project-root `annotations.json` currently exists."""

        return self.path.is_file()

    def snapshot(self) -> dict[str, Any]:
        """CODEX: Return an independent Undo snapshot of mutable COCO state.

        The deep copy includes region annotations, image records, categories,
        and `info`. It excludes folder identity, loaded image paths, the JSON
        path, the original payload, category-loading policy, and import notices
        because Undo must not change project identity, loading precedence, or
        the completed import report.

        GUI Undo orchestration snapshots arrow annotations separately.
        """

        return {
            "annotations_by_image": copy.deepcopy(self.annotations_by_image),
            "image_records": copy.deepcopy(self.image_records),
            "categories": copy.deepcopy(self.categories),
            "info": copy.deepcopy(self.info),
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Replace mutable COCO region state from an Undo snapshot.

        Deep-copying the snapshot keeps it independent and reusable. Project
        identity, loaded image paths, JSON-loading policy, and arrow annotations
        remain untouched. The caller owns persistence, auditing, and GUI
        refresh.
        """

        self.annotations_by_image = copy.deepcopy(snapshot["annotations_by_image"])
        self.image_records = copy.deepcopy(snapshot["image_records"])
        self.categories = copy.deepcopy(snapshot["categories"])
        self.info = copy.deepcopy(snapshot["info"])
