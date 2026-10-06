"""Own canvas context-menu orchestration."""

from __future__ import annotations

from functools import partial
import tkinter as tk
from typing import cast
from typing import Protocol

from annotator.coco.type_helpers import annotation_export_type
from annotator.gui.annotation_delete_menu import AnnotationDeleteMenuHost
from annotator.gui.annotation_delete_menu import add_annotation_delete_menu
from annotator.gui.annotation_merging import AnnotationMergingHost
from annotator.gui.annotation_merging import merge_selected_annotations
from annotator.gui.annotation_merging import start_merge_annotation_at
from annotator.gui.annotation_modes import resample_outline_enabled
from annotator.gui.annotation_resampling import AnnotationResamplingHost
from annotator.gui.annotation_resampling import resample_selected_annotations
from annotator.gui.annotation_resampling import simplify_annotation_at
from annotator.gui.arrow_editing import ArrowEditingHost
from annotator.gui.arrow_editing import start_draw_arrow
from annotator.gui.arrow_interaction import ArrowInteractionHost
from annotator.gui.arrow_interaction import arrow_index_at
from annotator.gui.context_menu_sections import ContextMenuSectionHost
from annotator.gui.context_menu_sections import build_change_class_menu
from annotator.gui.context_menu_sections import build_new_annotation_menu
from annotator.gui.hit_testing import annotation_indexes_at
from annotator.gui.menu_support import add_menu_cascade
from annotator.gui.menu_support import add_menu_command
from annotator.gui.menu_support import bind_menu_key
from annotator.gui.menu_support import menu_binding
from annotator.gui.menu_support import post_menu
from annotator.gui.polygon_start import PolygonStartHost
from annotator.gui.polygon_start import start_select_start_at
from annotator.gui.selection import current_annotations
from annotator.gui.selection import multiple_arrows_selected
from annotator.gui.selection import multiple_annotations_selected
from annotator.gui.selection import selected_annotation_indexes
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.gui.state import ViewState
from annotator.gui.view_geometry import canvas_event_point
from annotator.gui.view_geometry import image_point_from_canvas
from annotator.gui.window.state import WindowWidgets
from annotator.gui.audit.undo import UndoHost
from annotator.gui.audit.undo import undo
from annotator.preferences import Preferences


class ContextMenuHost(ContextMenuSectionHost, Protocol):
    """Application state and effects required by annotation context menus."""

    root: tk.Tk
    prefs: Preferences
    project: ProjectState
    view: ViewState
    interaction: InteractionState
    widgets: WindowWidgets
    autoclose_var: tk.BooleanVar


def show_canvas_menu(host: ContextMenuHost, event: tk.Event) -> None:
    """Open the image viewer context menu for the current pointer target."""

    canvas_point = canvas_event_point(host.widgets.viewer.canvas, event)
    image_point = image_point_from_canvas(canvas_point, host.view)
    annotations = current_annotations(host.project)
    annotation_indexes = (
        annotation_indexes_at(annotations, image_point)
        if image_point is not None
        else []
    )
    annotation_index = annotation_indexes[-1] if annotation_indexes else None

    # CMP: TODO - Clarify what happens with multiple overlapping arrows. The
    #      terminology here implies only a single arrow is possible, but that
    #      changes in the next few lines.
    arrow_index = (
        arrow_index_at(cast(ArrowInteractionHost, host), image_point)
        if image_point is not None
        else None
    )
    multi_selected = multiple_annotations_selected(host.interaction)
    arrow_rect_selected = bool(host.interaction.selected_arrow_indices)
    arrow_bulk_selected = multiple_arrows_selected(host.interaction)
    bulk_selected = multi_selected or arrow_bulk_selected
    can_edit_annotation = annotation_index is not None or multi_selected
    resample_indexes = selected_annotation_indexes(host.project, host.interaction)
    if not multi_selected:
        resample_indexes = [annotation_index] if annotation_index is not None else []
    can_resample = any(
        annotation_export_type(annotations[index]) != "rectangle"
        for index in resample_indexes
    )
    can_start_new = not bulk_selected
    can_select_start = annotation_index is not None and not bulk_selected
    menu = tk.Menu(host.root, tearoff=0)
    new_menu = build_new_annotation_menu(host, menu, can_start_new)
    class_menu = build_change_class_menu(
        host,
        menu,
        canvas_point,
        can_edit_annotation,
    )
    undo_enabled = bool(host.project.undo_stack) and not bulk_selected
    menu.add_command(
        label="Undo last action",
        command=partial(undo, cast(UndoHost, host)),
        state=tk.NORMAL if undo_enabled else tk.DISABLED,
    )
    bind_menu_key(
        menu,
        menu_binding(host.prefs, "key_binding_undo"),
        partial(undo, cast(UndoHost, host)),
        enabled=undo_enabled,
    )
    add_menu_cascade(
        host.prefs,
        menu,
        "New annotation",
        new_menu,
        "key_binding_new_annotation",
        event,
        state=tk.NORMAL if can_start_new else tk.DISABLED,
    )

    # CMP: TODO - clarify why arrow_index treated differently here.
    add_annotation_delete_menu(
        cast(AnnotationDeleteMenuHost, host),
        menu,
        event,
        canvas_point,
        annotation_indexes,
        arrow_index,
        multi_selected,
        arrow_rect_selected,
    )
    add_menu_command(
        host.prefs,
        menu,
        "Merge",
        lambda: (
            merge_selected_annotations(cast(AnnotationMergingHost, host))
            if multi_selected
            else start_merge_annotation_at(
                cast(AnnotationMergingHost, host),
                canvas_point,
            )
        ),
        "key_binding_merge_annotation",
        state=tk.NORMAL if can_edit_annotation else tk.DISABLED,
    )
    add_menu_command(
        host.prefs,
        menu,
        "Resample outline",
        lambda: (
            resample_selected_annotations(
                cast(AnnotationResamplingHost, host)
            )
            if multi_selected
            else simplify_annotation_at(
                cast(AnnotationResamplingHost, host),
                canvas_point,
            )
        ),
        "key_binding_simplify_polygon",
        state=(
            tk.NORMAL
            if resample_outline_enabled(host, can_resample)
            else tk.DISABLED
        ),
    )
    add_menu_command(
        host.prefs,
        menu,
        "Select start",
        partial(
            start_select_start_at,
            cast(PolygonStartHost, host),
            canvas_point,
        ),
        "key_binding_select_start",
        state=tk.NORMAL if can_select_start else tk.DISABLED,
        fallback_key="",
    )
    add_menu_command(
        host.prefs,
        menu,
        "Draw arrow",
        partial(start_draw_arrow, cast(ArrowEditingHost, host)),
        "key_binding_draw_arrow",
        state=(
            tk.NORMAL
            if host.view.current_image is not None and not bulk_selected
            else tk.DISABLED
        ),
    )
    add_menu_cascade(
        host.prefs,
        menu,
        "Change class",
        class_menu,
        "key_binding_change_class",
        event,
        state=tk.NORMAL if can_edit_annotation else tk.DISABLED,
    )
    post_menu(menu, event.x_root, event.y_root)
