"""CODEX: Write derived per-session edit timing CSVs.

The authoritative source is the SQLite ``audit_events`` table for one
``sessions.session_id``. This module reduces those rows into
benchmark-oriented operation summaries under ``teacup/statistics/``; it does
not record audit events, decide which GUI actions are timed, or own
turtle-shell inference rules.

Rows include operation counts, mean duration, population standard deviation,
and the turtle-shell-only average final polygon count.
"""

from __future__ import annotations

import csv
from pathlib import Path
import sqlite3
import statistics
import time
from typing import Any

from annotator.log.audit import SUMMARY_EDIT_COUNT_ACTIONS
from annotator.log.audit import audit_json_field
from annotator.log.turtle_shell_statistics import TURTLE_SHELL_OPERATION
from annotator.log.turtle_shell_statistics import completed_turtle_shells
from annotator.project.paths import statistics_folder

# CODEX: Keep this header stable: downstream spreadsheet imports read columns by name.
SESSION_STATISTICS_HEADER = (
    "session_id",
    "operation",
    "operation_count",
    "average_duration_ms",
    "stdev_duration_ms",
    "average_final_polygon_count",
)


def write_session_statistics_csv(
    folder: Path,
    connection: sqlite3.Connection,
    session_id: str,
    current_time_ms: int | None = None,
) -> Path:
    """CODEX: Write the current CSV summary for one application session.

    Only audit rows for ``session_id`` are considered. Timed actions from
    ``SUMMARY_EDIT_COUNT_ACTIONS`` are grouped by operation name; untimed rows
    and view/close events are ignored. ``create_annotation`` is split into
    ``create_<annotation_type>`` using ``details_json`` so polygon and rectangle
    creation remain separate benchmark rows.

    Completed turtle shells are inferred from the ordered audit history and
    emitted as the synthetic ``complete_turtle_shell`` operation.
    ``current_time_ms`` exists so callers and tests can make active-shell
    boundary calculations deterministic. The CSV is written to a temporary file
    and then replaces the session CSV.
    """

    # CODEX: SQL ordering gives turtle-shell inference the same chronology the
    # CODEX: audit UI sees.
    rows = connection.execute(
        """
        SELECT ae.audit_event_id,
               ae.event_completed_time_ms,
               ae.duration_ms,
               actions.action_key AS action,
               ae.details_json
        FROM audit_events AS ae
        JOIN audit_event_actions AS actions
          ON actions.audit_event_action_id = ae.audit_event_action_id
        WHERE ae.session_id = ?
        ORDER BY ae.event_completed_time_ms, ae.audit_event_id
        """,
        (session_id,),
    ).fetchall()
    events = _events_with_annotation_snapshots(connection, [dict(row) for row in rows])

    durations_by_action: dict[str, list[int]] = {}
    for event in events:
        action = str(event["action"])
        # CODEX: Only committed edit actions with measured durations become timing rows.
        if action in SUMMARY_EDIT_COUNT_ACTIONS and event["duration_ms"] is not None:
            operation = action
            if action == "create_annotation":
                # CODEX: Creation timing is split by requested annotation family.
                details = audit_json_field(event, "details_json")
                annotation_type = (
                    details.get("annotation_type", "unknown")
                    if isinstance(details, dict)
                    else "unknown"
                )
                operation = f"create_{annotation_type}"
            durations_by_action.setdefault(operation, []).append(
                int(event["duration_ms"])
            )
    # CODEX: Turtle shells are derived operations, not direct audit actions.
    turtle_shells = completed_turtle_shells(
        events,
        current_time_ms=(
            current_time_ms
            if current_time_ms is not None
            else time.time_ns() // 1_000_000
        ),
    )
    if turtle_shells:
        durations_by_action[TURTLE_SHELL_OPERATION] = [
            shell.duration_ms for shell in turtle_shells
        ]

    output_folder = statistics_folder(folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    path = output_folder / f"{session_id}.csv"
    temp_path = output_folder / f".{session_id}.csv.tmp"
    # CODEX: Replace from the same folder so readers do not observe a partial CSV.
    with temp_path.open("w", newline="", encoding="utf-8") as statistics_file:
        writer = csv.writer(statistics_file)
        writer.writerow(SESSION_STATISTICS_HEADER)
        for action in sorted(durations_by_action):
            durations = durations_by_action[action]
            average_final_polygon_count = ""
            if action == TURTLE_SHELL_OPERATION:
                # CODEX: Only turtle-shell rows have a meaningful final polygon-count metric.
                average_final_count = statistics.fmean(
                    shell.final_polygon_count for shell in turtle_shells
                )
                average_final_polygon_count = f"{average_final_count:.3f}"
            writer.writerow(
                (
                    session_id,
                    action,
                    len(durations),
                    f"{statistics.fmean(durations):.3f}",
                    f"{statistics.pstdev(durations):.3f}",
                    average_final_polygon_count,
                )
            )
    temp_path.replace(path)
    return path


def _events_with_annotation_snapshots(
    connection: sqlite3.Connection,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """CODEX: Add legacy-shaped snapshot fields from association rows."""

    if not events:
        return []
    event_by_id = {int(event["audit_event_id"]): event for event in events}
    placeholders = ",".join("?" for _ in event_by_id)
    rows = connection.execute(
        f"""
        SELECT audit_event_id, annotation_uuid, change_type,
               before_state_json, after_state_json
        FROM audit_event_annotations
        WHERE audit_event_id IN ({placeholders})
        ORDER BY audit_event_id, annotation_uuid
        """,
        tuple(event_by_id),
    ).fetchall()
    for event in events:
        details = audit_json_field(event, "details_json")
        event["event_time"] = int(event["event_completed_time_ms"])
        event["source_uuid"] = (
            details.get("_source_uuid") if isinstance(details, dict) else None
        )
        event["before_state_json"] = (
            details.get("_before_state_json")
            if isinstance(details, dict)
            and details.get("_before_state_json") is not None
            else {"annotations": []}
        )
        event["after_state_json"] = (
            details.get("_after_state_json")
            if isinstance(details, dict)
            and details.get("_after_state_json") is not None
            else {"annotations": []}
        )
    for row in rows:
        event = event_by_id[int(row["audit_event_id"])]
        if event["source_uuid"] is None:
            event["source_uuid"] = str(row["annotation_uuid"])
        if row["before_state_json"] is not None:
            _append_annotation_snapshot(
                event,
                "before_state_json",
                audit_json_field(dict(row), "before_state_json"),
            )
        if row["after_state_json"] is not None:
            _append_annotation_snapshot(
                event,
                "after_state_json",
                audit_json_field(dict(row), "after_state_json"),
            )
    return events


def _append_annotation_snapshot(
    event: dict[str, Any],
    field_name: str,
    snapshot: Any,
) -> None:
    """CODEX: Append an association snapshot to an event-shaped state field."""

    state = event.get(field_name)
    if not isinstance(state, dict):
        state = {"annotations": []}
        event[field_name] = state
    state.setdefault("annotations", []).append(snapshot)
