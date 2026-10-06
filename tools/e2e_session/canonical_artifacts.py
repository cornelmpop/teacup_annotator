"""CODEX: Project durable E2E state into a human-readable artifact golden.

This module reads application-owned backups and final image locations after a
clean recording or replay. Structured files are decoded so reviews compare
meaning rather than whitespace, while authoritative class, image, and arrow
state comes from the already-open SQLite connection. README and statistics
remain in ``outputs.json`` and are not duplicated here.
"""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import sqlite3
from typing import Any

from annotator.coco import ANNOTATION_FILENAME
from annotator.coco import POLYGON_ANNOTATION_FILENAME
from annotator.coco import RECTANGLE_ANNOTATION_FILENAME
from annotator.log.audit import AUDIT_EVENTS_FILENAME
from annotator.log.audit import DELETION_MARKS_FILENAME
from annotator.log.audit import TRASH_FOLDER_NAME
from annotator.project.paths import PER_IMAGE_JSON_FOLDER_NAME
from annotator.project.paths import PROJECT_DATA_FOLDER_NAME
from annotator.project.paths import per_image_json_folder
from annotator.project.paths import project_file_path
from tools.e2e_session.artifact_sqlite import sqlite_artifact_state


NONDETERMINISTIC_TIME_KEYS = frozenset(
    {"date_modified", "entry_time", "event_time", "started_time", "updated_at"}
)
AUDIT_HOST_VALUES = {
    "host_type": "<host-type>",
    "hostname": "<hostname>",
    "os": "<operating-system>",
    "session_timezone": "<timezone>",
}
EMBEDDED_JSON_KEYS = frozenset(
    {"after_state_json", "before_state_json", "details_json"}
)


def canonical_artifact_file(
    project_folder: Path,
    connection: sqlite3.Connection,
    canonicalize: Callable[[Any], Any],
) -> str:
    """CODEX: Return the canonical ``artifacts.json`` text for one completed project.

    Every fixed optional artifact remains visible with ``null`` when absent.
    Per-image backups are keyed by project-relative path, and root/trash image
    lists expose durable moves without duplicating immutable image bytes. JSON,
    JSONL, and model settings are decoded before the supplied canonicalizer is
    applied. Malformed structured output propagates its natural parser error.
    """

    # CODEX: Defer preference-owning modules until replay has established its
    # CODEX: isolated preference boundary; the application uses these same contracts.
    from annotator.local_class_settings import LOCAL_CLASS_SETTINGS_FILENAME
    from annotator.model.configuration import MODEL_CONF_FILENAME
    from annotator.model.configuration import read_model_conf

    # CODEX: Explicit nulls make a missing required backup visible to a human
    # CODEX: reviewer instead of letting absence disappear from the golden.
    artifact_json_paths = (
        ANNOTATION_FILENAME,
        f"{PROJECT_DATA_FOLDER_NAME}/{POLYGON_ANNOTATION_FILENAME}",
        f"{PROJECT_DATA_FOLDER_NAME}/{RECTANGLE_ANNOTATION_FILENAME}",
        f"{PROJECT_DATA_FOLDER_NAME}/{LOCAL_CLASS_SETTINGS_FILENAME}",
        f"{PROJECT_DATA_FOLDER_NAME}/{DELETION_MARKS_FILENAME}",
    )
    files = {
        relative_path: _json_file(project_folder / relative_path)
        for relative_path in artifact_json_paths
    }
    files.update(_per_image_json_files(project_folder))
    files[f"{PROJECT_DATA_FOLDER_NAME}/{AUDIT_EVENTS_FILENAME}"] = (
        _jsonl_file(project_file_path(project_folder, AUDIT_EVENTS_FILENAME))
    )
    model_path = project_file_path(project_folder, MODEL_CONF_FILENAME)
    files[f"{PROJECT_DATA_FOLDER_NAME}/{MODEL_CONF_FILENAME}"] = (
        read_model_conf(project_folder) if model_path.is_file() else None
    )
    payload = {
        "files": canonicalize(_normalize_artifact_value(files)),
        "images": canonicalize(_image_locations(project_folder)),
        "sqlite": sqlite_artifact_state(connection, canonicalize),
    }
    return f"{json.dumps(payload, indent=2, sort_keys=True)}\n"


def _json_file(path: Path) -> Any:
    """CODEX: Decode one optional JSON artifact, returning null when absent."""

    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl_file(path: Path) -> list[Any] | None:
    """CODEX: Decode nonblank rows from one optional JSONL audit backup."""

    if not path.is_file():
        return None
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _per_image_json_files(project_folder: Path) -> dict[str, Any]:
    """CODEX: Return decoded per-image JSON backups keyed by relative path."""

    folder = per_image_json_folder(project_folder)
    if not folder.is_dir():
        return {}
    return {
        path.relative_to(project_folder).as_posix(): _json_file(path)
        for path in sorted(folder.glob("*.json"))
    }


def _image_locations(project_folder: Path) -> dict[str, list[str]]:
    """CODEX: Return JPEG basenames currently at the project root and in trash."""

    trash_folder = project_file_path(project_folder, TRASH_FOLDER_NAME)
    return {
        "project_root": _jpeg_names(project_folder),
        "trash": _jpeg_names(trash_folder),
    }


def _jpeg_names(folder: Path) -> list[str]:
    """CODEX: Return sorted visible JPEG basenames from one existing directory."""

    if not folder.is_dir():
        return []
    return sorted(
        path.name
        for path in folder.iterdir()
        if path.is_file()
        and not path.name.startswith(".")
        and path.suffix.lower() in {".jpg", ".jpeg"}
    )


def _normalize_artifact_value(value: Any, key: str | None = None) -> Any:
    """CODEX: Normalize known runtime-only fields in readable artifact content.

    COCO backups receive a fresh modification time whenever they are written.
    Audit and deletion backups also include clock, duration, host, and nested
    JSON string fields that differ between equivalent recording and replay
    runs. Replace only those established nondeterministic values, decode the
    nested JSON fields for readable comparison, and otherwise preserve data.
    """

    if key in EMBEDDED_JSON_KEYS and isinstance(value, str):
        return _normalize_artifact_value(json.loads(value))
    if key in NONDETERMINISTIC_TIME_KEYS and value is not None:
        return 0
    if key == "duration_ms" and value is not None:
        return 0
    if key in AUDIT_HOST_VALUES:
        return AUDIT_HOST_VALUES[key]
    if isinstance(value, dict):
        return {
            item_key: _normalize_artifact_value(item_value, item_key)
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_normalize_artifact_value(item) for item in value]
    return value
