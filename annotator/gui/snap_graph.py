"""Explicit snap-graph, tolerance, cache, and live-line calculations."""

from __future__ import annotations

import math
from typing import Any

from annotator.geom.graph import build_existing_polygon_graph
from annotator.geom.polygon import polygon_distance_to_point
from annotator.geom.polygon import polygon_with_inserted_edge_vertices
from annotator.geom.snapping import apply_edge_insertions
from annotator.gui.interactions import MIN_ZOOM
from annotator.gui.selection import current_annotations
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState
from annotator.gui.view_geometry import image_point_from_canvas
from annotator.preferences import DEFAULT_PREFERENCE_VALUES
from annotator.preferences import Preferences
from annotator.preferences.validation import is_hex_colour

Point = tuple[float, float]


def snapping_tolerance_image(
    preferences: Preferences, view: ViewState
) -> float | None:
    """Return the configured snapping tolerance in image pixels."""

    tolerance_px = preferences.get_float(
        "snapping_tolerance_px",
        float(DEFAULT_PREFERENCE_VALUES["snapping_tolerance_px"]),
        minimum=0.0,
    )
    if tolerance_px <= 0:
        return None
    return tolerance_px / max(MIN_ZOOM, view.zoom)


def live_line_image_point(
    view: ViewState, interaction: InteractionState, live_lines_enabled: bool
) -> Point | None:
    """Return the cursor point for the live new-polygon guide line."""

    if (
        interaction.mode != "new"
        or not interaction.temp_polygon
        or not live_lines_enabled
        or view.cursor_canvas_point is None
    ):
        return None
    return image_point_from_canvas(view.cursor_canvas_point, view)

# CMP: TODO - Stylistic elements should not be hard coded here. Also, 'normal'
# in the context of a file dealing with geometric calculations is ambiguous;
# replace for 'default'
def live_line_colour(snap_target_visible: bool, configured_colour: str) -> str:
    """Return the normal or validated snapping colour for a live guide."""

    if not snap_target_visible:
        return "#f59e0b"
    colour = configured_colour.strip()
    return (
        colour
        if is_hex_colour(colour)
        else DEFAULT_PREFERENCE_VALUES["snap_live_line_colour"]
    )


def cursor_near_first_new_polygon_vertex(
    interaction: InteractionState, image_point: Point, tolerance: float | None
) -> bool:
    """Return whether the cursor is within snap tolerance of vertex one."""

    return bool(
        interaction.temp_polygon
        and tolerance is not None
        and math.dist(image_point, interaction.temp_polygon[0]) <= tolerance
    )

# CMP: TODO - Clarify docstrings. They don't make it clear why this function
# exists, or what is meant by key vocabulary such as 'edge-split vertices' or
# 'cache'
def temp_edge_insertion_cache_key(
    interaction: InteractionState,
) -> tuple[tuple[int, int, int, float, float], ...]:
    """Return a stable cache key for temporary edge-split vertices."""

    return tuple(
        (
            int(insertion["annotation_index"]),
            int(insertion["polygon_index"]),
            int(insertion["edge_index"]),
            round(float(insertion["point"][0]), 8),
            round(float(insertion["point"][1]), 8),
        )
        for insertion in interaction.temp_edge_insertions
    )

# CMP: TODO - Clarify docstrings - context is needed for 'temporary snapped edge
# vertices', for example.
def existing_polygons_for_snap_graph(
    project: ProjectState, interaction: InteractionState
) -> list[list[Point]]:
    """Return current polygons with temporary snapped edge vertices."""

    polygons: list[list[Point]] = []
    insertions_by_polygon: dict[tuple[int, int], list[tuple[int, Point]]] = {}

    # CMP: TODO - Add inline comment to clarify logic here.
    if interaction.mode == "new":
        for insertion in interaction.temp_edge_insertions:
            key = (
                int(insertion["annotation_index"]),
                int(insertion["polygon_index"]),
            )
            insertions_by_polygon.setdefault(key, []).append(
                (
                    int(insertion["edge_index"]),
                    insertion["point"],
                )
            )

    # CMP: TODO - again, a short inline comment would improve readability here.
    for annotation_index, annotation in enumerate(current_annotations(project)):
        for polygon_index, polygon in enumerate(annotation.polygons):
            insertions = insertions_by_polygon.get(
                (annotation_index, polygon_index),
                [],
            )
            polygons.append(
                polygon_with_inserted_edge_vertices(polygon, insertions)
                if insertions
                else polygon
            )
    return polygons


def current_snap_graph(
    project: ProjectState,
    view: ViewState,
    interaction: InteractionState,
    tolerance: float | None,
) -> dict[str, Any] | None:
    """Return the cached current-image polygon graph for snapping."""

    if tolerance is None or not project.image_paths:
        return None
    key = (
        str(project.folder) if project.folder is not None else "",
        project.image_paths[project.current_index].name,
        view.annotation_revision,
        round(tolerance, 8),
        temp_edge_insertion_cache_key(interaction),
    )
    if view.existing_polygon_graph_key != key or view.existing_polygon_graph is None:
        view.existing_polygon_graph = build_existing_polygon_graph(
            existing_polygons_for_snap_graph(project, interaction),
            tolerance,
        )
        view.existing_polygon_graph_key = key
    return view.existing_polygon_graph


# CODEX TODO[2026-08-25-16-24]: This name now understates that the query serves
# CODEX TODO[2026-08-25-16-24]: both polygon and rectangle creation; rename it
# CODEX TODO[2026-08-25-16-24]: with its main-canvas and zoom-preview callers.
def snap_context_polygons(
    project: ProjectState,
    view: ViewState,
    interaction: InteractionState,
    snap_new_enabled: bool, tolerance: float | None
) -> list[list[Point]]:
    """CODEX: Return existing polygons near a new region-annotation cursor."""

    if (
        interaction.mode not in {"new", "new_rectangle"}
        or not snap_new_enabled
        or view.cursor_canvas_point is None
    ):
        return []
    image_point = image_point_from_canvas(view.cursor_canvas_point, view)
    if image_point is None or tolerance is None:
        return []
    return [
        polygon
        for polygon in existing_polygons_for_snap_graph(project, interaction)
        if polygon_distance_to_point(polygon, image_point) <= tolerance
    ]


def invalidate_snap_graph(view: ViewState) -> None:
    """Drop the cached graph after annotation or temporary-edge changes."""

    view.existing_polygon_graph_key = None
    view.existing_polygon_graph = None


def apply_temp_edge_insertions_to_annotations(
    project: ProjectState, view: ViewState, interaction: InteractionState
) -> int:
    """Apply temporary snapped edge vertices and clear their graph cache."""

    if not interaction.temp_edge_insertions:
        return 0
    applied_count = apply_edge_insertions(
        current_annotations(project),
        interaction.temp_edge_insertions,
    )
    interaction.temp_edge_insertions = []
    invalidate_snap_graph(view)
    return applied_count
