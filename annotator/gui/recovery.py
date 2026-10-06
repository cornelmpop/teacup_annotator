"""Restore GUI project state from authoritative SQLite storage."""

# CMP: TODO - Clarify recovery from what.

from __future__ import annotations

from typing import Protocol

import annotator.sqlite as sql_backend
from annotator.gui.project.filtering import FilteringHost
from annotator.gui.project.filtering import refresh_filter_options
from annotator.gui.project.image_loading import load_current_image
from annotator.gui.render_state import mark_annotations_changed


class RecoveryHost(FilteringHost, Protocol):
    """Application state and effects required by authoritative recovery."""

# CMP: TODO - clarify what is meant by 'authoritative failure', and point
#      to cases that may trigger this. Also, consider changing the name
#      to restore_image_annotations or something like that.
# CODEX: mixed_selection_region_delete_reorders_arrows_2026-08-26 means this
# CODEX: recovery also reloads sparse annotation order state with the document.
def restore_document_from_sql(host: RecoveryHost) -> None:
    """Discard divergent annotation state after an authoritative failure."""

    if host.project.sql_connection is None or host.project.folder is None:
        return
    host.project.sql_connection.rollback()
    host.project.coco = sql_backend.document_from_database(
        host.project.sql_connection,
        host.project.folder,
        host.project.all_image_paths,
    )
    host.project.annotation_orders_by_uuid = sql_backend.load_annotation_orders(
        host.project.sql_connection
    )
    host.project.pending_audit_events.clear()
    mark_annotations_changed(host)
    refresh_filter_options(host)
    if host.project.image_paths:
        load_current_image(host)

# CMP: TODO - Clarify why are arrows not handled by the preceding functions, now that
#      they have been upgraded to full annotation status.
# CODEX: mixed_selection_region_delete_reorders_arrows_2026-08-26 keeps arrow
# CODEX: recovery paired with the same sparse order reload as document recovery.
def restore_arrows_from_sql(host: RecoveryHost) -> None:
    """Discard divergent arrow state after an authoritative write failure."""

    if host.project.sql_connection is not None:
        host.project.sql_connection.rollback()
        host.project.arrows_by_image = sql_backend.load_arrows(
            host.project.sql_connection
        )
        host.project.annotation_orders_by_uuid = sql_backend.load_annotation_orders(
            host.project.sql_connection
        )
    host.project.pending_audit_events.clear()
