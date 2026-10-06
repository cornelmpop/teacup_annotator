"""CODEX: Project region annotations into the generic SQLite annotation table.

This module writes polygon and rectangle rows only. Arrow rows share the same
table and image-local order sequence, so region writes preserve surviving
annotations by keeping their existing sparse order values instead of compacting
around the current region list.

Callers own image-row setup, class-row setup, transaction scope, and JSON backup
publication.
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from annotator.coco import CocoDocument
from annotator.sqlite.annotation_order import annotation_orders_for_image
from annotator.sqlite.annotation_order import discard_annotation_orders
from annotator.sqlite.annotation_order import order_for_annotation_uuid
from annotator.sqlite.annotation_order import region_annotation_orders_for_image
from annotator.sqlite.json.codec import _json_dumps
from annotator.sqlite.time import _unix_time


def _synchronize_region_annotations_for_image(
    connection: sqlite3.Connection,
    document: CocoDocument,
    image_name: str,
    image_id: int,
    session_id: str,
    class_id_by_category_id: dict[int, int],
    annotation_orders_by_uuid: dict[str, int] | None = None,
    human_edit: bool = False,
) -> None:
    """CODEX: Reconcile one image's region rows by durable annotation UUID.

    Delete only stored region UUIDs absent from the document, insert new UUIDs,
    update changed UUIDs, and leave matching rows untouched. Existing sparse
    image-local order values survive by UUID, while new annotations append
    after the current maximum without compacting arrows or future annotation
    families.

    ``human_edit`` asks each actually changed, surviving model-linked region to
    adopt manual source while retaining its model provenance. Callers own the
    transaction, image/class setup, audit event, and optional JSON output.
    """

    annotations = document.annotations_for(image_name)
    stored_orders = annotation_orders_for_image(connection, image_id)
    stored_region_orders = region_annotation_orders_for_image(connection, image_id)
    reserved_orders = set(stored_orders.values())
    desired_region_uuids: list[str] = []
    desired_region_orders: dict[str, int] = {}
    for annotation in annotations:
        annotation_uuid = _annotation_uuid(annotation.raw)
        annotation.raw["annotation_uuid"] = annotation_uuid
        desired_region_uuids.append(annotation_uuid)
        desired_region_orders[annotation_uuid] = order_for_annotation_uuid(
            connection,
            image_id,
            annotation_uuid,
            stored_orders,
            annotation_orders_by_uuid,
            reserved_orders,
        )
    stale_region_uuids = set(stored_region_orders) - set(desired_region_uuids)
    connection.executemany(
        "DELETE FROM annotations WHERE annotation_uuid = ?",
        [(annotation_uuid,) for annotation_uuid in sorted(stale_region_uuids)],
    )
    discard_annotation_orders(annotation_orders_by_uuid, stale_region_uuids)
    now = _unix_time()
    for annotation_uuid, annotation in zip(desired_region_uuids, annotations):
        _upsert_region_annotation(
            connection,
            document,
            annotation,
            image_id,
            session_id,
            class_id_by_category_id,
            annotation_order=desired_region_orders[annotation_uuid],
            now=now,
            human_edit=human_edit,
        )


def _upsert_region_annotation(
    connection: sqlite3.Connection,
    document: CocoDocument,
    annotation: Any,
    image_id: int,
    session_id: str,
    class_id_by_category_id: dict[int, int],
    *,
    annotation_order: int,
    now: int | None = None,
    human_edit: bool = False,
) -> bool:
    """CODEX: Insert a region row or update a changed UUID projection.

    The durable region identity is the ``annotation_uuid`` stored in annotation
    ``raw`` metadata and mirrored into the generic database identity column.
    Model-created annotations require a model-run class id before they can be
    recorded with ``annotation_source = 'model'``.

    An existing UUID is updated only when its stored image, class, provenance,
    order, geometry, confidence, or metadata differs. Conflict updates retain
    the annotation's original session and entry time because edit sessions are
    represented by audit events; a matching row receives no update at all
    during document-wide UUID synchronization.

    When ``human_edit`` is true, an actually written model-linked row adopts
    manual source in both SQLite and the in-memory annotation before the caller
    captures audit after-state. The model-run link, UUID, confidence, session,
    and entry time remain unchanged. Return whether the insert or conditional
    update wrote a row.
    """

    annotation_uuid = _annotation_uuid(annotation.raw)
    annotation.raw["annotation_uuid"] = annotation_uuid
    raw_metadata = dict(annotation.raw)
    # CODEX: Standard COCO fields are reconstructed from typed columns. Keeping
    # CODEX: their loaded copies here would make an unchanged row appear edited
    # CODEX: on the first UUID synchronization after reopening a project.
    for generated_key in (
        "annotation_uuid",
        "id",
        "image_id",
        "category_id",
        "segmentation",
        "bbox",
        "area",
        "iscrowd",
        "score",
    ):
        raw_metadata.pop(generated_key, None)
    category_id = annotation.category_id
    class_id = class_id_by_category_id[category_id]
    annotation_type = _region_annotation_type(annotation.raw)
    model_run_class_id = annotation.raw.get("model_run_class_id")
    annotation_source = _annotation_source(annotation.raw, model_run_class_id)
    metadata = _json_dumps(
        {
            "coco_annotation_id": annotation.annotation_id,
            "coco_image_id": annotation.image_id,
            "coco_category_id": category_id,
            "raw": raw_metadata,
        }
    )
    written_row = connection.execute(
        """
        INSERT INTO annotations(
            annotation_uuid, image_id, class_id, session_id, model_run_class_id,
            entry_time, annotation_type, annotation_role, annotation_order,
            geometry_json, model_confidence, annotation_source, metadata_json
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?)
        ON CONFLICT(annotation_uuid) DO UPDATE SET
            image_id = excluded.image_id,
            class_id = excluded.class_id,
            model_run_class_id = excluded.model_run_class_id,
            annotation_type = excluded.annotation_type,
            annotation_role = excluded.annotation_role,
            annotation_order = excluded.annotation_order,
            geometry_json = excluded.geometry_json,
            model_confidence = excluded.model_confidence,
            annotation_source = excluded.annotation_source,
            metadata_json = excluded.metadata_json
        WHERE annotations.image_id IS NOT excluded.image_id
           OR annotations.class_id IS NOT excluded.class_id
           OR annotations.model_run_class_id IS NOT excluded.model_run_class_id
           OR annotations.annotation_type IS NOT excluded.annotation_type
           OR annotations.annotation_role IS NOT excluded.annotation_role
           OR annotations.annotation_order IS NOT excluded.annotation_order
           OR annotations.geometry_json IS NOT excluded.geometry_json
           OR annotations.model_confidence IS NOT excluded.model_confidence
           OR annotations.annotation_source IS NOT excluded.annotation_source
           OR annotations.metadata_json IS NOT excluded.metadata_json
        RETURNING model_run_class_id, annotation_source
        """,
        (
            annotation_uuid,
            image_id,
            class_id,
            session_id,
            model_run_class_id,
            now if now is not None else _unix_time(),
            annotation_type,
            annotation_order,
            _json_dumps({"polygons": annotation.polygons}),
            annotation.score,
            annotation_source,
            metadata,
        ),
    ).fetchone()
    if written_row is None:
        return False
    if (
        human_edit
        and written_row["model_run_class_id"] is not None
        and written_row["annotation_source"] == "model"
    ):
        # CODEX: A committed human change owns current source, while the retained
        # CODEX: model-run link continues to identify the originating prediction.
        annotation.raw.pop("annotation_source", None)
        annotation.raw["entry_type"] = "manual"
        raw_metadata.pop("annotation_source", None)
        raw_metadata["entry_type"] = "manual"
        metadata = _json_dumps(
            {
                "coco_annotation_id": annotation.annotation_id,
                "coco_image_id": annotation.image_id,
                "coco_category_id": category_id,
                "raw": raw_metadata,
            }
        )
        connection.execute(
            """
            UPDATE annotations
            SET annotation_source = 'manual', metadata_json = ?
            WHERE annotation_uuid = ?
            """,
            (metadata, annotation_uuid),
        )
    return True


def _delete_region_annotations_for_image(
    connection: sqlite3.Connection,
    image_id: int,
) -> None:
    """CODEX: Delete only editable region annotations for one image."""

    connection.execute(
        """
        DELETE FROM annotations
        WHERE image_id = ?
          AND annotation_role = ''
          AND annotation_type IN ('polygon', 'rectangle')
        """,
        (image_id,),
    )


def _annotation_uuid(raw: dict[str, Any]) -> str:
    """CODEX: Return the current annotation UUID, generating one when absent."""

    value = raw.get("annotation_uuid")
    if value:
        annotation_uuid = value.strip()
        if annotation_uuid:
            return annotation_uuid
    return f"ann:{uuid.uuid4()}"


def _region_annotation_type(raw: dict[str, Any]) -> str:
    """CODEX: Return the stored region type supported by the native schema."""

    annotation_type = raw.get("annotation_type") or "polygon"
    if annotation_type == "rectangle":
        return "rectangle"
    return "polygon"


def _annotation_source(
    raw: dict[str, Any],
    model_run_class_id: int | None,
) -> str:
    """CODEX: Return schema provenance while respecting model-run constraints."""

    raw_source = (
        raw.get("annotation_source") or raw.get("entry_type") or "manual"
    ).strip()
    if raw_source == "automatic" and model_run_class_id is not None:
        return "model"
    if raw_source in {"manual", "model", "import", "teacup_internal"}:
        if raw_source == "model" and model_run_class_id is None:
            return "import"
        return raw_source
    return "import"
