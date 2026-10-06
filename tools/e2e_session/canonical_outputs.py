"""CODEX: Project GUI session outputs into deterministic golden files."""

from __future__ import annotations

from collections.abc import Mapping
import configparser
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from annotator.project.paths import project_file_path
from annotator.project.paths import statistics_folder
from annotator.project_metadata import README_FILENAME
from annotator.sqlite.constants import DATABASE_FILENAME
from tools.e2e_session.canonical_artifacts import canonical_artifact_file


UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


@dataclass(frozen=True, slots=True)
class CanonicalBaseline:
    """CODEX: Store post-load output state excluded from workflow goldens."""

    annotations_by_uuid: dict[str, dict[str, Any]]
    max_audit_event_id: int
    max_log_id: int


class Canonicalizer:
    """CODEX: Normalize project paths, model paths, and UUIDs in replay output."""

    def __init__(
        self,
        project_folder: Path,
        model_assets: Mapping[str, Path] | None = None,
    ) -> None:
        """CODEX: Store path, model asset, and UUID state for one comparison."""

        self.project_folder = str(project_folder)
        self.resolved_project_folder = str(project_folder.resolve())
        self.model_asset_paths: dict[str, str] = {}
        for token, path in ({} if model_assets is None else model_assets).items():
            # CODEX: Model-asset Paths cross into canonical text matching by
            # CODEX: resolved path string; preflight owns content verification.
            resolved_path = str(path.expanduser().resolve())
            self.model_asset_paths[resolved_path] = token
        self.uuid_ordinals: dict[str, str] = {}

    def value(self, value: Any) -> Any:
        """CODEX: Return ``value`` with paths, UUIDs, and floats normalized."""

        if isinstance(value, dict):
            return {key: self.value(value[key]) for key in sorted(value)}
        if isinstance(value, list):
            return [self.value(item) for item in value]
        if isinstance(value, tuple):
            return [self.value(item) for item in value]
        if isinstance(value, float):
            return _rounded_number(value)
        if isinstance(value, str):
            text = value
            for resolved_path, token in sorted(
                self.model_asset_paths.items(),
                key=lambda item: len(item[0]),
                reverse=True,
            ):
                text = text.replace(resolved_path, token)
            text = text.replace(self.resolved_project_folder, "<fixture>")
            text = text.replace(self.project_folder, "<fixture>")
            return UUID_PATTERN.sub(self._uuid_placeholder, text)
        return value

    def _uuid_placeholder(self, match: re.Match[str]) -> str:
        """CODEX: Return the first-occurrence placeholder for one UUID."""

        uuid_text = match.group(0).lower()
        if uuid_text not in self.uuid_ordinals:
            self.uuid_ordinals[uuid_text] = f"<uuid:{len(self.uuid_ordinals) + 1}>"
        return self.uuid_ordinals[uuid_text]


def capture_canonical_baseline(app: Any) -> CanonicalBaseline:
    """CODEX: Capture output state immediately after the project loads."""

    connection = app.project.sql_connection
    if connection is None:
        raise AssertionError("cannot capture e2e baseline without SQLite")
    return CanonicalBaseline(
        annotations_by_uuid=_annotation_records(connection),
        max_audit_event_id=_max_row_id(connection, "audit_events", "audit_event_id"),
        max_log_id=_max_row_id(connection, "logs", "log_id"),
    )


def canonical_output_files(
    project_folder: Path,
    baseline: CanonicalBaseline,
    menu_snapshots: dict[str, list[dict[str, Any]]],
    model_assets: Mapping[str, Path] | None = None,
) -> dict[str, str]:
    """CODEX: Return canonical replay output with local asset paths tokenized."""

    connection = _connect_readonly(project_folder)
    try:
        canonicalizer = Canonicalizer(project_folder, model_assets)
        output = {
            "annotation_changes": _annotation_changes(
                connection,
                baseline,
                canonicalizer,
            ),
            "audit_events": _audit_events(connection, baseline, canonicalizer),
            "logs": _logs(connection, baseline, canonicalizer),
            "menu_snapshots": canonicalizer.value(menu_snapshots),
            "readme": _readme(project_folder, canonicalizer),
            "statistics": _statistics(project_folder, canonicalizer),
        }
        artifact_text = canonical_artifact_file(
            project_folder,
            connection,
            canonicalizer.value,
        )
    finally:
        connection.close()
    text = json.dumps(output, indent=2, sort_keys=True)
    return {
        "artifacts.json": artifact_text,
        "outputs.json": f"{text}\n",
    }


def write_canonical_output_files(
    output_dir: Path,
    output_files: dict[str, str],
) -> None:
    """CODEX: Write canonical recording output into a new golden directory.

    ``output_files`` comes from the canonical projection owned by this module,
    so its relative names are trusted. Missing parents are created, while an
    existing golden directory raises ``FileExistsError``. The caller owns
    reviewing the resulting golden before committing it.
    """

    output_dir.mkdir(parents=True)
    for relative_name, content in output_files.items():
        output_path = output_dir / relative_name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")


def _connect_readonly(project_folder: Path) -> sqlite3.Connection:
    """CODEX: Open the replayed database without mutating output artifacts."""

    database_path = project_file_path(project_folder, DATABASE_FILENAME)
    connection = sqlite3.connect(
        f"{database_path.resolve().as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    return connection


def _annotation_changes(
    connection: sqlite3.Connection,
    baseline: CanonicalBaseline,
    canonicalizer: Canonicalizer,
) -> dict[str, list[Any]]:
    """CODEX: Return annotation changes in stable project annotation order."""

    final_records = _annotation_records(connection)
    baseline_records = baseline.annotations_by_uuid
    # CODEX: UUID text is random; retain the SQL-backed semantic order so UUID
    # CODEX: placeholders and list positions remain stable between equivalent runs.
    added = [
        canonicalizer.value(record)
        for uuid, record in final_records.items()
        if uuid not in baseline_records
    ]
    removed = [
        canonicalizer.value(record)
        for uuid, record in baseline_records.items()
        if uuid not in final_records
    ]
    modified = []
    for uuid, record in final_records.items():
        if uuid in baseline_records and record != baseline_records[uuid]:
            modified.append(
                {
                    "after": canonicalizer.value(record),
                    "before": canonicalizer.value(baseline_records[uuid]),
                }
            )
    return {"added": added, "modified": modified, "removed": removed}


def _annotation_records(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """CODEX: Read current region annotations from authoritative SQLite rows."""

    rows = connection.execute(
        """
        SELECT ann.annotation_uuid, ann.annotation_type, ann.annotation_source,
               ann.annotation_order, ann.geometry_json, img.image_name,
               classes.class_name
        FROM annotations AS ann
        JOIN project_images AS img ON img.image_id = ann.image_id
        LEFT JOIN annotation_classes AS classes ON classes.class_id = ann.class_id
        WHERE ann.annotation_role = ''
          AND ann.annotation_type IN ('polygon', 'rectangle')
        ORDER BY img.image_sequence_index, img.image_name,
                 ann.annotation_order, ann.annotation_id
        """
    ).fetchall()
    records = {}
    for row in rows:
        geometry = json.loads(row["geometry_json"])
        records[row["annotation_uuid"]] = {
            "uuid": row["annotation_uuid"],
            "image": row["image_name"],
            "class": row["class_name"],
            "type": row["annotation_type"],
            "source": row["annotation_source"],
            "order": row["annotation_order"],
            "polygons": _canonical_polygons(geometry["polygons"]),
        }
    return records


def _audit_events(
    connection: sqlite3.Connection,
    baseline: CanonicalBaseline,
    canonicalizer: Canonicalizer,
) -> list[dict[str, Any]]:
    """CODEX: Return new audit rows with deterministic event references."""

    rows = connection.execute(
        """
        SELECT ae.audit_event_id, ae.audit_event_uuid, ae.session_id,
               ae.event_completed_time_ms, ae.duration_ms,
               ae.undo_of_audit_event_id, ae.event_summary, ae.details_json,
               actions.action_key AS action
        FROM audit_events AS ae
        JOIN audit_event_actions AS actions
          ON actions.audit_event_action_id = ae.audit_event_action_id
        WHERE ae.audit_event_id > ?
        ORDER BY ae.audit_event_id
        """,
        (baseline.max_audit_event_id,),
    ).fetchall()
    event_ids = [row["audit_event_id"] for row in rows]
    event_names = {
        event_id: f"event:{index + 1}"
        for index, event_id in enumerate(event_ids)
    }
    events = []
    for row in rows:
        details = _event_details(row["details_json"])
        source_uuid = details.pop("_source_uuid", None)
        details.pop("_before_state_json", None)
        details.pop("_after_state_json", None)
        events.append(
            {
                "id": event_names[row["audit_event_id"]],
                "uuid": canonicalizer.value(row["audit_event_uuid"]),
                "session_id": canonicalizer.value(row["session_id"]),
                "source_uuid": canonicalizer.value(source_uuid),
                "completed_time_ms": 0,
                "duration_ms": 0 if row["duration_ms"] is not None else None,
                "action": row["action"],
                "summary": row["event_summary"],
                "undo_of": _event_reference(
                    row["undo_of_audit_event_id"],
                    event_names,
                ),
                "details": canonicalizer.value(details),
                "annotation_links": canonicalizer.value(
                    _audit_annotation_links(connection, row["audit_event_id"])
                ),
            }
        )
    return events


def _logs(
    connection: sqlite3.Connection,
    baseline: CanonicalBaseline,
    canonicalizer: Canonicalizer,
) -> list[dict[str, Any]]:
    """CODEX: Return UI log rows written after the post-load baseline."""

    rows = connection.execute(
        """
        SELECT log_id, session_id, log_timestamp, log_entry
        FROM logs
        WHERE log_id > ?
        ORDER BY log_id
        """,
        (baseline.max_log_id,),
    ).fetchall()
    return [
        {
            "id": f"log:{index + 1}",
            "session_id": canonicalizer.value(row["session_id"]),
            "timestamp": 0,
            "entry": canonicalizer.value(row["log_entry"]),
        }
        for index, row in enumerate(rows)
    ]


def _readme(project_folder: Path, canonicalizer: Canonicalizer) -> dict[str, Any]:
    """CODEX: Return canonical README sections written by explicit Save."""

    path = project_file_path(project_folder, README_FILENAME)
    if not path.is_file():
        return {}
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(path, encoding="utf-8")
    sections = {
        section: dict(parser.items(section, raw=True))
        for section in parser.sections()
    }
    provenance = sections.get("provenance")
    if provenance and "last_save_date_time" in provenance:
        provenance["last_save_date_time"] = "0000-00-00T00:00:00"
    return canonicalizer.value(sections)


def _statistics(
    project_folder: Path,
    canonicalizer: Canonicalizer,
) -> list[dict[str, Any]]:
    """CODEX: Return session-statistics CSV content in canonical UUID order.

    Statistics filenames are session UUIDs, so their raw lexical order changes
    between equivalent runs. Ordering after canonicalization keeps the output
    independent of those random filenames.
    """

    folder = statistics_folder(project_folder)
    if not folder.is_dir():
        return []
    files = []
    for path in sorted(folder.glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as statistics_file:
            rows = []
            for row in csv.DictReader(statistics_file):
                canonical_row = dict(row)
                if "average_duration_ms" in canonical_row:
                    canonical_row["average_duration_ms"] = "0.000"
                if "stdev_duration_ms" in canonical_row:
                    canonical_row["stdev_duration_ms"] = "0.000"
                rows.append(canonicalizer.value(canonical_row))
        files.append({"file": canonicalizer.value(path.name), "rows": rows})
    # CODEX: Raw UUID filenames are random; only placeholders have stable order.
    files.sort(key=lambda item: item["file"])
    return files


def _audit_annotation_links(
    connection: sqlite3.Connection,
    audit_event_id: int,
) -> list[dict[str, Any]]:
    """CODEX: Return annotation association rows for one audit event."""

    rows = connection.execute(
        """
        SELECT annotation_uuid, change_type, before_state_json, after_state_json
        FROM audit_event_annotations
        WHERE audit_event_id = ?
        ORDER BY annotation_uuid
        """,
        (audit_event_id,),
    ).fetchall()
    return [
        {
            "uuid": row["annotation_uuid"],
            "change": row["change_type"],
            "before": _json_or_none(row["before_state_json"]),
            "after": _json_or_none(row["after_state_json"]),
        }
        for row in rows
    ]


def _event_details(value: str) -> dict[str, Any]:
    """CODEX: Decode details and nested legacy state snapshots for goldens."""

    details = json.loads(value)
    for key in ("_before_state_json", "_after_state_json"):
        if isinstance(details.get(key), str):
            details[key] = json.loads(details[key])
    return details


def _event_reference(
    audit_event_id: int | None,
    event_names: dict[int, str],
) -> str | None:
    """CODEX: Return a stable reference for an undo target event."""

    if audit_event_id is None:
        return None
    return event_names.get(audit_event_id, f"baseline:{audit_event_id}")


def _json_or_none(value: str | None) -> Any:
    """CODEX: Decode optional JSON snapshots from SQLite output rows."""

    if value is None:
        return None
    return json.loads(value)


def _canonical_polygons(polygons: list[Any]) -> list[list[list[float | int]]]:
    """CODEX: Return polygons with stable numeric precision."""

    canonical_polygons = []
    for polygon in polygons:
        canonical_polygon = []
        for point in polygon:
            # CODEX: Geometry JSON is a file/database boundary, so point
            # CODEX: coordinates are normalized while projecting to goldens.
            x_coord = _rounded_number(float(point[0]))
            y_coord = _rounded_number(float(point[1]))
            canonical_polygon.append([x_coord, y_coord])
        canonical_polygons.append(canonical_polygon)
    return canonical_polygons


def _rounded_number(value: float) -> float | int:
    """CODEX: Keep geometry readable without losing subpixel replay evidence."""

    rounded = round(value, 3)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def _max_row_id(connection: sqlite3.Connection, table: str, column: str) -> int:
    """CODEX: Return the current maximum integer key for a known table."""

    row = connection.execute(f"SELECT MAX({column}) AS max_id FROM {table}").fetchone()
    return row["max_id"] or 0
