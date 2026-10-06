"""CODEX: Preserve image-local annotation order as a sparse database sort key.

All annotation families share ``annotations.annotation_order`` within each
image. Runtime region indexes and arrow indexes are dense list positions derived
after sorting; they are not the stored order contract. This module keeps order
lookup and allocation in the SQLite layer so region, arrow, and future
non-deletable annotation families do not compact each other during partial edits.

Callers own transaction scope, project-image row creation, and deciding which
annotation UUIDs remain live after an edit.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from collections.abc import Mapping


def load_annotation_orders(connection: sqlite3.Connection) -> dict[str, int]:
    """CODEX: Return stored annotation orders keyed by durable annotation UUID."""

    rows = connection.execute(
        """
        SELECT annotation_uuid, annotation_order
        FROM annotations
        """
    ).fetchall()
    return {row["annotation_uuid"]: row["annotation_order"] for row in rows}


def annotation_orders_for_image(
    connection: sqlite3.Connection,
    image_id: int,
) -> dict[str, int]:
    """CODEX: Return all stored orders for one image keyed by annotation UUID."""

    rows = connection.execute(
        """
        SELECT annotation_uuid, annotation_order
        FROM annotations
        WHERE image_id = ?
        """,
        (image_id,),
    ).fetchall()
    return {row["annotation_uuid"]: row["annotation_order"] for row in rows}


def region_annotation_orders_for_image(
    connection: sqlite3.Connection,
    image_id: int,
) -> dict[str, int]:
    """CODEX: Return stored polygon and rectangle orders for one image."""

    rows = connection.execute(
        """
        SELECT annotation_uuid, annotation_order
        FROM annotations
        WHERE image_id = ?
          AND annotation_role = ''
          AND annotation_type IN ('polygon', 'rectangle')
        """,
        (image_id,),
    ).fetchall()
    return {row["annotation_uuid"]: row["annotation_order"] for row in rows}


def arrow_annotation_orders(connection: sqlite3.Connection) -> dict[str, int]:
    """CODEX: Return stored arrow orders across the whole project."""

    rows = connection.execute(
        """
        SELECT annotation_uuid, annotation_order
        FROM annotations
        WHERE annotation_type = 'keypoints'
          AND annotation_role = 'arrow'
        """
    ).fetchall()
    return {row["annotation_uuid"]: row["annotation_order"] for row in rows}


def discard_annotation_orders(
    annotation_orders_by_uuid: dict[str, int] | None,
    annotation_uuids: Iterable[str],
) -> None:
    """CODEX: Remove order-map entries for annotations no longer live."""

    if annotation_orders_by_uuid is None:
        return
    for annotation_uuid in annotation_uuids:
        annotation_orders_by_uuid.pop(annotation_uuid, None)


def order_for_annotation_uuid(
    connection: sqlite3.Connection,
    image_id: int,
    annotation_uuid: str,
    stored_orders: Mapping[str, int],
    annotation_orders_by_uuid: dict[str, int] | None,
    reserved_orders: set[int],
) -> int:
    """CODEX: Return a stable stored order for an annotation UUID.

    The GUI order map is consulted first because Undo snapshots can remember an
    order after a row was deleted from SQLite. The database supplies the current
    order for rows that still exist. A previously unseen UUID is appended after
    the image's current maximum stored or reserved order.
    """

    order = None
    if annotation_orders_by_uuid is not None:
        order = annotation_orders_by_uuid.get(annotation_uuid)
    if order is None:
        order = stored_orders.get(annotation_uuid)
    if order is None:
        order = next_annotation_order(connection, image_id, reserved_orders)
    reserved_orders.add(order)
    if annotation_orders_by_uuid is not None:
        annotation_orders_by_uuid[annotation_uuid] = order
    return order


def next_annotation_order(
    connection: sqlite3.Connection,
    image_id: int,
    reserved_orders: set[int],
) -> int:
    """CODEX: Return the first order after the image's current known maximum."""

    row = connection.execute(
        """
        SELECT MAX(annotation_order) AS max_order
        FROM annotations
        WHERE image_id = ?
        """,
        (image_id,),
    ).fetchone()
    candidate_orders = set(reserved_orders)
    if row["max_order"] is not None:
        candidate_orders.add(row["max_order"])
    if not candidate_orders:
        return 0
    return max(candidate_orders) + 1
