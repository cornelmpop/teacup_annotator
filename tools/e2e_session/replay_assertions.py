"""CODEX: Compare replay observations with curated GUI state."""

from __future__ import annotations

from tkinter import TclError
from typing import Any

from tools.e2e_session.recording_observations import format_vertex_refs
from tools.e2e_session.recording_writer import format_number
from tools.e2e_session.recording_writer import format_point as format_observation_point
from tools.e2e_session.replay_runtime import ReplayRuntime
from tools.e2e_session.replay_setup import ReplaySetup
from tools.e2e_session.session_format import SessionEntry


POINT_TOLERANCE_PX = 0.5


def assert_loaded_fields(
    app: Any,
    runtime: ReplayRuntime,
    setup: ReplaySetup,
    entry: SessionEntry,
) -> None:
    """CODEX: Compare a loaded line's key-value facts with app state."""

    runtime.wait_until(
        lambda: app.project.folder is not None,
        entry.location,
        "project load",
    )
    assert_field_tokens(app, runtime, setup, entry, entry.arguments)


def assert_entry_observations(
    app: Any,
    runtime: ReplayRuntime,
    setup: ReplaySetup,
    entry: SessionEntry,
) -> None:
    """CODEX: Compare an action line's observations with app state."""

    if entry.observations:
        assert_field_tokens(app, runtime, setup, entry, entry.observations)


def assert_field_tokens(
    app: Any,
    runtime: ReplayRuntime,
    setup: ReplaySetup,
    entry: SessionEntry,
    tokens: tuple[str, ...],
) -> None:
    """CODEX: Assert each ``key=value`` token against the current replay state."""

    for token in tokens:
        key, separator, expected = token.partition("=")
        if separator != "=":
            raise AssertionError(f"{entry.location}: expected key=value observation")
        _assert_field(app, runtime, setup, entry, key, expected)


def _assert_field(
    app: Any,
    runtime: ReplayRuntime,
    setup: ReplaySetup,
    entry: SessionEntry,
    key: str,
    expected: str,
) -> None:
    """CODEX: Dispatch one observation key to its state comparison."""

    if key == "vertex":
        actual_vertex = _actual_vertex_value(app, entry, expected)
        _assert_vertex_point(entry, actual_vertex, expected)
        return
    actual = _actual_field_value(app, runtime, setup, key, expected)
    comparison_expected = (
        str(setup.project_folder)
        if key == "folder" and expected == "<fixture>"
        else expected
    )
    if isinstance(actual, tuple):
        _assert_point(entry, key, actual, expected)
        return
    if actual != comparison_expected:
        raise AssertionError(
            f"{entry.location}: expected {key}={expected}, got {key}={actual}"
        )


def _actual_field_value(
    app: Any,
    runtime: ReplayRuntime,
    setup: ReplaySetup,
    key: str,
    expected: str,
) -> str | tuple[float, float]:
    """CODEX: Return a comparable value for one supported observation key."""

    if key == "folder":
        folder = app.project.folder
        return "" if folder is None else str(folder)
    if key == "images":
        return str(len(app.project.image_paths))
    if key == "index":
        return str(app.project.current_index)
    if key == "classes":
        from annotator.gui.model.settings import active_class_names

        return _format_list(active_class_names(app))
    if key == "mode":
        return app.interaction.mode or "none"
    if key == "temp_vertices":
        return str(len(app.interaction.temp_polygon))
    if key == "temp_arrow":
        start = app.interaction.temp_arrow_start
        return "none" if start is None else format_observation_point(start)
    if key == "zoom":
        return format_number(app.view.zoom)
    if key == "annotations":
        return str(_current_annotation_count(app))
    if key == "arrows":
        if not app.project.image_paths:
            return "0"
        image_name = app.project.image_paths[app.project.current_index].name
        return str(len(app.project.arrows_by_image.get(image_name, ())))
    if key == "selected":
        selected = app.interaction.selected_annotation_index
        return "none" if selected is None else str(selected)
    if key == "selected_regions":
        indexes = tuple(
            str(index)
            for index in sorted(app.interaction.selected_annotation_indices)
        )
        return _format_list(indexes)
    if key == "selected_arrows":
        indexes = tuple(
            str(index)
            for index in sorted(app.interaction.selected_arrow_indices)
        )
        return _format_list(indexes)
    if key == "selected_vertices":
        return format_vertex_refs(app.interaction.selected_vertices)
    if key == "dirty":
        return "1" if app.project.dirty else "0"
    if key == "undo_depth":
        return str(len(app.project.undo_stack))
    if key == "audit_queue":
        return str(len(app.project.pending_audit_events))
    if key == "review_flagged":
        if not app.project.image_paths:
            return "0"
        image_name = app.project.image_paths[app.project.current_index].name
        return "1" if image_name in app.project.review_flags else "0"
    if key == "in_transaction":
        connection = app.project.sql_connection
        return "1" if connection is not None and connection.in_transaction else "0"
    if key == "window":
        return _format_size(runtime.root_size())
    if key == "canvas":
        return _format_size(runtime.canvas_size(app.widgets.viewer.canvas))
    if key == "image":
        if runtime.last_image_point is None:
            raise AssertionError("no image point has been recorded")
        return runtime.last_image_point
    if key == "closed":
        try:
            exists = app.root.winfo_exists()
        except TclError:
            return "1"
        return "0" if exists else "1"
    raise AssertionError(f"unsupported observation key {key!r}")


def _actual_vertex_value(
    app: Any,
    entry: SessionEntry,
    expected: str,
) -> tuple[float, float]:
    """CODEX: Return the current point for one recorded annotation vertex."""

    annotation_index, polygon_index, vertex_index, _point = _parse_vertex_token(
        entry,
        expected,
    )
    if app.project.coco is None or not app.project.image_paths:
        raise AssertionError(f"{entry.location}: no loaded annotations")
    image_name = app.project.image_paths[app.project.current_index].name
    annotations = app.project.coco.annotations_for(image_name)
    if not 0 <= annotation_index < len(annotations):
        raise AssertionError(
            f"{entry.location}: annotation index {annotation_index} is unavailable"
        )
    annotation = annotations[annotation_index]
    if not 0 <= polygon_index < len(annotation.polygons):
        raise AssertionError(
            f"{entry.location}: polygon index {polygon_index} is unavailable"
        )
    polygon = annotation.polygons[polygon_index]
    if not 0 <= vertex_index < len(polygon):
        raise AssertionError(
            f"{entry.location}: vertex index {vertex_index} is unavailable"
        )
    return polygon[vertex_index]


def _current_annotation_count(app: Any) -> int:
    """CODEX: Return the annotation count for the current image."""

    if app.project.coco is None or not app.project.image_paths:
        return 0
    image_name = app.project.image_paths[app.project.current_index].name
    return len(app.project.coco.annotations_for(image_name))


def _format_list(values: tuple[str, ...]) -> str:
    """CODEX: Format a compact list to match session observation syntax."""

    return "[" + ",".join(values) + "]"


def _format_size(size: tuple[int, int]) -> str:
    """CODEX: Format a width-height pair as ``WIDTHxHEIGHT``."""

    return f"{size[0]}x{size[1]}"


def _assert_point(
    entry: SessionEntry,
    key: str,
    actual: tuple[float, float],
    expected: str,
) -> None:
    """CODEX: Compare image point observations with a small event tolerance."""

    expected_point = _parse_point(entry, key, expected)
    if (
        abs(actual[0] - expected_point[0]) > POINT_TOLERANCE_PX
        or abs(actual[1] - expected_point[1]) > POINT_TOLERANCE_PX
    ):
        raise AssertionError(
            f"{entry.location}: expected {key}={expected}, "
            f"got {key}={actual[0]:.2f},{actual[1]:.2f}"
        )


def _assert_vertex_point(
    entry: SessionEntry,
    actual: tuple[float, float],
    expected: str,
) -> None:
    """CODEX: Compare a referenced vertex against its expected image point."""

    _annotation_index, _polygon_index, _vertex_index, expected_point = (
        _parse_vertex_token(entry, expected)
    )
    _assert_point(entry, "vertex", actual, _format_point(expected_point))


def _parse_vertex_token(
    entry: SessionEntry,
    expected: str,
) -> tuple[int, int, int, tuple[float, float]]:
    """CODEX: Parse ``ANNOTATION:POLYGON:VERTEX@X,Y`` observations."""

    reference_text, separator, point_text = expected.partition("@")
    if separator != "@":
        raise AssertionError(
            f"{entry.location}: expected vertex=ANNOTATION:POLYGON:VERTEX@X,Y"
        )
    reference_parts = reference_text.split(":")
    if len(reference_parts) != 3:
        raise AssertionError(
            f"{entry.location}: expected vertex=ANNOTATION:POLYGON:VERTEX@X,Y"
        )
    try:
        # CODEX: Session files are external text, so this is the reference parser.
        annotation_index, polygon_index, vertex_index = (
            int(part) for part in reference_parts
        )
    except ValueError as exc:
        raise AssertionError(
            f"{entry.location}: vertex reference indexes must be integers"
        ) from exc
    expected_point = _parse_point(entry, "vertex", point_text)
    return annotation_index, polygon_index, vertex_index, expected_point


def _parse_point(
    entry: SessionEntry,
    key: str,
    expected: str,
) -> tuple[float, float]:
    """CODEX: Parse one expected image point from an observation value."""

    x_text, separator, y_text = expected.partition(",")
    if separator != ",":
        raise AssertionError(f"{entry.location}: expected {key}=X,Y")
    try:
        # CODEX: Observation values are external text, so this is the point parser.
        return float(x_text), float(y_text)
    except ValueError as exc:
        raise AssertionError(f"{entry.location}: expected {key}=X,Y") from exc


def _format_point(point: tuple[float, float]) -> str:
    """CODEX: Format a point for the existing tolerance comparison."""

    return f"{point[0]},{point[1]}"
