"""CODEX: Synchronize COCO categories with Teacup project-class rows."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from annotator.sqlite.time import _unix_time

# CODEX: Temporarily move class rows outside any realistic final order range
# CODEX: so the class-list uniqueness constraint cannot observe reordering collisions.
CLASS_ORDER_REORDER_OFFSET = 1_000_000


def _upsert_class_rows(
    connection: sqlite3.Connection,
    categories: list[dict[str, Any]],
    class_colours: tuple[str, ...] = (),
    *,
    class_source: str = "import",
    source_reference: str | None = None,
    reorder_classes: bool = True,
) -> dict[int, int]:
    """CODEX: Synchronize project classes and return ids by COCO category id."""

    from annotator.sqlite.connect import _ensure_session
    from annotator.sqlite.queries import _colour_by_category_name

    now = _unix_time()
    session_id = _ensure_session(connection)
    colour_by_name = _colour_by_category_name(categories, class_colours)
    desired_rows = _desired_class_rows(categories)
    if reorder_classes:
        connection.execute(
            """
            UPDATE annotation_classes
            SET class_list_order = class_list_order + ?
            WHERE annotation_family = 'region'
            """,
            (CLASS_ORDER_REORDER_OFFSET,),
        )
    class_id_by_category_id: dict[int, int] = {}
    for row in desired_rows:
        existing = _existing_class_row(
            connection,
            int(row["coco_category_id"]),
            row["name"],
            allow_name_match=not reorder_classes,
        )
        if existing is None:
            class_id = _insert_class_row(
                connection,
                row,
                class_colours=colour_by_name,
                class_source=class_source,
                source_reference=source_reference,
                session_id=session_id,
                now=now,
                class_list_order=(
                    int(row["order"])
                    if reorder_classes
                    else _next_class_list_order(connection)
                ),
            )
        else:
            class_id = int(existing["class_id"])
            if int(existing["coco_category_id"]) == int(row["coco_category_id"]):
                _update_class_row(
                    connection,
                    class_id,
                    row,
                    colour_by_name,
                    class_list_order=(
                        int(row["order"])
                        if reorder_classes
                        else int(existing["class_list_order"])
                    ),
                )
        class_id_by_category_id[int(row["coco_category_id"])] = int(class_id)
    return class_id_by_category_id


def _existing_class_row(
    connection: sqlite3.Connection,
    coco_category_id: int,
    class_name: str,
    *,
    allow_name_match: bool,
) -> sqlite3.Row | None:
    """CODEX: Return an existing region class by COCO id or optional name."""

    existing = connection.execute(
        """
        SELECT *
        FROM annotation_classes
        WHERE annotation_family = 'region' AND coco_category_id = ?
        """,
        (coco_category_id,),
    ).fetchone()
    if existing is not None or not allow_name_match:
        return existing
    return connection.execute(
        """
        SELECT *
        FROM annotation_classes
        WHERE annotation_family = 'region' AND class_name = ?
        """,
        (class_name,),
    ).fetchone()


def _insert_class_row(
    connection: sqlite3.Connection,
    row: dict[str, object],
    *,
    class_colours: dict[str, str],
    class_source: str,
    source_reference: str | None,
    session_id: str,
    now: int,
    class_list_order: int,
) -> int:
    """CODEX: Insert one new project class and return its database id."""

    cursor = connection.execute(
        """
        INSERT INTO annotation_classes(
            class_uuid, class_name, class_list_order, annotation_family,
            class_source, supercategory, display_color, session_id,
            entry_time, source_reference, coco_category_id
        )
        VALUES(?, ?, ?, 'region', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"class:{uuid.uuid4()}",
            row["name"],
            class_list_order,
            class_source,
            row["supercategory"],
            class_colours.get(row["name"]),
            session_id,
            now,
            source_reference,
            int(row["coco_category_id"]),
        ),
    )
    return int(cursor.lastrowid)


def _update_class_row(
    connection: sqlite3.Connection,
    class_id: int,
    row: dict[str, object],
    class_colours: dict[str, str],
    *,
    class_list_order: int,
) -> None:
    """CODEX: Update mutable display/category fields for one project class."""

    connection.execute(
        """
        UPDATE annotation_classes
        SET class_name = ?,
            class_list_order = ?,
            supercategory = ?,
            display_color = ?
        WHERE class_id = ?
        """,
        (
            row["name"],
            class_list_order,
            row["supercategory"],
            class_colours.get(row["name"]),
            class_id,
        ),
    )


def _desired_class_rows(categories: list[dict[str, Any]]) -> list[dict[str, object]]:
    """CODEX: Return normalized class rows in document category order."""

    rows: list[dict[str, object]] = []
    for order, category in enumerate(categories):
        category_id = _category_id(category, order + 1)
        rows.append(
            {
                "coco_category_id": category_id,
                "name": str(category.get("name") or f"class_{category_id}"),
                "supercategory": str(category.get("supercategory") or "object"),
                "order": order + 1,
            }
        )
    return rows


def _next_class_list_order(connection: sqlite3.Connection) -> int:
    """CODEX: Return the next available project class-list order value."""

    row = connection.execute(
        "SELECT COALESCE(MAX(class_list_order), -1) + 1 AS next_order "
        "FROM annotation_classes"
    ).fetchone()
    return int(row["next_order"])


def _category_id(category: dict[str, Any], fallback: int) -> int:
    """CODEX: Return a COCO category id, falling back to document order."""

    try:
        return int(category.get("id", fallback))
    except (TypeError, ValueError):
        return fallback
