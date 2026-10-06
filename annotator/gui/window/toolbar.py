"""Build the application toolbar."""

from __future__ import annotations

from functools import partial
import tkinter as tk
from tkinter import ttk
from typing import cast

from annotator.gui.display import FILTER_ALL
from annotator.gui.display import FILTER_NULL
from annotator.gui.model.run import ModelRunHost
from annotator.gui.model.run import run_model
from annotator.gui.project.archive import archive_folder
from annotator.gui.project.deletion import mark_current_image_for_deletion
from annotator.gui.project.filtering import apply_selected_filter
from annotator.gui.project.folder_loading import load_folder_dialog
from annotator.gui.project.review import toggle_current_image_review
from annotator.gui.project.review import toggle_flagged_view
from annotator.gui.project.save import save_annotations
from annotator.gui.tooltip import ToolTip
from annotator.gui.window.state import ToolbarWidgets
from annotator.gui.window.state import WindowHost


def build_toolbar(host: WindowHost) -> ToolbarWidgets:
    """Create toolbar widgets with commands bound to the application host."""

    toolbar = ttk.Frame(host.root, padding=(8, 6, 8, 4))
    toolbar.grid(row=0, column=0, sticky="ew")
    toolbar.columnconfigure(13, weight=1)

    load_button = ttk.Button(
        toolbar,
        image=host.toolbar_icons["load"],
        command=partial(load_folder_dialog, host),
        width=3,
    )
    load_button.grid(row=0, column=0, sticky="w")
    ToolTip(load_button, "Load")

    run_button = ttk.Button(
        toolbar,
        image=host.toolbar_icons["run"],
        command=partial(run_model, cast(ModelRunHost, host)),
        width=3,
    )
    run_button.grid(row=0, column=1, sticky="w", padx=(4, 0))
    ToolTip(run_button, "Run model")

    save_button = ttk.Button(
        toolbar,
        image=host.toolbar_icons["save"],
        command=partial(save_annotations, host),
        width=3,
    )
    save_button.grid(row=0, column=2, sticky="w", padx=(4, 0))
    ToolTip(save_button, "Save")

    archive_button = ttk.Button(
        toolbar,
        image=host.toolbar_icons["archive"],
        command=partial(archive_folder, host),
        width=3,
    )
    archive_button.grid(row=0, column=3, sticky="w", padx=(4, 0))
    ToolTip(archive_button, "Archive")

    config_button = ttk.Button(
        toolbar,
        image=host.toolbar_icons["config"],
        command=host.open_config_window,
        width=3,
    )
    config_button.grid(row=0, column=4, sticky="w", padx=(4, 0))
    ToolTip(config_button, "Configuration")
    ttk.Separator(toolbar, orient=tk.VERTICAL).grid(
        row=0,
        column=5,
        sticky="ns",
        padx=(10, 6),
    )

    filter_dropdown = ttk.OptionMenu(
        toolbar,
        host.filter_var,
        FILTER_ALL,
        FILTER_ALL,
        FILTER_NULL,
    )
    filter_dropdown.grid(row=0, column=6, sticky="w")
    ToolTip(filter_dropdown, "Class filter")
    filter_button = ttk.Button(
        toolbar,
        text="Filter by class",
        command=partial(apply_selected_filter, host),
    )
    filter_button.grid(row=0, column=7, sticky="w", padx=(4, 0))
    view_flagged_button = ttk.Button(
        toolbar,
        text="View flagged",
        command=partial(toggle_flagged_view, host),
    )
    view_flagged_button.grid(row=0, column=8, sticky="w", padx=(4, 0))
    ttk.Separator(toolbar, orient=tk.VERTICAL).grid(
        row=0,
        column=9,
        sticky="ns",
        padx=(10, 6),
    )

    delete_image_button = ttk.Button(
        toolbar,
        image=host.toolbar_icons["delete"],
        command=partial(mark_current_image_for_deletion, host),
        width=3,
    )
    delete_image_button.grid(row=0, column=10, sticky="w")
    delete_image_tooltip = ToolTip(delete_image_button, "Delete")
    reset_zoom_button = ttk.Button(
        toolbar,
        image=host.toolbar_icons["reset_zoom"],
        command=host.reset_zoom,
        width=3,
    )
    reset_zoom_button.grid(row=0, column=11, sticky="w", padx=(4, 0))
    ToolTip(reset_zoom_button, "Reset zoom")
    flag_review_button = ttk.Button(
        toolbar,
        image=host.toolbar_icons["flag"],
        command=partial(toggle_current_image_review, host),
        width=3,
    )
    flag_review_button.grid(row=0, column=12, sticky="w", padx=(4, 0))
    ToolTip(flag_review_button, "Flag for review")
    return ToolbarWidgets(
        load_button=load_button,
        run_button=run_button,
        save_button=save_button,
        archive_button=archive_button,
        config_button=config_button,
        filter_dropdown=filter_dropdown,
        view_flagged_button=view_flagged_button,
        filter_button=filter_button,
        delete_image_button=delete_image_button,
        delete_image_tooltip=delete_image_tooltip,
        reset_zoom_button=reset_zoom_button,
        flag_review_button=flag_review_button,
    )
