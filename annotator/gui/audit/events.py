"""CODEX: Write and finalize authoritative SQLite audit events."""

from __future__ import annotations

from typing import Any
from typing import Protocol
from typing import cast
import json
import sqlite3
import time

import annotator.sqlite as sql_backend
from annotator.gui.audit.state import current_audit_state
from annotator.gui.state import ProjectState
from annotator.log.annotation_changes import affected_annotation_changes
from annotator.log.annotation_changes import affected_arrow_changes
from annotator.log.audit import SUMMARY_EDIT_COUNT_ACTIONS
from annotator.log.audit import VIEW_AUDIT_ACTION
from annotator.log.audit import append_audit_event
from annotator.preferences import Preferences


class AuditEventHost(Protocol):
    """CODEX: Project, preferences, and logging required for audit writes."""

    project: ProjectState
    prefs: Preferences

    def log(self, message: str) -> None:
        """CODEX: Record one audit message."""

        ...

# CMP: TODO - Check that no unaudited event is sitting in the transaction
# (i.e., that we didn't leave an event accidentally unqueued).
#      TODO 2 - Check that this is indeed an atomic write; what happens
#      (and how do we know) that the connection was not established with
#      autocommit=True?
#   QUESTION - What happens if the process crashes before this function loses
#   the pending audit records? Do the underlying changes being audited also
#   roll back?
def flush_pending_audit_events(host: AuditEventHost) -> None:
    """CODEX: Commit staged state and pending audit events atomically."""

    # CMP: TODO - consider flushing to backup .JSON if the SQL connection
    #      fails, so we don't lose the audit events?
    if host.project.sql_connection is None:
        if host.project.pending_audit_events:
            raise sqlite3.ProgrammingError("No SQLite database is open")
        return
    written_events: list[dict[str, Any]] = []
    committed_undo_links: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if host.project.pending_audit_events:
        for index, event in enumerate(host.project.pending_audit_events):
            next_event = (
                host.project.pending_audit_events[index + 1]
                if index + 1 < len(host.project.pending_audit_events)
                else None
            )

            # CMP: TODO - What happens if one event is "all_images" and another
            # event is not? (e.g., current_image)?
            # CMP: TODO - we should probably ensure these are actual booleans rather
            # than casting them as booleans, which could introduce errors (e.g.,
            # 'false' -> True.
            same_scope = next_event is not None and bool(
                next_event.get("all_images")
            ) == bool(event.get("all_images"))
            same_image = next_event is not None and (
                bool(event.get("all_images"))
                or next_event.get("image_name") == event.get("image_name")
            )
            if same_scope and same_image:
                after_state = next_event["before_state"]
            else:
                after_state = current_audit_state(
                    host,
                    bool(event.get("all_images")),
                    event.get("image_name"),
                )
            written_event = write_audit_event(
                host,
                action=event["action"],
                before_state=event["before_state"],
                after_state=after_state,
                details=event["details"],
                source_uuid=event["source_uuid"],
                undo_of_audit_event_id=event.get("undo_of_audit_event_id"),
                source_table=event.get("source_table", "annotations"),
                duration_ms=duration_ms_for_event(event),
                commit=False,
            )

            # CMP: TODO - So what if it IS None? It looks like
            # we still commit, even in that case. What does none really
            # mean as a return from write_audit_event?
            if written_event is not None:
                written_events.append(written_event)
                if "undo_snapshot" in event:
                    committed_undo_links.append(
                        (event["undo_snapshot"], written_event)
                    )

    # CMP: QUESTION - what happens if a commit fails?
    host.project.sql_connection.commit()
    # CODEX: Publish the source event identity only after SQLite makes the
    # CODEX: edit and its audit row durable in the same transaction.
    for undo_snapshot, written_event in committed_undo_links:
        undo_snapshot["audit_event_id"] = written_event["audit_event_id"]
    host.project.pending_audit_events.clear()
    # CMP: QUESTION - what happens if this next line fails? We've already committed.
    finalize_committed_audit_events(host, written_events)

# CMP: TODO - Security issue: why is commit defaulting to True? In that
# case no error is raised and the app is allowed to continue operating
# with a simple inocuous log message that audit failed (which may not
# even be seen by the user) More importantly, why are there two different
# policies based on the value of commit?
#    - TODO - justify why having a default source_table here makes sense.
#      what if the caller forgets to specify the correct table?

def write_audit_event(
    host: AuditEventHost,
    action: str,
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
    details: dict[str, Any] | None = None,
    source_uuid: str | None = None,
    undo_of_audit_event_id: int | None = None,
    source_table: str = "annotations",
    duration_ms: int | None = None,
    commit: bool = True,
) -> dict[str, Any] | None:
    """CODEX: Append one SQLite audit event and optional JSONL backup."""

    if host.project.sql_connection is None:
        if not commit:
            raise sqlite3.ProgrammingError("No SQLite database is open")
        host.log("Audit log failed: no SQLite connection is active")
        return None

    # CMP: TODO - why are we recording event time here, instead of
    # when it was generated? Can there be potentially significant
    # time differences between the event and flush time?
    # CMP: TODO - we are recording things that are no longer in the
    #      database schema (e.g., pdf_id, page_id).
    # CMP: Shouldn't these values be validated against a known value list?
    #      e.g., action should be one of several known actions, and nothing
    #      else (e.g., a typo).
    event = {
        "audit_event_id": None,
        "session_id": None,
        "pdf_id": None,
        "page_id": None,
        "stage_name": "stage_4",
        "event_time": time.time_ns() // 1_000_000,
        "duration_ms": duration_ms,
        "action": action,
        "source_table": source_table,
        "source_row_id": None,
        "source_uuid": source_uuid,
        "before_state_json": json.dumps(before_state, sort_keys=True),
        "after_state_json": json.dumps(after_state, sort_keys=True),
        "details_json": json.dumps(details or {}, sort_keys=True),
        "undo_of_audit_event_id": undo_of_audit_event_id,
    }
    annotation_changes = affected_annotation_changes(before_state, after_state)
    arrow_changes = affected_arrow_changes(before_state, after_state)
    try:
        audit_event_id = sql_backend.append_audit_event(
            host.project.sql_connection,
            event,
            affected_annotations=annotation_changes,
            affected_arrows=arrow_changes,
            commit=commit,
        )
    except sqlite3.Error as exc:
        if not commit:
            raise

        # CMP: TODO - Fix - the application should not be able to silently
        # continue if the audit failed. How did we get here?

        # CMP: QUESTION - Why is there no rollback here?
        host.log(f"SQL audit log failed: {exc}")
        return None
    event["audit_event_id"] = audit_event_id
    if commit:
        finalize_committed_audit_events(host, [event])
    return event


def duration_ms_for_event(event: dict[str, Any]) -> int | None:
    """CODEX: Return elapsed edit time for an event with a monotonic start."""

    started = event.get("started_monotonic_ns")
    if started is None:
        return None
    return max(0, (time.monotonic_ns() - int(started)) // 1_000_000)


def finalize_committed_audit_events(
    host: AuditEventHost,
    events: list[dict[str, Any]],
) -> None:
    """CODEX: Publish backup and GUI bookkeeping for committed SQL events."""

    if not events:
        return
    from annotator.gui.persistence import write_json_backups_enabled

    if write_json_backups_enabled(host) and host.project.folder is not None:
        for event in events:
            try:
                append_audit_event(host.project.folder, event)
            except OSError as exc:
                host.log(f"Audit JSON backup failed: {exc}")
    host.project.last_audit_event_id = int(events[-1]["audit_event_id"])
    host.project.next_audit_event_id = host.project.last_audit_event_id + 1
    if any(
        event["action"] == VIEW_AUDIT_ACTION
        or event["action"] in SUMMARY_EDIT_COUNT_ACTIONS
        for event in events
    ):
        from annotator.gui.project.status import StatusHost
        from annotator.gui.project.status import update_edit_summary

        update_edit_summary(cast(StatusHost, host))
