"""CODEX: Isolate global Teacup preferences before tests import Annotator."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile

import pytest

TEST_PREFERENCE_ROOT = Path(tempfile.mkdtemp(prefix="teacup-test-prefs-")).resolve()

if sys.platform == "darwin":
    os.environ["HOME"] = str(TEST_PREFERENCE_ROOT)
elif sys.platform == "win32":
    os.environ["APPDATA"] = str(TEST_PREFERENCE_ROOT)
else:
    os.environ["XDG_CONFIG_HOME"] = str(TEST_PREFERENCE_ROOT)

from annotator.preferences import DEFAULT_PREFERENCE_VALUES
from annotator.preferences.files import read_loose_key_value_text
from annotator.resources import read_preference_defaults_text

PACKAGED_PREFERENCE_VALUES = read_loose_key_value_text(
    read_preference_defaults_text()
)

assert DEFAULT_PREFERENCE_VALUES == PACKAGED_PREFERENCE_VALUES


@pytest.fixture
def test_preference_root() -> Path:
    """CODEX: Return the isolated preference root for tests that assert it."""

    return TEST_PREFERENCE_ROOT


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    """CODEX: Remove the temporary preference root after pytest finishes."""

    shutil.rmtree(TEST_PREFERENCE_ROOT, ignore_errors=True)
