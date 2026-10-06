"""Build and apply class and review filters for visible images."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol
from typing import cast

import tkinter as tk

from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.display import FILTER_ALL
from annotator.gui.display import FILTER_NULL
from annotator.gui.display import filtered_image_paths
from annotator.gui.model.settings import active_class_names
from annotator.gui.model.settings import ModelSettingsHost
from annotator.gui.project.image_loading import clear_view_interaction_state
from annotator.gui.project.image_loading import ImageLoadingHost
from annotator.gui.project.image_loading import load_current_image
from annotator.gui.project.navigation import current_image_name
from annotator.gui.project.status import update_buttons
from annotator.gui.render_state import RenderStateHost
from annotator.gui.render_state import invalidate_annotation_overlay
from annotator.gui.render_state import invalidate_display_cache


class FilteringHost(ImageLoadingHost, ModelSettingsHost, Protocol):
    """Application state and widgets required by filtering actions."""

    filter_var: tk.StringVar

# CMP: TODO - Change function name to be more specific - we may want to
#      filter on things other than class (e.g., filenames), and the name
#      of this function implies that filter would also fall under this function.
def refresh_filter_options(host: FilteringHost) -> None:
    """Refresh the class filter dropdown from document classes or preferences."""

    options = (FILTER_ALL, FILTER_NULL, *active_class_names(host))

    # CMP: TODO - Explain why deduping is necessary.
    deduped_options: list[str] = []
    for option in options:
        if option not in deduped_options:
            deduped_options.append(option)

    host.project.filter_options = tuple(deduped_options)
    if host.filter_var.get() not in host.project.filter_options:
        host.filter_var.set(FILTER_ALL)
    if not hasattr(host, "widgets"):
        return
    menu = host.widgets.toolbar.filter_dropdown["menu"]
    menu.delete(0, tk.END)
    for option in host.project.filter_options:
        menu.add_command(
            label=option,
            command=tk._setit(host.filter_var, option),
        )


def apply_selected_filter(host: FilteringHost) -> None:
    """Apply the dropdown class filter to the visible image list."""

    selected_filter = host.filter_var.get().strip() or FILTER_ALL
    current_name = current_image_name(host) if host.project.image_paths else None
    apply_image_filter(host, selected_filter, preferred_image_name=current_name)


def apply_image_filter(
    host: FilteringHost,
    selected_filter: str,
    preferred_image_name: str | None = None,
    load_image: bool = True,
) -> None:
    """Update the visible image list for a class/null/all filter."""

    if selected_filter not in host.project.filter_options:
        selected_filter = FILTER_ALL
    host.project.active_filter = selected_filter
    host.filter_var.set(selected_filter)
    image_paths = filtered_image_paths(
        host.project.all_image_paths,
        host.project.coco,
        selected_filter,
    )
    if host.project.review_only:
        image_paths = [
            path for path in image_paths if path.name in host.project.review_flags
        ]
    host.project.image_paths = image_paths
    host.project.current_index = index_for_preferred_image(
        host.project.image_paths,
        preferred_image_name,
    )
    if load_image:
        if host.project.image_paths:
            load_current_image(host)
        else:
            host.view.current_image = None
            host.photo_image = None
            clear_view_interaction_state(host)
            invalidate_display_cache(cast(RenderStateHost, host))
            invalidate_annotation_overlay(cast(RenderStateHost, host))
            redraw_canvas(cast(CanvasRenderHost, host))
            update_buttons(host)


def index_for_preferred_image(
    image_paths: list[Path],
    preferred_image_name: str | None,
) -> int:
    """Return the index of a preferred image name in an image list."""

    if preferred_image_name:
        for index, image_path in enumerate(image_paths):
            if image_path.name == preferred_image_name:
                return index
    return 0
