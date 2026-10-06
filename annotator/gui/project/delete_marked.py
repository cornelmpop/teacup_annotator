"""CODEX: Save-time reconciliation and movement of deletion-marked images."""

from __future__ import annotations

from tkinter import messagebox
from typing import cast

import annotator.sqlite as sql_backend
from annotator.gui.audit.events import write_audit_event
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.persistence import persist_arrows
from annotator.gui.project.deletion import DeletionHost
from annotator.gui.project.deletion import remove_deleted_images_from_state
from annotator.gui.project.filtering import apply_image_filter
from annotator.gui.project.filtering import refresh_filter_options
from annotator.gui.project.image_loading import clear_view_interaction_state
from annotator.gui.project.image_loading import load_current_image
from annotator.gui.project.navigation import current_image_name
from annotator.gui.project.status import update_buttons
from annotator.gui.render_state import invalidate_annotation_overlay
from annotator.gui.render_state import invalidate_display_cache
from annotator.log.audit import TRASH_FOLDER_NAME
from annotator.log.audit import move_image_to_trash
from annotator.log.audit import remove_moved_image_sidecars
from annotator.log.audit import save_deletion_marks
from annotator.project.paths import PROJECT_DATA_FOLDER_NAME

# CMP: TODO - The function naming is poor, as the 'maybe' implies a
# non-deterministic outcome and hides work that always happens.
# Also, fix docstring - it's not the 'deletion marks' that
# get moved to a trash folder. More importantly, the flow here is poorly documented,
# and this is a long function, so keeping track of all the branches is cognitively
# demanding - the overall logic should be made clear, so compliance can be scanned
# for efficiently in a code review, and separately from whether the logic makes sense.
# Also, place in-line comments where decisions are not
# obvious from the context of this file alone (i.e., the wider project context has to
# be considered to understand the code.
def maybe_delete_marked_images_on_save(host: DeletionHost) -> None:
    """CODEX: Ask whether saved deletion marks should be moved to folder trash."""

    if (
        host.project.folder is None
        or host.project.coco is None
        or host.project.sql_connection is None
    ):
        return

    current_name = current_image_name(host) if host.project.image_paths else None
    reconciled_names, _restored_names = sql_backend.reconcile_image_deletions(
        host.project.sql_connection,
        host.project.folder,
    )
    if reconciled_names:
        remove_deleted_images_from_state(
            host.project,
            reconciled_names,
        )
        persist_arrows(host)
        refresh_after_deleted_images(host, current_name)
    host.project.deletion_marks = sql_backend.load_pending_deletions(
        host.project.sql_connection
    )
    remove_moved_image_sidecars(
        host.project.folder,
        sql_backend.moved_image_names(host.project.sql_connection),
    )
    if not host.project.deletion_marks:
        save_deletion_marks(
            host.project.folder,
            host.project.deletion_marks,
        )
        return
    confirmed = messagebox.askyesno(
        "Delete marked images?",
        (
            f"{len(host.project.deletion_marks)} image(s) are marked for deletion.\n\n"
            f"Move them to {PROJECT_DATA_FOLDER_NAME}/{TRASH_FOLDER_NAME}/ and "
            "remove their "
            "per-image JSON backups now?"
        ),
    )
    if not confirmed:
        save_deletion_marks(
            host.project.folder,
            host.project.deletion_marks,
        )
        return

    moved_names: set[str] = set()
    try:
        for image_name in sorted(host.project.deletion_marks):
            move_image_to_trash(host.project.folder, image_name)
            sql_backend.persist_image_deletion_state(
                host.project.sql_connection,
                {image_name},
                marked_for_deletion=False,
                moved_to_trash=True,
            )
            moved_names.add(image_name)
            remove_deleted_images_from_state(
                host.project,
                {image_name},
            )
            save_deletion_marks(
                host.project.folder,
                host.project.deletion_marks,
            )
            write_audit_event(
                host,
                action="delete_marked_images",
                before_state=None,
                after_state={
                    "image_names": [image_name],
                    "trash_folder": (f"{PROJECT_DATA_FOLDER_NAME}/{TRASH_FOLDER_NAME}"),
                    "source_table": "project_images",
                },
                details={"image_names": [image_name]},
                source_table="project_images",
            )
    finally:
        if moved_names:
            refresh_after_deleted_images(host, current_name)
    persist_arrows(host)
    host.log(
        f"Moved {len(moved_names)} marked image(s) to "
        f"{PROJECT_DATA_FOLDER_NAME}/{TRASH_FOLDER_NAME}/"
    )


def refresh_after_deleted_images(
    host: DeletionHost,
    current_name: str | None,
) -> None:
    """CODEX: Refresh navigation after one or more images have reached trash."""

    refresh_filter_options(host)
    apply_image_filter(
        host,
        host.project.active_filter,
        preferred_image_name=current_name,
        load_image=False,
    )
    if host.project.image_paths:
        host.project.current_index = min(
            host.project.current_index,
            len(host.project.image_paths) - 1,
        )
        load_current_image(host)
    else:
        host.view.current_image = None
        host.photo_image = None
        clear_view_interaction_state(host)
        invalidate_display_cache(host)
        invalidate_annotation_overlay(host)
        redraw_canvas(cast(CanvasRenderHost, host))
        update_buttons(host)
