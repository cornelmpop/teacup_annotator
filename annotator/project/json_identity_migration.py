"""CODEX: Migrate legacy JSON identity fields before live project loading.

Current Teacup code uses ``annotation_uuid`` as the only durable annotation
identity name. Older COCO-style JSON backups, audit JSONL backups, and SQLite
JSON blobs may still contain the former ``component_uuid`` key. This module is
the only place that understands that legacy spelling.

File migrations first create ``<original-name>_0.9.8_migration.bak`` beside the
source file, then publish the upgraded content in place. SQLite cleanup rewrites
JSON values only; it does not change the packaged schema.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any

CURRENT_IDENTITY_KEY = "annotation_uuid"
LEGACY_IDENTITY_KEY = "component_uuid"
MIGRATION_BACKUP_SUFFIX = "_0.9.8_migration.bak"
_AUDIT_STATE_FIELDS = ("before_state_json", "after_state_json")
_DETAIL_STATE_FIELDS = ("_before_state_json", "_after_state_json")


def migrate_coco_json_file(path: Path) -> bool:
    """CODEX: Upgrade one COCO-style JSON annotation file when needed."""

    if not path.is_file():
        return False
    with path.open("r", encoding="utf-8") as json_file:
        payload = json.load(json_file)
    if not isinstance(payload, dict):
        raise ValueError(f"Unsupported JSON annotation payload: {path}")
    annotations = payload.get("annotations")
    if annotations is not None:
        if not isinstance(annotations, list):
            raise ValueError(f"Unsupported annotations value in {path}")
        for index, annotation in enumerate(annotations):
            if not isinstance(annotation, dict):
                raise ValueError(f"Unsupported annotation row {index} in {path}")
    if not _rename_legacy_identity_keys(payload):
        return False
    _backup_file(path)
    temp_path = path.with_name(f".{path.name}.0.9.8_migration.tmp")
    with temp_path.open("w", encoding="utf-8") as json_file:
        json.dump(payload, json_file, indent=2)
        json_file.write("\n")
    os.replace(temp_path, path)
    return True


def migrate_audit_jsonl_file(path: Path) -> bool:
    """CODEX: Upgrade one newline-delimited audit JSON backup when needed."""

    if not path.is_file():
        return False
    events: list[dict[str, Any]] = []
    changed = False
    with path.open("r", encoding="utf-8") as audit_file:
        for line_number, line in enumerate(audit_file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Unsupported audit JSONL row in {path} at line {line_number}"
                ) from exc
            if not isinstance(event, dict):
                raise ValueError(
                    f"Unsupported audit JSONL row in {path} at line {line_number}"
                )
            changed = _migrate_audit_event(event) or changed
            events.append(event)
    if not changed:
        return False
    _backup_file(path)
    temp_path = path.with_name(f".{path.name}.0.9.8_migration.tmp")
    with temp_path.open("w", encoding="utf-8") as audit_file:
        for event in events:
            json.dump(event, audit_file, sort_keys=True)
            audit_file.write("\n")
    os.replace(temp_path, path)
    return True


def migrate_sqlite_json_identities(connection: sqlite3.Connection) -> bool:
    """CODEX: Upgrade legacy identity keys stored inside SQLite JSON columns."""

    changed = False
    changed = _migrate_table_json(
        connection,
        "annotations",
        ("annotation_id",),
        ("metadata_json",),
    ) or changed
    changed = _migrate_table_json(
        connection,
        "audit_event_annotations",
        ("audit_event_id", "annotation_uuid"),
        ("before_state_json", "after_state_json"),
    ) or changed
    changed = _migrate_table_json(
        connection,
        "audit_events",
        ("audit_event_id",),
        ("details_json",),
        details_columns={"details_json"},
    ) or changed
    return changed


def _migrate_table_json(
    connection: sqlite3.Connection,
    table_name: str,
    key_columns: tuple[str, ...],
    json_columns: tuple[str, ...],
    *,
    details_columns: set[str] | None = None,
) -> bool:
    """CODEX: Upgrade selected JSON columns in one SQLite table."""

    columns = (*key_columns, *json_columns)
    rows = connection.execute(f"SELECT {', '.join(columns)} FROM {table_name}").fetchall()
    changed = False
    for row in rows:
        replacements = []
        row_changed = False
        for column in json_columns:
            replacement, column_changed = _migrate_json_text(
                row[column],
                f"{table_name}.{column}",
                nested_fields=(
                    _DETAIL_STATE_FIELDS if column in (details_columns or set()) else ()
                ),
            )
            replacements.append(replacement)
            row_changed = column_changed or row_changed
        if not row_changed:
            continue
        set_clause = ", ".join(f"{column} = ?" for column in json_columns)
        where_clause = " AND ".join(f"{column} = ?" for column in key_columns)
        connection.execute(
            f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}",
            (*replacements, *(row[column] for column in key_columns)),
        )
        changed = True
    return changed


def _migrate_audit_event(event: dict[str, Any]) -> bool:
    """CODEX: Upgrade decoded audit event state and detail payload fields."""

    changed = False
    for field_name in _AUDIT_STATE_FIELDS:
        changed = _migrate_encoded_field(event, field_name) or changed
    changed = (
        _migrate_encoded_field(event, "details_json", nested_fields=_DETAIL_STATE_FIELDS)
        or changed
    )
    changed = _rename_legacy_identity_keys(event) or changed
    return changed


def _migrate_encoded_field(
    mapping: dict[str, Any],
    field_name: str,
    *,
    nested_fields: tuple[str, ...] = (),
) -> bool:
    """CODEX: Decode, upgrade, and re-encode one optional JSON payload field."""

    value = mapping.get(field_name)
    if value in (None, ""):
        return False
    if isinstance(value, str):
        replacement, changed = _migrate_json_text(
            value,
            field_name,
            nested_fields=nested_fields,
        )
        if changed:
            mapping[field_name] = replacement
        return changed
    if nested_fields and not isinstance(value, dict):
        raise TypeError(f"Unsupported JSON object in {field_name}")
    if isinstance(value, (dict, list)):
        changed = False
        if isinstance(value, dict):
            for nested_field in nested_fields:
                changed = _migrate_encoded_field(value, nested_field) or changed
        changed = _rename_legacy_identity_keys(value) or changed
        return changed
    raise TypeError(f"Unsupported JSON value in {field_name}")


def _migrate_json_text(
    value: Any,
    context: str,
    *,
    nested_fields: tuple[str, ...] = (),
) -> tuple[str | None, bool]:
    """CODEX: Upgrade one optional JSON text value and return replacement text."""

    if value is None:
        return None, False
    if not isinstance(value, str):
        raise TypeError(f"Unsupported JSON value in {context}")
    if not value.strip():
        return value, False
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Unsupported JSON text in {context}") from exc
    if nested_fields and not isinstance(payload, dict):
        raise ValueError(f"Unsupported JSON object in {context}")
    changed = False
    if isinstance(payload, dict):
        for nested_field in nested_fields:
            changed = _migrate_encoded_field(payload, nested_field) or changed
    changed = _rename_legacy_identity_keys(payload) or changed
    if not changed:
        return value, False
    return json.dumps(payload, sort_keys=True, separators=(",", ":")), True


def _rename_legacy_identity_keys(value: Any) -> bool:
    """CODEX: Rename legacy identity keys throughout one decoded JSON value."""

    if isinstance(value, dict):
        changed = False
        if LEGACY_IDENTITY_KEY in value:
            legacy_value = value[LEGACY_IDENTITY_KEY]
            current_value = value.get(CURRENT_IDENTITY_KEY)
            if CURRENT_IDENTITY_KEY in value and current_value != legacy_value:
                raise ValueError("Conflicting annotation identity values")
            value[CURRENT_IDENTITY_KEY] = legacy_value
            del value[LEGACY_IDENTITY_KEY]
            changed = True
        for child in list(value.values()):
            changed = _rename_legacy_identity_keys(child) or changed
        return changed
    if isinstance(value, list):
        changed = False
        for child in value:
            changed = _rename_legacy_identity_keys(child) or changed
        return changed
    return False


def _backup_file(path: Path) -> None:
    """CODEX: Copy ``path`` to its versioned migration backup name."""

    backup_path = path.with_name(f"{path.name}{MIGRATION_BACKUP_SUFFIX}")
    if backup_path.exists():
        raise FileExistsError(f"Migration backup already exists: {backup_path}")
    shutil.copy2(path, backup_path)
