"""CODEX: Public SQLite JSON bridge API for native row helpers."""

from __future__ import annotations

from annotator.sqlite.json.classes import _upsert_class_rows
from annotator.sqlite.json.codec import _coerce_int
from annotator.sqlite.json.codec import _json_dumps
from annotator.sqlite.json.codec import _json_loads
from annotator.sqlite.json.components import _delete_region_annotations_for_image
from annotator.sqlite.json.components import _synchronize_region_annotations_for_image
from annotator.sqlite.json.components import _upsert_region_annotation
from annotator.sqlite.json.context import _ensure_project_image_row
from annotator.sqlite.json.detection import _report_progress
from annotator.sqlite.json.detection import json_migration_required
from annotator.sqlite.json.detection import json_sources_exist
from annotator.sqlite.json.detection import native_project_established

__all__ = [
    "_coerce_int",
    "_delete_region_annotations_for_image",
    "_ensure_project_image_row",
    "_json_dumps",
    "_json_loads",
    "_report_progress",
    "_synchronize_region_annotations_for_image",
    "_upsert_class_rows",
    "_upsert_region_annotation",
    "json_migration_required",
    "json_sources_exist",
    "native_project_established",
]
