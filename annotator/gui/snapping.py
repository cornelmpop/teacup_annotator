"""Explicit snap candidate and temporary edge-insertion operations."""

from __future__ import annotations

from annotator.geom.graph import nearest_graph_node
from annotator.geom.polygon import nearest_snap_point_on_polygon_edges
from annotator.geom.snapping import edge_insertion_exists
from annotator.geom.snapping import edge_insertion_for_snap_point
from annotator.gui.selection import current_annotations
from annotator.gui.snap_graph import cursor_near_first_new_polygon_vertex
from annotator.gui.snap_graph import current_snap_graph
from annotator.gui.snap_graph import invalidate_snap_graph
from annotator.gui.snap_graph import live_line_colour
from annotator.gui.state import InteractionState, ProjectState, ViewState
from annotator.gui.view_geometry import clamp_point_to_image

Point = tuple[float, float]


def snapped_new_point(
    project: ProjectState,
    view: ViewState,
    interaction: InteractionState,
    image_point: Point,
    snap_new_enabled: bool,
    tolerance: float | None,
) -> Point:
    """Snap a new-annotation point to nearby existing polygon edges."""

    if not snap_new_enabled:
        return image_point
    snapped = snap_candidate_new_point_to_annotations(
        project, view, interaction, image_point, tolerance
    )
    return clamp_point_to_image(snapped, view) if snapped is not None else image_point

# CMP: TODO - clarify docstring. 'outside' is confusing.
def snapped_edit_point(
    project: ProjectState,
    view: ViewState,
    interaction: InteractionState,
    image_point: Point,
    snap_edits_enabled: bool,
    tolerance: float | None,
) -> Point:
    """Snap an edited point outside the active annotation."""

    if not snap_edits_enabled:
        return image_point
    snapped = snap_candidate_point_to_annotations(
        project,
        view,
        image_point,
        tolerance,
        exclude_annotation_index=interaction.selected_annotation_index,
    )
    return clamp_point_to_image(snapped, view) if snapped is not None else image_point


def snap_preview_image_point(
    project: ProjectState,
    view: ViewState,
    interaction: InteractionState,
    image_point: Point | None,
    snap_new_enabled: bool,
    tolerance: float | None,
) -> Point | None:
    """Return the visible snap target for the current cursor state."""

    if (
        image_point is None
        or interaction.mode not in {"new", "new_rectangle"}
        or not snap_new_enabled
    ):
        return None
    return snap_candidate_new_point_to_annotations(
        project, view, interaction, image_point, tolerance
    )


def new_polygon_live_line_colour(
    project: ProjectState,
    view: ViewState,
    interaction: InteractionState,
    image_point: Point, snap_new_enabled: bool, tolerance: float | None,
    configured_colour: str,
) -> str:
    """Return the live-line colour for the current cursor snap state."""

    snap_target_visible = (
        snap_preview_image_point(
            project,
            view,
            interaction,
            image_point,
            snap_new_enabled,
            tolerance,
        )
        is not None
        or cursor_near_first_new_polygon_vertex(
            interaction,
            image_point,
            tolerance,
        )
    )
    return live_line_colour(snap_target_visible, configured_colour)

# CMP: TODO - consider changing the function name or docstrings. The difference
# between the intended purpose of this function and snapped_new_point() is unclear.
def snap_candidate_new_point_to_annotations(
    project: ProjectState,
    view: ViewState,
    interaction: InteractionState,
    image_point: Point,
    tolerance: float | None,
) -> Point | None:
    """Return a new-annotation snap point, preferring shared vertices."""

    vertex = snap_candidate_vertex_to_annotations(
        project, view, interaction, image_point, tolerance
    )
    if vertex is not None:
        return vertex
    return snap_candidate_point_to_annotations(
        project,
        view,
        image_point,
        tolerance,
    )


def snap_candidate_vertex_to_annotations(
    project: ProjectState,
    view: ViewState,
    interaction: InteractionState,
    image_point: Point, tolerance: float | None
) -> Point | None:
    """Return a nearby graph vertex for a new annotation."""

    if tolerance is None:
        return None
    graph = current_snap_graph(project, view, interaction, tolerance)
    if graph is None:
        return None
    node_index = nearest_graph_node(graph, image_point, tolerance)
    return None if node_index is None else graph["nodes"][node_index]

# CMP: TODO - This is the third function whose purpose cannot be
# easily distinguished from the name. The name is too similar to the
# other two functions, so change.
def snap_candidate_point_to_annotations(
    project: ProjectState,
    view: ViewState,
    image_point: Point,
    tolerance: float | None,
    exclude_annotation_index: int | None = None,
) -> Point | None:
    """Return a nearby annotation-edge snap point, if one is in range."""

    if view.current_image is None or tolerance is None:
        return None
    polygons: list[list[Point]] = []
    for annotation_index, annotation in enumerate(current_annotations(project)):
        if annotation_index != exclude_annotation_index:
            polygons.extend(annotation.polygons)
    snapped = nearest_snap_point_on_polygon_edges(
        image_point,
        polygons,
        tolerance,
    )
    return None if snapped is None else clamp_point_to_image(snapped, view)

# CMP: TODO - revise docstring - the imperative 'register' in the function name doesn't seem to
#      match the passive 'track' in the docstring.
def register_new_polygon_edge_snap(
    project: ProjectState,
    view: ViewState,
    interaction: InteractionState,
    snapped_point: Point, snap_new_enabled: bool, tolerance: float | None
) -> Point:
    """Track a snapped edge point as a temporary source-polygon vertex."""

    if interaction.mode != "new" or not snap_new_enabled:
        return snapped_point
    graph = current_snap_graph(project, view, interaction, tolerance)
    if tolerance is None or graph is None:
        return snapped_point
    if nearest_graph_node(graph, snapped_point, 1e-6) is not None:
        return snapped_point
    insertion = edge_insertion_for_snap_point(
        current_annotations(project),
        snapped_point,
        tolerance,
    )
    if insertion is None or edge_insertion_exists(
        interaction.temp_edge_insertions,
        insertion,
        tolerance,
    ):
        return snapped_point
    interaction.temp_edge_insertions.append(insertion)
    invalidate_snap_graph(view)
    return insertion["point"]
