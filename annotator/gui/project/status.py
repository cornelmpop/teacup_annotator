"""Synchronize image status, edit summary, and enabled controls."""

from __future__ import annotations

from functools import partial
from typing import Any
from typing import cast
from typing import Mapping
from typing import Protocol

import tkinter as tk

import annotator.sqlite as sql_backend
from annotator.gui.project.navigation import current_image_name
from annotator.gui.selection import current_annotations
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.log.audit import empty_image_edit_summary
from annotator.log.audit import format_image_edit_summary
from annotator.log.audit import image_edit_summary
from annotator.log.audit import image_edit_summary_from_events


class StatusHost(Protocol):
    """Application state and widgets required by status effects."""

    root: tk.Tk
    project: ProjectState
    interaction: InteractionState
    widgets: Any
    toolbar_icons: Mapping[str, Any]
    image_index_var: tk.StringVar

# CMP: TODO - The function name should probably link this function
# specifically to navigation, or the docstring should be fixed.
def update_image_status(host: StatusHost) -> None:
    """Update image navigation status text."""

    if not host.project.image_paths:
        update_image_index_entry(host, force=True)
        total = len(host.project.all_image_paths)
        host.widgets.viewer.image_count_label.configure(
            text=f"/ 0 filtered of {total}"
        )
        if total:
            filter_name = (
                f"{host.project.active_filter} + flagged"
                if host.project.review_only
                else host.project.active_filter
            )
            host.widgets.viewer.image_status.configure(
                text=f"No images match filter: {filter_name}"
            )
        else:
            host.widgets.viewer.image_status.configure(text="No folder loaded")
        return
    update_image_index_entry(host)
    host.widgets.viewer.image_count_label.configure(
        text=(
            f"/ {len(host.project.image_paths)} filtered of "
            f"{len(host.project.all_image_paths)}"
        )
    )
    annotations = len(current_annotations(host.project))
    dirty = " *" if host.project.dirty else ""
    marked = (
        " [marked for deletion]"
        if current_image_name(host) in host.project.deletion_marks
        else ""
    )
    review = (
        " [pending review]"
        if current_image_name(host) in host.project.review_flags
        else ""
    )
    host.widgets.viewer.image_status.configure(
        text=(
            f"{current_image_name(host)} ({annotations} annotations)"
            f"{dirty}{marked}{review}"
        )
    )


def update_image_index_entry(host: StatusHost, force: bool = False) -> None:
    """Keep the jump entry synchronized without overwriting active typing."""

    if not hasattr(host, "widgets"):
        return
    focused_widget = host.root.focus_get()
    if not force and focused_widget == host.widgets.viewer.image_index_entry:
        return
    value = str(host.project.current_index + 1) if host.project.image_paths else ""
    if host.image_index_var.get() != value:
        host.image_index_var.set(value)


def update_edit_summary(host: StatusHost) -> None:
    """Show a compact audit summary for the current image."""

    if not hasattr(host, "widgets"):
        return
    if host.project.folder is None or not host.project.image_paths:
        summary = empty_image_edit_summary()
    elif host.project.sql_connection is not None:
        summary = image_edit_summary_from_events(
            sql_backend.read_audit_events(host.project.sql_connection),
            current_image_name(host),
        )
    else:
        summary = image_edit_summary(host.project.folder, current_image_name(host))
    text = format_image_edit_summary(summary)
    host.widgets.controls.summary_text.configure(state=tk.NORMAL)
    host.widgets.controls.summary_text.delete("1.0", tk.END)
    host.widgets.controls.summary_text.insert("1.0", text)
    host.widgets.controls.summary_text.configure(state=tk.DISABLED)


def update_review_controls(host: StatusHost) -> None:
    """Synchronize review button state, icon, and filter text."""

    if not hasattr(host, "widgets"):
        return
    has_loaded_images = bool(host.project.all_image_paths)
    has_visible_images = bool(host.project.image_paths)
    enabled = not host.interaction.worker_running
    flagged = (
        has_visible_images
        and current_image_name(host) in host.project.review_flags
    )
    host.widgets.toolbar.flag_review_button.configure(
        image=host.toolbar_icons["flag_off" if flagged else "flag"],
        state="normal" if enabled and has_visible_images else "disabled",
    )
    host.widgets.toolbar.view_flagged_button.configure(
        text="View all" if host.project.review_only else "View flagged",
        state="normal" if enabled and has_loaded_images else "disabled",
    )


def update_deletion_control(host: StatusHost) -> None:
    """CODEX: Synchronize the image deletion slot with pending restore state."""

    from annotator.gui.project.deletion import mark_current_image_for_deletion
    from annotator.gui.project.deletion import restore_current_image_from_trash

    has_visible_images = bool(host.project.image_paths)
    enabled = not host.interaction.worker_running
    marked = (
        has_visible_images
        and current_image_name(host) in host.project.deletion_marks
    )
    if marked:
        icon_name = "restore"
        tooltip_text = "Restore from trash"
        command = partial(restore_current_image_from_trash, host)
    else:
        icon_name = "delete"
        tooltip_text = "Delete"
        command = partial(mark_current_image_for_deletion, host)
    host.widgets.toolbar.delete_image_button.configure(
        image=host.toolbar_icons[icon_name],
        command=command,
        state=tk.NORMAL if enabled and has_visible_images else tk.DISABLED,
    )
    host.widgets.toolbar.delete_image_tooltip.set_text(tooltip_text)


def update_buttons(host: StatusHost) -> None:
    """Enable or disable controls according to current state."""

    from annotator.gui.input.state import MotionHost
    from annotator.gui.input.viewport import update_canvas_cursor

    has_loaded_images = bool(host.project.all_image_paths)
    has_visible_images = bool(host.project.image_paths)
    state = tk.DISABLED if host.interaction.worker_running else tk.NORMAL
    host.widgets.toolbar.load_button.configure(state=state)
    host.widgets.toolbar.run_button.configure(
        state=state if has_loaded_images else tk.DISABLED
    )
    host.widgets.toolbar.save_button.configure(
        state=state if has_loaded_images else tk.DISABLED
    )
    host.widgets.toolbar.archive_button.configure(
        state=state if has_loaded_images else tk.DISABLED
    )
    host.widgets.toolbar.config_button.configure(state=state)
    host.widgets.toolbar.filter_button.configure(
        state=state if has_loaded_images else tk.DISABLED
    )
    host.widgets.toolbar.filter_dropdown.configure(
        state=state if has_loaded_images else tk.DISABLED
    )
    update_deletion_control(host)
    host.widgets.toolbar.reset_zoom_button.configure(
        state=state if has_visible_images else tk.DISABLED
    )
    host.widgets.viewer.previous_button.configure(
        state=(
            tk.NORMAL
            if has_visible_images and host.project.current_index > 0
            else tk.DISABLED
        )
    )
    host.widgets.viewer.next_button.configure(
        state=(
            tk.NORMAL
            if has_visible_images
            and host.project.current_index + 1 < len(host.project.image_paths)
            else tk.DISABLED
        )
    )
    host.widgets.viewer.image_index_entry.configure(
        state=state if has_visible_images else tk.DISABLED
    )
    update_review_controls(host)
    update_canvas_cursor(cast(MotionHost, host))
