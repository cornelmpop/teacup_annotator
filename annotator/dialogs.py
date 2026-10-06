"""Own custom Tk dialogs that need persistent classic-widget styling.

Most simple prompts stay at their call sites through `tkinter.messagebox`.
This module contains dialogs that need custom buttons, scrollable/copyable
details, colour picking, progress updates, or modal state. Its local palette
constants are a temporary classic-Tk styling boundary until shared GUI colours
move into `annotator.gui.theme`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser
from tkinter import messagebox
from tkinter import scrolledtext
from tkinter import simpledialog
from tkinter import ttk
from typing import Any
from typing import cast

from annotator.class_names import class_name_error
from annotator.preferences.validation import is_hex_colour


LOCAL_CLASS_PROMPT = (
    "Folder-specific annotation classes were found in classes.json. Would you "
    "like to use them, or use the classes already present in the annotations "
    "(falling back to the application default for an empty folder)?"
)
# TODO: Move these classic Tk dialog palette constants to annotator/gui/theme.py
# with the related class-panel and window canvas colours once the app has one
# shared theme boundary.
DIALOG_BACKGROUND = "#f0f0f0"
DIALOG_FOREGROUND = "#000000"
DIALOG_BUTTON_BACKGROUND = "#e6e6e6"
DIALOG_ACTIVE_BACKGROUND = "#d0d0d0"
DIALOG_BUTTON_STYLE: dict[str, Any] = {
    "background": DIALOG_BUTTON_BACKGROUND,
    "foreground": DIALOG_FOREGROUND,
    "activebackground": DIALOG_ACTIVE_BACKGROUND,
    "activeforeground": DIALOG_FOREGROUND,
    "highlightbackground": DIALOG_BACKGROUND,
}


class LocalClassSourceDialog(simpledialog.Dialog):
    """Modal choice for using folder-local classes or annotation/default classes.

    The custom button order matches the user-facing class-source decision, so it
    cannot be replaced cleanly with a generic messagebox.
    """

    result: str | None

    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, title="Choose annotation classes")

    def body(self, master: tk.Misc) -> None:
        """Build the custom/default question shown by the modal dialog."""

        self.configure(background=DIALOG_BACKGROUND)
        cast(Any, master).configure(background=DIALOG_BACKGROUND)
        tk.Label(
            master,
            text=LOCAL_CLASS_PROMPT,
            wraplength=420,
            justify=tk.LEFT,
            background=DIALOG_BACKGROUND,
            foreground=DIALOG_FOREGROUND,
        ).pack(padx=12, pady=(12, 6))

    def buttonbox(self) -> None:
        """Create the two requested buttons in custom/default order."""

        box = tk.Frame(self, background=DIALOG_BACKGROUND)
        tk.Button(
            box,
            text="Use folder classes",
            command=lambda: self._choose("custom"),
            **DIALOG_BUTTON_STYLE,
        ).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(
            box,
            text="Use annotation/default classes",
            command=lambda: self._choose("defaults"),
            **DIALOG_BUTTON_STYLE,
        ).pack(side=tk.LEFT)
        box.pack(padx=12, pady=(6, 12))
        self.bind("<Escape>", self.cancel)

    def _choose(self, result: str) -> None:
        """Record one of the two explicit choices and close the dialog."""

        self.result = result
        self.cancel()


class NewLocalClassDialog(simpledialog.Dialog):
    """CODEX: Collect a valid new class name and display colour.

    The shared class-name contract owns syntax and case-insensitive uniqueness.
    This dialog owns the classic Tk entry, colour picker, and error display.
    """

    result: tuple[str, str] | None

    def __init__(
        self,
        root: tk.Tk,
        existing_names: tuple[str, ...],
        initial_colour: str,
    ) -> None:
        self.existing_names = existing_names
        self.initial_colour = initial_colour
        super().__init__(root, title="Add annotation class")

    def body(self, master: tk.Misc) -> tk.Entry:
        """Build name and colour controls and return the initial entry."""

        self.configure(background=DIALOG_BACKGROUND)
        cast(Any, master).configure(background=DIALOG_BACKGROUND)
        self.name_var = tk.StringVar(master=self)
        self.colour_var = tk.StringVar(master=self, value=self.initial_colour)
        class_name_label = tk.Label(
            master, text="Class name", background=DIALOG_BACKGROUND,
            foreground=DIALOG_FOREGROUND,
        )
        class_name_label.grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=(0, 8),
        )
        self.name_entry = tk.Entry(
            master,
            textvariable=self.name_var,
            width=32,
            background="#ffffff",
            foreground=DIALOG_FOREGROUND,
            insertbackground=DIALOG_FOREGROUND,
        )
        self.name_entry.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(0, 8))
        colour_label = tk.Label(
            master, text="Colour", background=DIALOG_BACKGROUND,
            foreground=DIALOG_FOREGROUND,
        )
        colour_label.grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 8),
        )
        self.colour_swatch = tk.Canvas(
            master,
            width=20,
            height=20,
            background=self.initial_colour,
            highlightthickness=1,
            highlightbackground="#777777",
        )
        self.colour_swatch.grid(row=1, column=1, sticky="w")
        choose_button = tk.Button(
            master,
            text="Choose colour",
            command=self._choose_colour,
            **DIALOG_BUTTON_STYLE,
        )
        choose_button.grid(
            row=1,
            column=2,
            sticky="w",
            padx=(8, 0),
        )
        return self.name_entry

    def buttonbox(self) -> None:
        """Create compact Add and Cancel buttons for the modal dialog."""

        box = tk.Frame(self, background=DIALOG_BACKGROUND)
        add_button = tk.Button(
            box, text="Add", command=self.ok, **DIALOG_BUTTON_STYLE
        )
        cancel_button = tk.Button(
            box, text="Cancel", command=self.cancel, **DIALOG_BUTTON_STYLE
        )
        add_button.pack(side=tk.LEFT, padx=(0, 6))
        cancel_button.pack(side=tk.LEFT)
        box.pack(pady=(6, 12))
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

    def _choose_colour(self) -> None:
        """Open the system colour picker and update the visible swatch."""

        _rgb, colour = colorchooser.askcolor(
            color=self.colour_var.get(),
            parent=self,
        )
        if colour:
            self.colour_var.set(colour)
            self.colour_swatch.configure(background=colour)

    def validate(self) -> bool:
        """CODEX: Return whether the entered name and colour can be added."""

        name = self.name_var.get().strip()
        colour = self.colour_var.get().strip()
        name_error = class_name_error((*self.existing_names, name))
        if name_error is not None:
            messagebox.showerror(
                "Invalid class name",
                name_error,
                parent=self,
            )
            return False
        if not is_hex_colour(colour):
            messagebox.showerror(
                "Invalid class colour",
                "Choose a valid class colour.",
                parent=self,
            )
            return False
        return True

    def apply(self) -> None:
        """Store the validated name and colour as the dialog result."""

        self.result = (
            self.name_var.get().strip(),
            self.colour_var.get().strip(),
        )


class ErrorDetailsDialog:
    """CODEX: Resizable details window with selectable text and copy support.

    Long failures and reports need more than a messagebox: users can inspect,
    scroll, select, and copy the original details unchanged. Callers may supply
    a context-specific copy-button label while errors retain ``Copy error``.
    """

    def __init__(
        self,
        root: tk.Tk,
        title: str,
        details: str,
        *,
        copy_button_text: str = "Copy error",
    ) -> None:
        """CODEX: Open one modal details window with caller-owned text."""

        self.details = details
        self.window = tk.Toplevel(root)
        self.window.title(title)
        self.window.transient(root)
        self.window.geometry("900x500")
        self.window.minsize(500, 300)
        self.window.configure(background=DIALOG_BACKGROUND)

        frame = tk.Frame(
            self.window, padx=12, pady=12, background=DIALOG_BACKGROUND
        )
        frame.pack(fill=tk.BOTH, expand=True)
        self.details_text = scrolledtext.ScrolledText(
            frame,
            wrap=tk.WORD,
            background="#ffffff",
            foreground=DIALOG_FOREGROUND,
            insertbackground=DIALOG_FOREGROUND,
        )
        self.details_text.insert("1.0", details)
        self.details_text.configure(state=tk.DISABLED)
        self.details_text.pack(fill=tk.BOTH, expand=True)

        buttons = tk.Frame(frame, background=DIALOG_BACKGROUND)
        buttons.pack(fill=tk.X, pady=(8, 0))
        tk.Button(
            buttons, text=copy_button_text, command=self.copy_details,
            **DIALOG_BUTTON_STYLE
        ).pack(side=tk.LEFT)
        tk.Button(
            buttons, text="Close", command=self.close,
            **DIALOG_BUTTON_STYLE
        ).pack(side=tk.RIGHT)
        self.window.bind("<Escape>", self.close)
        self.window.grab_set()

    def copy_details(self) -> None:
        """CODEX: Copy the complete, unmodified details to the clipboard."""

        self.window.clipboard_clear()
        self.window.clipboard_append(self.details)

    def close(self, _event: tk.Event | None = None) -> None:
        """Close the error-details window."""

        self.window.destroy()


class ProgressDialog:
    """Small non-closable progress window for operations that block editing.

    The window deliberately owns immediate Tk updates so long save/load/model
    workflows can report progress while the main interaction surface is locked.
    """

    def __init__(
        self,
        root: tk.Tk,
        title: str,
        heading: str,
        message: str,
    ) -> None:
        self.root = root
        self.window = tk.Toplevel(root)
        self.window.title(title)
        self.window.transient(root)
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", lambda: None)
        self.window.configure(background=DIALOG_BACKGROUND)
        self.message_var = tk.StringVar(master=self.window, value=message)
        self.progress_var = tk.DoubleVar(master=self.window, value=0)
        frame = tk.Frame(self.window, padx=16, pady=16, background=DIALOG_BACKGROUND)
        frame.grid(row=0, column=0, sticky="nsew")
        tk.Label(
            frame,
            text=heading,
            font=("Helvetica", 13, "bold"),
            background=DIALOG_BACKGROUND,
            foreground=DIALOG_FOREGROUND,
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        tk.Label(
            frame,
            textvariable=self.message_var,
            width=52,
            anchor="w",
            background=DIALOG_BACKGROUND,
            foreground=DIALOG_FOREGROUND,
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(0, 8),
        )
        self.progress = ttk.Progressbar(
            frame,
            maximum=100,
            length=320,
            variable=self.progress_var,
        )
        self.progress.grid(row=2, column=0, sticky="ew")
        self.window.update_idletasks()
        self._center_over_root()
        self.window.update()

    def update_progress(self, value: float, message: str) -> None:
        """Update the operation progress window immediately."""

        self.progress_var.set(value)
        self.message_var.set(message)
        self.window.update_idletasks()
        self.window.update()

    def close(self) -> None:
        """Close the operation progress window."""

        try:
            self.window.destroy()
        except tk.TclError:
            return

    def _center_over_root(self) -> None:
        """Place the dialog near the center of the main window."""

        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_width = max(1, self.root.winfo_width())
        root_height = max(1, self.root.winfo_height())
        dialog_width = self.window.winfo_reqwidth()
        dialog_height = self.window.winfo_reqheight()
        x_coord = root_x + max(0, (root_width - dialog_width) // 2)
        y_coord = root_y + max(0, (root_height - dialog_height) // 2)
        self.window.geometry(f"+{x_coord}+{y_coord}")
