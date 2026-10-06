"""CODEX: Navigate image lists while keeping the index aligned with loaded pixels."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from typing import Any
from typing import Protocol
from typing import cast

from annotator.gui.audit.events import write_audit_event
from annotator.gui.state import ProjectState
from annotator.log.audit import VIEW_AUDIT_ACTION
from annotator.preferences import Preferences


class CurrentImageHost(Protocol):
    """CODEX: Project state required to name the current image."""

    project: ProjectState


class ImagePositionHost(CurrentImageHost, Protocol):
    """CODEX: Preferences and project state required for image position persistence."""

    prefs: Preferences


class NavigationHost(ImagePositionHost, Protocol):
    """CODEX: Application state required by interactive navigation actions."""

    root: tk.Tk
    image_index_var: tk.StringVar


class ViewAuditHost(ImagePositionHost, Protocol):
    """CODEX: Application state and audit effect required by view recording."""

    def log(self, message: str) -> None:
        """CODEX: Record one view-audit message."""

        ...


def _navigate_to_image_index(host: NavigationHost, image_index: int) -> None:
    """CODEX: Restore the published image index when decoding its target fails."""

    previous_index = host.project.current_index
    host.project.current_index = image_index
    from annotator.gui.project.image_loading import load_current_image

    if load_current_image(cast(Any, host)):
        return
    # CODEX: The old pixels remain active, so their image index must remain active too.
    host.project.current_index = previous_index


def previous_image(host: NavigationHost) -> None:
    """CODEX: Navigate backward while preserving the prior target on failure."""

    if host.project.current_index > 0:
        _navigate_to_image_index(host, host.project.current_index - 1)


def next_image(host: NavigationHost) -> None:
    """CODEX: Navigate forward while preserving the prior target on failure."""

    # CMP: TODO - I think this check should be done when the image loads,
    # so that we can, for instance, make the 'Next' button inactive.
    if host.project.current_index + 1 < len(host.project.image_paths):
        _navigate_to_image_index(host, host.project.current_index + 1)


def jump_to_image_index_from_entry(
    host: NavigationHost,
    _event: tk.Event | None = None,
) -> str:
    """CODEX: Try a one-based index while preserving the prior target on failure."""

    from annotator.gui.project.status import update_image_index_entry

    if not host.project.image_paths:
        update_image_index_entry(cast(Any, host), force=True)
        return "break"
    value = host.image_index_var.get().strip()
    try:
        requested_index = int(value)
    except ValueError:
        host.root.bell()
        update_image_index_entry(cast(Any, host), force=True)
        return "break"
    if requested_index < 1 or requested_index > len(host.project.image_paths):
        host.root.bell()
        update_image_index_entry(cast(Any, host), force=True)
        return "break"
    new_index = requested_index - 1
    if new_index != host.project.current_index:
        _navigate_to_image_index(host, new_index)
    else:
        update_image_index_entry(cast(Any, host), force=True)
    return "break"


def remembered_image_index_for_folder(
    host: ImagePositionHost,
    folder: Path,
    image_paths: list[Path],
) -> int:
    """CODEX: Return the last viewed image index for this folder when available."""

    last_image_name = remembered_image_name_for_folder(host, folder)
    if last_image_name:
        for index, image_path in enumerate(image_paths):
            if image_path.name == last_image_name:
                return index
    try:
        # CMP: TODO - Justify the type casting here. I think the return of the
        # get function here is always a string?
        last_index = int(host.prefs.values.get("last_image_index", "").strip())
    except ValueError:
        return 0
    if 0 <= last_index < len(image_paths):
        return last_index
    return 0


def remembered_image_name_for_folder(
    host: ImagePositionHost,
    folder: Path,
) -> str | None:
    """CODEX: Return the persisted last image name for a folder."""

    if host.prefs.values.get("last_image_folder", "").strip() != str(folder):
        return None
    last_image_name = host.prefs.values.get("last_image_name", "").strip()
    if last_image_name:
        return last_image_name
    return None


def persist_current_image_position(host: ImagePositionHost) -> None:
    """CODEX: Save the current folder/image position for the next app launch."""

    if host.project.folder is None or not host.project.image_paths:
        return
    values = {
        "last_image_folder": str(host.project.folder),
        "last_image_name": current_image_name(host),
        "last_image_index": str(host.project.current_index),
    }
    changed = False
    for key, value in values.items():
        if host.prefs.values.get(key) != value:
            host.prefs.values[key] = value
            changed = True
    if changed:
        host.prefs.save()


def record_current_image_view(host: ViewAuditHost) -> None:
    """CODEX: Append a view event for the current image."""

    if host.project.folder is None or not host.project.image_paths:
        return
    image_name = current_image_name(host)
    write_audit_event(
        host,
        action=VIEW_AUDIT_ACTION,
        before_state=None,
        after_state={
            "image_name": image_name,
            "image_index": host.project.current_index,
            "source_table": "project_images",
        },
        details={
            "image_name": image_name,
            "image_index": host.project.current_index,
            "view_index": host.project.current_index + 1,
        },
        source_table="project_images",
    )


def current_image_name(host: CurrentImageHost) -> str:
    """CODEX: Return the basename of the current image."""

    return host.project.image_paths[host.project.current_index].name
