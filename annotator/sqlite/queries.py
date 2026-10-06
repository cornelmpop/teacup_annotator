"""CODEX: Read Teacup-native SQLite rows into application state.

This module projects authoritative SQLite rows into in-memory application and
COCO-compatible dictionaries. Schema-owned numeric identifiers are converted at
projection boundaries, while schema-owned text values are trusted as stored so
malformed database state is not hidden by runtime string coercion.

Permissive decoding remains limited to JSON metadata, geometry payloads, and
loose COCO-style category dictionaries, where legacy or external values may be
absent or malformed.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from PIL import Image

from annotator.arrows import Arrow
from annotator.class_names import class_name_error
from annotator.geom.polygon import area
from annotator.geom.polygon import bbox
from annotator.sqlite.annotation_order import (
    load_annotation_orders as _load_annotation_orders,
)
from annotator.sqlite.json import _coerce_int
from annotator.sqlite.json import _json_loads
from annotator.sqlite.schema import ensure_schema


# CMP: 'document' here is images. I'm leaving this as-is because
# it's not worth the refactor hassle (for now - but, a TODO).
def database_has_document(connection: sqlite3.Connection) -> bool:
    """CODEX: Return True once the folder has project image rows in SQL."""

    row = connection.execute("SELECT COUNT(*) AS count FROM project_images").fetchone()
    return bool(row and int(row["count"]) > 0)


def load_arrows(
    connection: sqlite3.Connection,
) -> dict[str, list[Arrow]]:
    """CODEX: Load folder arrow annotations from generic keypoint rows.

    SQLite stores arrows as full annotations with
    ``annotation_type = 'keypoints'`` and ``annotation_role = 'arrow'``. Return
    their image-local ordered lists keyed by image name, including rows
    belonging to images currently recorded as moved to trash.

    Moved-image entries are not rendered because those images are absent from
    navigation. They remain in this folder-wide projection so later arrow
    persistence does not erase annotation rows needed by manual restoration.
    """

    ensure_schema(connection)
    rows = connection.execute(
        """
        SELECT ann.annotation_uuid, img.image_name, ann.geometry_json
        FROM annotations AS ann
        JOIN project_images AS img
          ON img.image_id = ann.image_id
        WHERE ann.annotation_type = 'keypoints'
          AND ann.annotation_role = 'arrow'
        ORDER BY img.image_name, ann.annotation_order, ann.annotation_id
        """
    ).fetchall()

    arrows: dict[str, list[Arrow]] = {}

    # CMP: Removed type casting added by Codex - there is no valid reason
    # why image_name, for instance, should be type casted here. DB errors
    # should propagate naturally.
    for row in rows:
        start, end = _arrow_points(row["geometry_json"])
        arrows.setdefault(row["image_name"], []).append(
            Arrow(
                row["annotation_uuid"],
                start[0],
                start[1],
                end[0],
                end[1],
            )
        )
    return arrows


def load_annotation_orders(connection: sqlite3.Connection) -> dict[str, int]:
    """CODEX: Return stored annotation orders for GUI persistence state."""

    ensure_schema(connection)
    return _load_annotation_orders(connection)


# CMP: Removed type casting added by Codex for the image name in the
# return. Errors in the database should not be masked.
def load_review_flags(connection: sqlite3.Connection) -> set[str]:
    """CODEX: Return image names currently marked as pending review."""

    ensure_schema(connection)
    rows = connection.execute(
        "SELECT image_name FROM project_images WHERE pending_review = 1"
    ).fetchall()
    return {row["image_name"] for row in rows}


# CMP: Removed type casting added by Codex for the image name in the
# return. Errors in the database should not be masked.
def load_pending_deletions(connection: sqlite3.Connection) -> set[str]:
    """CODEX: Return image names marked for deletion but not yet moved."""

    ensure_schema(connection)
    rows = connection.execute(
        """
        SELECT image_name
        FROM project_images
        WHERE marked_for_deletion = 1 AND moved_to_trash = 0
        """
    ).fetchall()
    return {row["image_name"] for row in rows}


# CMP: Removed type casting added by Codex for strings.
# Errors in the database should not be masked.
def _categories_from_database(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """CODEX: Return valid COCO categories from region annotation-class rows.

    SQLite project files cross the external-data trust boundary here. Apply the
    shared class-name contract before publishing an in-memory document, while
    leaving malformed authoritative rows unchanged for explicit repair.
    """

    rows = connection.execute(
        """
        SELECT coco_category_id, class_name, supercategory
        FROM annotation_classes
        WHERE annotation_family = 'region'
        ORDER BY class_list_order, class_id
        """
    ).fetchall()

    name_error = class_name_error(row["class_name"] for row in rows)
    if name_error is not None:
        raise ValueError(name_error)

    categories: list[dict[str, Any]] = []
    for row in rows:
        category: dict[str, Any] = {
            "id": int(row["coco_category_id"]),
            "name": row["class_name"],
        }
        if row["supercategory"]:
            category["supercategory"] = row["supercategory"]
        categories.append(category)
    return categories


def load_region_class_settings(
    connection: sqlite3.Connection,
) -> tuple[tuple[str, ...], tuple[str | None, ...]]:
    """CODEX: Return authoritative region-class names and display colours.

    Rows retain SQLite class-list order. Text values are returned without
    coercion, and nullable ``display_color`` values remain ``None`` so the GUI
    can apply its existing display-only palette without rewriting the database.
    """

    ensure_schema(connection)
    rows = connection.execute(
        """
        SELECT class_name, display_color
        FROM annotation_classes
        WHERE annotation_family = 'region'
        ORDER BY class_list_order, class_id
        """
    ).fetchall()
    class_names = tuple(row["class_name"] for row in rows)
    class_colours = tuple(row["display_color"] for row in rows)
    return class_names, class_colours

# CMP: Removed str type casting added by Codex.
# Errors in the database should not be masked.
def _image_records_from_database(
    connection: sqlite3.Connection,
    image_paths: list[Path],
) -> dict[str, dict[str, Any]]:
    """CODEX: Return COCO image records for registered loadable images.

    Every supplied path must already exist in ``project_images``. Prompted
    folder-load reconciliation owns accepted row creation for new root JPEGs,
    so database projection raises when a caller tries to synthesize GUI state
    for an unregistered file.
    """

    rows = {
        row["image_name"]: row
        for row in connection.execute("SELECT * FROM project_images").fetchall()
    }

    records: dict[str, dict[str, Any]] = {}
    for image_path in image_paths:
        row = rows.get(image_path.name)
        if row is None:
            raise ValueError(
                "Image is not registered in SQLite project_images: "
                f"{image_path.name}"
            )
        image_id = row["coco_image_id"]
        width = row["width"]
        height = row["height"]

        record: dict[str, Any] = {
            "id": image_id,
            "file_name": image_path.name,
        }

        if width and height:
            record["width"] = width
            record["height"] = height
        record["image_md5sum"] = row["image_md5sum"]

        records[image_path.name] = record

    return records

# CMP: Removed str type casting added by Codex.
# Errors in the database should not be masked.
def _annotations_from_database(
    connection: sqlite3.Connection,
    image_records: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """CODEX: Return COCO region annotation payloads from native rows."""

    image_names = list(image_records)
    if not image_names:
        return []
    placeholders = ",".join("?" for _ in image_names)
    rows = connection.execute(
        f"""
        SELECT ann.*, img.image_name, ac.coco_category_id, ac.class_name
        FROM annotations AS ann
        JOIN project_images AS img
          ON img.image_id = ann.image_id
        LEFT JOIN annotation_classes AS ac
          ON ac.class_id = ann.class_id
        WHERE img.image_name IN ({placeholders})
          AND ann.annotation_role = ''
          AND ann.annotation_type IN ('polygon', 'rectangle')
        ORDER BY img.image_sequence_index, img.image_name,
                 ann.annotation_order, ann.annotation_id
        """,
        image_names,
    ).fetchall()

    annotations: list[dict[str, Any]] = []
    for row in rows:
        image_name = row["image_name"]
        image_id = int(image_records[image_name]["id"])
        metadata = _json_loads(row["metadata_json"], {})
        raw = dict(metadata.get("raw") or {})
        raw.pop("annotation_source", None)
        polygons = _polygons_from_geometry(row["geometry_json"])
        annotation_id = _coerce_int(
            metadata.get("coco_annotation_id"),
            int(row["annotation_id"]),
        )
        category_id = _coerce_int(
            metadata.get("coco_category_id"),
            _coerce_int(row["coco_category_id"], 1),
        )

        raw.update(
            {
                "id": annotation_id,
                "image_id": image_id,
                "category_id": category_id,
                "segmentation": _segmentation_payload(polygons),
                "bbox": bbox(polygons),
                "area": area(polygons),
                "iscrowd": 0,
                "annotation_uuid": row["annotation_uuid"],
                "annotation_type": row["annotation_type"],
            }
        )
        raw.setdefault("entry_type", _entry_type_from_source(row["annotation_source"]))

        if row["model_run_class_id"] is not None:
            raw["model_run_class_id"] = int(row["model_run_class_id"])
        if row["model_confidence"] is not None:
            raw["score"] = float(row["model_confidence"])
        annotations.append(raw)

    return annotations


def _coco_info_json(connection: sqlite3.Connection) -> str | None:
    """CODEX: Return the preserved top-level COCO info object as JSON."""

    row = connection.execute(
        "SELECT info_json FROM coco_info WHERE coco_info_id = 1"
    ).fetchone()
    if row is None:
        return None

    return row["info_json"]


def _set_coco_info_json(
    connection: sqlite3.Connection,
    value: str,
    updated_time: int,
) -> None:
    """CODEX: Store the preserved top-level COCO info object."""

    connection.execute(
        """
        INSERT INTO coco_info(coco_info_id, info_json, updated_time)
        VALUES(1, ?, ?)
        ON CONFLICT(coco_info_id) DO UPDATE SET
            info_json = excluded.info_json,
            updated_time = excluded.updated_time
        """,
        (value, updated_time),
    )


def _image_path_for_name(document: Any, image_name: str) -> Path:
    """CODEX: Return the loaded image path for a basename."""

    for image_path in document.image_paths:
        if image_path.name == image_name:
            return image_path
    raise ValueError(f"Image is not loaded: {image_name}")


def _image_index_for_name(document: Any, image_name: str) -> int:
    """CODEX: Return the current folder order index for a basename."""

    for index, image_path in enumerate(document.image_paths):
        if image_path.name == image_name:
            return index
    return 0


def _image_size(image_path: Path) -> tuple[int | None, int | None]:
    """CODEX: Return image dimensions without keeping the image file open."""

    try:
        with Image.open(image_path) as image:
            return int(image.width), int(image.height)
    except OSError:
        return None, None


def _colour_by_category_name(
    categories: list[dict[str, Any]],
    class_colours: tuple[str, ...],
) -> dict[str, str]:
    """CODEX: Map display colours onto category names when lengths match."""

    names = [str(category.get("name") or "") for category in categories]
    if len(names) != len(class_colours):
        return {}
    return {
        name: colour for name, colour in zip(names, class_colours) if name and colour
    }


def _polygons_from_geometry(value: str) -> list[list[tuple[float, float]]]:
    """CODEX: Decode polygon geometry from ``annotations.geometry_json``."""

    geometry = _json_loads(value, {})
    polygons = geometry.get("polygons") if isinstance(geometry, dict) else None
    normalized: list[list[tuple[float, float]]] = []

    if not isinstance(polygons, list):
        return normalized

    for polygon in polygons:
        points: list[tuple[float, float]] = []

        if not isinstance(polygon, list):
            continue
        for point in polygon:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                points.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError):
                continue

        if len(points) >= 3:
            normalized.append(points)

    return normalized


def _segmentation_payload(
    polygons: list[list[tuple[float, float]]],
) -> list[list[float]]:
    """CODEX: Return COCO flat segmentation arrays."""

    return [
        [coordinate for point in polygon for coordinate in (point[0], point[1])]
        for polygon in polygons
        if len(polygon) >= 3
    ]


def _arrow_points(value: str) -> tuple[tuple[float, float], tuple[float, float]]:
    """CODEX: Decode an arrow's two stored keypoints from geometry JSON."""

    geometry = _json_loads(value, {})
    points = geometry.get("points") if isinstance(geometry, dict) else None
    if not isinstance(points, list) or len(points) < 2:
        raise ValueError("Stored arrow annotation is missing two keypoints")
    return _point(points[0]), _point(points[1])


def _point(value: Any) -> tuple[float, float]:
    """CODEX: Return one two-coordinate point from decoded geometry JSON."""

    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise ValueError("Stored keypoint is not a two-coordinate point")
    return float(value[0]), float(value[1])


def _entry_type_from_source(source: str) -> str:
    """CODEX: Return legacy COCO metadata wording for one source value."""

    if source == "model":
        return "automatic"
    return source
