"""CODEX: Reset unloaded folder state and install loaded project records."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any
from typing import Protocol
from typing import cast

import annotator.sqlite as sql_backend
from annotator.coco import CocoDocument
from annotator.coco.category_helpers import is_unused_default_category
from annotator.gui.class_panel import ClassPanelHost
from annotator.gui.class_panel import refresh_class_panel
from annotator.gui.display import FILTER_ALL
from annotator.gui.display import FILTER_NULL
from annotator.gui.constants import ANNOTATION_OUTLINE
from annotator.gui.model.preferences import maybe_use_folder_model_conf
from annotator.gui.model.preferences import ModelPreferenceHost
from annotator.gui.model.settings import active_class_colours
from annotator.gui.model.settings import active_class_names
from annotator.gui.model.settings import ModelSettingsHost
from annotator.gui.project.filtering import apply_image_filter
from annotator.gui.project.filtering import FilteringHost
from annotator.gui.project.filtering import refresh_filter_options
from annotator.gui.project.image_loading import clear_view_interaction_state
from annotator.gui.project.image_loading import load_current_image
from annotator.gui.project.navigation import remembered_image_index_for_folder
from annotator.gui.project.navigation import remembered_image_name_for_folder
from annotator.gui.project.status import update_buttons
from annotator.project.paths import PROJECT_DATA_FOLDER_NAME
from annotator.gui.render_state import RenderStateHost
from annotator.gui.render_state import invalidate_annotation_overlay
from annotator.gui.render_state import invalidate_display_cache
from annotator.gui.snap_graph import invalidate_snap_graph
from annotator.project.loading import LoadedProject
from annotator.project_metadata import read_project_metadata


class FolderStateHost(FilteringHost, Protocol):
    """Application state and widgets reset when a folder unloads."""

    configuration_window: Any | None


def reset_loaded_folder_state(host: FolderStateHost) -> None:
    """CODEX: Restore the state used when no image folder is loaded."""

    host.project.folder = None
    host.project.project_metadata = read_project_metadata(None, host.prefs.values)
    host.project.all_image_paths = []
    host.project.image_paths = []
    host.project.current_index = 0
    host.project.coco = None
    host.project.sql_connection = None
    host.project.session_model_values = {}
    host.project.session_class_names = ()
    host.project.session_class_colours = ()
    host.session_default_class_var.set("")
    host.project.using_folder_model_conf = False
    host.project.using_local_class_settings = False
    host.view.current_image = None
    host.photo_image = None
    host.view.zoom = 1.0
    host.view.display_size = (0, 0)
    host.view.image_origin = (0.0, 0.0)
    host.view.annotation_revision = 0
    host.view.cursor_canvas_point = None
    host.project.undo_stack.clear()
    host.project.pending_audit_events.clear()
    host.project.next_audit_event_id = 1
    host.project.last_audit_event_id = None
    clear_view_interaction_state(host)
    host.interaction.temp_edge_insertions = []
    host.interaction.drag_vertex_ref = None
    host.interaction.drag_rectangle_side_ref = None
    host.interaction.drag_vertex_original_point = None
    host.interaction.drag_shared_vertex_refs = []
    host.interaction.drag_rectangle_context = None
    host.interaction.drag_arrow_endpoint_index = None
    host.interaction.panning = False
    host.project.arrows_by_image = {}
    host.project.annotation_orders_by_uuid = {}
    host.project.deletion_marks = set()
    host.project.session_deletion_marks = set()
    host.project.review_flags = set()
    host.project.review_only = False
    host.project.active_filter = FILTER_ALL
    host.project.filter_options = (FILTER_ALL, FILTER_NULL)
    host.filter_var.set(FILTER_ALL)
    host.project.dirty = False
    host.view.annotation_overlap_key = None
    host.view.annotation_overlap_geometry = ([], [])
    invalidate_display_cache(cast(RenderStateHost, host))
    invalidate_annotation_overlay(cast(RenderStateHost, host))
    invalidate_snap_graph(host.view)
    load_current_image(host)
    if (
        host.configuration_window is not None
        and host.configuration_window.window.winfo_exists()
    ):
        host.configuration_window.load_values(dict(host.prefs.values))
    update_buttons(host)


def install_loaded_folder_state(
    host: FolderStateHost,
    folder: Path,
    loaded: LoadedProject,
) -> None:
    """CODEX: Publish loaded database, document, and session projections.

    Native class names and order become the folder session vocabulary. A null
    SQL display colour uses the existing preference palette for display only;
    this publication step does not rewrite SQLite or ``classes.json``.
    """

    host.project.sql_connection = loaded.connection
    host.project.folder = folder
    host.project.project_metadata = loaded.plan.project_metadata
    host.project.all_image_paths = loaded.plan.discovery.image_paths
    host.project.image_paths = list(loaded.plan.discovery.image_paths)
    host.project.coco = loaded.document
    host.project.arrows_by_image = loaded.arrows_by_image
    host.project.annotation_orders_by_uuid = loaded.annotation_orders_by_uuid
    host.project.review_flags = loaded.review_flags
    host.project.deletion_marks = loaded.deletion_marks
    palette = host.prefs.get_class_colours() or (ANNOTATION_OUTLINE,)
    host.project.session_class_names = loaded.class_names
    host.project.session_class_colours = tuple(
        colour if colour is not None else palette[index % len(palette)]
        for index, colour in enumerate(loaded.class_colours)
    )
    host.project.using_local_class_settings = bool(loaded.class_names)
    host.project.next_audit_event_id = loaded.next_audit_event_id
    host.project.last_audit_event_id = (
        host.project.next_audit_event_id - 1
        if host.project.next_audit_event_id > 1
        else None
    )

# CMP: TODO - naming here is odd. The previous function is literally
#      named after the first words of this docstring, so what's the
#      difference. Clarify docstrings, also including an overview of the
#      required steps.
def finish_loaded_project(
    host: FolderStateHost,
    folder: Path,
    migration_required: bool,
    native_project_established: bool,
    initial_class_settings_selected: bool,
) -> None:
    """CODEX: Finish settings and UI publication after project installation.

    Folder model configuration remains a session choice on every load. For a
    new project only, replace an unused current or legacy default placeholder
    when no class backup was selected, ensure the resulting active classes
    exist, and persist that initial vocabulary. Established projects skip every
    class mutation because SQLite already owns names, order, and colours.
    """

    maybe_use_folder_model_conf(cast(ModelPreferenceHost, host), folder)
    class_names = active_class_names(cast(ModelSettingsHost, host))
    document = cast(CocoDocument, host.project.coco)
    connection = cast(sqlite3.Connection, host.project.sql_connection)
    if not native_project_established:
        if (
            not initial_class_settings_selected
            and is_unused_default_category(
                document.category_names(),
                any(document.annotations_by_image.values()),
            )
        ):
            document.categories = []
            host.project.session_class_names = ()
            host.project.session_class_colours = ()
            host.project.using_local_class_settings = False
            class_names = active_class_names(cast(ModelSettingsHost, host))
        for class_name in class_names:
            document.category_id_for_name(class_name)
        sql_backend.persist_classes(
            connection,
            document.categories,
            active_class_colours(cast(ModelSettingsHost, host)),
        )
    if (
        host.configuration_window is not None
        and host.configuration_window.window.winfo_exists()
    ):
        host.configuration_window.load_values(dict(host.prefs.values))
    refresh_class_panel(cast(ClassPanelHost, host))
    refresh_filter_options(host)
    apply_image_filter(
        host,
        FILTER_ALL,
        preferred_image_name=remembered_image_name_for_folder(host, folder),
        load_image=False,
    )
    if host.project.image_paths:
        host.project.current_index = remembered_image_index_for_folder(
            host,
            folder,
            host.project.image_paths,
        )
    if migration_required:
        host.log(
            "Migrated JSON annotations to "
            f"{PROJECT_DATA_FOLDER_NAME}/{sql_backend.DATABASE_FILENAME}"
        )
    host.log(f"Last folder opened: {folder}")
    load_current_image(host)
    update_buttons(host)
    host.prefs.set_path("image_folder", folder)
