"""CODEX: Functional arrow creation, deletion, and persistence."""

from __future__ import annotations

import sqlite3
import time
from tkinter import messagebox
from typing import Protocol
from typing import cast

from annotator.arrows import new_arrow
from annotator.gui.audit.events import flush_pending_audit_events
from annotator.gui.audit.undo import push_undo
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.persistence import persist_arrows
from annotator.gui.project.navigation import current_image_name
from annotator.gui.recovery import RecoveryHost
from annotator.gui.recovery import restore_arrows_from_sql
from annotator.gui.state import InteractionState
from annotator.gui.view_geometry import clamp_point_to_image


class ArrowEditingHost(RecoveryHost, Protocol):
    """CODEX: Application state and effects required to edit saved arrows."""

    interaction: InteractionState

    def set_canvas_cursor(self, cursor: str = "") -> None: ...
    def update_canvas_cursor(self) -> None: ...


def delete_arrow_at(host: ArrowEditingHost, arrow_index: int) -> None:
    """CODEX: Delete a saved arrow by image-local index."""

    if host.project.folder is None:
        return
    image_name = current_image_name(host)
    arrows = host.project.arrows_by_image.get(image_name, [])
    if not (0 <= arrow_index < len(arrows)):
        return
    arrow = arrows[arrow_index]
    push_undo(
        host,
        action="delete_arrow",
        details={
            "image_name": image_name,
            "arrow_index": arrow_index,
            "arrow_uuid": arrow.arrow_uuid,
            "arrow": arrow.coords,
        },
        source_uuid=arrow.arrow_uuid,
        source_table="annotations",
    )
    del arrows[arrow_index]
    if arrows:
        host.project.arrows_by_image[image_name] = arrows
    else:
        host.project.arrows_by_image.pop(image_name, None)
    host.interaction.selected_arrow_index = None
    host.interaction.selected_arrow_indices.clear()
    save_arrows_after_edit(host)
    redraw_canvas(cast(CanvasRenderHost, host))


def start_draw_arrow(host: ArrowEditingHost) -> None:
    """CODEX: Enter two-click mode for drawing an arrow."""

    if host.view.current_image is None:
        return

    # CMP: TODO - As commented elsewhere, this is lot for a
    # human to reliably keep track of. The most that should be
    # passed to interaction, I would think, is mode = "arrow" -
    # the rest of the effective reset should be owned by
    # host.interaction, no?
    host.interaction.mode = "arrow"
    host.interaction.temp_polygon = []
    host.interaction.merge_primary_index = None
    host.interaction.select_start_annotation_index = None
    host.interaction.select_start_polygon_index = None
    host.interaction.selected_annotation_index = None
    host.interaction.selected_annotation_indices.clear()
    host.interaction.selected_arrow_index = None
    host.interaction.selected_arrow_indices.clear()
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    host.interaction.temp_arrow_start = None
    host.interaction.temp_arrow_current = None
    host.interaction.edit_started_at_monotonic_ns = time.monotonic_ns()
    host.set_canvas_cursor("cross")
    host.log("Draw arrow: click the base, then click the tip.")
    redraw_canvas(cast(CanvasRenderHost, host))


def handle_arrow_click(
    host: ArrowEditingHost,
    image_point: tuple[float, float],
) -> None:
    """CODEX: Record an arrow start point or finish a complete arrow edit."""

    if host.project.folder is None or not host.project.image_paths:
        return
    image_point = clamp_point_to_image(image_point, host.view)

    # CMP: TODO - as specified elsewhere, logging this event without a uuid
    # may be problematic from an audit perspective.
    if host.interaction.temp_arrow_start is None:
        host.interaction.temp_arrow_start = image_point
        host.interaction.temp_arrow_current = image_point
        host.log(f"Arrow base: ({image_point[0]:.1f}, {image_point[1]:.1f})")
        redraw_canvas(cast(CanvasRenderHost, host))
        return

    arrow = new_arrow(host.interaction.temp_arrow_start, image_point)
    push_undo(
        host,
        action="draw_arrow",
        details={
            "image_name": current_image_name(host),
            "arrow_uuid": arrow.arrow_uuid,
            "arrow": arrow.coords,
        },
        source_uuid=arrow.arrow_uuid,
        source_table="annotations",
        started_monotonic_ns=host.interaction.edit_started_at_monotonic_ns,
    )
    host.project.arrows_by_image.setdefault(current_image_name(host), []).append(arrow)
    host.interaction.temp_arrow_start = None
    host.interaction.temp_arrow_current = None
    host.interaction.edit_started_at_monotonic_ns = None
    host.interaction.mode = None
    try:
        persist_arrows(host, commit=False)
        flush_pending_audit_events(host)
    except sqlite3.Error as exc:
        restore_arrows_from_sql(host)
        messagebox.showerror("Could not save arrow", str(exc))
        host.log(f"Could not save arrow: {exc}")
        redraw_canvas(cast(CanvasRenderHost, host))
        return

    # CMP: TODO - Document how time is recorded here (start|end
    # and/or duration).
    host.log(
        f"Arrow: ({arrow.start_x:.1f}, {arrow.start_y:.1f}) "
        f"to ({arrow.end_x:.1f}, {arrow.end_y:.1f})"
    )
    host.update_canvas_cursor()
    redraw_canvas(cast(CanvasRenderHost, host))


# CMP: TODO - It would be useful to document here when this is
# expected to be triggered. Presumably you don't want to have
# 100 arrows in an image, unsaved, before you try to commit and
# notice that they couldn't be written.
def save_arrows_after_edit(
    host: ArrowEditingHost,
) -> None:
    """CODEX: Persist one arrow edit and flush its pending audit event."""

    if host.project.folder is None:
        return
    try:
        persist_arrows(host, commit=False)
        flush_pending_audit_events(host)
    except sqlite3.Error as exc:
        restore_arrows_from_sql(host)
        host.log(f"Could not save arrows: {exc}")
        messagebox.showerror("Could not save arrows", str(exc))
        redraw_canvas(cast(CanvasRenderHost, host))
