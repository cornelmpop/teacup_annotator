"""Own annotation fills and outlines in the zoom preview."""

from __future__ import annotations

from typing import Any
from typing import Protocol
from typing import TYPE_CHECKING

from PIL import Image

from annotator.coco.type_helpers import annotation_export_type
from annotator.geom.coordinates import map_polygon_between_spaces
from annotator.gui.annotation_styles import annotation_fill
from annotator.gui.annotation_styles import annotation_outline
from annotator.gui.annotation_styles import AnnotationStyleHost
from annotator.geom.polygon import polygon_intersects_box
from annotator.gui.constants import ZOOM_VIEW_SIZE
from annotator.gui.model.settings import class_colour_map
from annotator.gui.selection import current_annotations
from annotator.gui.selection import selected_annotation
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState
from annotator.overlays import mixed_annotation_overlay

if TYPE_CHECKING:
    from annotator.gui.window.state import WindowWidgets


class ZoomAnnotationHost(AnnotationStyleHost, Protocol):
    """Document, style queries, and widgets required by zoom annotations."""

    project: ProjectState
    view: ViewState
    interaction: InteractionState
    widgets: WindowWidgets


def draw_annotation_overlay_on_crop(
    host: ZoomAnnotationHost,
    crop: Image.Image,
    crop_left: int,
    crop_top: int,
    crop_size: int,
) -> None:
    """Composite translucent annotation fills into an image-space crop."""

    crop_box = (
        float(crop_left),
        float(crop_top),
        float(crop_left + crop_size),
        float(crop_top + crop_size),
    )
    colour_map = class_colour_map(host)
    polygon_fills: list[
        tuple[list[tuple[float, float]], tuple[int, int, int, int]]
    ] = []
    for annotation in current_annotations(host.project):
        fill = annotation_fill(host, annotation, colour_map)
        for polygon in annotation.polygons:
            if len(polygon) < 3 or not polygon_intersects_box(
                polygon,
                crop_box,
            ):
                continue
            points = map_polygon_between_spaces(
                polygon,
                source_origin=(crop_left, crop_top),
            )
            polygon_fills.append((points, fill))
    overlay = mixed_annotation_overlay(crop.size, polygon_fills)
    if overlay is not None:
        crop.alpha_composite(overlay)


def draw_drag_delta_fill_on_crop(
    host: ZoomAnnotationHost,
    crop: Image.Image,
    crop_left: int,
    crop_top: int,
) -> None:
    """CODEX: Add current local geometry above the frozen drag fill.

    A free-polygon vertex contributes the triangle between its current
    neighbours, including synchronized shared vertices. A constrained rectangle
    contributes its current complete shape because corner and side edits can
    move more than one vertex. Additive compositing makes the moving region
    visibly denser until release rebuilds the exact stable fill.
    """

    annotation = selected_annotation(host.project, host.interaction)
    if annotation is None:
        return
    colour_map = class_colour_map(host)
    polygon_fills: list[
        tuple[list[tuple[float, float]], tuple[int, int, int, int]]
    ] = []
    if annotation_export_type(annotation) == "rectangle":
        fill = annotation_fill(host, annotation, colour_map)
        for polygon in annotation.polygons:
            points = map_polygon_between_spaces(
                polygon,
                source_origin=(crop_left, crop_top),
            )
            polygon_fills.append((points, fill))
    elif host.interaction.drag_vertex_ref is not None:
        polygon_index, vertex_index = host.interaction.drag_vertex_ref
        polygon = annotation.polygons[polygon_index]
        neighbour_triangle = [
            polygon[(vertex_index - 1) % len(polygon)],
            polygon[vertex_index],
            polygon[(vertex_index + 1) % len(polygon)],
        ]
        points = map_polygon_between_spaces(
            neighbour_triangle,
            source_origin=(crop_left, crop_top),
        )
        polygon_fills.append(
            (points, annotation_fill(host, annotation, colour_map))
        )

        annotations = current_annotations(host.project)
        for (
            annotation_index,
            shared_polygon_index,
            shared_vertex_index,
        ) in host.interaction.drag_shared_vertex_refs:
            shared_annotation = annotations[annotation_index]
            shared_polygon = shared_annotation.polygons[shared_polygon_index]
            shared_triangle = [
                shared_polygon[(shared_vertex_index - 1) % len(shared_polygon)],
                shared_polygon[shared_vertex_index],
                shared_polygon[(shared_vertex_index + 1) % len(shared_polygon)],
            ]
            shared_points = map_polygon_between_spaces(
                shared_triangle,
                source_origin=(crop_left, crop_top),
            )
            polygon_fills.append(
                (
                    shared_points,
                    annotation_fill(host, shared_annotation, colour_map),
                )
            )

    delta_overlay = mixed_annotation_overlay(crop.size, polygon_fills)
    if delta_overlay is not None:
        crop.alpha_composite(delta_overlay)

def draw_zoom_annotation_outlines(
    host: ZoomAnnotationHost,
    crop_left: int,
    crop_top: int,
    crop_size: int,
) -> None:
    """Draw crisp annotation outlines directly on the zoom canvas.

    CMP: Simply zooming in on the main composite image produces blury results,
    so it's important to redraw instead.
    """

    if crop_size <= 0:
        return
    crop_box = (
        float(crop_left),
        float(crop_top),
        float(crop_left + crop_size),
        float(crop_top + crop_size),
    )
    scale = ZOOM_VIEW_SIZE / crop_size
    canvas = host.widgets.controls.zoom_canvas
    for annotation in current_annotations(host.project):
        outline = annotation_outline(host, annotation)
        for polygon in annotation.polygons:
            if len(polygon) < 3 or not polygon_intersects_box(
                polygon,
                crop_box,
            ):
                continue
            zoom_points = map_polygon_between_spaces(
                polygon,
                source_origin=(crop_left, crop_top),
                scale=(scale, scale),
            )
            canvas_points = [
                coordinate for point in zoom_points for coordinate in point
            ]
            if len(canvas_points) >= 6:
                canvas.create_polygon(
                    canvas_points,
                    fill="",
                    outline=outline,
                    width=1,
                    tags=("annotation",),
                )
