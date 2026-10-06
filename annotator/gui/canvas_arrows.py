"""Own saved and temporary arrow rendering."""

from __future__ import annotations

import tkinter as tk
from typing import Any
from typing import Protocol
from typing import TYPE_CHECKING

from annotator.arrows import Arrow
from annotator.gui.constants import VERTEX_HALF
from annotator.gui.project.navigation import current_image_name
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState
from annotator.gui.view_geometry import image_to_canvas_point

if TYPE_CHECKING:
    from annotator.gui.window.state import WindowWidgets

class CanvasArrowHost(Protocol):
    """Project, interaction, view, and widgets required for arrow rendering."""

    project: ProjectState
    view: ViewState
    interaction: InteractionState
    widgets: WindowWidgets

# CMP: TODO - Move the hard coded colours and things like
# arrow widths to constants (constants.py?)
def draw_arrows(host: CanvasArrowHost) -> None:
    """Draw saved arrows for the current image."""

    if host.view.current_image is None or not host.project.image_paths:
        return
    for arrow_index, arrow in enumerate(
        host.project.arrows_by_image.get(current_image_name(host), [])
    ):
        selected = (
            arrow_index == host.interaction.selected_arrow_index
            or arrow_index in host.interaction.selected_arrow_indices
        )
        draw_arrow(
            host,
            arrow,
            fill="#0057ff" if selected else "#d92323",
            width=3 if selected else 2,
        )
        if (
            selected
            and arrow_index == host.interaction.selected_arrow_index
            and len(host.interaction.selected_arrow_indices) <= 1
        ):
            draw_arrow_handles(host, arrow)

# CMP: TODO - move the hard coded colours, width, etc to constants.py
def draw_temp_arrow(host: CanvasArrowHost) -> None:
    """Draw the in-progress arrow while choosing its endpoint."""

    if (
        host.interaction.temp_arrow_start is None
        or host.interaction.temp_arrow_current is None
    ):
        return
    draw_arrow(
        host,
        Arrow(
            "temp",
            host.interaction.temp_arrow_start[0],
            host.interaction.temp_arrow_start[1],
            host.interaction.temp_arrow_current[0],
            host.interaction.temp_arrow_current[1],
        ),
        fill="#f59e0b",
        width=2,
        dash=(5, 3),
    )


def draw_arrow(
    host: CanvasArrowHost,
    arrow: Arrow,
    fill: str,
    width: int,
    dash: tuple[int, int] | None = None,
) -> None:
    """Draw one image-space arrow on the canvas."""

    start_x, start_y = image_to_canvas_point(arrow.start, host.view)
    end_x, end_y = image_to_canvas_point(arrow.end, host.view)
    options: dict[str, Any] = {
        "fill": fill,
        "width": width,
        "arrow": tk.LAST,
        "arrowshape": (14, 18, 6),
        "tags": ("arrow",),
    }
    if dash is not None:
        options["dash"] = dash
    host.widgets.viewer.canvas.create_line(start_x, start_y, end_x, end_y, **options)

# CMP: TODO - again, take hard coded colours out of here.
def draw_arrow_handles(host: CanvasArrowHost, arrow: Arrow) -> None:
    """Draw editable endpoint handles for the selected arrow."""

    for endpoint in (arrow.start, arrow.end):
        canvas_x, canvas_y = image_to_canvas_point(endpoint, host.view)
        host.widgets.viewer.canvas.create_rectangle(
            canvas_x - VERTEX_HALF,
            canvas_y - VERTEX_HALF,
            canvas_x + VERTEX_HALF,
            canvas_y + VERTEX_HALF,
            fill="white",
            outline="#0057ff",
            width=1,
            tags=("arrow_vertex",),
        )
