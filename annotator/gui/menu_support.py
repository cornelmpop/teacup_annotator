"""Own menu posting, accelerators, commands, and cascades for Tk menus."""

from __future__ import annotations

import tkinter as tk
from typing import Any
from typing import Callable
from typing import cast
from typing import Literal

from annotator.preferences import DEFAULT_PREFERENCE_VALUES
from annotator.preferences import Preferences


MenuState = Literal["normal", "active", "disabled"]


def menu_binding(
    prefs: Preferences,
    key: str,
    fallback_key: str | None = None,
) -> str:
    """Return one configured single-key menu accelerator."""

    value = prefs.values.get(key, "").strip()
    if value.lower() in {"none", "null"}:
        return ""
    if not value:
        value = fallback_key or DEFAULT_PREFERENCE_VALUES.get(key, "")
    return value.strip()[:1].lower()


def bind_menu_key(
    menu: tk.Menu,
    key: str,
    command: Callable[[], Any],
    enabled: bool = True,
    close_after: bool = True,
) -> None:
    """Bind a single-letter accelerator while a menu is open."""

    normalized = key.strip()[:1].lower()
    if not normalized:
        return

    def invoke(_event: tk.Event) -> str:
        """Invoke one enabled command and consume its Tk key event."""

        if enabled:
            if close_after:
                try:
                    menu.unpost()
                except tk.TclError:
                    pass
            command()
        return "break"

    menu.bind(f"<KeyPress-{normalized}>", invoke)
    menu.bind(f"<KeyPress-{normalized.upper()}>", invoke)


def post_menu(menu: tk.Menu, x_root: int, y_root: int) -> None:
    """Post a menu and give it focus for one-key accelerators."""

    menu.tk_popup(x_root, y_root)
    try:
        menu.focus_set()
    except tk.TclError:
        return


def add_menu_command(
    prefs: Preferences,
    menu: tk.Menu,
    label: str,
    command: Callable[[], Any],
    binding_key: str,
    state: str = tk.NORMAL,
    fallback_key: str | None = None,
) -> None:
    """Add a menu command with its configured keyboard accelerator."""

    key = menu_binding(prefs, binding_key, fallback_key=fallback_key)
    menu.add_command(
        label=label,
        command=command,
        state=cast(MenuState, state),
        accelerator=key,
    )
    bind_menu_key(menu, key, command, enabled=state == tk.NORMAL)


def add_menu_cascade(
    prefs: Preferences,
    menu: tk.Menu,
    label: str,
    submenu: tk.Menu,
    binding_key: str,
    event: tk.Event,
    state: str = tk.NORMAL,
) -> None:
    """Add a submenu cascade with its configured keyboard accelerator."""

    key = menu_binding(prefs, binding_key)
    menu.add_cascade(
        label=label,
        menu=submenu,
        state=cast(MenuState, state),
        accelerator=key,
    )

    # CMP: TODO - Why 18 here? Provide short justification.
    bind_menu_key(
        menu,
        key,
        lambda: post_menu(submenu, event.x_root + 18, event.y_root + 18),
        enabled=state == tk.NORMAL,
        close_after=False,
    )


def class_menu_shortcut_map(class_names: tuple[str, ...]) -> dict[str, str]:
    """Return numeric shortcuts for the first ten active classes."""

    shortcuts: dict[str, str] = {}
    for index, class_name in enumerate(class_names[:10]):
        shortcuts.setdefault(class_name, str(index))
    return shortcuts
