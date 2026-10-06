"""Build distribution ZIPs from saved annotation projects.

Archive creation snapshots the live SQLite database, regenerates a COCO export
from that snapshot, rewrites README `[files]` metadata for the ZIP contents,
and writes checksums for every included member. GUI validation and prompts live
in `annotator.gui.project.archive`; this module owns only filesystem packaging.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

import annotator.sqlite as sql_backend
from annotator.project.paths import project_file_path
from annotator.project_metadata import CasePreservingConfigParser
from annotator.project_metadata import README_FILENAME


CLASS_DEFINITIONS_FILENAME = "class_definitions.txt"
CHECKSUMS_FILENAME = "checksums.txt"
REQUIRED_ARCHIVE_METADATA_KEYS = (
    "dataset_version",
    "data_license",
    "source_image_origin",
    "source_image_rights",
    "collection_methodology",
    "annotation_methodology",
    "quality_control_methodology",
)
ARCHIVE_FILE_DESCRIPTIONS = {
    "README.txt": "Project, provenance, rights, and archive file metadata.",
    sql_backend.DATABASE_FILENAME: "Authoritative annotation database snapshot.",
    "annotations.json": "COCO annotations generated from the database snapshot.",
    CLASS_DEFINITIONS_FILENAME: "Human-authored class definitions and edge cases.",
    CHECKSUMS_FILENAME: "SHA-256 checksums for every other archive member.",
    "*.jpg / *.jpeg": "Source images included in this annotation dataset.",
}
ProgressCallback = Callable[[int, str], None]


def missing_archive_metadata(values: dict[str, str]) -> tuple[str, ...]:
    """Return required distribution metadata fields that are empty.

    These fields are the minimum FAIR-oriented gate before archive creation;
    optional provenance fields are intentionally not required here.
    """

    return tuple(
        key
        for key in REQUIRED_ARCHIVE_METADATA_KEYS
        if not str(values.get(key, "")).strip()
    )


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest for one archive member.

    Source images may be large, so the digest is computed without reading the
    whole file into memory.
    """

    with path.open("rb") as source_file:
        return hashlib.file_digest(source_file, "sha256").hexdigest()


def create_archive(
    folder: Path,
    image_paths: list[Path],
    connection: sqlite3.Connection,
    output_path: Path,
    progress: ProgressCallback | None = None,
) -> Path:
    """Create a distribution ZIP from a live project database and image set.

    The archive contains a SQLite backup, a COCO JSON export generated from
    that same backup, archive-specific README metadata, class definitions,
    source JPEGs, and checksums. The destination is replaced only after the
    temporary ZIP is fully written.
    """

    # Build beside the destination so the final replace stays on the same volume.
    with tempfile.TemporaryDirectory(
        prefix=".teacup-archive-",
        dir=output_path.parent,
    ) as temp_dir:
        temp_folder = Path(temp_dir)
        database_path = temp_folder / sql_backend.DATABASE_FILENAME
        if progress is not None:
            progress(3, "Verifying source image checksums")
        sql_backend.verify_project_image_hashes(connection, image_paths)
        if progress is not None:
            progress(5, "Creating a consistent SQLite snapshot")
        # Every generated archive artifact derives from this snapshot so SQLite
        # and COCO describe the same saved state.
        snapshot = sqlite3.connect(database_path)
        try:
            connection.backup(snapshot)
        finally:
            snapshot.close()

        if progress is not None:
            progress(15, "Generating annotations.json from the SQLite snapshot")
        snapshot = sqlite3.connect(database_path)
        snapshot.row_factory = sqlite3.Row
        try:
            document = sql_backend.document_from_database(
                snapshot,
                folder,
                image_paths,
            )
        finally:
            snapshot.close()
        annotations_path = temp_folder / "annotations.json"
        with annotations_path.open("w", encoding="utf-8") as annotation_file:
            json.dump(document.to_payload(), annotation_file, indent=2)
            annotation_file.write("\n")

        if progress is not None:
            progress(25, "Preparing archive metadata")
        readme_path = temp_folder / "README.txt"
        parser = CasePreservingConfigParser(interpolation=None)
        parser.read(
            project_file_path(folder, README_FILENAME),
            encoding="utf-8",
        )
        # The project README may describe teacup/ working files; the archive
        # copy describes only the flat files included in the ZIP.
        parser.remove_section("files")
        parser.add_section("files")
        for filename, description in ARCHIVE_FILE_DESCRIPTIONS.items():
            parser.set("files", filename, description)
        with readme_path.open("w", encoding="utf-8") as readme_file:
            parser.write(readme_file)

        # Archive member names stay flat and stable, independent of the
        # project's internal teacup/ working layout.
        members = [
            (readme_path, "README.txt"),
            (database_path, sql_backend.DATABASE_FILENAME),
            (annotations_path, "annotations.json"),
            (
                project_file_path(folder, CLASS_DEFINITIONS_FILENAME),
                CLASS_DEFINITIONS_FILENAME,
            ),
            *((image_path, image_path.name) for image_path in image_paths),
        ]
        checksums = []
        total_members = len(members)
        for index, (path, archive_name) in enumerate(members, start=1):
            if progress is not None:
                progress(
                    25 + round(index * 35 / total_members),
                    f"Checksumming {archive_name}",
                )
            checksums.append(f"{sha256_file(path)}  {archive_name}")

        temporary_zip = temp_folder / output_path.name
        with zipfile.ZipFile(
            temporary_zip,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for index, (path, archive_name) in enumerate(members, start=1):
                if progress is not None:
                    progress(
                        60 + round(index * 35 / total_members),
                        f"Adding {archive_name}",
                    )
                # JPEGs are already compressed; storing them avoids wasted CPU
                # while text, JSON, README, and SQLite still benefit from ZIP.
                compression = (
                    zipfile.ZIP_STORED
                    if path.suffix.casefold() in {".jpg", ".jpeg"}
                    else zipfile.ZIP_DEFLATED
                )
                archive.write(path, archive_name, compress_type=compression)
            # checksums.txt cannot include its own digest because writing that
            # digest would change the file being checksummed.
            archive.writestr(CHECKSUMS_FILENAME, "\n".join(checksums) + "\n")
        # Publish only after the ZIP is complete, avoiding a partial destination.
        temporary_zip.replace(output_path)
    if progress is not None:
        progress(100, f"Archive created: {output_path.name}")
    return output_path
