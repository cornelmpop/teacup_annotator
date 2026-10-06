"""CODEX: Own installation, persistence, recovery, and publication of model results."""

from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox
from typing import Protocol
from typing import cast

import annotator.sqlite as sql_backend
from annotator.gui.audit.events import flush_pending_audit_events
from annotator.gui.audit.undo import push_undo
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.model.worker import ModelWorkerHost
from annotator.gui.model.worker import set_model_progress
from annotator.gui.persistence import AnnotationPersistenceHost
from annotator.gui.persistence import BackupPreferenceHost
from annotator.gui.persistence import persist_all_annotations
from annotator.gui.persistence import write_json_backups_enabled
from annotator.gui.project.filtering import apply_image_filter
from annotator.gui.project.filtering import refresh_filter_options
from annotator.gui.project.image_loading import clear_view_interaction_state
from annotator.gui.project.image_loading import load_current_image
from annotator.gui.project.navigation import current_image_name
from annotator.gui.project.status import update_buttons
from annotator.gui.recovery import RecoveryHost
from annotator.gui.recovery import restore_document_from_sql
from annotator.gui.render_state import mark_annotations_changed
from annotator.gui.render_state import RenderStateHost
from annotator.gui.selection import clear_annotation_selection
from annotator.gui.state import InteractionState
from annotator.model.workflow import ModelRunResult
from annotator.project_metadata import write_project_metadata


class ModelResultHost(
    AnnotationPersistenceHost,
    BackupPreferenceHost,
    RecoveryHost,
    RenderStateHost,
    ModelWorkerHost,
    Protocol,
):
    """CODEX: Application state and effects required to publish model results."""

    root: tk.Tk
    interaction: InteractionState

    def log(self, message: str) -> None:
        """CODEX: Record one model-result message."""

        ...

# CMP: TODO - This is a long function that should list steps/logic in the docstrings
# as plainly as possible, so the evaluation of the design and the implementation can
# be conducted reasonably during review. Also, inline comments are needed here to
# lower the cognitive burden.
def finish_model_run(host: ModelResultHost, result: ModelRunResult) -> None:
    """CODEX: Replace untouched model output while retaining human-owned annotations."""

    if host.project.coco is None:
        return
    configuration = result.configuration
    push_undo(
        host,
        action="run_model",
        all_images=True,
        details={
            "annotation_count": len(result.annotations),
            "model_path": str(configuration.weights_path),
            "model_md5sum": result.model_md5sum,
            **result.provenance,
        },
    )
    project_category_ids, installed_annotations = (
        host.project.coco.replace_with_model_annotations(
            result.annotations,
            configuration.class_names,
        )
    )
    mark_annotations_changed(host)
    try:
        if host.project.sql_connection is not None:
            model_run_class_ids = sql_backend.record_model_run(
                host.project.sql_connection,
                weights_path=configuration.weights_path,
                model_md5sum=result.model_md5sum,
                model_type=configuration.model_type,
                checkpoint_model_name=configuration.checkpoint_model_name,
                checkpoint_resolution=configuration.input_resolution,
                checkpoint_class_count=configuration.num_classes,
                confidence_threshold=configuration.threshold,
                confidence_threshold_source=sql_backend.confidence_threshold_source_key(
                    configuration.threshold_source,
                    configuration.weights_path,
                ),
                preprocessing=result.provenance["input_preprocessing"],
                class_names=configuration.class_names,
                project_category_ids=project_category_ids,
                class_colours=(),
                commit=False,
            )
            for annotation in installed_annotations:
                model_class_index = int(annotation.raw["model_class_index"])
                annotation.raw["model_run_class_id"] = model_run_class_ids[
                    model_class_index
                ]
        persist_all_annotations(host, commit=False)
        flush_pending_audit_events(host)
    except sqlite3.Error as exc:
        restore_document_from_sql(host)
        host.interaction.worker_running = False
        set_model_progress(host, 0)
        update_buttons(host)
        messagebox.showerror("Could not save model results", str(exc))
        return
    try:
        if (
            write_json_backups_enabled(host)
            and host.project.sql_connection is not None
            and host.project.folder is not None
        ):
            sql_backend.save_json_backups_from_database(
                host.project.sql_connection,
                host.project.folder,
                host.project.all_image_paths,
            )
        if host.project.folder is not None:
            write_project_metadata(
                host.project.folder,
                host.project.project_metadata,
                model_weights_file=configuration.weights_path.name,
            )
    except (OSError, sqlite3.Error) as exc:
        host.log(f"Model results saved; auxiliary file write failed: {exc}")
        messagebox.showerror(
            "Model results saved, but an auxiliary file failed",
            str(exc),
        )
    host.interaction.worker_running = False
    host.project.dirty = False
    set_model_progress(host, 100)
    refresh_filter_options(host)
    preferred_name = current_image_name(host) if host.project.image_paths else None
    apply_image_filter(
        host,
        host.project.active_filter,
        preferred_image_name=preferred_name,
        load_image=False,
    )
    clear_annotation_selection(host.interaction)
    host.interaction.selected_vertices.clear()
    host.interaction.selection_rect = None
    host.interaction.merge_primary_index = None
    if host.project.image_paths:
        load_current_image(host)
    else:
        host.view.current_image = None
        clear_view_interaction_state(host)
        redraw_canvas(cast(CanvasRenderHost, host))
    update_buttons(host)
    host.log(f"Model annotations saved: {len(result.annotations)} annotations")
