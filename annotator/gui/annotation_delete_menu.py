"""Context-menu construction for exact and bulk annotation deletion."""

from __future__ import annotations

from functools import partial
import tkinter as tk
from typing import cast
from typing import Protocol

from annotator.coco.document import CocoDocument
from annotator.geom.polygon import area
from annotator.gui.annotation_deletion import AnnotationDeletionHost
from annotator.gui.annotation_deletion import delete_annotation_at
from annotator.gui.annotation_deletion import delete_annotation_index
from annotator.gui.annotation_deletion import delete_selected_arrows
from annotator.gui.annotation_deletion import delete_selected_annotations
from annotator.gui.menu_support import add_menu_command
from annotator.gui.menu_support import bind_menu_key
from annotator.gui.menu_support import menu_binding
from annotator.gui.menu_support import post_menu
from annotator.gui.selection import current_annotations

# CMP: TODO - do a better job of documenting why this class is needed
class AnnotationDeleteMenuHost(AnnotationDeletionHost, Protocol):
    """Application menu effects required by annotation-deletion commands."""

# CMP: TODO - Document why this is needed (i.e., so users can pick what to
# delete.
def add_annotation_delete_menu(
    host: AnnotationDeleteMenuHost,
    menu: tk.Menu,
    event: tk.Event,
    canvas_point: tuple[float, float],
    annotation_indexes: list[int],
    arrow_index: int | None,
    multi_selected: bool,
    arrow_bulk_selected: bool = False,
) -> None:
    """Add direct or overlap-aware annotation deletion to a context menu."""

    shortcut = menu_binding(host.prefs, "key_binding_delete_annotation")
    if annotation_indexes and not multi_selected:
        delete_menu = tk.Menu(menu, tearoff=0)
        annotations = current_annotations(host.project)

        # CMP: Sort by area - this often matches up with visual
        #      cues making identification of the annotation to delete easier.
        # CMP: TODO - Evaluate changing the border colour of the annotation
        #      as the user hovers over different sub-menu options.
        choices = sorted(
            (
                (index, area(annotations[index].polygons))
                for index in annotation_indexes
            ),
            key=lambda choice: choice[1],
            reverse=True,
        )

        # CMP: TODO - document 'document' and cast() here.
        document = cast(CocoDocument, host.project.coco)
        for index, pixel_area in choices:
            annotation = annotations[index]
            delete_menu.add_command(
                label=(
                    f"{document.category_name_for_id(annotation.category_id)} "
                    f"({round(pixel_area):,} px)"
                ),
                command=partial(delete_annotation_index, host, index),
            )

        menu.add_cascade(
            label="Delete",
            menu=delete_menu,
            state=tk.NORMAL,
            accelerator=shortcut,
        )

        # CMP: TODO - explain the branching here. Important.
        if len(choices) == 1:
            bind_menu_key(
                menu,
                shortcut,
                partial(delete_annotation_index, host, choices[0][0]),
            )
        else:
            bind_menu_key(
                menu,
                shortcut,
                partial(
                    post_menu,
                    delete_menu,
                    event.x_root + 18,
                    event.y_root + 18,
                ),
                close_after=False,
            )
        return

    # CMP: TODO - Explain this a bit, specifically why arrow_bulk_selected is treated
    # separately from multi-selected
    can_delete = bool(annotation_indexes) or arrow_index is not None or multi_selected
    can_delete = can_delete or arrow_bulk_selected

    # CMP: TODO - Document this a bit better. What does 'partial' do here?
    # CMP: TODO - clarify why arrows are treated separately, given they are
    # full annotations now.
    add_menu_command(
        host.prefs,
        menu,
        "Delete",
        (
            partial(delete_selected_annotations, host)
            if multi_selected
            else partial(delete_selected_arrows, host)
            if arrow_bulk_selected
            else partial(delete_annotation_at, host, canvas_point)
        ),
        "key_binding_delete_annotation",
        state=tk.NORMAL if can_delete else tk.DISABLED,
    )
