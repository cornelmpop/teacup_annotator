"""Pending-review persistence and toolbar effects."""

from __future__ import annotations

import sqlite3
from tkinter import messagebox
from typing import Protocol

import annotator.sqlite as sql_backend
from annotator.gui.project.filtering import apply_image_filter
from annotator.gui.project.filtering import FilteringHost
from annotator.gui.project.navigation import current_image_name
from annotator.gui.project.status import update_buttons
from annotator.gui.project.status import update_image_status


class ReviewHost(FilteringHost, Protocol):
    """Application state and effects required by review toolbar actions."""


def toggle_current_image_review(host: ReviewHost) -> None:
    """Toggle the current image's durable pending-review status."""

    # CMP: QUESTION - Under what valid app state would this function
    # be called when this condition is met?
    if (
        host.project.sql_connection is None
        or host.project.coco is None
        or not host.project.image_paths
    ):
        return
    image_name = current_image_name(host)
    pending_review = image_name not in host.project.review_flags
    try:
        sql_backend.persist_image_review_flag(
            host.project.sql_connection,
            host.project.coco,
            image_name,
            pending_review,
        )
    # CMP: TODO - This should probably be logged, no? With some
    # useful diagnostics perhaps...
    except sqlite3.Error as exc:
        messagebox.showerror("Could not update review flag", str(exc))
        return
    if pending_review:
        host.project.review_flags.add(image_name)
    else:
        host.project.review_flags.discard(image_name)
    host.log(
        f"{'Flagged for' if pending_review else 'Removed from'} review: "
        f"{image_name}"
    )
    if host.project.review_only:
        apply_image_filter(
            host,
            host.project.active_filter,
            preferred_image_name=image_name,
        )
    else:
        update_image_status(host)
        update_buttons(host)


def toggle_flagged_view(host: ReviewHost) -> None:
    """Toggle whether navigation is restricted to pending-review images."""

    current_name = current_image_name(host) if host.project.image_paths else None
    host.project.review_only = not host.project.review_only
    apply_image_filter(
        host,
        host.project.active_filter,
        preferred_image_name=current_name,
    )
