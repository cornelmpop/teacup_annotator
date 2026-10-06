"""CODEX: Replay parsed GUI sessions against a live Teacup Tk application."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from typing import Any

from tools.e2e_session.canonical_outputs import CanonicalBaseline
from tools.e2e_session.canonical_outputs import canonical_output_files
from tools.e2e_session.canonical_outputs import capture_canonical_baseline
from tools.e2e_session.golden_compare import compare_golden_outputs
from tools.e2e_session.model_assets import MODEL_ASSET_REGISTRY_PATH
from tools.e2e_session.model_assets import resolve_required_model_assets
from tools.e2e_session.replay_actions import ReplayActionDispatcher
from tools.e2e_session.replay_runtime import ReplayRuntime
from tools.e2e_session.replay_setup import prepare_replay_setup
from tools.e2e_session.replay_setup import ReplaySetup
from tools.e2e_session.session_format import SessionDocument
from tools.e2e_session.session_format import parse_session_file


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """CODEX: Summarize a completed replay run."""

    project_folder: Path
    actions_run: int
    output_files: dict[str, str]


def replay_session_file(
    path: Path,
    *,
    project_folder: Path,
    model_asset_registry_path: Path = MODEL_ASSET_REGISTRY_PATH,
    pump_statistics_callbacks: bool = True,
) -> ReplayResult:
    """CODEX: Preflight and replay a session into an exact project folder.

    The optional registry path redirects only machine-local model lookup,
    primarily for focused tests; session and fixture path semantics are fixed.
    """

    session_path = path.expanduser().resolve()
    return replay_session(
        parse_session_file(session_path),
        fixture_base=session_path.parent,
        project_folder=project_folder,
        model_asset_registry_path=model_asset_registry_path,
        pump_statistics_callbacks=pump_statistics_callbacks,
    )


def replay_session(
    document: SessionDocument,
    *,
    fixture_base: Path,
    project_folder: Path,
    model_asset_registry_path: Path = MODEL_ASSET_REGISTRY_PATH,
    pump_statistics_callbacks: bool = True,
) -> ReplayResult:
    """CODEX: Replay against a copy with an explicit statistics-pump policy.

    Correctness callers retain the default and service the recurring statistics
    callback during ordinary pumps. Duration benchmarks disable that callback
    while continuing to pump model-worker polling and all normal Tk work.
    """

    model_assets = resolve_required_model_assets(
        document,
        model_asset_registry_path,
    )
    setup = prepare_replay_setup(
        document,
        fixture_base=fixture_base,
        project_folder=project_folder,
        model_assets=model_assets,
    )
    root = tk.Tk()
    app: Any | None = None
    actions_run = 0
    baseline: CanonicalBaseline | None = None

    def capture_reconciled_save_baseline(_host: Any) -> None:
        """CODEX: Capture output baseline before load-time reconciliation save."""

        nonlocal baseline

        if app is None:
            raise AssertionError("cannot capture replay baseline before app exists")
        if baseline is None:
            baseline = capture_canonical_baseline(app)

    try:
        with ReplayRuntime(
            root,
            project_folder=setup.project_folder,
            model_assets=model_assets,
            pump_statistics_callbacks=pump_statistics_callbacks,
        ) as runtime:
            from annotator.gui.app import AnnotatorApp

            app = AnnotatorApp(root)
            runtime.before_reconciled_save = capture_reconciled_save_baseline
            runtime.pump()
            _apply_initial_geometry(runtime, app, setup, document)
            dispatcher = ReplayActionDispatcher(
                app,
                runtime,
                setup,
                document.actions,
            )
            # CODEX: Startup dialogs may run only after their recorded expectations
            # CODEX: exist.
            runtime.release_startup()
            for entry in document.actions:
                dispatcher.dispatch(entry)
                actions_run += 1
                if entry.verb == "loaded" and baseline is None:
                    baseline = capture_canonical_baseline(app)
            output_files = _check_expectations(document, setup, runtime, baseline)
            return ReplayResult(
                project_folder=setup.project_folder,
                actions_run=actions_run,
                output_files=output_files,
            )
    finally:
        _cleanup_app(root, app)


def _apply_initial_geometry(
    runtime: ReplayRuntime,
    app: Any,
    setup: ReplaySetup,
    document: SessionDocument,
) -> None:
    """CODEX: Apply setup geometry before startup one-shots are pumped."""

    if setup.window_size is None:
        return
    from tools.e2e_session.session_format import SourceLocation

    location = SourceLocation(document.source_name, 1)
    app.root.geometry(f"{setup.window_size[0]}x{setup.window_size[1]}")
    runtime.wait_until(
        lambda: runtime.root_size() == setup.window_size,
        location,
        f"expected initial window size {setup.window_size}",
        timeout_details=lambda: f"achieved {runtime.root_size()}",
    )
    if setup.canvas_size is not None:
        canvas = app.widgets.viewer.canvas
        runtime.wait_until(
            lambda: runtime.canvas_size(canvas) == setup.canvas_size,
            location,
            f"expected initial canvas size {setup.canvas_size}",
            timeout_details=lambda: f"achieved {runtime.canvas_size(canvas)}",
        )


def _check_expectations(
    document: SessionDocument,
    setup: ReplaySetup,
    runtime: ReplayRuntime,
    baseline: CanonicalBaseline | None,
) -> dict[str, str]:
    """CODEX: Compare canonical replay outputs against declared goldens."""

    if not document.expectations:
        return {}
    if baseline is None:
        raise AssertionError(
            f"{document.source_name}:1: expect outputs requires a loaded baseline"
        )
    output_files = canonical_output_files(
        setup.project_folder,
        baseline,
        runtime.menu_snapshots,
        setup.model_assets,
    )
    compare_golden_outputs(document, output_files)
    return output_files


def _cleanup_app(root: tk.Tk, app: Any | None) -> None:
    """CODEX: Close SQL and destroy the root after replay finishes."""

    if app is not None and app.project.sql_connection is not None:
        app.close_sql_connection()
    try:
        if root.winfo_exists():
            root.destroy()
    except tk.TclError:
        return
