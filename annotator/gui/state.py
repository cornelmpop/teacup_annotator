"""Typed mutable state records shared by the GUI controller layers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

from PIL import Image

from annotator.arrows import Arrow
from annotator.coco import CocoDocument
from annotator.geom.snapping import EdgeInsertion
from annotator.gui.display import FILTER_ALL
from annotator.gui.display import FILTER_NULL

Point = tuple[float, float]
Rectangle = tuple[float, float, float, float]


@dataclass(slots=True)
class ProjectState:
    """Own mutable folder, document, persistence, and review state."""

    project_metadata: dict[str, str] = field(default_factory=dict)
    folder: Path | None = None
    all_image_paths: list[Path] = field(default_factory=list)
    image_paths: list[Path] = field(default_factory=list)
    current_index: int = 0
    coco: CocoDocument | None = None
    sql_connection: sqlite3.Connection | None = None
    session_model_values: dict[str, str] = field(default_factory=dict)
    session_class_names: tuple[str, ...] = ()
    session_class_colours: tuple[str, ...] = ()
    using_folder_model_conf: bool = False
    using_local_class_settings: bool = False
    arrows_by_image: dict[str, list[Arrow]] = field(default_factory=dict)
    annotation_orders_by_uuid: dict[str, int] = field(default_factory=dict)
    undo_stack: list[dict[str, Any]] = field(default_factory=list)
    pending_audit_events: list[dict[str, Any]] = field(default_factory=list)
    next_audit_event_id: int = 1
    last_audit_event_id: int | None = None
    dirty: bool = False
    deletion_marks: set[str] = field(default_factory=set)
    session_deletion_marks: set[str] = field(default_factory=set)
    review_flags: set[str] = field(default_factory=set)
    review_only: bool = False
    active_filter: str = FILTER_ALL
    filter_options: tuple[str, ...] = (FILTER_ALL, FILTER_NULL)


@dataclass(slots=True)
class ViewState:
    """Own non-widget image, coordinate, and rendered-geometry cache state."""

    current_image: Image.Image | None = None
    annotation_overlay_image: Image.Image | None = None
    zoom: float = 1.0
    display_size: tuple[int, int] = (0, 0)
    image_origin: Point = (0.0, 0.0)
    annotation_revision: int = 0
    cursor_canvas_point: Point | None = None
    annotation_overlap_key: tuple[Any, ...] | None = None
    annotation_overlap_geometry: tuple[
        list[tuple[Point, Point]],
        list[Point],
    ] = field(default_factory=lambda: ([], []))
    existing_polygon_graph_key: tuple[Any, ...] | None = None
    existing_polygon_graph: dict[str, Any] | None = None


@dataclass(slots=True)
class InteractionState:
    """Own selection, temporary-edit, drag, key, and input-lock state."""

    selected_annotation_index: int | None = None
    selected_annotation_indices: set[int] = field(default_factory=set)
    selected_arrow_index: int | None = None
    selected_arrow_indices: set[int] = field(default_factory=set)
    selected_vertices: set[tuple[int, int]] = field(default_factory=set)
    selection_rect: Rectangle | None = None
    selection_drag_start: Point | None = None
    selection_drag_current: Point | None = None
    annotation_selection_drag_start: Point | None = None
    annotation_selection_drag_current: Point | None = None
    annotation_selection_rect: Rectangle | None = None
    mode: str | None = None
    temp_polygon: list[Point] = field(default_factory=list)
    temp_edge_insertions: list[EdgeInsertion] = field(default_factory=list)
    edit_started_at_monotonic_ns: int | None = None
    merge_primary_index: int | None = None
    select_start_annotation_index: int | None = None
    select_start_polygon_index: int | None = None
    temp_arrow_start: Point | None = None
    temp_arrow_current: Point | None = None
    panning: bool = False
    drag_vertex_ref: tuple[int, int] | None = None
    drag_rectangle_side_ref: tuple[int, int] | None = None
    drag_vertex_original_point: Point | None = None
    drag_shared_vertex_refs: list[tuple[int, int, int]] = field(default_factory=list)
    drag_rectangle_context: dict[str, Any] | None = None
    drag_arrow_endpoint_index: int | None = None
    a_down: bool = False
    x_down: bool = False
    w_down: bool = False
    z_down: bool = False
    worker_running: bool = False
