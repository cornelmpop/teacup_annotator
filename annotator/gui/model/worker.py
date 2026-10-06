"""CODEX: Own background model execution and Tk-thread queue delivery."""

from __future__ import annotations

import queue
import tkinter as tk
import traceback
from typing import Any
from typing import Callable
from typing import cast
from typing import Protocol
from typing import TYPE_CHECKING

from annotator.dialogs import ErrorDetailsDialog
from annotator.dialogs import ProgressDialog
from annotator.gui.project.status import StatusHost
from annotator.gui.project.status import update_buttons
from annotator.gui.state import InteractionState
from annotator.gui.state import ProjectState
from annotator.model.workflow import execute_model_run
from annotator.model.workflow import ModelRunConfiguration
from annotator.model.workflow import ModelRunResult

if TYPE_CHECKING:
    from annotator.gui.model.results import ModelResultHost


class ModelWorkerHost(Protocol):
    """CODEX: Queue, dialog, and GUI effects required by worker delivery."""

    root: tk.Tk
    project: ProjectState
    interaction: InteractionState
    worker_queue: queue.Queue[tuple[str, Any]]
    model_progress_dialog: ProgressDialog | None

    def log(self, message: str) -> None:
        """CODEX: Record one worker message."""

        ...


ModelResultHandler = Callable[["ModelResultHost", ModelRunResult], None]


def set_model_progress(
    host: ModelWorkerHost,
    value: float,
    message: str | None = None,
) -> None:
    """CODEX: Update or close the RF-DETR model progress window."""

    if host.model_progress_dialog is None:
        return
    if message is None:
        host.model_progress_dialog.close()
        host.model_progress_dialog = None
        return
    host.model_progress_dialog.update_progress(value, message)


def run_model_worker(
    host: ModelWorkerHost,
    configuration: ModelRunConfiguration,
) -> None:
    """CODEX: Run inference in a background thread and enqueue its outcome."""

    try:
        result = execute_model_run(
            host.project.all_image_paths,
            configuration,
            progress=lambda value, message: host.worker_queue.put(
                ("progress", (value, message))
            ),
        )
    except Exception:
        details = traceback.format_exc()
        traceback.print_exc()
        host.worker_queue.put(("error", details))
        return
    host.worker_queue.put(("done", result))


def poll_worker_queue(
    host: ModelWorkerHost,
    finish_result: ModelResultHandler,
) -> None:
    """CODEX: Apply queued worker events on the Tk thread and schedule the next poll."""

    while True:
        try:
            event_type, payload = host.worker_queue.get_nowait()
        except queue.Empty:
            break
        if event_type == "progress":
            value, message = payload
            set_model_progress(host, value, message)
            host.log(message)
        elif event_type == "error":
            host.interaction.worker_running = False
            set_model_progress(host, 0)
            update_buttons(cast(StatusHost, host))
            ErrorDetailsDialog(host.root, "Model failed", str(payload))
            host.log(f"Model failed: {payload}")
        elif event_type == "done":
            finish_result(cast("ModelResultHost", host), payload)
    host.root.after(100, poll_worker_queue, host, finish_result)
