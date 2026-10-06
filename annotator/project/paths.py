"""Define canonical paths inside a loaded image project.

This module owns the folder names and path builders for Teacup-managed project
artifacts under the user-selected image folder. Keeping the names beside the
helpers gives callers one source for the ``teacup/`` layout without turning
project constants into a generic variable module.

The helpers only construct paths. They do not create directories, check
existence, read or write project files, decide which images are loadable, or
manage GUI prompts; those effects belong to the workflow that asked for the
path.
"""

from __future__ import annotations

from pathlib import Path


# These names are user-visible in manuals, prompts, archives, and backups, so
# keep them centralized with the path builders that apply them.
PROJECT_DATA_FOLDER_NAME = "teacup"
PER_IMAGE_JSON_FOLDER_NAME = "pi_json"
STATISTICS_FOLDER_NAME = "statistics"
CROPS_FOLDER_NAME = "crops"


def project_data_folder(folder: Path) -> Path:
    """Return the Teacup-managed project data folder under ``folder``.

    ``folder`` is the user-selected source image folder. The returned path is
    constructed only; callers decide whether to create it, require it to exist,
    or report an error.
    """

    return folder / PROJECT_DATA_FOLDER_NAME


def project_file_path(folder: Path, filename: str) -> Path:
    """Return the path for one Teacup-managed project file.

    ``filename`` is interpreted relative to ``teacup/``. This helper is for
    stable project artifacts such as SQLite state, README metadata, audit
    backups, model settings, class settings, and deletion state. It does not
    create parent directories or validate whether the named file belongs to a
    particular workflow.
    """

    return project_data_folder(folder) / filename


def per_image_json_folder(folder: Path) -> Path:
    """Return the folder for per-image JSON backup files.

    Per-image JSON files mirror annotations outside SQLite for recovery and
    interchange. This helper only constructs the directory path; save and delete
    workflows own directory creation, cleanup, and whether those backups are
    enabled.
    """

    return project_data_folder(folder) / PER_IMAGE_JSON_FOLDER_NAME


def statistics_folder(folder: Path) -> Path:
    """Return the folder for derived session statistics CSV files.

    Session statistics are generated outputs under ``teacup/statistics``. This
    helper only names their directory; logging and statistics workflows own
    creation, refresh timing, and file contents.
    """

    return project_data_folder(folder) / STATISTICS_FOLDER_NAME


def crops_folder(folder: Path) -> Path:
    """CODEX: Return the folder for Save-generated annotation crop exports.

    CODEX: Each class owns a subfolder of maximum-quality JPEG crops and one
    crop-coordinate ``annotations.json``. This helper constructs the path only;
    the crop export workflow owns replacement and cleanup.
    """

    return project_data_folder(folder) / CROPS_FOLDER_NAME
