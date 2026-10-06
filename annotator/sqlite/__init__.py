"""CODEX: Public SQLite backend API for Teacup Annotator.

The implementation lives in focused submodules within this package. This
package root is the storage API used by GUI controllers and tests, while the
split files keep connection, schema, document writes, JSON migration, queries,
and audit logic reviewable in smaller units.
"""

from __future__ import annotations

from annotator.sqlite.annotations import document_from_database
from annotator.sqlite.annotations import load_or_import_document
from annotator.sqlite.annotations import replace_database_from_document
from annotator.sqlite.audit import append_audit_event
from annotator.sqlite.audit import append_log_entry
from annotator.sqlite.audit import import_audit_events_if_empty
from annotator.sqlite.audit import next_audit_event_id
from annotator.sqlite.audit import read_audit_events
from annotator.sqlite.connect import connect_database
from annotator.sqlite.connect import current_session_id
from annotator.sqlite.constants import DATABASE_FILENAME
from annotator.sqlite.constants import ProgressCallback
from annotator.sqlite.deletion import moved_image_names
from annotator.sqlite.deletion import reconcile_folder_image_deletions
from annotator.sqlite.deletion import reconcile_image_deletions
from annotator.sqlite.doc_updates import persist_annotations
from annotator.sqlite.doc_updates import persist_classes
from annotator.sqlite.doc_updates import persist_document
from annotator.sqlite.doc_updates import persist_image
from annotator.sqlite.doc_updates import persist_image_deletion_state
from annotator.sqlite.doc_updates import persist_image_review_flag
from annotator.sqlite.doc_updates import persist_arrows
from annotator.sqlite.doc_updates import save_json_backups_from_database
from annotator.sqlite.image_identity import image_md5sum
from annotator.sqlite.image_identity import verify_project_image_hashes
from annotator.sqlite.image_reconciliation import apply_folder_image_reconciliation
from annotator.sqlite.image_reconciliation import FolderImageReconciliation
from annotator.sqlite.image_reconciliation import inspect_folder_image_reconciliation
from annotator.sqlite.json import json_migration_required
from annotator.sqlite.json import json_sources_exist
from annotator.sqlite.json import native_project_established
from annotator.sqlite.model import confidence_threshold_source_key
from annotator.sqlite.model import record_model_run
from annotator.sqlite.queries import database_has_document
from annotator.sqlite.queries import load_annotation_orders
from annotator.sqlite.queries import load_pending_deletions
from annotator.sqlite.queries import load_arrows
from annotator.sqlite.queries import load_region_class_settings
from annotator.sqlite.queries import load_review_flags
from annotator.sqlite.schema import ensure_schema

__all__ = [
    "DATABASE_FILENAME",
    "ProgressCallback",
    "append_audit_event",
    "append_log_entry",
    "apply_folder_image_reconciliation",
    "confidence_threshold_source_key",
    "connect_database",
    "current_session_id",
    "database_has_document",
    "document_from_database",
    "ensure_schema",
    "FolderImageReconciliation",
    "image_md5sum",
    "inspect_folder_image_reconciliation",
    "import_audit_events_if_empty",
    "json_migration_required",
    "json_sources_exist",
    "load_annotation_orders",
    "load_or_import_document",
    "load_pending_deletions",
    "load_arrows",
    "load_region_class_settings",
    "load_review_flags",
    "moved_image_names",
    "native_project_established",
    "next_audit_event_id",
    "persist_annotations",
    "persist_classes",
    "persist_document",
    "persist_image",
    "persist_image_deletion_state",
    "persist_image_review_flag",
    "persist_arrows",
    "read_audit_events",
    "reconcile_folder_image_deletions",
    "reconcile_image_deletions",
    "record_model_run",
    "replace_database_from_document",
    "save_json_backups_from_database",
    "verify_project_image_hashes",
]
