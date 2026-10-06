"""CODEX: Hash and verify Teacup project image identity.

This module owns source-image content identity checks that prevent SQLite
annotation state from being applied to a different image that happens to share
a filename. It computes streaming MD5 digests for source images and compares
stored hashes before load, save, archive, and restore workflows trust
authoritative SQLite state. Project-image row creation stores digests supplied
by this module.

The digest is an annotation identity check, not a security signature. Archive
packaging still writes SHA-256 member checksums for distribution integrity.

"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from annotator.sqlite.schema import ensure_schema

# CMP: (TODO) consider a more I/O efficient implementation
def image_md5sum(path: Path) -> str:
    """CMP/CODEX: Return a streaming MD5 digest for one source image file.

    MD5 is used here for the purpose for stable content identity for
    annotation linkage. It is not used for adversarial integrity checks.
    """

    with path.open("rb") as image_file:
        return hashlib.file_digest(image_file, "md5").hexdigest()


def verify_project_image_hashes(
    connection: sqlite3.Connection,
    image_paths: list[Path],
) -> None:
    """CODEX/CMP: Raise ``ValueError`` when source paths are not verified.

    Every supplied image path must already have a ``project_images`` row, and
    that row's stored digest must match the current source bytes. Folder-load
    reconciliation owns explicitly accepted creation of rows for newly added
    root JPEGs before this identity check runs.
    """

    ensure_schema(connection)
    rows = connection.execute(
        """
        SELECT image_name, image_md5sum
        FROM project_images
        """
    ).fetchall()

    # CMP: Replaced CODEX type-casted construction here to let errors propagate
    # naturally and to prevent weirdness (e.g., None being translated to "None")
    stored_md5s = {row["image_name"]: row["image_md5sum"] for row in rows}

    for image_path in image_paths:
        stored_md5sum = stored_md5s.get(image_path.name)

        # CMP: Continue if the image doesn't (yet) have a row, ergo md5sum.
        # CODEX: folder_load_reconciles_jpeg_files_with_sqlite_2026-08-26
        # CODEX: moves that old skip into prompted folder-load reconciliation.
        if stored_md5sum is None:
            raise ValueError(
                "Image is not registered in SQLite project_images: "
                f"{image_path.name}"
            )
        current_md5sum = image_md5sum(image_path)

        # CODEX: A stored digest means annotations already belong to specific
        # CODEX: image bytes; a mismatch would attach existing state to a different file.
        if current_md5sum != stored_md5sum:
            raise ValueError(
                "Image content mismatch for "
                f"{image_path.name}: stored MD5 {stored_md5sum} does not "
                f"match current MD5 {current_md5sum}. The project database "
                "may belong to a different image folder, or the image file "
                "may have been replaced."
            )
