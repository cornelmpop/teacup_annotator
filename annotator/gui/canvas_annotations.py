"""Own main-canvas annotation polygons, labels, and vertex handles."""

from __future__ import annotations

import tkinter as tk
from typing import Protocol
from typing import TYPE_CHECKING

from PIL import ImageTk

from annotator.geom.coordinates import map_polygon_between_spaces
from annotator.geom.polygon import polygon_centroid
from annotator.geom.polygon import signed_polygon_area
from annotator.gui.annotation_styles import annotation_fill
from annotator.gui.annotation_styles import annotation_outline
from annotator.gui.annotation_styles import AnnotationStyleHost
from annotator.gui.canvas_tooltips import CanvasTooltipHost
from annotator.gui.canvas_tooltips import draw_canvas_class_label
from annotator.gui.constants import VERTEX_HALF
from annotator.gui.model.settings import class_colour_map
from annotator.gui.selection import current_annotations
from annotator.gui.selection import selected_annotation
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState
from annotator.gui.view_geometry import canvas_polygon_points
from annotator.gui.view_geometry import image_to_canvas_point
from annotator.overlays import mixed_annotation_overlay

if TYPE_CHECKING:
    from annotator.gui.window.state import WindowWidgets


class CanvasAnnotationHost(AnnotationStyleHost, CanvasTooltipHost, Protocol):
    """State, retained images, and widgets needed for canvas annotations."""

    project: ProjectState
    view: ViewState
    interaction: InteractionState
    widgets: WindowWidgets
    show_labels_var: tk.BooleanVar
    annotation_overlay_photo: ImageTk.PhotoImage | None
    annotation_overlay_key: tuple[object, ...] | None


# CMP: TODO - Document this function better, including with inline
# comments to explain e.g., the math for the image_points (relative
# to zoom factor)
def draw_annotations(host: CanvasAnnotationHost) -> None:
    """Draw translucent fills and polygon outlines for the current image."""

    width, height = host.view.display_size
    overlay_key = (
        host.project.current_index,
        width,
        height,
        round(host.view.zoom, 6),
        host.view.annotation_revision,
    )
    if host.annotation_overlay_key != overlay_key:
        colour_map = class_colour_map(host)
        polygon_fills = []
        for annotation in current_annotations(host.project):
            fill = annotation_fill(host, annotation, colour_map)
            for polygon in annotation.polygons:
                image_points = map_polygon_between_spaces(
                    polygon,
                    scale=(host.view.zoom, host.view.zoom),
                )
                if len(image_points) >= 3:
                    polygon_fills.append((image_points, fill))
        overlay = mixed_annotation_overlay((width, height), polygon_fills)
        # CODEX: Zoom drags crop this retained pre-drag raster instead of
        # CODEX: rebuilding every annotation fill for each pointer movement.
        host.view.annotation_overlay_image = overlay
        host.annotation_overlay_photo = (
            ImageTk.PhotoImage(overlay) if overlay is not None else None
        )
        host.annotation_overlay_key = overlay_key

    if host.annotation_overlay_photo is not None:
        host.widgets.viewer.canvas.create_image(
            host.view.image_origin[0],
            host.view.image_origin[1],
            image=host.annotation_overlay_photo,
            anchor=tk.NW,
            tags=("annotation_fill",),
        )

    for annotation_index, annotation in enumerate(current_annotations(host.project)):
        outline = annotation_outline(host, annotation)
        for polygon in annotation.polygons:
            points = canvas_polygon_points(polygon, host.view)
            if len(points) < 6:
                continue
            host.widgets.viewer.canvas.create_polygon(
                points,
                fill="",
                outline=outline,
                width=1,
                tags=("annotation", f"annotation:{annotation_index}"),
            )

# CMP: TODO - Clarify what is meant here by its largest polygon. Each
# annotation should correspond to one polygon, rectangle, or arrow. Multiple
# polygons per annotation are not supported (or shouldn't be supported).
def draw_annotation_labels(host: CanvasAnnotationHost) -> None:
    """Draw each annotation class at the center of its largest polygon."""

    if not host.show_labels_var.get() or host.project.coco is None:
        return
    for annotation in current_annotations(host.project):
        polygons = [polygon for polygon in annotation.polygons if len(polygon) >= 3]
        if not polygons:
            continue
        polygon = max(polygons, key=lambda item: abs(signed_polygon_area(item)))
        class_name = host.project.coco.category_name_for_id(annotation.category_id)
        if not class_name:
            continue
        draw_canvas_class_label(
            host,
            image_to_canvas_point(polygon_centroid(polygon), host.view),
            class_name,
            "annotation_label",
            tk.CENTER,
        )

# CMP: TODO - The default colours should not be defined here, but rather in constants
def draw_selected_vertices(host: CanvasAnnotationHost) -> None:
    """Draw editable vertex handles for the selected annotation."""

    annotation = selected_annotation(host.project, host.interaction)
    if annotation is None:
        return
    for polygon_index, polygon in enumerate(annotation.polygons):
        for vertex_index, (x_coord, y_coord) in enumerate(polygon):
            canvas_x, canvas_y = image_to_canvas_point(
                (x_coord, y_coord), host.view
            )
            fill = (
                "#d92323"
                if (polygon_index, vertex_index) in host.interaction.selected_vertices
                else "white"
            )

            # CMP: TODO - Briefly explain the math here.
            host.widgets.viewer.canvas.create_rectangle(
                canvas_x - VERTEX_HALF,
                canvas_y - VERTEX_HALF,
                canvas_x + VERTEX_HALF,
                canvas_y + VERTEX_HALF,
                fill=fill,
                outline="#0057ff",
                width=1,
                tags=("vertex",),
            )
