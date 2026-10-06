"""Discover loadable project images before loading a folder.

This module owns the first non-GUI project-loading step: reconcile any
interrupted image-deletion moves, identify source JPEG files that should enter
a project, and return them in deterministic display/load order.

It does not prompt users, perform full SQLite project loading, import
annotations, apply image filters, load image pixels, or publish state into the
GUI. Those responsibilities live in GUI project loading and
``annotator.project.loading``.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

import annotator.sqlite as sql_backend

IMAGE_EXTENSIONS = {".jpg", ".jpeg"}


@dataclass(frozen=True, slots=True)
class ProjectDiscovery:
    """Named result record for one project-folder discovery pass.

    ``discover_project`` performs the filesystem inspection when the GUI asks
    to load a folder; this dataclass is only the structured return value.
    Keeping the folder and ordered image paths together makes the
    project-loading handoff clearer than passing a tuple.

    ``frozen`` prevents callers from rebinding fields accidentally, and
    ``slots`` keeps the available fields explicit. The ``image_paths`` list
    itself remains a normal list because later GUI state keeps a mutable
    filtered copy separately.

    CODEX: Reconciled deletion names are carried forward so loading can update
    compatibility deletion marks without repeating the filesystem check.
    """

    folder: Path
    image_paths: list[Path]
    completed_deletion_names: frozenset[str] = field(default_factory=frozenset)
    restored_deletion_names: frozenset[str] = field(default_factory=frozenset)


def is_loadable_image_file(path: Path) -> bool:
    """Return whether ``path`` is a visible source JPEG for project loading.

    Only regular ``.jpg`` and ``.jpeg`` files are loadable. Dot-prefixed files,
    including macOS metadata files such as ``.DS_Store`` and resource-fork
    files such as ``._image.jpg``, are skipped before extension checks so
    filesystem metadata does not appear as annotatable images.
    """

    name = path.name
    is_regular_file = path.is_file()
    is_visible_file = not name.startswith(".")
    has_supported_extension = path.suffix.lower() in IMAGE_EXTENSIONS
    filtered = is_regular_file and is_visible_file and has_supported_extension
    return filtered


def discover_project(folder: Path) -> ProjectDiscovery:
    """Return a reconciled, case-insensitively ordered discovery result.

    Deletion reconciliation runs before folder enumeration so interrupted
    source/trash moves are resolved before the image list is built. The
    returned paths include only loadable source images, sorted by case-folded
    filename for stable display and processing order across platforms.
    """

    # Resolve pending source/trash moves before deciding which images are loadable.
    completed_names, restored_names = sql_backend.reconcile_folder_image_deletions(
        folder
    )
    # Stable case-insensitive ordering keeps load order predictable across filesystems.
    image_paths = sorted(
        (path for path in folder.iterdir() if is_loadable_image_file(path)),
        key=lambda path: path.name.casefold(),
    )
    return ProjectDiscovery(
        folder=folder,
        image_paths=image_paths,
        completed_deletion_names=frozenset(completed_names),
        restored_deletion_names=frozenset(restored_names),
    )
