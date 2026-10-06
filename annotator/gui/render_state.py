"""Explicit effects for annotation revisions and rendered-image caches."""

# CMP: TODO - Clarify what is meant by effects, in the module and functions' docstrings

from __future__ import annotations

from typing import Any
from typing import cast
from typing import Protocol
from typing import TYPE_CHECKING

from annotator.gui.snap_graph import invalidate_snap_graph
from annotator.gui.state import ViewState

if TYPE_CHECKING:
    from annotator.gui.class_panel import ClassPanelHost


class RenderStateHost(Protocol):
    """Application state and effects required by render-state functions."""

    view: ViewState
    annotation_overlay_key: tuple[Any, ...] | None
    annotation_overlay_photo: Any | None
    zoom_photo: Any | None
    photo_image_key: tuple[Any, ...] | None
    photo_image: Any | None


def invalidate_annotation_overlay(host: RenderStateHost) -> None:
    """Drop cached annotation fill and zoom preview images."""

    host.view.annotation_overlay_image = None
    host.annotation_overlay_key = None
    host.annotation_overlay_photo = None
    host.zoom_photo = None


def invalidate_display_cache(host: RenderStateHost) -> None:
    """Drop the cached resized main image."""

    host.photo_image_key = None
    host.photo_image = None


def mark_annotations_changed(host: RenderStateHost) -> None:
    """Refresh annotation-derived UI and invalidate dependent render state."""

    # Import after module initialization to avoid the render/panel import cycle.
    from annotator.gui.class_panel import refresh_class_panel

    host.view.annotation_revision += 1
    refresh_class_panel(cast("ClassPanelHost", host))
    invalidate_annotation_overlay(host)
    invalidate_snap_graph(host.view)
