"""CODEX: Build isolated projects from source fixtures for e2e replay tests."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from annotator.project.discovery import discover_project
from annotator.project.loading import LoadedProject
from annotator.project.loading import load_project
from annotator.project.loading import prepare_project_load


E2E_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
E2E_SOURCE_PROJECT = E2E_FIXTURE_ROOT / "tiny_source_project"
E2E_IMAGE_NAMES = (
    "a3_01_page_076.jpg",
    "a4_01_page_147.jpg",
)
E2E_CATEGORY_NAMES = frozenset({"figure_other", "figure_lithics"})


def validate_e2e_loaded_project(loaded: LoadedProject) -> None:
    """CODEX: Fail loudly when a source fixture did not migrate as intended."""

    loaded_image_names = tuple(path.name for path in loaded.plan.discovery.image_paths)
    annotation_count = sum(
        len(loaded.document.annotations_for(image_name))
        for image_name in E2E_IMAGE_NAMES
    )
    category_names = {
        category.get("name") for category in loaded.document.categories
    }

    assert loaded.plan.migration_required, (
        "E2E source fixture did not trigger JSON migration. Check that the "
        "seed file is named annotations.json and is visible to the loader."
    )
    assert loaded_image_names == E2E_IMAGE_NAMES
    assert annotation_count > 0, "E2E source fixture migrated without annotations."
    assert category_names == E2E_CATEGORY_NAMES


def build_e2e_project_baseline(
    source_project: Path,
    destination_parent: Path,
) -> Path:
    """CODEX: Copy a source fixture, run the real loader, and return the result."""

    destination_parent.mkdir(parents=True, exist_ok=True)
    project_folder = destination_parent / source_project.name
    shutil.copytree(source_project, project_folder)

    discovery = discover_project(project_folder)
    plan = prepare_project_load(discovery, {})
    loaded = load_project(plan, class_colours=())
    try:
        validate_e2e_loaded_project(loaded)
    finally:
        loaded.connection.close()
    return project_folder


@pytest.fixture(scope="session")
def e2e_source_project() -> Path:
    """CODEX: Return the committed source fixture directory."""

    return E2E_SOURCE_PROJECT


@pytest.fixture
def e2e_build_baseline() -> Callable[[Path, Path], Path]:
    """CODEX: Expose the baseline builder to focused fixture tests."""

    return build_e2e_project_baseline


@pytest.fixture(scope="session")
def e2e_built_project_baseline(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """CODEX: Build the source fixture once through the real load path."""

    baseline_parent = tmp_path_factory.mktemp("e2e-built-baseline")
    return build_e2e_project_baseline(E2E_SOURCE_PROJECT, baseline_parent)


@pytest.fixture
def e2e_project_folder(
    tmp_path: Path,
    e2e_built_project_baseline: Path,
) -> Path:
    """CODEX: Return a fresh writable copy of the built e2e project."""

    project_folder = tmp_path / "project"
    shutil.copytree(e2e_built_project_baseline, project_folder)
    return project_folder


@pytest.fixture
def e2e_require_tk() -> None:
    """CODEX: Require Tk for GUI replay tests, skipping only outside CI."""

    try:
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import tkinter as tk; root = tk.Tk(); root.destroy()",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        if os.environ.get("CI"):
            pytest.fail("Tk root creation timed out in CI")
        pytest.skip("Tk root creation timed out")
    if probe.returncode != 0:
        stderr = probe.stderr.strip() or f"exit code {probe.returncode}"
        if os.environ.get("CI"):
            pytest.fail(f"Tk is not available in CI: {stderr}")
        pytest.skip(f"Tk is not available: {stderr}")
