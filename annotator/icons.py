"""Load packaged logo and toolbar images for Tk widgets.

This module is the GUI boundary for image resources: resource lookup stays in
`annotator.resources`, while this module converts packaged PNG files into Tk
image objects owned by the root window. Callers must keep references to the
returned images because Tk can otherwise garbage-collect images still assigned
to widgets.
"""

from __future__ import annotations

import tkinter as tk

from PIL import Image
from PIL import ImageTk

from annotator.resources import packaged_icon_path

# Toolbar icon keys match packaged PNG stems.
TOOLBAR_ICON_NAMES = (
    "load",
    "run",
    "save",
    "archive",
    "config",
    "delete",
    "reset_zoom",
    "restore",
    "flag",
    "flag_off",
)


def create_logo_photo(root: tk.Tk) -> tk.PhotoImage:
    """Return the packaged window logo as a root-owned Tk image.

    The caller stores the returned object on the app so the window icon remains
    alive for the life of the Tk process.
    """

    with packaged_icon_path("logo_trans.png") as path:
        return tk.PhotoImage(master=root, file=str(path))


def create_toolbar_icons(root: tk.Tk) -> dict[str, ImageTk.PhotoImage]:
    """Return root-owned toolbar icon images keyed by widget-facing icon name.

    Icons are loaded from packaged PNG resources and converted to RGBA before
    becoming `ImageTk.PhotoImage` objects, preserving alpha transparency for
    toolbar buttons.
    """

    icons: dict[str, ImageTk.PhotoImage] = {}
    for name in TOOLBAR_ICON_NAMES:
        with packaged_icon_path(f"{name}.png") as path, Image.open(path) as image:
            # Convert through Pillow so every toolbar icon has an RGBA image
            # with alpha.
            icons[name] = ImageTk.PhotoImage(image.convert("RGBA"), master=root)
    return icons
