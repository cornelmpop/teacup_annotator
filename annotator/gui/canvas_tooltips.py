"""Own hover and persistent class-label drawing on the image canvas."""

from __future__ import annotations

import tkinter as tk
from typing import Literal
from typing import Protocol
from typing import TYPE_CHECKING

from annotator.gui.constants import CLASS_TOOLTIP_FONT
from annotator.gui.hit_testing import annotation_index_at
from annotator.gui.selection import current_annotations
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState

if TYPE_CHECKING:
    from annotator.gui.window.state import WindowWidgets

CanvasAnchor = Literal["nw", "n", "ne", "w", "center", "e", "sw", "s", "se"]


class CanvasTooltipHost(Protocol):
    """Document, interaction, and widgets required by canvas class labels."""

    project: ProjectState
    interaction: InteractionState
    widgets: WindowWidgets


def update_hover_class_tooltip(
    host: CanvasTooltipHost,
    canvas_point: tuple[float, float],
    image_point: tuple[float, float] | None,
) -> None:
    """Show the unselected annotation class beside the current pointer."""

    canvas = host.widgets.viewer.canvas
    canvas.delete("class_tooltip")
    if (
        host.project.coco is None
        or image_point is None
        or host.interaction.mode is not None
    ):
        return
    annotations = current_annotations(host.project)
    annotation_index = annotation_index_at(annotations, image_point)

    if (
        annotation_index is None
        or annotation_index == host.interaction.selected_annotation_index
    ):
        return

    # CMP: QUESTION - Under what valid application state could the
    # annotation index be greater or equal to len(annotations)?
    if not (0 <= annotation_index < len(annotations)):
        return
    class_name = host.project.coco.category_name_for_id(
        annotations[annotation_index].category_id
    )
    if not class_name:
        return
    draw_canvas_class_label(
        host,
        (canvas_point[0] + 14, canvas_point[1] - 12),
        class_name,
        "class_tooltip",
        "sw",
    )

# CMP: TODO - Stylistic elements (e.g., colour) should not be hard-coded here.
def draw_canvas_class_label(
    host: CanvasTooltipHost,
    canvas_point: tuple[float, float],
    class_name: str,
    tag: str,
    anchor: CanvasAnchor,
) -> None:
    """Draw one class label with the shared hover-tooltip styling."""

    canvas = host.widgets.viewer.canvas
    text_id = canvas.create_text(
        canvas_point[0],
        canvas_point[1],
        text=class_name,
        anchor=anchor,
        fill="#111111",
        font=CLASS_TOOLTIP_FONT,
        tags=(tag,),
    )
    bbox = canvas.bbox(text_id)
    if bbox is None:
        return
    pad = 4
    rect_id = canvas.create_rectangle(
        bbox[0] - pad,
        bbox[1] - pad,
        bbox[2] + pad,
        bbox[3] + pad,
        fill="#fff7cc",
        outline="#333333",
        width=1,
        tags=(tag,),
    )
    canvas.tag_lower(rect_id, text_id)
    canvas.tag_raise(tag)
