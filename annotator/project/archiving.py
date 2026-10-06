"""Inspect project readiness before distribution archive prompts.

This module owns the project-level facts the GUI needs before asking the user
to create an archive: the required class definitions file path and the required
project metadata keys that are still empty.

It does not create ZIP files, snapshot SQLite, regenerate COCO exports, write
checksums, show dialogs, open Configuration, or decide whether the user wants
to continue. ZIP packaging lives in ``annotator.archive``; GUI prompting lives
in ``annotator.gui.project.archive``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from annotator.archive import CLASS_DEFINITIONS_FILENAME
from annotator.archive import missing_archive_metadata
from annotator.project.paths import project_file_path


@dataclass(frozen=True, slots=True)
class ArchiveReadiness:
    """Immutable result record for one archive readiness inspection.

    ``inspect_archive_readiness`` is the function that performs the check when
    the GUI needs it; this dataclass is only the named return value. It keeps
    the related facts together without giving them behavior of their own.

    ``class_definitions_path`` is returned even when the file is missing so the
    GUI can show the exact required location. ``class_definitions_present`` and
    ``missing_metadata_keys`` remain separate facts because the archive workflow
    reports missing class definitions before metadata.

    ``frozen`` makes the object a snapshot of readiness at inspection time, and
    ``slots`` keeps the available fields explicit and lightweight.
    """

    class_definitions_path: Path
    class_definitions_present: bool
    missing_metadata_keys: tuple[str, ...]


def inspect_archive_readiness(
    folder: Path,
    project_metadata: dict[str, str],
) -> ArchiveReadiness:
    """Return archive readiness facts without GUI or packaging effects.

    The caller supplies already-loaded project metadata. This function checks
    only whether the required class definitions file exists and delegates the
    required metadata-key policy to ``annotator.archive.missing_archive_metadata``.

    It does not create folders, open files, prompt users, mutate project state,
    or start archive creation.
    """

    # The GUI needs the expected path for its error message even when it is absent.
    class_definitions_path = project_file_path(folder, CLASS_DEFINITIONS_FILENAME)
    return ArchiveReadiness(
        class_definitions_path=class_definitions_path,
        class_definitions_present=class_definitions_path.is_file(),
        # Keep the required metadata policy shared with archive packaging constants.
        missing_metadata_keys=missing_archive_metadata(project_metadata),
    )
