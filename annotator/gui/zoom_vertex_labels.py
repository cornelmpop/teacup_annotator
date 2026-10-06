"""Own vertex-ID layout and drawing in the zoom preview."""

from __future__ import annotations

from typing import Any
from typing import Protocol
from typing import TYPE_CHECKING

from annotator.geom.coordinates import map_point_between_spaces
from annotator.gui.constants import VERTEX_ID_FONT
from annotator.gui.constants import ZOOM_VIEW_SIZE
from annotator.gui.selection import selected_annotation
from annotator.gui.vertex_labels import non_overlapping_or_focus_vertex_labels
from annotator.gui.vertex_labels import vertex_label_specs_for_canvas_polygon
from annotator.gui.vertex_labels import VertexLabelHost
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState

if TYPE_CHECKING:
    from annotator.gui.window.state import WindowWidgets


class ZoomVertexLabelHost(VertexLabelHost, Protocol):
    """Selection, layout queries, and widgets required by zoom vertex labels."""

    project: ProjectState
    interaction: InteractionState
    widgets: WindowWidgets

# CMP: TODO - Consider refactoring - see zoom_overlaps.py too. This seems to duplicate
# existing functionality.
def draw_zoom_vertex_ids(
    host: ZoomVertexLabelHost,
    crop_left: int,
    crop_top: int,
    crop_size: int,
) -> None:
    """Lay out and draw selected-annotation vertex IDs in the zoom canvas."""

    if not host.show_vertex_ids_var.get():
        return
    annotation = selected_annotation(host.project, host.interaction)
    if annotation is None or crop_size <= 0:
        return
    scale = ZOOM_VIEW_SIZE / crop_size
    origin = map_point_between_spaces(
        (0.0, 0.0),
        source_origin=(crop_left, crop_top),
        scale=(scale, scale),
    )
    label_specs = [
        spec
        for polygon_index, polygon in enumerate(annotation.polygons)
        for spec in vertex_label_specs_for_canvas_polygon(
            polygon,
            polygon_index=polygon_index,
            scale=scale,
            origin=origin,
            visible_box=(
                0.0,
                0.0,
                float(ZOOM_VIEW_SIZE),
                float(ZOOM_VIEW_SIZE),
            ),
        )
    ]
    for spec in non_overlapping_or_focus_vertex_labels(host, label_specs):
        draw_zoom_vertex_label(host, spec)

# CMP: TODO - See comment on the above function. Also, stylistic elements
# should not be hard coded; move to a theme file.
def draw_zoom_vertex_label(
    host: ZoomVertexLabelHost,
    spec: dict[str, Any],
) -> None:
    """Draw one boxed vertex-ID label on the zoom canvas."""

    canvas = host.widgets.controls.zoom_canvas
    left, top, right, bottom = spec["bbox"]
    canvas.create_rectangle(
        left,
        top,
        right,
        bottom,
        fill="#fff7cc",
        outline="#333333",
        width=1,
        tags=("vertex_id",),
    )
    canvas.create_text(
        spec["x"],
        spec["y"],
        text=spec["text"],
        fill="#111111",
        font=VERTEX_ID_FONT,
        tags=("vertex_id",),
    )
