"""CODEX: Project loaded image identity into SQLite project-image rows.

This module writes or refreshes the ``project_images`` row that anchors
annotations for a loaded image. Existing database rows are treated as
authoritative SQLite state; byte identity is verified before path, dimensions,
COCO image ID, ordering, or metadata are refreshed.

Callers own image discovery, COCO document setup, transaction scope, and
downstream annotation synchronization.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PIL import Image

from annotator.coco import CocoDocument
from annotator.sqlite.image_identity import image_md5sum
from annotator.sqlite.json.codec import _json_dumps


def _ensure_project_image_row(
    connection: sqlite3.Connection,
    document: CocoDocument,
    image_path: Path,
    image_index: int,
) -> sqlite3.Row:
    """CODEX: Return the project image row matching one loaded source image.

    ``project_images`` is the parent table for annotations. The row is created
    before region or arrow annotations are written so every child row can
    reference Teacup's integer image id while the stored MD5 digest guards
    against same-filename image substitutions.

    Values read from existing ``project_images`` rows are used directly because
    SQLite owns their normalization. The remaining conversions are write-boundary
    conversions for filesystem paths and COCO image-record IDs preserved from
    JSON.
    """

    existing = connection.execute(
        "SELECT * FROM project_images WHERE image_name = ?",
        (image_path.name,),
    ).fetchone()
    width, height = _image_size(image_path)
    current_md5sum = image_md5sum(image_path)
    image_record = dict(document.image_records[image_path.name])
    metadata = _json_dumps(
        {
            "source": "Teacup image folder",
            "coco_image_record": image_record,
        }
    )
    if existing:
        stored_md5sum = existing["image_md5sum"]
        existing_image_id = existing["image_id"]
        # CODEX: Existing annotation rows belong to exact image bytes, not just
        # CODEX: a filename, so path and size updates are allowed only after
        # CODEX: identity is verified.
        if current_md5sum != stored_md5sum:
            raise ValueError(
                "Image content mismatch for "
                f"{image_path.name}: stored MD5 {stored_md5sum} does not "
                f"match current MD5 {current_md5sum}. The project database "
                "may belong to a different image folder, or the image file "
                "may have been replaced."
            )
        connection.execute(
            """
            UPDATE project_images
            SET image_path = ?,
                width = ?,
                height = ?,
                coco_image_id = ?,
                image_sequence_index = ?,
                metadata_json = ?
            WHERE image_id = ?
            """,
            (
                str(image_path),
                width,
                height,
                int(image_record["id"]),
                image_index,
                metadata,
                existing_image_id,
            ),
        )
        return connection.execute(
            "SELECT * FROM project_images WHERE image_id = ?",
            (existing_image_id,),
        ).fetchone()

    connection.execute(
        """
        INSERT INTO project_images(
            image_name, image_path, image_md5sum, width, height,
            coco_image_id, image_sequence_index, metadata_json
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            image_path.name,
            str(image_path),
            current_md5sum,
            width,
            height,
            int(image_record["id"]),
            image_index,
            metadata,
        ),
    )
    image_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    return connection.execute(
        "SELECT * FROM project_images WHERE image_id = ?",
        (image_id,),
    ).fetchone()


def _image_size(image_path: Path) -> tuple[int | None, int | None]:
    """CODEX: Return image dimensions without keeping the image file open."""

    try:
        with Image.open(image_path) as image:
            return image.width, image.height
    except OSError:
        return None, None
