"""CODEX: Load Teacup COCO document projections from native SQLite or recovery JSON.

This module owns folder-open source selection, first-time COCO JSON import,
complete document-projection writes, and reconstruction of ``CocoDocument``
views. Once SQLite contains project-image rows, it is authoritative and JSON
files are not compared or overlaid.

Targeted edit persistence and JSON export belong to ``doc_updates``. Row-level
encoding and query projection belong to the ``json`` and ``queries`` packages.
This module also acquires exclusive loaded-project ownership through SQLite's
operating-system-backed lock. Callers own successful returned connections and
internal-writer transactions.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from annotator.arrows import ARROW_SPEC_CLASS_ID
from annotator.coco import CocoDocument
from annotator.coco.category_helpers import is_unused_default_category
from annotator.project.json_identity_migration import migrate_sqlite_json_identities
from annotator.sqlite.connect import _ensure_session
from annotator.sqlite.connect import connect_database
from annotator.sqlite.constants import ProgressCallback
from annotator.sqlite.image_identity import verify_project_image_hashes
from annotator.sqlite.json import _ensure_project_image_row
from annotator.sqlite.json import _json_dumps
from annotator.sqlite.json import _json_loads
from annotator.sqlite.json import _report_progress
from annotator.sqlite.json import _synchronize_region_annotations_for_image
from annotator.sqlite.json import _upsert_class_rows
from annotator.sqlite.queries import _annotations_from_database
from annotator.sqlite.queries import _categories_from_database
from annotator.sqlite.queries import _coco_info_json
from annotator.sqlite.queries import _image_records_from_database
from annotator.sqlite.queries import _set_coco_info_json
from annotator.sqlite.queries import database_has_document
from annotator.sqlite.schema import ensure_schema
from annotator.sqlite.time import _unix_time


def load_or_import_document(
    folder: Path,
    image_paths: list[Path],
    class_colours: tuple[str, ...] = (),
    initial_class_settings: tuple[tuple[str, ...], tuple[str, ...]] | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[CocoDocument, sqlite3.Connection]:
    """CODEX: Return the current document view and an open SQLite connection.

    ``image_paths`` supplies the ordered source-image set for both projections.
    The function opens or creates the folder database, prepares the schema, and
    ensures this process's session row. If any project-image row exists, SQLite
    is authoritative: source hashes are verified and a region-only
    ``CocoDocument`` is reconstructed without reading or overlaying JSON.

    An empty SQL document is instead initialized from the normal COCO loader,
    including the project-root and per-image recovery files. Optional initial
    class settings are applied only on this empty-document path, before the
    imported vocabulary is first written to SQLite. ``class_colours`` supplies
    display colours for imported categories not named by those settings. The
    optional progress callback receives the established folder-load stages.

    Both successful paths return the connection open for the caller and leave
    schema/session preparation or the complete import committed. The returned
    connection retains exclusive loaded-project ownership until the caller
    closes it. Any exception closes the connection created here and propagates
    unchanged.
    """

    connection: sqlite3.Connection | None = None
    try:
        _report_progress(progress, 5, "Opening SQLite database")
        opened_connection: sqlite3.Connection = connect_database(folder)
        connection = opened_connection
        # CODEX: Retain SQLite's OS-backed lock for this loaded document's lifetime.
        opened_connection.execute("PRAGMA main.locking_mode = EXCLUSIVE")
        opened_connection.execute("BEGIN EXCLUSIVE")
        opened_connection.rollback()
        _report_progress(progress, 15, "Preparing SQLite schema")
        ensure_schema(opened_connection)
        _ensure_session(opened_connection)
        migrate_sqlite_json_identities(opened_connection)
        # CODEX: Once any project image exists, SQL is authoritative; recovery JSON
        # CODEX: is neither compared nor overlaid during normal folder opens.
        if database_has_document(opened_connection):
            _report_progress(progress, 45, "Verifying source image checksums")
            verify_project_image_hashes(opened_connection, image_paths)
            opened_connection.commit()
            _report_progress(progress, 75, "Loading annotations from SQLite")
            document = document_from_database(opened_connection, folder, image_paths)
            _report_progress(progress, 100, "SQLite annotations loaded")
            return document, opened_connection

        # CODEX: An empty SQL document is the sole gateway to recovery JSON import.
        _report_progress(progress, 35, "Reading existing JSON annotations")
        document = CocoDocument.load(folder, image_paths)
        imported_class_colours = _apply_initial_class_settings(
            document,
            class_colours,
            initial_class_settings,
        )
        _report_progress(progress, 70, "Migrating annotations to SQLite")
        replace_database_from_document(
            opened_connection,
            document,
            imported_class_colours,
        )
        _report_progress(progress, 100, "SQLite migration complete")
        return document, opened_connection
    except Exception:
        if connection is not None:
            connection.close()
        raise


def _apply_initial_class_settings(
    document: CocoDocument,
    default_colours: tuple[str, ...],
    settings: tuple[tuple[str, ...], tuple[str, ...]] | None,
) -> tuple[str, ...]:
    """CODEX: Apply a new project's selected class backup before SQL import.

    Return one display colour per resulting category. Without selected settings,
    the document and supplied preference palette pass through unchanged. With
    settings, their names lead the category list, existing category IDs and
    metadata are retained, and categories required by imported annotations
    remain as extras. An unused current or legacy default placeholder is
    discarded because it is setup state rather than project data.

    Selected colours follow their names. Extra imported categories use the
    caller's cyclic preference palette; an empty palette leaves their database
    colour null through the existing SQLite writer contract.
    """

    if settings is None:
        return default_colours
    class_names, class_colours = settings
    if is_unused_default_category(
        document.category_names(),
        any(document.annotations_by_image.values()),
    ):
        document.categories = []

    category_by_name = {
        category.get("name"): category for category in document.categories
    }
    ordered_categories: list[dict[str, Any]] = []
    for class_name in class_names:
        category = category_by_name.get(class_name)
        if category is None:
            document.category_id_for_name(class_name)
            category = document.categories[-1]
        ordered_categories.append(category)
    ordered_categories.extend(
        category
        for category in document.categories
        if category.get("name") not in class_names
    )
    document.categories = ordered_categories

    selected_colours = dict(zip(class_names, class_colours))
    return tuple(
        selected_colours.get(
            category.get("name"),
            (
                default_colours[index % len(default_colours)]
                if default_colours
                else ""
            ),
        )
        for index, category in enumerate(document.categories)
    )


def replace_database_from_document(
    connection: sqlite3.Connection,
    document: CocoDocument,
    class_colours: tuple[str, ...] = (),
) -> None:
    """CODEX: Replace the complete SQL document projection and commit it.

    This recovery/import operation deletes every generic annotation row,
    including arrows, together with project images, annotation classes, and
    stored COCO info before writing ``document``. Session, model-run, and
    UUID-based audit-history tables are not reset.

    The function owns the final commit. Normal completed edits must use targeted
    persistence instead so they do not discard Teacup-only state. SQLite and
    projection errors propagate to the caller's existing load boundary.
    """

    ensure_schema(connection)
    _clear_annotation_tables(connection)
    _write_document_rows(connection, document, class_colours)
    connection.commit()


def _write_document_rows(
    connection: sqlite3.Connection,
    document: CocoDocument,
    class_colours: tuple[str, ...] = (),
) -> None:
    """CODEX: Write a complete document projection in the caller's transaction.

    Materialize the document's COCO view, store top-level info, ensure the
    current process session, synchronize region classes, and reconcile region
    rows for every image in ``document.image_paths`` order. Existing arrow rows
    and unchanged region-row identities survive image-level synchronization.

    This helper neither clears unrelated rows, commits, nor writes JSON
    backups. Import and global-persistence callers own those surrounding
    operations.
    """

    document.to_payload()
    _set_coco_info_json(connection, _json_dumps(document.info), _unix_time())
    session_id = _ensure_session(connection)
    class_id_by_category_id = _upsert_class_rows(
        connection,
        document.categories,
        class_colours,
    )
    for image_index, image_path in enumerate(document.image_paths):
        project_image = _ensure_project_image_row(
            connection,
            document,
            image_path,
            image_index,
        )
        _synchronize_region_annotations_for_image(
            connection,
            document,
            image_path.name,
            int(project_image["image_id"]),
            session_id,
            class_id_by_category_id,
        )
    _delete_unused_classes(connection, document.categories)


def document_from_database(
    connection: sqlite3.Connection,
    folder: Path,
    image_paths: list[Path],
) -> CocoDocument:
    """CODEX: Reconstruct a region-only document for the ordered image paths.

    Read region classes, current image records, polygon/rectangle rows, and the
    stored top-level COCO info into a fresh ``CocoDocument``. ``image_paths``
    determines the returned scope and order; each supplied path must already
    have a ``project_images`` row.

    Arrow annotations, review flags, deletion state, sessions, and audit data
    remain outside the COCO document view. A missing or non-object info value
    receives the standard description. Hash verification belongs to
    ``load_or_import_document`` rather than this projection helper.
    """

    ensure_schema(connection)
    categories = _categories_from_database(connection)
    image_records = _image_records_from_database(connection, image_paths)
    annotations = _annotations_from_database(connection, image_records)
    info = _json_loads(_coco_info_json(connection), {})
    if not isinstance(info, dict):
        info = {}
    info.setdefault("description", "Image annotations")
    payload: dict[str, Any] = {
        "info": info,
        "images": list(image_records.values()),
        "annotations": annotations,
        "categories": categories,
    }
    return CocoDocument(folder, image_paths, payload)


def _clear_annotation_tables(connection: sqlite3.Connection) -> None:
    """CODEX: Delete the complete COCO projection before recovery import.

    Remove generic annotation rows (regions and arrows), project-image rows,
    visible annotation classes, and the singleton COCO-info row in
    foreign-key-safe order. Sessions, model-run records, UUID-based audit
    history, and the reserved hidden arrow class remain.

    This helper does not commit; the recovery import owns the surrounding
    transaction and replacement write.
    """

    # CODEX: The delete order follows native foreign keys from leaves back to
    # CODEX: roots while preserving sessions, audit rows, and model-run provenance.
    for table_name in (
        "annotations",
        "project_images",
        "coco_info",
    ):
        connection.execute(f"DELETE FROM {table_name}")
    connection.execute(
        """
        DELETE FROM annotation_classes
        WHERE class_id <> ?
        """,
        (ARROW_SPEC_CLASS_ID,),
    )


def _delete_unused_classes(
    connection: sqlite3.Connection,
    categories: list[dict[str, Any]],
) -> None:
    """CODEX: Remove unreferenced region classes absent from the document.

    COCO category IDs define the retained region vocabulary. A class also
    remains when any live annotation references it, even if the current
    category list omits it. An empty category list removes every unreferenced
    region class, while keypoint/arrow classes are never candidates.

    This helper mutates only the caller's current transaction and does not
    commit.
    """

    category_ids = [int(category.get("id", 0)) for category in categories]
    placeholders = ",".join("?" for _ in category_ids)
    category_filter = (
        f"AND coco_category_id NOT IN ({placeholders})" if category_ids else ""
    )
    connection.execute(
        f"""
        DELETE FROM annotation_classes
        WHERE annotation_family = 'region'
        {category_filter}
        AND class_id NOT IN (
            SELECT class_id FROM annotations WHERE class_id IS NOT NULL
        )
        """,
        category_ids,
    )
