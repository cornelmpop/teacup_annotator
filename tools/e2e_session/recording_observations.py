"""CODEX: Capture curated replay observations after recorded actions."""

from __future__ import annotations

from pathlib import Path
from tkinter import TclError
from typing import Any

from tools.e2e_session.recording_writer import format_number
from tools.e2e_session.recording_writer import format_point
from tools.e2e_session.recording_writer import format_size


DEFAULT_OBSERVATION_KEYS = (
    "mode",
    "temp_vertices",
    "temp_arrow",
    "zoom",
    "index",
    "annotations",
    "arrows",
    "selected",
    "selected_regions",
    "selected_arrows",
    "selected_vertices",
    "dirty",
    "undo_depth",
    "audit_queue",
    "review_flagged",
)

LOADED_OBSERVATION_KEYS = (
    "folder",
    "images",
    "index",
    "classes",
    "annotations",
)


def observation_tokens(
    app: Any,
    keys: tuple[str, ...] = DEFAULT_OBSERVATION_KEYS,
    *,
    project_folder: Path | None = None,
    root_size: tuple[int, int] | None = None,
    canvas_size: tuple[int, int] | None = None,
    last_image_point: tuple[float, float] | None = None,
) -> tuple[str, ...]:
    """CODEX: Return ``key=value`` tokens for the recorder's curated state."""

    tokens: list[str] = []
    for key in keys:
        value = observation_value(
            app,
            key,
            project_folder=project_folder,
            root_size=root_size,
            canvas_size=canvas_size,
            last_image_point=last_image_point,
        )
        tokens.append(f"{key}={value}")
    return tuple(tokens)


def observation_value(
    app: Any,
    key: str,
    *,
    project_folder: Path | None = None,
    root_size: tuple[int, int] | None = None,
    canvas_size: tuple[int, int] | None = None,
    last_image_point: tuple[float, float] | None = None,
) -> str:
    """CODEX: Return one replay-supported observation value from app state."""

    if key == "folder":
        folder = app.project.folder
        if folder is None:
            return ""
        if project_folder is not None and Path(folder).resolve() == project_folder.resolve():
            return "<fixture>"
        return str(folder)
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
        return "none" if start is None else format_point(start)
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
        if root_size is None:
            return "unknown"
        return format_size(root_size)
    if key == "canvas":
        if canvas_size is None:
            return "unknown"
        return format_size(canvas_size)
    if key == "image":
        if last_image_point is None:
            return "none"
        return format_point(last_image_point)
    if key == "closed":
        try:
            exists = app.root.winfo_exists()
        except TclError:
            return "1"
        return "0" if exists else "1"
    raise ValueError(f"unsupported observation key {key!r}")


def _current_annotation_count(app: Any) -> int:
    """CODEX: Return the annotation count for the currently displayed image."""

    if app.project.coco is None or not app.project.image_paths:
        return 0
    image_name = app.project.image_paths[app.project.current_index].name
    return len(app.project.coco.annotations_for(image_name))


def _format_list(values: tuple[str, ...]) -> str:
    """CODEX: Format a compact list to match replay observation syntax."""

    return "[" + ",".join(values) + "]"


def format_vertex_refs(vertices: set[tuple[int, int]]) -> str:
    """CODEX: Format selected polygon vertices as stable session references."""

    refs = tuple(
        f"{polygon_index}:{vertex_index}"
        for polygon_index, vertex_index in sorted(vertices)
    )
    return _format_list(refs)
