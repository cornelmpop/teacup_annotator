"""CODEX: Arrow queries and endpoint-drag interactions."""

from __future__ import annotations

import math
from typing import Protocol
from typing import cast

from annotator.arrows import Arrow
from annotator.geom.polygon import arrow_polygon_boundary_start
from annotator.geom.rectangle import point_in_arrow_bbox
from annotator.gui.audit.undo import push_undo
from annotator.gui.arrow_editing import ArrowEditingHost
from annotator.gui.arrow_editing import save_arrows_after_edit
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.constants import ARROW_HIT_TOLERANCE
from annotator.gui.constants import VERTEX_HALF
from annotator.gui.interactions import MIN_ZOOM
from annotator.gui.project.navigation import current_image_name
from annotator.gui.state import ProjectState
from annotator.gui.view_geometry import clamp_point_to_image
from annotator.gui.view_geometry import image_to_canvas_point


class ArrowInteractionHost(ArrowEditingHost, Protocol):
    """CODEX: Application state and effects required by arrow interaction."""

    def set_canvas_cursor(self, cursor: str = "") -> None: ...

# CMP: TODO - Clarify nearest to what, and why that distance to X measurement
# makes sense.
def arrow_for_polygon_start(
    project: ProjectState,
    image_name: str,
    polygon: list[tuple[float, float]],
) -> Arrow | None:
    """CODEX: Return the nearest saved arrow that crosses a polygon boundary."""

    best_arrow: Arrow | None = None
    best_distance: float | None = None
    for arrow in project.arrows_by_image.get(image_name, []):
        start = arrow_polygon_boundary_start(polygon, arrow.coords)
        if start is None:
            continue
        distance = math.dist(arrow.start, start)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_arrow = arrow
    return best_arrow

# CMP: TODO - Clarify why the topmost arrow is returned, and what options there
# are for selecting the 'right' arrow (if there are multiple) on e.g. a delete
# operation.
def arrow_index_at(
    host: ArrowInteractionHost,
    image_point: tuple[float, float],
) -> int | None:
    """CODEX: Return the topmost arrow whose minimum bounding box contains a point."""

    if not host.project.image_paths:
        return None

    # CMP: Explain the zoom calculation here
    tolerance = ARROW_HIT_TOLERANCE / max(MIN_ZOOM, host.view.zoom)
    arrows = host.project.arrows_by_image.get(current_image_name(host), [])
    for index in range(len(arrows) - 1, -1, -1):
        if point_in_arrow_bbox(image_point, arrows[index].coords, tolerance):
            return index
    return None


def selected_arrow(
    host: ArrowInteractionHost,
) -> Arrow | None:
    """CODEX: Return the selected arrow, if any."""

    if host.interaction.selected_arrow_index is None or not host.project.image_paths:
        return None
    arrows = host.project.arrows_by_image.get(current_image_name(host), [])
    if 0 <= host.interaction.selected_arrow_index < len(arrows):
        return arrows[host.interaction.selected_arrow_index]
    return None


def arrow_endpoint_at(
    host: ArrowInteractionHost,
    canvas_point: tuple[float, float],
) -> int | None:
    """CODEX: Return the selected arrow endpoint index under a canvas point."""

    if len(host.interaction.selected_arrow_indices) > 1:
        return None
    arrow = selected_arrow(host)
    if arrow is None:
        return None
    endpoints = (arrow.start, arrow.end)

    # CMP: TODO - Explain the logic here.
    for endpoint_index, endpoint in enumerate(endpoints):
        canvas_x, canvas_y = image_to_canvas_point(endpoint, host.view)
        if (
            abs(canvas_point[0] - canvas_x) <= VERTEX_HALF
            and abs(canvas_point[1] - canvas_y) <= VERTEX_HALF
        ):
            return endpoint_index
    return None


def begin_arrow_endpoint_drag(
    host: ArrowInteractionHost,
    endpoint_index: int,
) -> None:
    """CODEX: Begin dragging a selected arrow endpoint."""

    arrow = selected_arrow(host)
    if arrow is None:
        return

    # CMP: TODO - As mentioned elsewhere as well - are we still using
    # arrow_uuid?
    push_undo(
        host,
        action="move_arrow_endpoint",
        details={
            "image_name": current_image_name(host),
            "arrow_index": host.interaction.selected_arrow_index,
            "arrow_uuid": arrow.arrow_uuid,
            "endpoint_index": endpoint_index,
            "arrow": arrow.coords,
        },
        source_uuid=arrow.arrow_uuid,
        source_table="annotations",
    )
    host.interaction.drag_arrow_endpoint_index = endpoint_index
    host.set_canvas_cursor("cross")


def drag_selected_arrow_endpoint_to(
    host: ArrowInteractionHost,
    image_point: tuple[float, float],
) -> None:
    """CODEX: Move one endpoint of the selected arrow."""

    # CMP - TODO: Clarify what conditions would trigger this
    if (
        host.interaction.selected_arrow_index is None
        or host.interaction.drag_arrow_endpoint_index is None
    ):
        return
    arrows = host.project.arrows_by_image.get(current_image_name(host), [])
    if not (0 <= host.interaction.selected_arrow_index < len(arrows)):
        return
    image_point = clamp_point_to_image(image_point, host.view)
    arrows[host.interaction.selected_arrow_index] = arrows[
        host.interaction.selected_arrow_index
    ].moved_endpoint(host.interaction.drag_arrow_endpoint_index, image_point)


def finish_arrow_endpoint_drag(host: ArrowInteractionHost) -> None:
    """CODEX: Finish dragging a selected arrow endpoint and persist the result."""

    host.interaction.drag_arrow_endpoint_index = None
    save_arrows_after_edit(host)
    redraw_canvas(cast(CanvasRenderHost, host))
