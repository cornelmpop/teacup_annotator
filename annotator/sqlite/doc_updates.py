"""CODEX: Synchronize Teacup's editable annotation state with native SQLite.

SQLite is the authoritative project store. This module provides the write
boundaries used for a complete active document, one image, selected regions,
the project class vocabulary, arrows, and image workflow flags. Row encoding
and low-level query projection belong to the ``json`` and ``queries`` modules.

Callers choose whether a write commits immediately or remains in a larger
transaction with its audit event. Optional COCO JSON files are backup
projections written after SQL work; they cannot participate in the SQLite
transaction. A filesystem error can therefore leave earlier backup files
refreshed and later ones stale even though authoritative SQL remains valid.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from annotator.arrows import ARROW_SPEC_CLASS_ID
from annotator.arrows import Arrow
from annotator.coco import CocoDocument
from annotator.sqlite.annotation_order import annotation_orders_for_image
from annotator.sqlite.annotation_order import arrow_annotation_orders
from annotator.sqlite.annotation_order import discard_annotation_orders
from annotator.sqlite.annotation_order import order_for_annotation_uuid
from annotator.sqlite.annotations import _delete_unused_classes
from annotator.sqlite.annotations import document_from_database
from annotator.sqlite.connect import _ensure_session
from annotator.sqlite.constants import ProgressCallback
from annotator.sqlite.json import _ensure_project_image_row
from annotator.sqlite.json import _json_dumps
from annotator.sqlite.json import _report_progress
from annotator.sqlite.json import _synchronize_region_annotations_for_image
from annotator.sqlite.json import _upsert_class_rows
from annotator.sqlite.json import _upsert_region_annotation
from annotator.sqlite.json.components import _annotation_uuid
from annotator.sqlite.queries import _image_index_for_name
from annotator.sqlite.queries import _image_path_for_name
from annotator.sqlite.queries import _set_coco_info_json
from annotator.sqlite.region_synchronization import _synchronize_document_regions
from annotator.sqlite.schema import ensure_schema
from annotator.sqlite.time import _unix_time


def persist_document(
    connection: sqlite3.Connection,
    document: CocoDocument,
    write_json_backups: bool = True,
    class_colours: tuple[str, ...] = (),
    commit: bool = True,
    annotation_orders_by_uuid: dict[str, int] | None = None,
) -> None:
    """CODEX: Synchronize the active document's complete region projection.

    This operation is used after accepted model output and all-image Undo,
    where regions may change across multiple active images. It reconciles
    polygon and rectangle rows by durable UUID rather than deleting the
    project-wide region table. UUIDs absent from active images are removed,
    new or changed UUIDs are written, and unchanged rows retain their database
    identity and creation metadata.

    Arrow rows, project-image identities, review and deletion flags, sessions,
    audit history, model-run records, and regions belonging to images outside
    the active document remain intact. Stored annotation order is preserved by
    UUID; newly introduced UUIDs are appended after the image's current maximum
    order.

    With ``commit=False``, the SQL changes remain in the caller's transaction
    so the corresponding audit event can commit atomically with them. JSON
    backup generation requires ``commit=True`` because filesystem output
    cannot join the SQLite transaction. A later backup failure does not roll
    back authoritative SQL and may leave a partially refreshed backup set.
    """

    ensure_schema(connection)
    _synchronize_document_regions(
        connection,
        document,
        class_colours,
        annotation_orders_by_uuid,
    )
    if commit:
        connection.commit()
    if write_json_backups:
        if not commit:
            raise ValueError("JSON backups require a committed SQLite document")
        save_json_backups_from_database(
            connection,
            document.folder,
            document.image_paths,
        )


def persist_classes(
    connection: sqlite3.Connection,
    categories: list[dict[str, Any]],
    class_colours: tuple[str, ...] = (),
) -> None:
    """CODEX: Synchronize and commit the project region-class vocabulary.

    Upsert the supplied COCO categories and display colours, then remove only
    omitted region classes that no live annotation references. Image rows,
    annotations, model runs, and arrow classes are not changed. This dedicated
    boundary commits before returning because its current callers perform a
    complete class-list save rather than composing an audit transaction.
    """

    ensure_schema(connection)
    _upsert_class_rows(connection, categories, class_colours)
    _delete_unused_classes(connection, categories)
    connection.commit()


def save_json_backups_from_database(
    connection: sqlite3.Connection,
    folder: Path,
    image_paths: list[Path],
    progress: ProgressCallback | None = None,
) -> None:
    """CODEX: Refresh COCO JSON backup files from authoritative SQLite state.

    Reconstruct one region-only document for ``image_paths``, write each
    per-image backup, then write the combined and type-specific COCO files.
    Progress reports cover the read, per-image output, combined output, and
    completion stages.

    The files are replaced independently rather than as one atomic set. If an
    output fails, files written earlier in the sequence can reflect newer SQL
    state while files not yet reached remain older. The exception propagates;
    no SQL data is rolled back because these files are recovery mirrors rather
    than the authoritative store.
    """

    _report_progress(progress, 5, "Reading saved annotations from SQLite")
    document = document_from_database(connection, folder, image_paths)
    document.save_all_images(
        lambda completed, total: _report_progress(
            progress,
            10 + int(75 * completed / max(1, total)),
            f"Writing JSON backup {completed} of {total}",
        )
    )
    _report_progress(progress, 90, "Writing combined JSON backups")
    document.save()
    _report_progress(progress, 100, "JSON backups complete")


def persist_image(
    connection: sqlite3.Connection,
    document: CocoDocument,
    image_name: str,
    write_json_backup: bool = True,
    class_colours: tuple[str, ...] = (),
    commit: bool = True,
    annotation_orders_by_uuid: dict[str, int] | None = None,
    human_edit: bool = False,
) -> Path | None:
    """CODEX: Reconcile one image's complete region projection in SQLite.

    Normal autosave uses this boundary after an edit can delete, add, reorder,
    or change any region on the current image. A UUID delta makes in-memory
    absence authoritative without scanning the rest of the project, preserves
    unchanged row identity and creation metadata, and updates changed rows in
    place. Sparse image-local order keeps reloaded visual stacking equal to the
    edited in-memory document without rewriting non-region rows.

    ``human_edit`` promotes only actually changed, surviving model-linked rows
    to manual source. A restoration or model-owned caller leaves it false so
    the source present in its document is persisted exactly.

    ``commit=False`` leaves the SQL change open so the caller can record and
    commit the associated audit event in the same transaction. When
    ``write_json_backup`` is true, the per-image backup is written separately
    and its path is returned; otherwise the return value is ``None``. Callers
    composing an uncommitted SQL transaction must disable that filesystem
    output because JSON cannot share SQLite's rollback boundary.
    """

    ensure_schema(connection)
    document.ensure_image_records()
    document.normalize_image_polygons(image_name)
    _set_coco_info_json(connection, _json_dumps(document.info), _unix_time())
    session_id = _ensure_session(connection)
    class_id_by_category_id = _upsert_class_rows(
        connection,
        document.categories,
        class_colours,
    )
    image_path = _image_path_for_name(document, image_name)
    image_index = _image_index_for_name(document, image_name)
    project_image = _ensure_project_image_row(
        connection,
        document,
        image_path,
        image_index,
    )
    _synchronize_region_annotations_for_image(
        connection,
        document,
        image_name,
        int(project_image["image_id"]),
        session_id,
        class_id_by_category_id,
        annotation_orders_by_uuid,
        human_edit,
    )
    if commit:
        connection.commit()
    if write_json_backup:
        return document.save_image(image_name)
    return None


def persist_annotations(
    connection: sqlite3.Connection,
    document: CocoDocument,
    image_name: str,
    annotation_indices: list[int],
    write_json_backup: bool = True,
    class_colours: tuple[str, ...] = (),
    commit: bool = True,
    annotation_orders_by_uuid: dict[str, int] | None = None,
    human_edit: bool = False,
) -> Path | None:
    """CODEX: Store selected region updates inside a larger image save.

    Deduplicate and sort ``annotation_indices``, ignore indices outside the
    current image list, and upsert only the referenced polygon or rectangle
    rows. This targeted path is appropriate when the caller knows an operation
    changed existing annotations without deleting others; deletion and broad
    reordering require ``persist_image`` instead. Shared COCO info, categories,
    and the project-image row are synchronized as part of the image-level
    projection. Existing annotation order is preserved by UUID, and new UUIDs
    are appended after the image's current maximum order.

    The function exists as the inner SQL portion of a larger save: with
    ``commit=False``, the caller can append the matching audit event and commit
    both effects atomically. A requested per-image JSON backup is external to
    that transaction and returns its path; disabling it returns ``None``.

    ``human_edit`` applies manual source only when the conditional upsert writes
    a model-linked row. Merely including an unchanged index does not change its
    provenance.
    """

    ensure_schema(connection)
    document.ensure_image_records()
    document.normalize_image_polygons(image_name)
    _set_coco_info_json(connection, _json_dumps(document.info), _unix_time())
    session_id = _ensure_session(connection)
    class_id_by_category_id = _upsert_class_rows(
        connection,
        document.categories,
        class_colours,
    )
    image_path = _image_path_for_name(document, image_name)
    image_index = _image_index_for_name(document, image_name)
    project_image = _ensure_project_image_row(
        connection,
        document,
        image_path,
        image_index,
    )
    annotations = document.annotations_for(image_name)
    image_id = int(project_image["image_id"])
    stored_orders = annotation_orders_for_image(connection, image_id)
    reserved_orders = set(stored_orders.values())
    for annotation_index in sorted(set(annotation_indices)):
        if not (0 <= annotation_index < len(annotations)):
            continue
        annotation = annotations[annotation_index]
        annotation_uuid = _annotation_uuid(annotation.raw)
        annotation.raw["annotation_uuid"] = annotation_uuid
        annotation_order = order_for_annotation_uuid(
            connection,
            image_id,
            annotation_uuid,
            stored_orders,
            annotation_orders_by_uuid,
            reserved_orders,
        )
        _upsert_region_annotation(
            connection,
            document,
            annotation,
            image_id,
            session_id,
            class_id_by_category_id,
            annotation_order=annotation_order,
            human_edit=human_edit,
        )
    if commit:
        connection.commit()
    if write_json_backup:
        return document.save_image(image_name)
    return None


def persist_arrows(
    connection: sqlite3.Connection,
    arrows_by_image: dict[str, list[Arrow]],
    commit: bool = True,
    annotation_orders_by_uuid: dict[str, int] | None = None,
) -> None:
    """CODEX: Reconcile the project-wide arrow projection by durable UUID.

    The GUI edits arrows as image-local ordered lists while SQLite stores them
    as generic annotation rows. ``arrows_by_image`` is the complete durable
    projection, including hidden entries for images moved to trash. Stored UUIDs
    absent from that mapping are deleted, new UUIDs are inserted, changed rows
    are updated in place, and matching rows are left untouched. Existing rows
    retain their database identity, creation session, and entry time.

    Every referenced image name must already exist in ``project_images``
    because arrows use the stable image row rather than filename text. Existing
    arrow orders are preserved by UUID, while previously unseen arrows are
    appended after their image's current maximum stored order. With
    ``commit=True`` the reconciliation is committed; otherwise the caller owns
    the surrounding transaction and its corresponding audit event.
    """

    ensure_schema(connection)
    now = _unix_time()
    session_id = _ensure_session(connection)
    arrow_class_id = ARROW_SPEC_CLASS_ID
    stored_arrow_orders = arrow_annotation_orders(connection)
    current_arrow_uuids = {
        arrow.arrow_uuid for arrows in arrows_by_image.values() for arrow in arrows
    }
    stale_arrow_uuids = set(stored_arrow_orders) - current_arrow_uuids
    discard_annotation_orders(
        annotation_orders_by_uuid,
        stale_arrow_uuids,
    )
    image_contexts: dict[str, tuple[int, dict[str, int]]] = {}
    for image_name in sorted(arrows_by_image):
        row = connection.execute(
            """
            SELECT image_id
            FROM project_images
            WHERE image_name = ?
            """,
            (image_name,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Arrow image is not loaded in SQLite: {image_name}")
        image_id = row["image_id"]
        image_contexts[image_name] = (
            image_id,
            annotation_orders_for_image(connection, image_id),
        )

    # CODEX: Delete stale arrows before allocating new mixed-order slots so
    # CODEX: removed UUIDs release their image-local positions.
    connection.executemany(
        "DELETE FROM annotations WHERE annotation_uuid = ?",
        [(annotation_uuid,) for annotation_uuid in sorted(stale_arrow_uuids)],
    )
    for image_name in sorted(arrows_by_image):
        image_id, stored_orders = image_contexts[image_name]
        current_orders = annotation_orders_for_image(connection, image_id)
        reserved_orders = set(current_orders.values())
        for arrow in arrows_by_image[image_name]:
            annotation_order = order_for_annotation_uuid(
                connection,
                image_id,
                arrow.arrow_uuid,
                stored_orders,
                annotation_orders_by_uuid,
                reserved_orders,
            )
            geometry_json = _json_dumps(
                {
                    "points": [
                        [arrow.start_x, arrow.start_y],
                        [arrow.end_x, arrow.end_y],
                    ],
                    "labels": ["base", "tip"],
                }
            )
            metadata_json = _json_dumps(
                {
                    "arrow_uuid": arrow.arrow_uuid,
                    "start_x": arrow.start_x,
                    "start_y": arrow.start_y,
                    "end_x": arrow.end_x,
                    "end_y": arrow.end_y,
                }
            )
            # CODEX: Keep update and insert separate so matching UUIDs neither
            # CODEX: rewrite their rows nor consume an autoincrement value.
            if arrow.arrow_uuid in stored_arrow_orders:
                connection.execute(
                    """
                    UPDATE annotations
                    SET image_id = ?,
                        class_id = ?,
                        annotation_order = ?,
                        geometry_json = ?,
                        annotation_source = 'manual',
                        metadata_json = ?
                    WHERE annotation_uuid = ?
                      AND (
                          image_id IS NOT ?
                          OR class_id IS NOT ?
                          OR annotation_order IS NOT ?
                          OR geometry_json IS NOT ?
                          OR annotation_source IS NOT 'manual'
                          OR metadata_json IS NOT ?
                      )
                    """,
                    (
                        image_id,
                        arrow_class_id,
                        annotation_order,
                        geometry_json,
                        metadata_json,
                        arrow.arrow_uuid,
                        image_id,
                        arrow_class_id,
                        annotation_order,
                        geometry_json,
                        metadata_json,
                    ),
                )
                continue

            connection.execute(
                """
                INSERT INTO annotations(
                    annotation_uuid, image_id, class_id, session_id,
                    entry_time, annotation_type, annotation_role,
                    annotation_order, geometry_json, annotation_source,
                    metadata_json
                )
                VALUES(?, ?, ?, ?, ?, 'keypoints', 'arrow', ?, ?, 'manual', ?)
                """,
                (
                    arrow.arrow_uuid,
                    image_id,
                    arrow_class_id,
                    session_id,
                    now,
                    annotation_order,
                    geometry_json,
                    metadata_json,
                ),
            )
    if commit:
        connection.commit()


def persist_image_review_flag(
    connection: sqlite3.Connection,
    document: CocoDocument,
    image_name: str,
    pending_review: bool,
) -> None:
    """CODEX: Record and commit whether one image awaits review.

    Ensure the image has its stable project row, update its ``pending_review``
    flag, and commit without changing annotations or other image workflow
    state. The document supplies the current path and folder-order index needed
    when the row does not yet exist.
    """

    ensure_schema(connection)
    document.ensure_image_records()
    project_image = _ensure_project_image_row(
        connection,
        document,
        _image_path_for_name(document, image_name),
        _image_index_for_name(document, image_name),
    )
    connection.execute(
        """
        UPDATE project_images
        SET pending_review = ?
        WHERE image_id = ?
        """,
        (
            int(pending_review),
            int(project_image["image_id"]),
        ),
    )
    connection.commit()


def persist_image_deletion_state(
    connection: sqlite3.Connection,
    image_names: set[str],
    *,
    marked_for_deletion: bool,
    moved_to_trash: bool,
) -> None:
    """CODEX: Record and commit deletion workflow flags for named images.

    An empty name set is a no-op. Otherwise, update the mark and trash flags in
    deterministic name order. A request that marks images for deletion does
    not overwrite rows already recorded as moved; clearing or completing the
    workflow may update those rows. Image files and annotation rows are outside
    this function's responsibility.
    """

    if not image_names:
        return
    marked = int(marked_for_deletion)
    moved = int(moved_to_trash)
    connection.executemany(
        """
        UPDATE project_images
        SET marked_for_deletion = ?, moved_to_trash = ?
        WHERE image_name = ?
          AND (moved_to_trash = 0 OR ? = 0)
        """,
        [(marked, moved, image_name, marked) for image_name in sorted(image_names)],
    )
    connection.commit()
