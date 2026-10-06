"""CODEX: Record and retrieve authoritative SQLite audit events and UI log entries.

This module owns event insertion, action-vocabulary lookup, generic annotation
change associations, ordered event reads, empty-history JSONL recovery, and
durable free-form log rows. Audit events link to stored application sessions;
annotation associations retain UUID-based before/after snapshots independently
of whether live annotation rows still exist.

GUI audit orchestration owns event construction, change derivation, measured
durations, transaction grouping, and optional JSONL backup publication. The
legacy ``annotator.log.audit`` module owns backup file I/O. This module does not
interpret action-specific details or write ``audit_event_classes`` rows.
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any, cast

from annotator.log.annotation_changes import AuditChange
from annotator.sqlite.connect import _ensure_session
from annotator.sqlite.json import _json_dumps
from annotator.sqlite.json import _json_loads
from annotator.sqlite.schema import ensure_audit_event_action
from annotator.sqlite.schema import ensure_schema
from annotator.sqlite.time import _unix_time
from annotator.sqlite.time import _unix_time_ms


def append_audit_event(
    connection: sqlite3.Connection,
    event: dict[str, Any],
    affected_annotations: list[AuditChange] | None = None,
    affected_arrows: list[AuditChange] | None = None,
    commit: bool = True,
) -> int:
    """CODEX: Insert one audit event and its annotation associations.

    ``event`` is a JSON-friendly mapping. A supplied ``audit_event_id`` is
    passed to SQLite as the requested primary key; when it is omitted, SQLite
    allocates the ID. SQLite owns integer and uniqueness enforcement, and
    invalid requested IDs fail rather than being silently replaced. Missing
    session, action, completion time, UUID, summary, and details values receive
    the established application defaults. ``affected_annotations`` and
    ``affected_arrows`` use the same generic ``AuditChange`` tuple shape and
    are inserted into ``audit_event_annotations`` after the parent event.

    The function adds the selected ``session_id`` to the caller's event and,
    after the SQL rows succeed, adds the complete nested ``session`` record.
    These fields are then available to the optional JSONL backup writer. The
    complete record is required for recovery into a fresh database: a session
    UUID alone cannot recreate the required ``sessions`` row, so SQLite would
    reject the restored audit event because its session foreign key has no
    target.

    The returned integer is the stored audit ID; callers add it to the event
    when needed. With ``commit=True`` the completed write is committed. With
    ``commit=False`` the caller owns the surrounding transaction. SQLite and
    snapshot-constraint failures propagate unchanged.
    """

    ensure_schema(connection)
    now = _unix_time_ms()
    session_id = event.get("session_id") or _ensure_session(connection)
    event["session_id"] = session_id
    audit_event_id = event.get("audit_event_id")
    action_key = str(event.get("action") or "unknown")
    action_id = ensure_audit_event_action(connection, action_key)
    details_json = _details_json_for_event(event)
    cursor = connection.execute(
        """
        INSERT INTO audit_events(
            audit_event_id, audit_event_uuid, session_id,
            event_completed_time_ms, duration_ms, undo_of_audit_event_id,
            audit_event_action_id, event_summary, details_json
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            audit_event_id,
            event.get("audit_event_uuid") or f"audit:{uuid.uuid4()}",
            session_id,
            event.get("event_completed_time_ms") or event.get("event_time") or now,
            event.get("duration_ms"),
            event.get("undo_of_audit_event_id"),
            action_id,
            event.get("event_summary") or action_key,
            details_json,
        ),
    )
    stored_audit_event_id = cast(int, cursor.lastrowid)
    _insert_annotation_links(
        connection,
        stored_audit_event_id,
        [*(affected_annotations or []), *(affected_arrows or [])],
    )
    # CODEX: Make each optional JSONL row carry the session record needed to
    # CODEX: reconstruct its audit-event foreign key in a fresh database.
    session_row = connection.execute(
        """
        SELECT session_id, app_version, started_time, session_timezone,
               hostname, host_type, os
        FROM sessions
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    event["session"] = dict(session_row)
    if commit:
        connection.commit()
    return stored_audit_event_id


def next_audit_event_id(connection: sqlite3.Connection) -> int:
    """CODEX: Return one greater than the largest stored audit event ID.

    Return 1 when no audit events exist. For example, stored IDs 1 and 3 produce
    4; the function does not search for the unused ID 2. Folder loading uses the
    result to determine whether JSONL recovery is permitted and to initialize
    the GUI's last-event state used by undo. The result does not reserve an ID;
    normal event insertion lets SQLite allocate it.
    """

    ensure_schema(connection)
    row = connection.execute(
        "SELECT MAX(audit_event_id) AS max_id FROM audit_events"
    ).fetchone()
    return int(row["max_id"] or 0) + 1


def read_audit_events(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """CODEX: Project audit event rows into mappings ordered by event ID.

    Each mapping retains the stored event columns and resolved action key,
    aliases ``event_completed_time_ms`` as ``event_time``, and exposes legacy
    ``source_uuid``, ``before_state_json``, and ``after_state_json`` values from
    reserved keys in ``details_json``. ``source_table`` is returned as ``None``
    because native event rows do not store that legacy field.

    This reader does not join session metadata or annotation/class association
    tables, replace the serialized details payload with its decoded value, or
    commit the connection.
    """

    ensure_schema(connection)
    rows = connection.execute(
        """
        SELECT ae.audit_event_id,
               ae.audit_event_uuid,
               ae.session_id,
               ae.event_completed_time_ms,
               ae.duration_ms,
               ae.undo_of_audit_event_id,
               ae.event_summary,
               ae.details_json,
               actions.action_key AS action
        FROM audit_events AS ae
        JOIN audit_event_actions AS actions
          ON actions.audit_event_action_id = ae.audit_event_action_id
        ORDER BY ae.audit_event_id
        """
    ).fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        event = dict(row)
        details = _json_loads(event["details_json"], {})
        event["event_time"] = int(row["event_completed_time_ms"])
        event["source_uuid"] = (
            details.get("_source_uuid") if isinstance(details, dict) else None
        )
        event["source_table"] = None
        event["before_state_json"] = (
            details.get("_before_state_json") if isinstance(details, dict) else None
        )
        event["after_state_json"] = (
            details.get("_after_state_json") if isinstance(details, dict) else None
        )
        events.append(event)
    return events


def import_audit_events_if_empty(
    connection: sqlite3.Connection,
    events: list[dict[str, Any]],
) -> None:
    """CODEX: Import JSONL event mappings only when SQL history is empty.

    A nonempty ``audit_events`` table makes the operation a no-op. Current
    backup rows with a nested ``session`` record restore that foreign-key target
    before preserving the event's session UUID. When the UUID already exists,
    the stored session row remains authoritative. Older rows containing only
    ``session_id`` discard that orphan UUID and use the importing application
    session.

    Each input mapping is copied before the normal audit-field mapping is
    applied. Requested event IDs and legacy state fields are retained where the
    native event schema supports them. JSONL does not contain ``AuditChange``
    collections, so the import does not reconstruct annotation or class
    association rows.

    The connection context commits the whole batch or rolls back all imported
    events and sessions when any row fails. Schema, foreign-key, and payload
    errors propagate unchanged.
    """

    if next_audit_event_id(connection) != 1:
        return
    with connection:
        for event in events:
            imported_event = dict(event)
            session = imported_event.get("session")
            # CODEX: New backups own exact session restoration; UUID-only
            # CODEX: backups cannot satisfy the native session contract.
            if session is None:
                imported_event.pop("session_id", None)
            else:
                connection.execute(
                    """
                    INSERT INTO sessions(
                        session_id, app_version, started_time, session_timezone,
                        hostname, host_type, os
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO NOTHING
                    """,
                    (
                        session["session_id"],
                        session["app_version"],
                        session["started_time"],
                        session["session_timezone"],
                        session["hostname"],
                        session["host_type"],
                        session["os"],
                    ),
                )
                imported_event["session_id"] = session["session_id"]
            append_audit_event(connection, imported_event, commit=False)


def append_log_entry(connection: sqlite3.Connection, message: str) -> None:
    """CODEX: Append and commit one free-form UI log message.

    Ensure the current schema and application session, store the message with
    the current UTC Unix-seconds timestamp, and commit immediately. This writes
    the ``logs`` table rather than structured audit-event or association tables.
    SQLite errors propagate unchanged.
    """

    ensure_schema(connection)
    now = _unix_time()
    session_id = _ensure_session(connection)
    connection.execute(
        """
        INSERT INTO logs(session_id, log_timestamp, log_entry)
        VALUES(?, ?, ?)
        """,
        (session_id, now, message),
    )
    connection.commit()


def _insert_annotation_links(
    connection: sqlite3.Connection,
    audit_event_id: int,
    changes: list[AuditChange],
) -> None:
    """CODEX: Insert UUID-based annotation links for one audit event.

    ``changes`` contains ``AuditChange`` tuples derived from region or arrow
    state. Both families use the generic ``audit_event_annotations`` table. Its
    UUID is deliberately independent of the live annotation table so deleted
    annotations remain traceable.

    Absent snapshots become SQL ``NULL`` and dictionary snapshots become JSON.
    The schema owns change-type and snapshot-shape enforcement. An empty list is
    a no-op; the caller owns parent-event creation, transaction scope, and
    commit.
    """

    connection.executemany(
        """
        INSERT INTO audit_event_annotations(
            audit_event_id, annotation_uuid, change_type,
            before_state_json, after_state_json
        )
        VALUES(?, ?, ?, ?, ?)
        """,
        [
            (
                audit_event_id,
                annotation_uuid,
                change_type,
                _json_or_none(before_state),
                _json_or_none(after_state),
            )
            for annotation_uuid, change_type, before_state, after_state in changes
        ],
    )


def _json_or_none(value: dict[str, Any] | None) -> str | None:
    """CODEX: Prepare an optional audit snapshot for SQLite storage.

    Return ``None`` for a missing snapshot so SQLite stores ``NULL``. Otherwise,
    convert the snapshot dictionary to JSON text. Created and deleted
    association rules determine which side of a change may be missing.
    """

    if value is None:
        return None
    return _json_dumps(value)


def _details_json_for_event(event: dict[str, Any]) -> str:
    """CODEX: Encode native details plus reserved legacy state fields.

    Decode ``details_json`` as an object, using an empty object for missing,
    malformed, or non-object input. Supplied before-state, after-state, and
    source UUID values are added under reserved keys only when the details
    object does not already define them, so explicit detail values win. The
    event mapping is not changed.
    """

    details = _json_loads(event.get("details_json"), {})
    if not isinstance(details, dict):
        details = {}
    if event.get("before_state_json") is not None:
        details.setdefault("_before_state_json", event["before_state_json"])
    if event.get("after_state_json") is not None:
        details.setdefault("_after_state_json", event["after_state_json"])
    if event.get("source_uuid") is not None:
        details.setdefault("_source_uuid", event["source_uuid"])
    return _json_dumps(details)
