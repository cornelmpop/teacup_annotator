"""Configuration-window tab builders."""

from __future__ import annotations

from functools import partial
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from annotator.gui.interactions import bind_canvas_wheel

if TYPE_CHECKING:
    from annotator.config_window import ConfigurationWindow


def build_project_tab(self: ConfigurationWindow) -> None:
    """Build editable author and project metadata controls."""

    self.project_tab.columnconfigure(0, weight=1)
    self.project_tab.rowconfigure(0, weight=1)
    # TODO: Move configuration editor chrome and text-field colours to
    # annotator/gui/theme.py with the other GUI palette constants.
    background = ttk.Style(self.window).lookup("TFrame", "background") or "#f0f0f0"
    self.project_canvas = tk.Canvas(
        self.project_tab,
        background=background,
        highlightthickness=0,
    )
    project_scrollbar = ttk.Scrollbar(
        self.project_tab,
        orient=tk.VERTICAL,
        command=self.project_canvas.yview,
    )
    self.project_canvas.configure(yscrollcommand=project_scrollbar.set)
    self.project_canvas.grid(row=0, column=0, sticky="nsew")
    project_scrollbar.grid(row=0, column=1, sticky="ns")

    project_form = ttk.Frame(self.project_canvas)
    project_form.columnconfigure(1, weight=1)
    project_window = self.project_canvas.create_window(
        (0, 0),
        window=project_form,
        anchor="nw",
    )
    project_form.bind(
        "<Configure>",
        lambda _event: self.project_canvas.configure(
            scrollregion=self.project_canvas.bbox("all")
        ),
    )
    self.project_canvas.bind(
        "<Configure>",
        lambda event: self.project_canvas.itemconfigure(
            project_window,
            width=event.width,
        ),
    )

    for row, key in enumerate(self.PROJECT_LINE_KEYS):
        self.add_labeled_entry(project_form, row, key, width=68)

    self.project_text_widgets = {}
    for row, key in enumerate(
        self.PROJECT_TEXT_KEYS,
        start=len(self.PROJECT_LINE_KEYS),
    ):
        ttk.Label(
            project_form,
            text=self.LABELS[key],
        ).grid(row=row, column=0, sticky="nw", padx=(0, 8), pady=2)
        text_widget = tk.Text(
            project_form,
            height=5,
            wrap=tk.WORD,
            background="white",
            foreground="black",
            insertbackground="black",
        )
        scrollbar = ttk.Scrollbar(
            project_form,
            orient=tk.VERTICAL,
            command=text_widget.yview,
        )
        text_widget.configure(yscrollcommand=scrollbar.set)
        text_widget.grid(row=row, column=1, sticky="ew", pady=2)
        scrollbar.grid(row=row, column=2, sticky="ns", pady=2)
        self.project_text_widgets[key] = text_widget

    bind_canvas_wheel(self.project_canvas, self._on_project_wheel)
    bind_canvas_wheel(project_form, self._on_project_wheel)
    for widget in project_form.winfo_children():
        if not isinstance(widget, tk.Text):
            bind_canvas_wheel(widget, self._on_project_wheel)


def build_model_tab(self: ConfigurationWindow) -> None:
    """Build model and default-class controls."""

    self.model_tab.columnconfigure(1, weight=1)
    row = 0
    ttk.Button(
        self.model_tab,
        text="Load model profile...",
        command=self.choose_model_profile,
    ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
    row += 1
    for key in self.MODEL_KEYS:
        if key in self.FOLDER_MODEL_KEYS:
            continue
        if key == "default_class":
            ttk.Label(
                self.model_tab,
                text=self.LABELS[key],
            ).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            variable = self.vars.setdefault(
                key,
                tk.StringVar(master=self.window),
            )
            self.default_class_combo = ttk.Combobox(
                self.model_tab,
                textvariable=variable,
                state="readonly",
                width=66,
            )
            self.default_class_combo.grid(
                row=row,
                column=1,
                sticky="ew",
                pady=2,
            )
            row += 1
            continue
        self.add_labeled_entry(self.model_tab, row, key, width=68)
        if key == "model_weights":
            ttk.Button(
                self.model_tab,
                text="Browse",
                command=self.choose_model_weights,
            ).grid(row=row, column=2, sticky="w", padx=(4, 0), pady=2)
        row += 1


def build_behavior_tab(self: ConfigurationWindow) -> None:
    """Build behavior and numeric preference controls."""

    self.behavior_tab.columnconfigure(1, weight=1)
    row = 0
    for key in self.BOOLEAN_KEYS:
        variable = tk.BooleanVar(master=self.window)
        self.bool_vars[key] = variable
        ttk.Checkbutton(
            self.behavior_tab,
            text=self.LABELS.get(key, key),
            variable=variable,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
        row += 1
    ttk.Separator(self.behavior_tab).grid(
        row=row, column=0, columnspan=2, sticky="ew", pady=8
    )
    row += 1
    for key in self.BEHAVIOR_KEYS:
        self.add_labeled_entry(self.behavior_tab, row, key, width=18)
        row += 1


def build_colour_tab(self: ConfigurationWindow) -> None:
    """Build non-class colour controls."""

    self.colour_tab.columnconfigure(1, weight=1)
    for row, key in enumerate(self.COLOUR_KEYS):
        self.add_labeled_entry(self.colour_tab, row, key, width=18)
        ttk.Button(
            self.colour_tab,
            text="Choose",
            command=partial(self.choose_colour, key),
        ).grid(row=row, column=2, sticky="w", padx=(4, 0), pady=2)


def build_keys_tab(self: ConfigurationWindow) -> None:
    """Build key-binding controls."""

    self.keys_tab.columnconfigure(1, weight=1)
    for row, key in enumerate(self.key_binding_keys):
        self.add_labeled_entry(
            self.keys_tab,
            row,
            key,
            label=key.replace("key_binding_", "").replace("_", " "),
            width=8,
        )
