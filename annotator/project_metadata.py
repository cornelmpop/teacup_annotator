"""CODEX: Own folder README metadata for project, provenance, and file inventory.

CODEX: This module is the boundary for `teacup/README.txt`: global preferences seed
metadata before a folder loads, folder `[project]` values override them, and
explicit saves refresh provenance and the bounded project-artifact file list.
"""

from __future__ import annotations

import configparser
from datetime import datetime
from pathlib import Path
from typing import Iterable

from annotator.coco.io import image_annotation_path
from annotator.project.paths import PROJECT_DATA_FOLDER_NAME
from annotator.project.paths import crops_folder
from annotator.project.paths import project_data_folder
from annotator.project.paths import project_file_path
from annotator.release_identity import APP_NAME, APP_VERSION, APP_ZENODO_DOI
from annotator.sqlite.constants import DATABASE_FILENAME


README_FILENAME = "README.txt"
# Stable contract for global preferences, Project config, README, and archiving.
PROJECT_METADATA_KEYS = (
    "author_name",
    "author_email",
    "author_primary_affiliation",
    "project_name",
    "dataset_version",
    "dataset_identifier",
    "data_license",
    "source_image_origin",
    "source_image_rights",
    "model_identifier",
    "model_access_and_license",
    "project_description",
    "collection_methodology",
    "annotation_methodology",
    "quality_control_methodology",
)
# Keep labels beside keys so configuration and archive prompts use the same text.
PROJECT_METADATA_LABELS = {
    "author_name": "Author name",
    "author_email": "Author e-mail",
    "author_primary_affiliation": "Author primary affiliation",
    "project_name": "Project name",
    "dataset_version": "Dataset version",
    "dataset_identifier": "Dataset identifier",
    "data_license": "Data license / rights statement",
    "source_image_origin": "Source-image origin",
    "source_image_rights": "Source-image rights",
    "model_identifier": "Model identifier",
    "model_access_and_license": "Model access and license",
    "project_description": "Project description",
    "collection_methodology": "Collection methodology",
    "annotation_methodology": "Annotation methodology",
    "quality_control_methodology": "Quality-control methodology",
}
# CODEX: Known single-file artifacts are static; repeated outputs are detected on save.
FILE_DESCRIPTIONS = {
    f"{PROJECT_DATA_FOLDER_NAME}/{README_FILENAME}": (
        "Project, provenance, and file metadata."
    ),
    f"{PROJECT_DATA_FOLDER_NAME}/{DATABASE_FILENAME}": (
        "Authoritative annotation database."
    ),
    "annotations.json": "Complete optional COCO JSON backup and recovery source.",
    f"{PROJECT_DATA_FOLDER_NAME}/annotations_polygons.json": (
        "Optional polygon-only COCO JSON export."
    ),
    f"{PROJECT_DATA_FOLDER_NAME}/annotations_rectangles.json": (
        "Optional rectangle-only COCO JSON export."
    ),
    f"{PROJECT_DATA_FOLDER_NAME}/model.conf": (
        "Folder model weights, threshold, class order, and default class."
    ),
    f"{PROJECT_DATA_FOLDER_NAME}/classes.json": (
        "Folder annotation class names and display colours."
    ),
    f"{PROJECT_DATA_FOLDER_NAME}/audit_events.jsonl": (
        "Optional human-readable annotation audit backup."
    ),
    f"{PROJECT_DATA_FOLDER_NAME}/deletion_marks.json": (
        "Images marked for deletion on the next confirmed save."
    ),
}


class CasePreservingConfigParser(configparser.ConfigParser):
    """INI parser that preserves README key spelling.

    README output is user-visible, so fields and filenames keep the spelling
    written by Teacup Annotator and archive generation instead of
    `configparser`'s default lowercasing.
    """

    def optionxform(self, optionstr: str) -> str:
        """Return option names unchanged for stable README output."""

        return optionstr


def read_project_metadata(
    folder: Path | None,
    defaults: dict[str, str],
) -> dict[str, str]:
    """Return active project metadata from defaults plus folder README values.

    The mapping always contains every supported key. Without a folder, global
    preferences are active metadata; with a folder README, `[project]` values
    take precedence, including intentionally blank values.
    """

    # Start from global defaults so the Configuration window has complete fields
    # before a folder exists and before a README has been written.
    values = {key: defaults.get(key, "") for key in PROJECT_METADATA_KEYS}
    if folder is None or not project_file_path(folder, README_FILENAME).is_file():
        return values
    parser = CasePreservingConfigParser(interpolation=None)
    parser.read(project_file_path(folder, README_FILENAME), encoding="utf-8")
    if parser.has_section("project"):
        # README keys are matched case-insensitively on read so older/manual
        # edits can vary spelling while writes still use canonical key names.
        project_values = {key.casefold(): value for key, value in parser.items("project", raw=True)}
        for key in PROJECT_METADATA_KEYS:
            if key in project_values:
                values[key] = project_values[key].strip()
    return values


def write_project_metadata(
    folder: Path,
    values: dict[str, str],
    *,
    image_paths: Iterable[Path] = (),
    record_save: bool = False,
    model_weights_file: str | None = None,
) -> Path:
    """Write project README metadata, provenance, and optional file inventory.

    Unknown sections are preserved so future/manual README fields are not lost.
    Configuration owns `[project]`, saves/model runs refresh `[provenance]`,
    and explicit Save rebuilds `[files]` because it describes current artifacts.
    """

    project_folder = project_data_folder(folder)
    project_folder.mkdir(exist_ok=True)
    path = project_folder / README_FILENAME
    parser = CasePreservingConfigParser(interpolation=None)
    # Preserve existing sections before updating the fields owned by the app.
    if path.is_file():
        parser.read(path, encoding="utf-8")
    if not parser.has_section("project"):
        parser.add_section("project")
    # Canonical key order keeps README diffs predictable and matches Project.
    for key in PROJECT_METADATA_KEYS:
        parser.set("project", key, values.get(key, "").strip())

    if record_save or model_weights_file is not None:
        if not parser.has_section("provenance"):
            parser.add_section("provenance")
        if record_save:
            saved_at = datetime.now().astimezone().isoformat(timespec="seconds")
            parser.set("provenance", "last_save_date_time", saved_at)
            parser.set("provenance", "annotator_name", APP_NAME)
            parser.set("provenance", "annotator_version", APP_VERSION)
            parser.set("provenance", "annotator_zenodo_doi", APP_ZENODO_DOI)
        # Model runs may record weights provenance without claiming a full save.
        if model_weights_file is not None:
            parser.set("provenance", "model_weights_file", model_weights_file)

    # File inventory is rebuilt only for explicit Save; otherwise model-result
    # provenance updates should not rewrite artifact listings.
    if record_save:
        image_paths = tuple(image_paths)
        parser.remove_section("files")
        parser.add_section("files")
        for filename, description in FILE_DESCRIPTIONS.items():
            # README always describes itself, even before other artifacts exist.
            if filename == f"{PROJECT_DATA_FOLDER_NAME}/{README_FILENAME}" or (
                folder / filename
            ).is_file():
                parser.set("files", filename, description)
        # Images and per-image backups come from the loaded image set.
        if any(image_path.is_file() for image_path in image_paths):
            parser.set("files", "*.jpg / *.jpeg", "Source images loaded for annotation.")
        if any(
            image_annotation_path(folder, image_path.name).is_file()
            for image_path in image_paths
        ):
            parser.set(
                "files",
                f"{PROJECT_DATA_FOLDER_NAME}/pi_json/<image-filename>.json",
                "Optional per-image annotation backup files.",
            )
        crop_output_folder = crops_folder(folder)
        if any(crop_output_folder.glob("*/annotations.json")):
            parser.set(
                "files",
                f"{PROJECT_DATA_FOLDER_NAME}/crops/<class>/annotations.json",
                "Crop-coordinate COCO annotations grouped by class.",
            )
        if any(crop_output_folder.glob("*/*.jpg")):
            parser.set(
                "files",
                f"{PROJECT_DATA_FOLDER_NAME}/crops/<class>/<source>_<crop>.jpg",
                "Padded annotation crop images grouped by class.",
            )

    with path.open("w", encoding="utf-8") as readme_file:
        parser.write(readme_file)
    return path
