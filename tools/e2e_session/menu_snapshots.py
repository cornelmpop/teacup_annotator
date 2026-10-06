"""CODEX: Serialize replay-captured Tk menus for golden comparison."""

from __future__ import annotations

from typing import Any
import tkinter as tk


def menu_snapshot(menu: tk.Menu) -> list[dict[str, Any]]:
    """CODEX: Return visible menu entries in deterministic nested form."""

    end_index = menu.index("end")
    if end_index is None:
        return []
    entries = []
    for index in range(end_index + 1):
        entry_type = str(menu.type(index))
        if entry_type == "tearoff":
            continue
        if entry_type == "separator":
            entries.append({"type": "separator"})
            continue
        entry = {
            "type": entry_type,
            "label": str(menu.entrycget(index, "label")),
            "state": str(menu.entrycget(index, "state") or tk.NORMAL),
        }
        accelerator = str(menu.entrycget(index, "accelerator") or "")
        if accelerator:
            entry["accelerator"] = accelerator
        if entry_type == "cascade":
            submenu_name = str(menu.entrycget(index, "menu"))
            submenu = menu.nametowidget(submenu_name)
            entry["entries"] = menu_snapshot(submenu)
        entries.append(entry)
    return entries
