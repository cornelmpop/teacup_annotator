"""Infer completed turtle-shell benchmark intervals from audit history.

Session statistics include a synthetic ``complete_turtle_shell`` operation even
though no direct audit action records that operation. This module reconstructs
those intervals from ordered audit rows: autoclose polygon creations start or
extend a shell, connected polygons remain in the same shell, and image changes,
application close, idle gaps, or disconnected creations complete the active
shell.

The inference is read-only. It does not write statistics CSVs, mutate audit
rows, decide whether an edit should be timed, or own the GUI Turtle shell mode
behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry import Polygon

from annotator.log.audit import CLOSE_AUDIT_ACTION
from annotator.log.audit import VIEW_AUDIT_ACTION
from annotator.log.audit import audit_event_image_name
from annotator.log.audit import audit_json_field

# Ten seconds without audit activity ends a shell at the last observed edit.
IDLE_TIMEOUT_MS = 10_000
# Session statistics emits this synthetic operation for inferred shell intervals.
TURTLE_SHELL_OPERATION = "complete_turtle_shell"

Point = tuple[float, float]


@dataclass(slots=True)
class ActiveTurtleShell:
    """Mutable state for one shell being inferred from audit rows.

    ``start_ms`` is the first component edit start, ``last_activity_ms`` tracks
    the latest audit activity before a boundary, and ``polygons`` stores
    component geometry used to decide whether later autoclose creations still
    touch the shell.
    """

    image_name: str
    start_ms: int
    last_activity_ms: int
    polygons: list[list[Point]]


@dataclass(frozen=True, slots=True)
class CompletedTurtleShell:
    """Immutable summary emitted when an active shell reaches a boundary.

    ``duration_ms`` excludes idle time when inactivity completes the shell.
    ``final_polygon_count`` lets session statistics report average
    completed-shell size.
    """

    duration_ms: int
    final_polygon_count: int


def completed_turtle_shell_durations_ms(
    events: list[dict[str, Any]],
    current_time_ms: int | None = None,
) -> list[int]:
    """Return only the durations for inferred completed turtle shells.

    This is a convenience wrapper for callers that do not need final polygon
    counts.
    """

    return [
        shell.duration_ms
        for shell in completed_turtle_shells(events, current_time_ms)
    ]


def completed_turtle_shells(
    events: list[dict[str, Any]],
    current_time_ms: int | None = None,
) -> list[CompletedTurtleShell]:
    """Return inferred completed turtle shells from ordered audit rows.

    ``events`` must already be in audit chronology. An autoclose
    ``create_annotation`` row with audited polygon geometry starts a shell.
    Subsequent autoclose creations extend the active shell only when they belong
    to the same image and intersect existing shell polygons.

    The active shell completes at the earliest boundary: ten seconds of audit
    inactivity, a view event for another image, normal application close, or
    the start time of a disconnected or non-shell creation. ``current_time_ms``
    lets a live statistics refresh close an otherwise active shell once it has
    been idle long enough.
    """

    completed: list[CompletedTurtleShell] = []
    active: ActiveTurtleShell | None = None
    for event in events:
        event_ms = audit_event_time_ms(event)
        event_start_ms = audit_event_start_ms(event)
        # CODEX: A long edit is active work; only the gap before it starts is idle.
        if (
            active is not None
            and event_start_ms - active.last_activity_ms >= IDLE_TIMEOUT_MS
        ):
            completed.append(completed_shell(active, active.last_activity_ms))
            active = None

        action = str(event.get("action", ""))
        image_name = audit_event_image_name(event)
        # Moving to another image is a workflow boundary for the active shell.
        if (
            active is not None
            and action == VIEW_AUDIT_ACTION
            and image_name != active.image_name
        ):
            completed.append(completed_shell(active, event_ms))
            active = None
        # Normal application close completes any shell still in progress.
        if active is not None and action == CLOSE_AUDIT_ACTION:
            completed.append(completed_shell(active, event_ms))
            active = None

        if action == "create_annotation":
            polygon = created_annotation_polygon(event)
            start_ms = event_start_ms
            # Disconnected or non-geometric creations end the current shell first.
            if active is not None and (
                image_name != active.image_name
                or polygon is None
                or not polygon_intersects_shell(polygon, active.polygons)
            ):
                completed.append(completed_shell(active, start_ms))
                active = None
            # Only autoclose creations with audited geometry contribute components.
            if is_turtle_shell_component(event) and polygon is not None:
                if active is None:
                    active = ActiveTurtleShell(
                        image_name or "",
                        start_ms,
                        event_ms,
                        [polygon],
                    )
                else:
                    active.polygons.append(polygon)

        if active is not None:
            active.last_activity_ms = max(active.last_activity_ms, event_ms)

    if (
        active is not None
        and current_time_ms is not None
        and current_time_ms - active.last_activity_ms >= IDLE_TIMEOUT_MS
    ):
        # Live CSV refreshes can close an idle shell before another audit row exists.
        completed.append(completed_shell(active, active.last_activity_ms))
    return completed


def is_turtle_shell_component(event: dict[str, Any]) -> bool:
    """Return whether an audit row created one turtle-shell component.

    Shell membership is explicit in audit details: the row must be a
    ``create_annotation`` action whose decoded ``details_json`` has
    ``autoclose`` set to ``True``.
    """

    details = audit_json_field(event, "details_json")
    return (
        str(event.get("action", "")) == "create_annotation"
        and isinstance(details, dict)
        and details.get("autoclose") is True
    )


def created_annotation_polygon(event: dict[str, Any]) -> list[Point] | None:
    """Return the newly created annotation polygon from an audit event.

    ``source_uuid`` identifies which annotation in ``after_state_json`` belongs
    to the creation event. Coordinates are converted to float tuples so Shapely
    receives a consistent point representation.
    """

    source_uuid = event.get("source_uuid")
    if not source_uuid:
        return None
    after_state = audit_json_field(event, "after_state_json")
    if not isinstance(after_state, dict):
        return None
    for annotation in after_state.get("annotations", []):
        if str(annotation.get("annotation_uuid")) == str(source_uuid):
            return [
                (float(point[0]), float(point[1]))
                for point in annotation["polygon_coords"]
            ]
    return None


def polygon_intersects_shell(
    polygon: list[Point],
    shell_polygons: list[list[Point]],
) -> bool:
    """Return whether a polygon touches or overlaps an inferred shell.

    Shapely ``intersects`` treats shared edges and shared vertices as
    connectivity, matching the way Turtle shell components grow around a shared
    outline.
    """

    shape = Polygon(polygon)
    return any(shape.intersects(Polygon(existing)) for existing in shell_polygons)


def audit_event_time_ms(event: dict[str, Any]) -> int:
    """Return the millisecond commit timestamp for one audit row."""

    return int(event.get("event_time") or 0)


def audit_event_start_ms(event: dict[str, Any]) -> int:
    """Return the inferred edit start time for one audit row.

    Timed events start at commit time minus ``duration_ms``. Untimed rows use
    their commit timestamp because no earlier edit start is available.
    """

    duration_ms = event.get("duration_ms")
    if duration_ms is None:
        return audit_event_time_ms(event)
    return max(0, audit_event_time_ms(event) - int(duration_ms))


def shell_duration_ms(shell: ActiveTurtleShell, end_ms: int) -> int:
    """Return non-negative elapsed shell time between start and boundary."""

    return max(0, end_ms - shell.start_ms)


def completed_shell(
    shell: ActiveTurtleShell,
    end_ms: int,
) -> CompletedTurtleShell:
    """Convert active shell state into the emitted completion summary."""

    return CompletedTurtleShell(
        duration_ms=shell_duration_ms(shell, end_ms),
        final_polygon_count=len(shell.polygons),
    )
