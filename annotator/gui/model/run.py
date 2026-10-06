"""CODEX: Own model-run prompts, preflight, worker locking, and thread launch."""

from __future__ import annotations

from pathlib import Path
import threading
from tkinter import filedialog
from tkinter import messagebox
import traceback
from typing import Protocol
from typing import cast

from annotator.class_names import class_name_key
from annotator.coco.category_helpers import is_unused_default_category
from annotator.dialogs import ErrorDetailsDialog
from annotator.dialogs import ProgressDialog
from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import redraw_canvas
from annotator.gui.local_class_persistence import LocalClassPersistenceHost
from annotator.gui.local_class_persistence import refresh_after_local_class_change
from annotator.gui.local_class_persistence import save_local_class_values
from annotator.gui.model.settings import ModelSettingsHost
from annotator.gui.model.settings import active_class_colours
from annotator.gui.model.settings import active_default_class
from annotator.gui.model.settings import active_model_weights_path
from annotator.gui.model.worker import ModelWorkerHost
from annotator.gui.model.worker import run_model_worker
from annotator.gui.project.image_loading import clear_view_interaction_state
from annotator.gui.project.image_loading import ImageLoadingHost
from annotator.gui.project.status import update_buttons
from annotator.model.configuration import MODEL_CONF_FILENAME
from annotator.model.workflow import configure_model_run
from annotator.project.paths import project_file_path


class ModelRunHost(ImageLoadingHost, ModelSettingsHost, Protocol):
    """CODEX: State and GUI effects required to start one model worker."""

    model_progress_dialog: ProgressDialog | None

    def log(self, message: str) -> None:
        """CODEX: Record one model-run message."""

        ...


MODEL_REPLACEMENT_WARNING = (
    "Running the model will replace existing model-generated annotations on "
    "the loaded images. Manual, imported, and human-corrected annotations will "
    "be preserved. The completed run can be reversed with Undo. Continue?"
)


def prompt_for_weights(host: ModelRunHost) -> Path | None:
    """CODEX: Ask for a weights file, seeding the picker from active settings."""

    session_weights = active_model_weights_path(host)
    if session_weights is not None and not session_weights.is_file():
        host.log(f"Configured model weights not found: {session_weights}")
    saved = host.prefs.get_path("model_weights")
    default = session_weights or saved
    initial_dir = default.parent if default and default.parent.is_dir() else Path.home()
    initial_file = default.name if default and default.is_file() else ""
    file_name = filedialog.askopenfilename(
        title="Select RF-DETR weights",
        initialdir=str(initial_dir),
        initialfile=initial_file,
        filetypes=(("PyTorch weights", "*.pt *.pth"), ("All files", "*")),
    )
    return Path(file_name) if file_name else None

# CMP: TODO - Consider removing the long text messages, and placing them instead
#      in a file that is meant just for storing them. Here they interfere with the
#      logic. It IS nice to have the message, as it provides context for the logic,
#      but in this case the text component of this function is just too long.
#      Also, as noted elsewhere for other functions, this one is too long, and requires
#      docstrings that clearly lay out steps and logic, so design and implementation
#      can be evaluated with reasonable ease.
def run_model(host: ModelRunHost) -> None:
    """CODEX: Resolve weights, adopt profile classes, and launch a worker."""

    if (
        host.project.folder is None
        or host.project.coco is None
        or not host.project.all_image_paths
    ):
        messagebox.showinfo(
            "Load images first", "Load a folder before running the model."
        )
        return
    if any(
        host.project.coco.annotations_for(image_path.name)
        for image_path in host.project.all_image_paths
    ) and not messagebox.askyesno(
        "Replace model annotations?",
        MODEL_REPLACEMENT_WARNING,
    ):
        return
    weights_path = active_model_weights_path(host)
    if weights_path is None:
        weights_path = prompt_for_weights(host)
    if weights_path is None:
        return
    try:
        folder_threshold = host.project.session_model_values.get(
            "default_threshold",
            "",
        ).strip()
        configuration = configure_model_run(
            weights_path,
            folder_threshold,
            project_file_path(host.project.folder, MODEL_CONF_FILENAME),
        )
    except Exception:
        details = traceback.format_exc()
        traceback.print_exc()
        ErrorDetailsDialog(host.root, "Could not configure model", details)
        return
    # CODEX: Freeze the parsed profile order for class persistence and GUI use.
    model_class_names = tuple(configuration.class_names.values())
    document = host.project.coco
    unused_placeholder = bool(model_class_names) and is_unused_default_category(
        document.category_names(),
        any(document.annotations_by_image.values()),
    )
    if unused_placeholder:
        # CODEX: An unused default vocabulary has no user-owned class contract, so
        # CODEX: the selected model profile becomes that contract in file order.
        document.categories = []
        for class_name in model_class_names:
            document.category_id_for_name(class_name)
        class_colours = active_class_colours(host)
        persistence_host = cast(LocalClassPersistenceHost, host)
        if not save_local_class_values(
            persistence_host,
            model_class_names,
            class_colours,
        ):
            return
        host.session_default_class_var.set(model_class_names[0])
        refresh_after_local_class_change(persistence_host)
    default_class = active_default_class(host)
    default_identity = class_name_key(default_class)
    model_class_identities = {
        class_name_key(class_name) for class_name in configuration.class_names.values()
    }
    if default_identity not in model_class_identities:
        messagebox.showerror(
            "Default class not supported",
            (
                f"The configured default class '{default_class}' is not "
                "defined by this model's configuration.\n\n"
                "Valid model classes:\n"
                f"{', '.join(configuration.class_names.values())}\n\n"
                "Open Configuration > Model, load this model's .conf "
                "profile, choose a valid Default class, and save the "
                "folder configuration. Model weights are not required for "
                "profile configuration. You may instead select a "
                "different model."
            ),
        )
        return
    model_label = (
        "object-detection"
        if configuration.model_type == "detection"
        else configuration.model_type
    )
    if not messagebox.askokcancel(
        "Confirm RF-DETR model",
        (
            "The selected checkpoint is an RF-DETR "
            f"{model_label} model with an input resolution "
            f"of {configuration.input_resolution} x "
            f"{configuration.input_resolution} pixels and "
            f"{configuration.num_classes} classes.\n\n"
            "Teacup Annotator will preserve each image's aspect ratio and add "
            "white margins to make a square input. This preprocessing may "
            "not match what the model expects, but it is the only mode "
            "currently supported.\n\n"
            "The model will run with a confidence threshold of "
            f"{configuration.threshold}, read from:\n"
            f"{configuration.threshold_source}\n"
            "Edit that file to change the threshold.\n\n"
            f"New manual annotations default to '{default_class}'.\n\n"
            "Run this model?"
        ),
    ):
        return
    clear_view_interaction_state(host)
    redraw_canvas(cast(CanvasRenderHost, host))
    if host.project.using_folder_model_conf:
        host.project.session_model_values["model_weights"] = str(weights_path)
    else:
        host.prefs.set_path("model_weights", weights_path)
    host.interaction.worker_running = True
    host.model_progress_dialog = ProgressDialog(
        host.root,
        f"RF-DETR {model_label}",
        f"Running {model_label} model — editing disabled",
        f"Starting {model_label} model",
    )
    host.log(
        f"Running RF-DETR {model_label} model: {weights_path} "
        f"(input {configuration.input_resolution}px, "
        f"threshold {configuration.threshold})"
    )
    update_buttons(host)
    thread = threading.Thread(
        target=run_model_worker,
        args=(host, configuration),
        daemon=True,
    )
    thread.start()
