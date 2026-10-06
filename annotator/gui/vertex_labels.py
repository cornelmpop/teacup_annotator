"""Own vertex-ID layout, filtering, and boxed label drawing."""

from __future__ import annotations

import tkinter as tk
from typing import Any
from typing import Protocol
from typing import TYPE_CHECKING

from annotator.geom.coordinates import map_point_between_spaces
from annotator.geom.polygon import outward_vertex_normal
from annotator.geom.polygon import polygon_centroid
from annotator.geom.rectangle import point_in_box
from annotator.geom.visualization import label_boxes_overlap
from annotator.geom.visualization import vertex_label_size
from annotator.gui.constants import VERTEX_ID_FONT
from annotator.gui.constants import VERTEX_ID_OFFSET
from annotator.gui.hit_testing import vertex_at
from annotator.gui.selection import selected_annotation
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState

if TYPE_CHECKING:
    from annotator.gui.window.state import WindowWidgets


class VertexLabelHost(Protocol):
    """Selection, view, and widgets required for vertex-ID labels."""

    project: ProjectState
    view: ViewState
    interaction: InteractionState
    widgets: WindowWidgets
    show_vertex_ids_var: tk.BooleanVar


def vertex_label_specs_for_canvas_polygon(
    polygon: list[tuple[float, float]],
    polygon_index: int,
    scale: float,
    origin: tuple[float, float],
    visible_box: tuple[float, float, float, float] | None,
) -> list[dict[str, Any]]:
    """Return fixed-size label placements for one displayed polygon."""

    if len(polygon) < 3:
        return []
    center = polygon_centroid(polygon)
    specs: list[dict[str, Any]] = []
    for vertex_index, point in enumerate(polygon):
        normal = outward_vertex_normal(polygon, vertex_index, center)
        canvas_x, canvas_y = map_point_between_spaces(
            point,
            target_origin=origin,
            scale=(scale, scale),
        )
        label_x = canvas_x + normal[0] * VERTEX_ID_OFFSET
        label_y = canvas_y + normal[1] * VERTEX_ID_OFFSET
        if visible_box is not None and not point_in_box(
            (label_x, label_y), visible_box
        ):
            continue
        text = str(vertex_index + 1)
        width, height = vertex_label_size(text)
        specs.append(
            {
                "text": text,
                "x": label_x,
                "y": label_y,
                "bbox": (
                    label_x - width / 2,
                    label_y - height / 2,
                    label_x + width / 2,
                    label_y + height / 2,
                ),
                "polygon_index": polygon_index,
                "vertex_index": vertex_index,
            }
        )
    return specs


def non_overlapping_or_focus_vertex_labels(
    host: VertexLabelHost,
    label_specs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return all labels when they fit, otherwise one focus label."""

    if not label_specs:
        return []
    if not label_boxes_overlap([spec["bbox"] for spec in label_specs]):
        return label_specs
    annotation = selected_annotation(host.project, host.interaction)
    focus_ref = (
        vertex_at(annotation, host.view.cursor_canvas_point, host.view)
        if host.view.cursor_canvas_point
        else None
    )
    if focus_ref is not None:
        for spec in label_specs:
            if (
                spec["polygon_index"] == focus_ref[0]
                and spec["vertex_index"] == focus_ref[1]
            ):
                return [spec]
    return [label_specs[0]]

# CMP: TODO - Refactor. Stylistic elements should not be hard coded. Move to
#      a theme file.
def draw_canvas_vertex_label(host: VertexLabelHost, spec: dict[str, Any]) -> None:
    """Draw one boxed vertex-ID label on the main canvas."""

    left, top, right, bottom = spec["bbox"]
    canvas = host.widgets.viewer.canvas
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


def draw_selected_vertex_ids(host: VertexLabelHost) -> None:
    """Draw visible vertex IDs for the selected annotation."""

    if not host.show_vertex_ids_var.get():
        return
    annotation = selected_annotation(host.project, host.interaction)
    if annotation is None:
        return
    label_specs = [
        spec
        for polygon_index, polygon in enumerate(annotation.polygons)
        for spec in vertex_label_specs_for_canvas_polygon(
            polygon,
            polygon_index=polygon_index,
            scale=host.view.zoom,
            origin=host.view.image_origin,
            visible_box=None,
        )
    ]
    for spec in non_overlapping_or_focus_vertex_labels(host, label_specs):
        draw_canvas_vertex_label(host, spec)
